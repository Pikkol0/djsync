"""Démo console de l'Étape 1 : python demo_step1.py "daft punk one more time" """
import sys
import tempfile

from djsync.core.duplicates import FakeLibrary
from djsync.core.service import MusicService


def main() -> None:
    query = " ".join(sys.argv[1:]) or "daft punk one more time"

    # Bibliothèque fictive (remplacée à l'Étape 2 par la vraie DB)
    library = FakeLibrary([("One More Time", "Daft Punk"), ("Titanium", "David Guetta")])
    service = MusicService(library)

    results = service.search(query, limit=8)
    for i, r in enumerate(results):
        flag = f"  [DÉJÀ PRÉSENT : {r.duplicate_of}]" if r.is_duplicate else ""
        print(f"{i:>2}. {r.title} - {r.artist} ({r.duration_str}){flag}")

    if not results:
        return
    choice = input("\nNuméro à télécharger (Entrée = quitter) : ").strip()
    if not choice.isdigit() or int(choice) >= len(results):
        return

    out_dir = tempfile.mkdtemp(prefix="djsync_")  # flux AAC/m4a natif, sans ré-encodage
    done = service.download(
        results[int(choice)], out_dir,
        on_progress=lambda p: print(f"\r{p.status} {p.percent:5.1f}% {p.message}", end=""),
    )
    print(f"\nFichier : {done.file_path}")


if __name__ == "__main__":
    main()
