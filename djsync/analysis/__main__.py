"""Vérifier l'analyse sur de vrais morceaux, sans toucher à la clé :

    python -m djsync.analysis "E:\\Contents\\Artiste\\Album\\son.m4a" [autres fichiers…]
    python -m djsync.analysis --compare E:\\     (compare aux BPM/tonalités de Rekordbox sur la clé, lecture seule)
    python -m djsync.analysis --compare E:\\ --csv diag.csv     (+ mesures détaillées pour calibrage)

--compare lit exportLibrary.db en LECTURE SEULE, réanalyse les sons déjà analysés par Rekordbox et
affiche les écarts : c'est le meilleur moyen de juger la précision sur VOTRE musique.
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


def _rekordbox_grid(lib, content_id: int):
    """(temps en s, numéros 1-4) de la grille Rekordbox (balise PQTZ du ANLZ0000.DAT sur la clé)."""
    import struct

    from .anlz import parse

    row = lib._read("SELECT analysisDataFilePath FROM content WHERE content_id = ?", (content_id,))
    if not row or not row[0][0]:
        return None
    try:
        tags = parse(lib.absolute_path(row[0][0]).read_bytes())
        body = tags["PQTZ"][0][1]
    except (OSError, ValueError, KeyError):
        return None
    beats = [struct.unpack(">HHI", body[i:i + 8]) for i in range(0, len(body) - 7, 8)]
    return [b[2] / 1000.0 for b in beats], [b[0] for b in beats]


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


def _compare(drive: str, ffmpeg: str | None, limit: int, csv_path: str | None = None) -> int:
    from ..db import RekordboxUsbLibrary, drive_from_letter
    from .decode import ANALYSIS_SR, decode
    from .key import analyze_key
    from .tempo import analyze_tempo

    rows = []
    with RekordboxUsbLibrary(drive_from_letter(drive), read_only=True) as lib:
        tracks = [t for t in lib.list_tracks() if t.is_analysed and t.bpm > 0][:limit]
        bpm_ok = octave = key_ok = key_rel = grid_ok = grid_n = down_ok = 0
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
            gap, same_down, signed = _grid_gap(grid, _rekordbox_grid(lib, t.content_id))
            same_bpm = abs(grid.bpm - t.bpm) <= 0.05
            is_oct = not same_bpm and (abs(grid.bpm - 2 * t.bpm) <= 0.1 or abs(2 * grid.bpm - t.bpm) <= 0.1)
            bpm_ok += same_bpm
            octave += is_oct
            key_ok += bool(mine and mine == theirs)
            key_rel += bool(mine and theirs and mine != theirs and mine[:-1] == theirs[:-1])
            grid_txt = ""
            if gap is not None and (same_bpm or is_oct):
                grid_n += 1
                grid_ok += gap <= 20
                down_ok += bool(same_down)
                if gap < 0.25 * 60000 / grid.bpm:
                    by_format.setdefault(t.path.rsplit(".", 1)[-1].lower(), []).append(signed)
                grid_txt = f"  grid {gap:5.1f} ms{'' if same_down else ' (downbeat shifted)'}"
            flag = "" if (same_bpm and mine == theirs) else "   <--"
            print(f"{i:4} {t.title[:40]:40}  Rekordbox {t.bpm:7.2f} {theirs or '?':>4}   DJSync {grid.bpm:7.2f} "
                  f"{mine or '?':>4}{' (octave)' if is_oct else ''}{' [variable]' if grid.variable else ''}"
                  f"{grid_txt}{flag}", flush=True)
            rows.append({"title": t.title, "file": t.path, "duration": round(audio.duration, 1),
                         "rb_bpm": t.bpm, "rb_key": theirs or "", "dj_bpm": grid.bpm, "dj_key": mine or "",
                         "dj_first_beat": round(grid.first_beat, 4), "dj_variable": grid.variable,
                         "grid_gap_ms": gap if gap is not None else "", "grid_signed_ms": signed if signed is not None else "",
                         "same_downbeat": same_down
                         if same_down is not None else "", **dbg})
        n = max(1, len(rows))
        print(f"\nSame BPM: {bpm_ok}/{len(rows)} ({100 * bpm_ok / n:.0f} %), octave errors: "
              f"{octave}   same key: {key_ok}/{len(rows)} ({100 * key_ok / n:.0f} %), "
              f"relative maj./min.: {key_rel}")
        if grid_n:
            print(f"Grids (tracks with the same tempo): beats within 20 ms of Rekordbox: {grid_ok}/{grid_n}   "
                  f"same downbeat: {down_ok}/{grid_n}")
            import statistics

            for fmt, vals in sorted(by_format.items()):
                print(f"  .{fmt:4}: {len(vals):3} tracks, median offset DJSync - Rekordbox {statistics.median(vals):+.1f} ms")
    if csv_path:
        import csv

        cols = list(dict.fromkeys(k for r in rows for k in r))
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
            w.writeheader()
            w.writerows(rows)
        print(f"Diagnostic written: {csv_path}  (send it back to calibrate the analysis)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.analysis", description="DJSync audio analysis (read-only): BPM, beat grid, key.\n\n"
                                 "  python -m djsync.analysis track.m4a [track2.mp3 ...]\n"
                                 "  python -m djsync.analysis --compare E:   compare with Rekordbox's analyses on a drive",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--compare", metavar="DRIVE", help="compare with the Rekordbox analyses of the drive (read-only)")
    ap.add_argument("--limit", type=int, default=10_000, help="maximum number of tracks compared (default: all)")
    ap.add_argument("--csv", metavar="FILE", help="with --compare: write detailed measurements (calibration)")
    ap.add_argument("--ffmpeg", default=None, help="folder containing ffmpeg(.exe)")
    args = ap.parse_args(argv)
    if args.compare:
        return _compare(args.compare, args.ffmpeg, args.limit, args.csv)
    if not args.files:
        ap.print_help()
        return 1
    for f in args.files:
        _one(f, args.ffmpeg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
