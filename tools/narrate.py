"""OUTIL DE DÉVELOPPEMENT (1.2.2, C17) : voix off et sous-titres d'une vidéo du studio.

    python tools/tour_video.py tour.mp4 --lang fr          # écrit aussi tour.mp4.voice.json
    python tools/narrate.py tour.mp4 --script              # script horodaté à relire (tour.mp4.script.md)
    python tools/narrate.py tour.mp4 --voice test          # essai sans synthèse : bips + silences calés
    python tools/narrate.py tour.mp4 --voice edge          # voix Microsoft Edge (pip install edge-tts, internet)
    python tools/narrate.py tour.mp4 --voice piper --piper-model fr_FR-siwis-medium.onnx   # hors ligne

Calage exact : répétition, mesure des répliques, tournage avec les plans allongés, puis voix :
    python tools/tour_video.py tour.mp4 --lang fr --dry
    python tools/narrate.py tour.mp4 --voice edge --measure          # -> tour.durations.json
    python tools/tour_video.py tour.mp4 --lang fr --voice tour.durations.json
    python tools/narrate.py tour.mp4 --voice edge

Sortie : tour.voice.mp4 (vidéo copiée telle quelle + piste voix), tour.srt (sous-titres YouTube).
Chaque réplique part à l'instant où son texte apparaît. Si elle déborde sur la suivante, elle est
accélérée (jusqu'à x1,25), sinon la suivante est décalée et un avertissement indique où allonger le
plan dans le scénario. La vidéo n'est jamais réencodée. Le teaser reste sans voix.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tour_texts import SAY_FIX, SPOKEN_EN, SPOKEN_FR  # noqa: E402

EDGE_VOICES = {"en": "en-US-AndrewNeural", "fr": "fr-FR-HenriNeural"}
MAX_TEMPO = 1.25
LEAD = 0.15                     # la voix part un peu après le texte
GAP = 0.12                      # silence minimal entre deux répliques


def spoken(event: Dict[str, Any], lang: str) -> str:
    table = SPOKEN_FR if lang == "fr" else SPOKEN_EN
    text = table.get(event.get("key", ""), event["text"])
    for a, b in SAY_FIX.get(lang, {}).items():
        text = re.sub(rf"(?<!\w){re.escape(a)}(?!\w)" if a[0].isalnum() else re.escape(a), b, text)
    text = re.sub(r"\(([^)]*\.(?:db|pdb))\)", "", text)          # noms de fichiers entre parenthèses : pas à l'oral
    return re.sub(r"\s+", " ", text).strip()


WORDS_PER_SECOND = {"en": 2.8, "fr": 2.6}


def voice_length(lang: str, durations: Any = None) -> Any:
    """Pour tools/tour_video.py --voice : durée parlée d'une réplique (mesurée par --measure, sinon
    estimée d'après le nombre de mots)."""
    measured: Dict[str, float] = {}
    if durations is not None:
        measured = json.loads(Path(durations).read_text(encoding="utf-8"))

    def length(key: str, shown: str) -> float:
        text = spoken({"key": key, "text": shown}, lang)
        if text in measured:
            return measured[text] / 1.1                       # un peu d'accélération reste permise
        return max(0.8, len(text.split()) / WORDS_PER_SECOND.get(lang, 2.7))

    return length


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out or 0)


# ------------------------------------------------------------------ synthèse
def synth_test(text: str, out: Path) -> None:
    """Pas de voix : un bip court puis un silence de la durée estimée de la phrase (≈ 2,6 mots / s)."""
    secs = max(0.8, len(text.split()) / 2.6)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.08",
                    "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-filter_complex",
                    f"[0]volume=0.3,aresample=24000[b];[1]atrim=0:{secs - 0.08:.3f}[s];[b][s]concat=n=2:v=0:a=1",
                    "-ac", "1", "-ar", "24000", str(out)], check=True)


def synth_edge(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts  # pip install edge-tts

    mp3 = out.with_suffix(".mp3")
    asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(mp3)))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(out)], check=True)
    mp3.unlink(missing_ok=True)


def synth_piper(text: str, out: Path, model: str) -> None:
    exe = shutil.which("piper")
    if exe is None:
        raise SystemExit("piper not found: pip install piper-tts (and download a voice .onnx + .onnx.json)")
    subprocess.run([exe, "--model", model, "--output_file", str(out)], input=text.encode("utf-8"), check=True)


