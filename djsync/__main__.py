from .ui.launcher import main

if __name__ == "__main__":       # 1.4.3 (A1-6) : pas relancé par les processus d'analyse (__mp_main__)
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
