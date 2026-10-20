"""Lancement de DJSync : l'écran de démarrage s'affiche AVANT le chargement des modules lourds
(customtkinter, yt-dlp, SQLCipher…), puis la fenêtre principale le remplace dès qu'elle est prête."""
from __future__ import annotations

import logging
import sys


def main() -> None:
    from .. import portable

    portable.prepare_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from . import splash

    screen = splash.show()
    try:
        from .app import DJSyncApp      # import lourd : pendant que l'écran de démarrage est visible

        app = DJSyncApp(splash=screen)
    except BaseException:
        if screen is not None:
            screen.close()
        splash.close_native()
        raise
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
