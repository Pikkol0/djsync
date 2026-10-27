"""Écran de démarrage : s'affiche dès le double-clic, pendant le chargement des modules lourds et la
construction de la fenêtre. Volontairement minimal : logo, nom, « Loading… », sans barre de progression.

Exécutable PyInstaller : l'écran natif (packaging/DJSync.spec) couvre la décompression ; 1.3.0-rc.4
(B24) : il est fermé juste avant la création de QApplication et celui-ci prend le relais.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .. import full_version
from .palettes import DEFAULT_THEME, DIM, PALETTES, SURFACE, TEXT

WIDTH, HEIGHT = 320, 200


def native_splash_active() -> bool:
    try:
        import pyi_splash  # noqa: F401  (n'existe que dans l'exécutable PyInstaller)
        return True
    except ImportError:
        return False


_native_closed = False


def close_native() -> None:
    """Ferme l'écran natif de l'exe (une seule fois : un 2e appel ne fait rien)."""
    global _native_closed
    if _native_closed:
        return
    _native_closed = True
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:  # noqa: BLE001 - pas d'écran natif (lancement depuis les sources)
        pass


def _saved_accent() -> str:
    """Couleur choisie dans les Paramètres, lue sans charger toute l'application."""
    try:
        from ..settings import Settings

        theme = json.loads(Settings.path().read_text(encoding="utf-8")).get("theme", DEFAULT_THEME)
    except Exception:  # noqa: BLE001 - pas encore de réglages : couleur par défaut
        theme = DEFAULT_THEME
    return PALETTES.get(theme, PALETTES[DEFAULT_THEME])


class Splash:
    """Fenêtre sans bordure, centrée (Qt gère le DPI). `close()` est idempotent."""

    def __init__(self, app: Any) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
        from PySide6.QtWidgets import QSplashScreen

        from .logo import logo_pixmap

        ratio = app.primaryScreen().devicePixelRatio() if app.primaryScreen() else 1.0
        pm = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(QColor(SURFACE))
        p = QPainter(pm)
        p.setPen(QColor(DIM))
        p.drawRect(0, 0, WIDTH - 1, HEIGHT - 1)
        accent = _saved_accent()
        logo = logo_pixmap(56, accent, SURFACE)        # déjà net en x2 ; 1.3.0-rc.3 : n'est plus dessiné deux fois trop grand
        p.drawPixmap((WIDTH - 56) // 2, 30, logo)
        f = QFont(app.font())
        f.setPointSizeF(18)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        p.drawText(0, 96, WIDTH, 34, Qt.AlignCenter, "DJSync")
        f.setPointSizeF(9)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(DIM))
        p.drawText(0, 132, WIDTH, 20, Qt.AlignCenter, "Loading…")
        # 1.3.0-rc.3 (C31) : version exacte sur sa propre ligne, dans la couleur choisie, bien lisible
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(accent))
        p.drawText(0, 154, WIDTH, 20, Qt.AlignCenter, f"v{full_version()}")
        p.end()
        self.widget: Optional[QSplashScreen] = QSplashScreen(pm, Qt.WindowStaysOnTopHint)
        self.widget.show()
        app.processEvents()

    def close(self) -> None:
        w, self.widget = self.widget, None
        if w is not None:
            w.close()
            w.deleteLater()


def show(app: Any) -> Optional[Splash]:
    """Affiche l'écran de démarrage. 1.3.0-rc.4 (B24) : toujours, y compris dans l'exe Windows, dont
    l'écran natif vient d'être fermé (voir launcher.main)."""
    try:
        return Splash(app)
    except Exception:  # noqa: BLE001 - pas d'écran : on s'en passe
        return None
