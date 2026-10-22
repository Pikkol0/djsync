"""Vérifier l'analyse sur de vrais morceaux, sans toucher à la clé :

    python -m djsync.analysis "E:\\Contents\\Artiste\\Album\\son.m4a" [autres fichiers…]
    python -m djsync.analysis --compare E:\\     (compare aux BPM/tonalités de Rekordbox sur la clé, lecture seule)
    python -m djsync.analysis --compare E:\\ --csv diag.csv     (+ mesures détaillées pour calibrage)
    python -m djsync.analysis --compare local --under "E:\\Contents"   (V1.1.0 : collection Rekordbox du PC,
        sons importés depuis la clé et analysés par Rekordbox)

--compare lit exportLibrary.db (ou master.db) en LECTURE SEULE, réanalyse les sons analysés par
REKORDBOX (jamais ceux que DJSync a analysés lui-même) et affiche les écarts : c'est le meilleur moyen de juger la précision sur VOTRE musique.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import analyze_file
from ..core.camelot import to_camelot


def _one(path: str, ffmpeg: str | None) -> None:
    r = analyze_file(path, ffmpeg)
    downbeat = next((t for n, t in r.grid.beats if n == 1), None)
    print(f"{Path(path).name}\n  BPM {r.bpm:.2f}   key {r.key.name or '?'} ({r.key.camelot or '?'})   "
          f"first beat {r.grid.first_beat * 1000:.0f} ms   first downbeat "
          f"{f'{downbeat:.3f}' if downbeat is not None else '?'} s\n"
          f"  duration {r.duration:.1f} s, {r.waveforms.detail_count} waveform points, computed in {r.seconds:.1f} s")


def _rekordbox_grid(lib, track):
    """(temps en s, numéros 1-4) de la grille Rekordbox (balise PQTZ de son ANLZ0000.DAT)."""
    import struct

    from .anlz import parse

    if not track.analysis_path:
        return None
    try:
        tags = parse(lib.absolute_path(track.analysis_path).read_bytes())
        body = tags["PQTZ"][0][1]
    except (OSError, ValueError, KeyError):
        return None
    beats = [struct.unpack(">HHI", body[i:i + 8]) for i in range(0, len(body) - 7, 8)]
    return [b[2] / 1000.0 for b in beats], [b[0] for b in beats]


def _open_source(source: str):
    """« local » = collection Rekordbox de cet ordinateur (master.db), sinon une clé (« E: »).
    Toujours en LECTURE SEULE. Renvoie (bibliothèque, ids des sons analysés par REKORDBOX)."""
    if source.lower() in ("local", "pc", "computer"):
        from ..db.local_library import LocalRekordboxLibrary, find_local_rekordbox
        from ..settings import Settings

        s = Settings.load()
        target = find_local_rekordbox(s.local_db_dir, s.local_music_dir)
        if target is None:
            raise SystemExit("Rekordbox (master.db) not found on this computer.")
        lib = LocalRekordboxLibrary(target, read_only=True).__enter__()
        owned = set(lib.owned.all())
        mine = {int(r[0]) for r in lib._read("SELECT ID, UUID FROM djmdContent") if r[1] in owned}
        native = {t.content_id for t in lib.list_tracks()} - mine
        return lib, native
    from ..db import RekordboxUsbLibrary, drive_from_letter

    lib = RekordboxUsbLibrary(drive_from_letter(source), read_only=True).__enter__()
    native = {int(r[0]) for r in lib._read("SELECT content_id FROM content WHERE masterDbId IS NOT NULL")}
    return lib, native


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """Intervalle de confiance à 95 % d'une proportion k/n (Wilson), en %."""
    if n <= 0:
        return 0.0, 100.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1)


