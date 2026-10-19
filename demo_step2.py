"""Démo console de l'Étape 2 (LECTURE SEULE) sur votre vraie clé.

    python demo_step2.py          -> détecte la clé automatiquement
    python demo_step2.py E        -> force la lettre de lecteur
"""
import sys

from djsync.db import AmbiguousDriveError, RekordboxUsbLibrary, find_usb_drives, resolve_drive


def main() -> None:
    forced = sys.argv[1] if len(sys.argv) > 1 else None
    print("Clés détectées :", [str(d) for d in find_usb_drives()] or "aucune")
    try:
        drive = resolve_drive(forced=forced)
    except AmbiguousDriveError as exc:
        print(exc)
        return

    # read_only=True : aucune écriture, aucune sauvegarde, rien ne peut être modifié
    with RekordboxUsbLibrary(drive, read_only=True) as lib:
        print(f"\nClé {drive} | journal={lib.journal_mode} | {lib.track_count()} sons\n")
        for p in lib.list_playlists():
            kind = "dossier" if p.is_folder else "playlist"
            print(f"[{p.playlist_id}] {p.name}  ({kind}, {p.track_count} sons)")
        pls = [p for p in lib.list_playlists() if not p.is_folder]
        if pls:
            print(f"\n5 premiers sons de « {pls[0].name} » :")
            for t in lib.get_playlist_tracks(pls[0].playlist_id)[:5]:
                print(f"  {t.display_name}  [{t.duration_seconds}s]")


if __name__ == "__main__":
    main()
