"""DJSync entry point:  python app.py   (or DJSync.exe once built)."""
from djsync.ui.launcher import main

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()     # 1.4.3 (A1-6) : processus d'analyse de l'exe (Windows, macOS)
    raise SystemExit(main())