def _grid_gap(mine, theirs) -> tuple:
    """(écart médian en ms entre chaque temps Rekordbox et le temps DJSync le plus proche,
    même 1er temps de mesure ?, écart SIGNÉ médian en ms : DJSync - Rekordbox) ; None si pas comparable."""
    import numpy as np

    if not theirs or not mine.beats:
        return None, None, None
    rb_t, rb_n = np.array(theirs[0]), theirs[1]
    my_t = np.array([t for _, t in mine.beats])
    idx = np.clip(np.searchsorted(my_t, rb_t), 1, my_t.size - 1)
    near = np.where(np.abs(my_t[idx] - rb_t) < np.abs(my_t[idx - 1] - rb_t), idx, idx - 1)
    gap = float(np.median(np.abs(my_t[near] - rb_t))) * 1000
    signed = float(np.median(my_t[near] - rb_t)) * 1000
    rb_down = next((t for t, n in zip(rb_t, rb_n) if n == 1), None)
    my_downs = np.array([t for n, t in mine.beats if n == 1])
    same_down = bool(rb_down is not None and my_downs.size and np.min(np.abs(my_downs - rb_down)) < 0.03)
    return round(gap, 1), same_down, round(signed, 1)


def _compare(source: str, ffmpeg: str | None, limit: int, csv_path: str | None = None,
             under: str | None = None) -> int:
    from .decode import ANALYSIS_SR, MP4_SUFFIXES, decode, mp4_timing, timeline_lead_seconds
    from .key import analyze_key
    from .tempo import analyze_tempo

    rows = []
    lib, native = _open_source(source)
    try:
        prefix = under.replace("\\", "/").rstrip("/").lower() if under else ""
        tracks = [t for t in lib.list_tracks() if t.is_analysed and t.bpm > 0 and t.content_id in native
                  and (not prefix or prefix in str(lib.absolute_path(t)).replace("\\", "/").lower())][:limit]
        skipped = sum(1 for t in lib.list_tracks() if t.is_analysed and t.content_id not in native)
        print(f"{len(tracks)} tracks analysed by Rekordbox to compare"
              f"{f' ({skipped} analysed by DJSync ignored)' if skipped else ''}.\n", flush=True)
        bpm_ok = octave = key_ok = key_rel = grid_ok = grid_n = down_ok = half_n = 0
        by_format: dict = {}
        for i, t in enumerate(tracks, start=1):
            dbg: dict = {}
            try:
                audio = decode(lib.absolute_path(t), ffmpeg, ANALYSIS_SR)
                grid = analyze_tempo(audio.samples, audio.sr, dbg)
                key = analyze_key(audio.samples, audio.sr, dbg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {t.title}: {exc}")
                continue
            mine, theirs = key.camelot, to_camelot(t.key)
            gap, same_down, signed = _grid_gap(grid, _rekordbox_grid(lib, t))
            same_bpm = abs(grid.bpm - t.bpm) <= 0.05
            is_oct = not same_bpm and (abs(grid.bpm - 2 * t.bpm) <= 0.1 or abs(2 * grid.bpm - t.bpm) <= 0.1)
            bpm_ok += same_bpm
            octave += is_oct
            key_ok += bool(mine and mine == theirs)
            key_rel += bool(mine and theirs and mine != theirs and mine[:-1] == theirs[:-1])
            grid_txt = ""
            half = False
            if gap is not None and (same_bpm or is_oct):
                grid_n += 1
                grid_ok += gap <= 20
                down_ok += bool(same_down)
                # 1.2.0-rc.4 (B11) : grille posée sur le contretemps = décalage d'un demi-temps à ±25 ms.
                half = signed is not None and abs(abs(signed) - 30000.0 / grid.bpm) <= 25
                half_n += half
                if gap < 0.25 * 60000 / grid.bpm:
                    by_format.setdefault(t.path.rsplit(".", 1)[-1].lower(), []).append(signed)
                grid_txt = (f"  grid {gap:5.1f} ms{' (half beat)' if half else ''}"
                            f"{'' if same_down else ' (downbeat shifted)'}")
            flag = "" if (same_bpm and mine == theirs) else "   <--"
            print(f"{i:4} {t.title[:40]:40}  Rekordbox {t.bpm:7.2f} {theirs or '?':>4}   DJSync {grid.bpm:7.2f} "
                  f"{mine or '?':>4}{' (octave)' if is_oct else ''}{' [variable]' if grid.variable else ''}"
                  f"{grid_txt}{flag}", flush=True)
            rows.append({"title": t.title, "file": t.path, "duration": round(audio.duration, 1),
                         "rb_bpm": t.bpm, "rb_key": theirs or "", "dj_bpm": grid.bpm, "dj_key": mine or "",
                         "dj_first_beat": round(grid.first_beat, 4), "dj_variable": grid.variable,
                         "grid_gap_ms": gap if gap is not None else "", "grid_signed_ms": signed if signed is not None else "",
                         "same_downbeat": same_down
                         if same_down is not None else "", "half_beat": half,
                         **(mp4_timing(lib.absolute_path(t)) if t.path.lower().endswith(MP4_SUFFIXES) else {}),
                         "lead_ms": round(timeline_lead_seconds(lib.absolute_path(t)) * 1000, 1), **dbg})
        _summary(len(rows), bpm_ok, octave, key_ok, key_rel, grid_n, grid_ok, down_ok, half_n)
        if by_format:
            import statistics

            for fmt, vals in sorted(by_format.items()):
                print(f"  .{fmt:4}: {len(vals):3} tracks, median offset DJSync - Rekordbox {statistics.median(vals):+.1f} ms")
    finally:
        lib.__exit__(None, None, None)
    if csv_path:
        import csv

        cols = list(dict.fromkeys(k for r in rows for k in r))
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        print(f"Diagnostic written: {csv_path}  (send it back to calibrate the analysis)")
    return 0


def _summary(n: int, bpm_ok: int, octave: int, key_ok: int, key_rel: int, grid_n: int, grid_ok: int,
             down_ok: int, half_n: int = 0) -> None:
    """Résumé avec intervalles de confiance à 95 % : au-dessous de ~100 sons, ils sont larges."""
    def line(name: str, k: int, total: int) -> str:
        lo, hi = wilson(k, total)
        pct = 100 * k / total if total else 0
        return f"  {name:34} {k:4}/{total:<4} {pct:5.1f} %   (95 % CI {lo:.0f}-{hi:.0f} %)"

    print("\n==== Summary (DJSync vs Rekordbox) ====")
    print(line("Same BPM (±0.05)", bpm_ok, n))
    print(line("Same BPM or ×2 / ÷2", bpm_ok + octave, n))
    print(line("Same key", key_ok, n))
    print(line("Same key or relative maj./min.", key_ok + key_rel, n))
    if grid_n:
        print(line("Grid: beats within 20 ms", grid_ok, grid_n))
        print(line("Grid: same downbeat (bar start)", down_ok, grid_n))
        print(line("Grid: shifted by half a beat", half_n, grid_n))
    if n < 100:
        print(f"\n  Only {n} tracks: margins of error are wide. 300-500 varied tracks give ±3-5 %.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.analysis", description="DJSync audio analysis (read-only): BPM, beat grid, key.\n\n"
                                 "  python -m djsync.analysis track.m4a [track2.mp3 ...]\n"
                                 "  python -m djsync.analysis --compare E:   compare with Rekordbox's analyses on a drive",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--compare", metavar="DRIVE|local",
                    help="compare with Rekordbox's analyses: of a drive (E:) or of this computer's collection (local)")
    ap.add_argument("--under", metavar="FOLDER", help="with --compare: only the tracks whose file is in this folder")
    ap.add_argument("--limit", type=int, default=10_000, help="maximum number of tracks compared (default: all)")
    ap.add_argument("--csv", metavar="FILE", help="with --compare: write detailed measurements (calibration)")
    ap.add_argument("--ffmpeg", default=None, help="folder containing ffmpeg(.exe)")
    args = ap.parse_args(argv)
    if args.compare:
        return _compare(args.compare, args.ffmpeg, args.limit, args.csv, args.under)
    if not args.files:
        ap.print_help()
        return 1
    for f in args.files:
        _one(f, args.ffmpeg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
