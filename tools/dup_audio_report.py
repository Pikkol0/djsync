"""OUTIL DE DÉVELOPPEMENT (1.3.0, B02) : calibrer la comparaison des doublons par le son sur une vraie
bibliothèque, sans rien modifier.

    python tools/dup_audio_report.py E:            # clé USB
    python tools/dup_audio_report.py E: -o rapport.txt

Pour chaque groupe proposé par les titres : verdict de chaque version par rapport à la référence
(« same », « variant », « different »), part du son en commun, distance et décalage. Sert à vérifier
les seuils de djsync/analysis/fingerprint.py (SAME_BER, SAME_SHARE, VARIANT_SHARE) : vrais doublons
trouvés, faux doublons évités (Afro Trap Pt. 3 / Pt. 7…).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv=None) -> int:
    from djsync.analysis.fingerprint import compare, file_fingerprint, is_usable
    from djsync.core.duplicates import best_keeper, find_duplicate_groups
    from djsync.db import RekordboxUsbLibrary, drive_from_letter

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("drive")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--ffmpeg", default="")
    args = ap.parse_args(argv)
    cache = Path(tempfile.gettempdir()) / "djsync_fp"
    lines = []
    with RekordboxUsbLibrary(drive_from_letter(args.drive), read_only=True, analyze=False) as lib:
        groups = find_duplicate_groups(lib.list_tracks())
        lines.append(f"{len(groups)} groups proposed by titles")
        for g in groups:
            ref = best_keeper(g)
            lines.append("")
            lines.append(f"* {ref.artist} - {ref.title} ({ref.duration_seconds} s) [reference]")
            try:
                fr = file_fingerprint(lib.absolute_path(ref), args.ffmpeg or None, cache)
            except Exception as exc:  # noqa: BLE001
                lines.append(f"    reference unreadable: {exc}")
                continue
            for x in g:
                if x is ref:
                    continue
                try:
                    fx = file_fingerprint(lib.absolute_path(x), args.ffmpeg or None, cache)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"  - {x.artist} - {x.title}: unreadable ({exc})")
                    continue
                if not (is_usable(fr) and is_usable(fx)):
                    lines.append(f"  - {x.artist} - {x.title}: too short or silent")
                    continue
                m = compare(fr, fx, float(ref.duration_seconds or 0), float(x.duration_seconds or 0))
                lines.append(f"  - {x.artist} - {x.title} ({x.duration_seconds} s): {m.verdict:9s} "
                             f"common {m.share * 100:5.1f} %  distance {m.ber:.3f}  shift {m.shift_ms / 1000:+.2f} s")
    text = "\n".join(lines)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
