"""Estimated-quality test bench (A05, 1.4.1). Development tool: not shipped, never run by the app.

    python tools/quality_bench.py "D:\\CD rips" --out bench_out

Takes a folder of TRUE lossless references (CD rips: .wav / .flac / .aiff, sub-folders included), makes
degraded copies of each with FFmpeg (MP3 128/192/256/320 and VBR, AAC, Opus, fake lossless WAV, the
"YouTube -> MP3 320 -> WAV" chain...), then measures every copy:

* what DJSync says today (`djsync.analysis.spectrum`: cutoff and equivalent bitrate);
* raw spectral features on three 20 s slices (25 %, 50 %, 75 % of the track), kept for calibration.

Outputs, in --out (nothing else is written; the references are only read):

* `features.jsonl`: one line per measured copy. NO title, NO path, NO audio: tracks and albums are
  identified by a hash only.
* `summary.txt`: confusion matrix "what the copy really is" x "what DJSync says today".

The run can be stopped and restarted: tracks already measured are skipped. Temporary copies go to a
temporary folder and are deleted after each track.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from djsync.analysis import spectrum  # noqa: E402

REF_EXT = {".wav", ".flac", ".aif", ".aiff"}
SLICE = 20.0
N_FFT = 2048
POSITIONS = (0.25, 0.50, 0.75)
BAND_LO, BAND_HI, BAND_STEP = 10000, 24000, 250           # mean spectrum, dB relative to the 1-8 kHz level
QBAND_LO, QBAND_HI = 12000, 22000                         # 1 kHz bands: quantiles of the cells (dBFS)

# name -> (FFmpeg encoder, extension, encoding options, nominal kbps, true class)
CODECS: Dict[str, Tuple[str, str, List[str], int, str]] = {
    "mp3_128": ("libmp3lame", "mp3", ["-b:a", "128k"], 128, "128"),
    "mp3_192": ("libmp3lame", "mp3", ["-b:a", "192k"], 192, "192"),
    "mp3_256": ("libmp3lame", "mp3", ["-b:a", "256k"], 256, "256"),
    "mp3_320": ("libmp3lame", "mp3", ["-b:a", "320k"], 320, "320"),
    "mp3_v2": ("libmp3lame", "mp3", ["-q:a", "2"], 190, "192"),
    "mp3_v0": ("libmp3lame", "mp3", ["-q:a", "0"], 245, "256"),
    "aac_128": ("aac", "m4a", ["-b:a", "128k"], 128, "128"),
    "aac_256": ("aac", "m4a", ["-b:a", "256k"], 256, "256"),
    "opus_128": ("libopus", "opus", ["-b:a", "128k"], 128, "128"),
    "opus_160": ("libopus", "opus", ["-b:a", "160k"], 160, "192"),
}
# Chains: (name, steps, true class = weakest link). A step is a CODECS name, or "wav44" / "wav48" / "flac"
# (16-bit lossless container: the "fake lossless" case).
CHAINS: List[Tuple[str, List[str], str]] = [
    ("ref_wav48", ["wav48"], "lossless"),
    ("youtube_mp3_320_wav", ["opus_160", "mp3_320", "wav44"], "192"),          # QUA-8 (1.4.0-rc.6)
    ("aac_128_mp3_320", ["aac_128", "mp3_320"], "128"),
    ("mp3_128_flac", ["mp3_128", "flac"], "128"),
]
CLASS_ORDER = ["lossless", "320", "256", "192", "128"]
_print_lock = threading.Lock()


def say(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _run(cmd: Sequence[str], timeout: int = 900) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                          timeout=timeout, creationflags=flags, check=False)


def encoders(ffmpeg: str) -> set:
    out = _run([ffmpeg, "-hide_banner", "-encoders"], 60).stdout.decode("utf-8", "replace")
    return {line.split()[1] for line in out.splitlines() if len(line.split()) > 1}


def probe(ffmpeg: str, path: Path) -> Tuple[float, int]:
    """(duration in seconds, sample rate) read from FFmpeg's own header dump."""
    err = _run([ffmpeg, "-hide_banner", "-i", str(path)], 60).stderr.decode("utf-8", "replace")
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Audio:.*?(\d+) Hz", err)
    return dur, int(m.group(1)) if m else 44100


