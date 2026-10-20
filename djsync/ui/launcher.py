"""Lancement de DJSync : l'écran de démarrage s'affiche AVANT le chargement des modules lourds
(yt-dlp, SQLCipher, analyse…), puis la fenêtre principale le remplace dès qu'elle est prête."""
from __future__ import annotations

import logging
import sys


def main() -> int:
    from .. import portable

    portable.prepare_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
