"""Vérifier l'analyse sur de vrais morceaux, sans toucher à la clé :

    python -m djsync.analysis "E:\\Contents\\Artiste\\Album\\son.m4a" [autres fichiers…]
    python -m djsync.analysis --compare E:\\     (compare aux BPM/tonalités de Rekordbox sur la clé, lecture seule)

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
    print(f"{Path(path).name}\n  BPM {r.bpm:.2f}   tonalité {r.key.name or '?'} ({r.key.camelot or '?'})   "
          f"1er temps {r.grid.first_beat * 1000:.0f} ms   1er temps fort "
          f"{f'{downbeat:.3f}' if downbeat is not None else '?'} s\n"
          f"  durée {r.duration:.1f} s, {r.waveforms.detail_count} points de forme d'onde, calcul {r.seconds:.1f} s")


def _compare(drive: str, ffmpeg: str | None, limit: int) -> int:
    from ..db import RekordboxUsbLibrary, drive_from_letter

    with RekordboxUsbLibrary(drive_from_letter(drive), read_only=True) as lib:
        tracks = [t for t in lib.list_tracks() if t.is_analysed and t.bpm > 0][:limit]
        bpm_ok = key_ok = key_same_number = 0
        for t in tracks:
            try:
                r = analyze_file(lib.absolute_path(t), ffmpeg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {t.title} : {exc}")
                continue
            ok_bpm = abs(r.bpm - t.bpm) <= 0.05 or abs(r.bpm - 2 * t.bpm) <= 0.1 or abs(2 * r.bpm - t.bpm) <= 0.1
            mine, theirs = r.key.camelot, to_camelot(t.key)
            bpm_ok += abs(r.bpm - t.bpm) <= 0.05
            key_ok += bool(mine and mine == theirs)
            key_same_number += bool(mine and theirs and mine[:-1] == theirs[:-1])
            flag = "" if (abs(r.bpm - t.bpm) <= 0.05 and mine == theirs) else "   <--"
            print(f"  {t.title[:40]:40}  Rekordbox {t.bpm:7.2f} {theirs or '?':>4}   DJSync {r.bpm:7.2f} {mine or '?':>4}"
                  f"{' (octave)' if ok_bpm and abs(r.bpm - t.bpm) > 0.05 else ''}{flag}")
        n = max(1, len(tracks))
        print(f"\nBPM identiques : {bpm_ok}/{len(tracks)} ({100 * bpm_ok / n:.0f} %)   tonalités identiques : "
              f"{key_ok}/{len(tracks)} ({100 * key_ok / n:.0f} %)   même numéro Camelot : {key_same_number}/{len(tracks)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.analysis", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--compare", metavar="CLÉ", help="comparer aux analyses Rekordbox de la clé (lecture seule)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--ffmpeg", default=None, help="dossier contenant ffmpeg(.exe)")
    args = ap.parse_args(argv)
    if args.compare:
        return _compare(args.compare, args.ffmpeg, args.limit)
    if not args.files:
        ap.print_help()
        return 1
    for f in args.files:
        _one(f, args.ffmpeg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
