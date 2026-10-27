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
    from .. import full_version

    logging.getLogger("djsync").info("DJSync %s starting (%s)", full_version(), sys.executable)


def main() -> int:
    import os

    if os.environ.get("DJSYNC_SELFTEST"):           # CI / dépannage : autotest sans interface
        from ..selftest import run

        return run(os.environ["DJSYNC_SELFTEST"])
    from .. import portable

    if portable.translocated() and portable.leave_translocation():
        return 0                                    # macOS : relancé depuis la clé, sans quarantaine
    _setup_logging()
    portable.prepare_environment()
    from PySide6.QtWidgets import QApplication

    from . import splash

    # 1.3.0-rc.4 (B24, C31) : l'écran natif de l'exe (image fixe, sans réglage d'échelle) est fermé AVANT
    # que Qt ne déclare à Windows qu'il gère lui-même le zoom : sinon, à 150-200 %, Windows le recalait en
    # pixels réels et il glissait vers le haut à gauche. L'écran Qt (centré, net, version exacte du code
    # qui tourne, même après une mise à jour depuis l'app) prend le relais tout de suite.
    splash.close_native()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setApplicationName("DJSync")
    screen = splash.show(app)
    try:
        from .app import DJSyncApp      # import lourd : pendant que l'écran de démarrage est visible

        window = DJSyncApp(splash=screen)
        from ..core import error_reports            # 1.2.3 : exceptions non rattrapées -> rapport proposé

        error_reports.install(window.ctrl.error_reporter)
    except BaseException:
        if screen is not None:
            screen.close()
        splash.close_native()
        raise
    window.reveal()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