def convert(ffmpeg: str, src: Path, dst: Path, step: str) -> bool:
    if step in ("wav44", "wav48"):
        opts = ["-c:a", "pcm_s16le", "-ar", "44100" if step == "wav44" else "48000"]
    elif step == "flac":
        opts = ["-c:a", "flac", "-sample_fmt", "s16"]
    else:
        enc, _ext, extra, _k, _c = CODECS[step]
        opts = ["-c:a", enc, *extra]
        if enc == "libmp3lame":
            opts += ["-ar", "44100"]                       # MP3 has no 48 kHz "YouTube" quirk to keep here
    r = _run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-map", "0:a:0", "-vn", *opts, str(dst)])
    return r.returncode == 0 and dst.is_file() and dst.stat().st_size > 1000


def ext_of(step: str) -> str:
    return {"wav44": "wav", "wav48": "wav", "flac": "flac"}.get(step) or CODECS[step][1]


def decode_slice(ffmpeg: str, path: Path, sr: int, start: float) -> np.ndarray:
    r = _run([ffmpeg, "-nostdin", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{SLICE:.0f}", "-i", str(path),
              "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], 120)
    return np.frombuffer(r.stdout, dtype=np.float32)


def slice_features(x: np.ndarray, sr: int) -> Optional[dict]:
    """Raw material for the calibration: mean spectrum above 10 kHz (relative to the 1-8 kHz level), and for
    each 1 kHz band from 12 to 22 kHz the 10th / 50th / 90th percentile of the time-frequency cells (dBFS) in
    the loud half of the frames. A codec leaves "holes" (very low 10th percentile) that a true lossless file
    does not have."""
    if x.size < N_FFT * 8:
        return None
    hop = N_FFT // 2
    n = 1 + (x.size - N_FFT) // hop
    idx = np.arange(N_FFT)[None, :] + hop * np.arange(n)[:, None]
    win = np.hanning(N_FFT).astype(np.float32)
    power = np.abs(np.fft.rfft(x[idx] * win[None, :], axis=1)) ** 2
    power /= float((win ** 2).sum()) ** 2 / 4.0             # roughly dBFS per bin for a full-scale sine
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    mid = (freqs >= 1000) & (freqs <= 8000)
    frame_level = 10 * np.log10(power[:, mid].mean(axis=1) + 1e-30)
    level = float(np.median(frame_level))
    if level < -90:
        return None
    loud = frame_level >= level
    mean_db = 10 * np.log10(power.mean(axis=0) + 1e-30)
    ref = float(np.median(mean_db[mid]))
    spec = []
    for lo in range(BAND_LO, BAND_HI, BAND_STEP):
        sel = (freqs >= lo) & (freqs < lo + BAND_STEP)
        spec.append(round(float(mean_db[sel].mean()) - ref, 1) if sel.any() else None)
    cells = 10 * np.log10(power[loud] + 1e-30)
    quant = []
    for lo in range(QBAND_LO, QBAND_HI, 1000):
        sel = (freqs >= lo) & (freqs < lo + 1000)
        if not sel.any():
            quant.append(None)
            continue
        q = np.percentile(cells[:, sel], (10, 50, 90))
        quant.append([round(float(v), 1) for v in q])
    return {"level": round(level, 1), "ref": round(ref, 1), "cutoff": spectrum.cutoff_of(x, sr),
            "spec": spec, "quant": quant}


def measure(ffmpeg: str, path: Path) -> dict:
    dur, sr = probe(ffmpeg, path)
    sr = min(sr, 96000)
    row: dict = {"sr": sr, "duration": round(dur, 1), "bytes": path.stat().st_size}
    try:
        cut = spectrum.measure(path, str(Path(ffmpeg).parent), duration=dur, native_sr=sr)
        row["now_cutoff"] = cut
        row["now_estimate"] = spectrum.estimate(cut, sr)
    except Exception as exc:  # noqa: BLE001 - the bench must go on
        row["now_error"] = str(exc)[:200]
    slices = []
    for pos in POSITIONS:
        start = max(0.0, dur * pos - SLICE / 2) if dur > SLICE else 0.0
        try:
            slices.append(slice_features(decode_slice(ffmpeg, path, sr, start), sr))
        except Exception as exc:  # noqa: BLE001
            slices.append({"error": str(exc)[:200]})
    row["slices"] = slices
    return row


def plan(available: set) -> Tuple[List[Tuple[str, List[str], str, int]], List[str]]:
    """Every copy to make: (name, steps, true class, nominal kbps). Skips what this FFmpeg cannot encode."""
    todo: List[Tuple[str, List[str], str, int]] = []
    skipped: List[str] = []

    def ok(steps: List[str]) -> bool:
        return all(s in ("wav44", "wav48", "flac") or CODECS[s][0] in available for s in steps)

    for name, (_enc, _ext, _opts, kbps, cls) in CODECS.items():
        for label, steps in ((name, [name]), (name + "_wav", [name, "wav48" if name.startswith("mp3") or name.startswith("aac") else "wav44"])):
            (todo if ok(steps) else skipped).append((label, steps, cls, kbps) if ok(steps) else label)  # type: ignore[arg-type]
    for name, steps, cls in CHAINS:
        if ok(steps):
            todo.append((name, steps, cls, 0))
        else:
            skipped.append(name)
    return todo, skipped


def process(ffmpeg: str, ref: Path, root: Path, todo, out_file: Path, lock: threading.Lock, work: Optional[str]) -> int:
    rel = ref.relative_to(root).as_posix()
    track = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    album = hashlib.sha1(ref.parent.relative_to(root).as_posix().encode("utf-8")).hexdigest()[:8]
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="djsync_bench_", dir=work))
    try:
        base = {"track": track, "album": album}
        rows.append({**base, "variant": "ref", "truth": "lossless", "kbps": 0, "chain": [], **measure(ffmpeg, ref)})
        made: Dict[Tuple[str, ...], Path] = {}
        for name, steps, cls, kbps in todo:
            src = ref
            good = True
            for i, step in enumerate(steps):
                key = tuple(steps[: i + 1])
                if key not in made:
                    dst = tmp / ("_".join(key) + "." + ext_of(step))
                    if not convert(ffmpeg, src, dst, step):
                        good = False
                        break
                    made[key] = dst
                src = made[key]
            if not good:
                rows.append({**base, "variant": name, "truth": cls, "kbps": kbps, "chain": steps, "error": "encode failed"})
                continue
            rows.append({**base, "variant": name, "truth": cls, "kbps": kbps, "chain": steps, **measure(ffmpeg, src)})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows.append({"track": track, "album": album, "variant": "_done"})
    with lock, out_file.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return len(rows) - 1


