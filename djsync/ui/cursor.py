"""Curseur de lecture commun (1.4.0, C52) : trait rouge vif, toujours le même quelle que soit la couleur
choisie, dans l'éditeur des cues et du BPM, la vue d'ensemble et le lecteur.

Le trait central reste fin et net : c'est lui qui donne la position exacte. Le halo, très léger, est
SYMÉTRIQUE autour de ce trait (il le rend visible de loin sans déplacer ni épaissir la position lue).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

CURSOR = "#FF2A3D"


def draw_cursor(p: Any, x: float, top: float, height: float, glow: bool = True) -> None:
    """Dessine le curseur centré sur `x` (coordonnées logiques)."""
    from . import theme

    core = max(1.5, theme.px(1.5))
    if glow:
        for width, alpha in ((theme.px(9), 26), (theme.px(5), 48)):
            c = QColor(CURSOR)
            c.setAlpha(alpha)
            p.fillRect(QRectF(x - width / 2, top, width, height), c)
    p.fillRect(QRectF(x - core / 2, top, core, height), QColor(CURSOR))
