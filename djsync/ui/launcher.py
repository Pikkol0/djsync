"""Lancement de DJSync : l'écran de démarrage s'affiche AVANT le chargement des modules lourds
(yt-dlp, SQLCipher, analyse…), puis la fenêtre principale le remplace dès qu'elle est prête."""
from __future__ import annotations

import logging
import sys


def _setup_logging() -> None:
    """Journal dans le dossier des réglages (djsync.log, 1 Mo × 3) : l'exe Windows n'a pas de console,
    c'est la seule trace en cas de souci sur un autre PC. Plus la console quand il y en a une."""
    from logging.handlers import RotatingFileHandler

    from ..settings import settings_dir

    handlers: list = []
    try:
        folder = settings_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(folder / "djsync.log", maxBytes=1_000_000, backupCount=2,
                                            encoding="utf-8"))
    except OSError:
        pass                                  # clé en lecture seule : pas de journal
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers or [logging.NullHandler()])
    from .. import __version__

    logging.getLogger("djsync").info("DJSync %s starting (%s)", __version__, sys.executable)


def main() -> int:
    import os

    if os.environ.get("DJSYNC_SELFTEST"):           # CI / dépannage : autotest sans interface
        from ..selftest import run

        return run(os.environ["DJSYNC_SELFTEST"])
    from .. import portable

    _setup_logging()
    portable.prepare_environment()
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setApplicationName("DJSync")
    from . import splash

    screen = splash.show(app)
    try:
        from .app import DJSyncApp      # import lourd : pendant que l'écran de démarrage est visible

        window = DJSyncApp(splash=screen)
    except BaseException:
        if screen is not None:
            screen.close()
        splash.close_native()
        raise
    window.reveal()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