def now_class(est: Optional[int]) -> str:
    if not est:
        return "unknown"
    return "lossless" if est >= spectrum.LOSSLESS else str(est)


def summary(out_file: Path) -> str:
    rows = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("variant") != "_done" and "error" not in r]
    cols = CLASS_ORDER + ["unknown"]
    lines = [f"DJSync quality bench - {len({r['track'] for r in rows})} tracks, {len(rows)} measured copies",
             f"spectrum.py classes today: {spectrum._CLASSES}", "",
             "1. True class (rows) x DJSync estimate today (columns)", "",
             "truth      " + "".join(f"{c:>10}" for c in cols) + "     exact"]
    for cls in CLASS_ORDER:
        sub = [r for r in rows if r["truth"] == cls]
        counts = [sum(1 for r in sub if now_class(r.get("now_estimate")) == c) for c in cols]
        exact = 100.0 * counts[cols.index(cls)] / len(sub) if sub else 0.0
        lines.append(f"{cls:<11}" + "".join(f"{c:>10}" for c in counts) + f"   {exact:5.1f} %")
    lines += ["", "2. Per kind of copy: estimate today, and measured cutoff (Hz: min / median / max)", "",
              f"{'copy':<24}{'truth':>9}{'n':>5}  " + "".join(f"{c:>9}" for c in cols) + "   cutoff"]
    for name in sorted({r["variant"] for r in rows}):
        sub = [r for r in rows if r["variant"] == name]
        counts = [sum(1 for r in sub if now_class(r.get("now_estimate")) == c) for c in cols]
        cuts = sorted(r["now_cutoff"] for r in sub if r.get("now_cutoff"))
        cut = f"{cuts[0]} / {cuts[len(cuts) // 2]} / {cuts[-1]}" if cuts else "-"
        lines.append(f"{name:<24}{sub[0]['truth']:>9}{len(sub):>5}  " + "".join(f"{c:>9}" for c in counts) + f"   {cut}")
    fake = [r for r in rows if r["truth"] != "lossless" and r["variant"].endswith(("_wav", "_flac"))]
    if fake:
        seen = sum(1 for r in fake if now_class(r.get("now_estimate")) != "lossless")
        lines += ["", f"3. Fake lossless (lossy copy put back in WAV / FLAC) detected today: {seen} / {len(fake)}"
                      f" ({100.0 * seen / len(fake):.1f} %)"]
    true = [r for r in rows if r["truth"] == "lossless"]
    if true:
        kept = sum(1 for r in true if now_class(r.get("now_estimate")) == "lossless")
        lines.append(f"4. True lossless kept as lossless today: {kept} / {len(true)} ({100.0 * kept / len(true):.1f} %)")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DJSync estimated-quality test bench (development tool, read-only on the references).")
    ap.add_argument("folder", help="folder of true lossless references (CD rips), sub-folders included")
    ap.add_argument("--out", default="bench_out", help="output folder (features.jsonl, summary.txt)")
    ap.add_argument("--ffmpeg", default=None, help="folder containing ffmpeg(.exe); default: the one on the PATH")
    ap.add_argument("--work", default=None, help="folder for the temporary copies (default: the system's)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="tracks processed at once")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tracks (quick trial)")
    args = ap.parse_args(argv)

    from djsync.analysis.decode import find_ffmpeg

    ffmpeg = find_ffmpeg(args.ffmpeg)
    if not ffmpeg:
        print("FFmpeg not found: add it to the PATH or pass --ffmpeg FOLDER.")
        return 2
    root = Path(args.folder)
    refs = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in REF_EXT)
    if not refs:
        print(f"No .wav / .flac / .aiff file under {root}")
        return 2
    if args.limit:
        refs = refs[: args.limit]
    todo, skipped = plan(encoders(ffmpeg))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / "features.jsonl"
    done = set()
    if out_file.exists():
        for line in out_file.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("variant") == "_done":
                done.add(r["track"])
    pending = [p for p in refs if hashlib.sha1(p.relative_to(root).as_posix().encode("utf-8")).hexdigest()[:12] not in done]
    print(f"FFmpeg: {ffmpeg}")
    print(f"{len(refs)} references, {len(done)} already measured, {len(pending)} to do; {len(todo) + 1} copies per track; {args.jobs} at once")
    if skipped:
        print("SKIPPED (this FFmpeg cannot encode them): " + ", ".join(skipped))
        if any("opus" in s or "youtube" in s for s in skipped):
            print("  -> no Opus encoder: the YouTube cases are missing. A full FFmpeg (libopus) on the PATH fixes it.")
    lock = threading.Lock()
    t0 = time.time()
    count = [0]

    def one(ref: Path) -> None:
        try:
            n = process(ffmpeg, ref, root, todo, out_file, lock, args.work)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the night
            say(f"  track skipped ({type(exc).__name__}: {exc})")
            return
        count[0] += 1
        left = (time.time() - t0) / count[0] * (len(pending) - count[0])
        say(f"  {count[0]}/{len(pending)} done ({n} copies), about {left / 60:.0f} min left")

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        list(pool.map(one, pending))
    text = summary(out_file)
    (out / "summary.txt").write_text(text, encoding="utf-8")
    print()
    print(text)
    print(f"Written: {out_file} and {out / 'summary.txt'} (no title, no path, no audio inside)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