# ------------------------------------------------------------------ calage
def schedule(lines: List[Tuple[float, str, float]], end: float) -> List[Dict[str, Any]]:
    """lines : (instant du texte, phrase, durée de la phrase) -> départ, accélération, retard."""
    plan: List[Dict[str, Any]] = []
    free = 0.0
    for i, (t, text, dur) in enumerate(lines):
        start = max(t + LEAD, free + GAP)
        nxt = lines[i + 1][0] + LEAD if i + 1 < len(lines) else end
        room = max(0.1, nxt - start - GAP)
        tempo = 1.0
        if dur > room:
            tempo = min(MAX_TEMPO, dur / room)
        length = dur / tempo
        plan.append({"t": t, "start": round(start, 3), "tempo": round(tempo, 3), "length": round(length, 3),
                     "late": round(max(0.0, start + length - nxt), 2), "text": text})
        free = start + length
    return plan


def srt_time(x: float) -> str:
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(plan: List[Dict[str, Any]], path: Path) -> None:
    rows = []
    for i, p in enumerate(plan, 1):
        rows.append(f"{i}\n{srt_time(p['start'])} --> {srt_time(p['start'] + max(p['length'], 1.2))}\n{p['text']}\n")
    path.write_text("\n".join(rows), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--voice", choices=("edge", "piper", "test"), default="test")
    ap.add_argument("--edge-voice", default="", help="e.g. fr-FR-DeniseNeural, en-GB-RyanNeural")
    ap.add_argument("--rate", default="+0%", help="edge-tts speaking rate, e.g. +8%%")
    ap.add_argument("--piper-model", default="")
    ap.add_argument("--script", action="store_true", help="only write the timed script to review")
    ap.add_argument("--measure", action="store_true",
                    help="synthesise every line and write <video>.durations.json, for tour_video.py --voice")
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    meta = json.loads(Path(str(args.video) + ".voice.json").read_text(encoding="utf-8"))
    lang = meta.get("lang", "en")
    events = [e for e in meta["events"] if e.get("text")]
    texts = [(float(e["t"]), spoken(e, lang)) for e in events]
    stem = args.video.with_suffix("")

    if args.script:
        md = [f"# Voice-over script ({lang}) — {args.video.name}", "",
              "| Time | On screen | Spoken |", "|---|---|---|"]
        for e, (t, text) in zip(events, texts):
            md.append(f"| {int(t // 60)}:{t % 60:04.1f} | {e['text']} | {text} |")
        out = Path(str(stem) + ".script.md")
        out.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"script: {out}")
        return 0

    if not shutil.which("ffmpeg"):
        print("FFmpeg is required.")
        return 1
    cache = Path(str(stem) + ".voice")
    cache.mkdir(exist_ok=True)
    voice = args.edge_voice or EDGE_VOICES.get(lang, EDGE_VOICES["en"])
    lines: List[Tuple[float, str, float]] = []
    clips: List[Path] = []
    for t, text in texts:
        h = hashlib.sha1(f"{args.voice}|{voice}|{args.rate}|{args.piper_model}|{text}".encode()).hexdigest()[:12]
        clip = cache / f"{h}.wav"
        if not clip.exists():
            if args.voice == "edge":
                synth_edge(text, clip, voice, args.rate)
            elif args.voice == "piper":
                synth_piper(text, clip, args.piper_model)
            else:
                synth_test(text, clip)
        lines.append((t, text, duration(clip)))
        clips.append(clip)

    if args.measure:
        out = Path(str(stem) + ".durations.json")
        out.write_text(json.dumps({text: round(d, 3) for _t, text, d in lines}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"durations: {out}  ->  python tools/tour_video.py {args.video.name} --lang {lang} --voice {out.name}")
        return 0
    end = float(meta.get("duration") or duration(args.video))
    plan = schedule(lines, end)
    for p in plan:
        if p["late"] > 0.3:
            print(f"  ! {int(p['t'] // 60)}:{p['t'] % 60:04.1f} runs {p['late']:.1f} s over: "
                  f"hold this shot longer in the scenario — {p['text'][:60]}")

    inputs: List[str] = ["-i", str(args.video)]
    parts: List[str] = []
    for i, (clip, p) in enumerate(zip(clips, plan), 1):
        inputs += ["-i", str(clip)]
        tempo = f",atempo={p['tempo']}" if p["tempo"] > 1.0 else ""
        parts.append(f"[{i}:a]aresample=48000{tempo},adelay={int(p['start'] * 1000)}:all=1[v{i}]")
    mix = "".join(f"[v{i}]" for i in range(1, len(clips) + 1))
    graph = ";".join(parts) + f";{mix}amix=inputs={len(clips)}:normalize=0,apad,atrim=0:{end:.3f}," \
                              f"loudnorm=I=-16:TP=-1.5:LRA=11[voice]"
    out = args.out or Path(str(stem) + ".voice.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "0:v", "-map",
                    "[voice]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)], check=True)
    write_srt(plan, Path(str(stem) + ".srt"))
    late = sum(1 for p in plan if p["late"] > 0.3)
    print(f"video with voice: {out}  ({len(plan)} lines, {late} over their shot)")
    print(f"subtitles: {stem}.srt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
