"""Curseur de lecture commun (1.3.2, C52) : trait rouge vif, toujours le même quelle que soit la couleur
choisie, dans l'éditeur des cues et du BPM, la vue d'ensemble et le lecteur.

Le trait central reste fin et net : c'est lui qui donne la position exacte. Le halo, très léger, est
SYMÉTRIQUE autour de ce trait (il le rend visible de loin sans déplacer ni épaissir la position lue).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

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


log = logging.getLogger(__name__)
METER_SECONDS = 10.0


class FrameMeter:
    """1.3.2 (C52, retour du testeur Mac) : images par seconde réellement affichées pendant la lecture,
    écrites dans le journal toutes les 10 s (toutes plateformes), avec la durée moyenne d'un dessin."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._start: Optional[float] = None
        self._frames = 0
        self._paint = 0.0

    def frame(self, paint_ms: float = 0.0) -> None:
        now = time.perf_counter()
        if self._start is None:
            self._start, self._frames, self._paint = now, 0, 0.0
            return
        self._frames += 1
        self._paint += paint_ms
        if now - self._start >= METER_SECONDS:
            fps = self._frames / (now - self._start)
            log.info("Playback frames (%s): %.0f fps, %.1f ms per drawing", self.name, fps,
                     self._paint / max(1, self._frames))
            self._start, self._frames, self._paint = now, 0, 0.0

    def stop(self) -> None:
        self._start = None


class Monotonic:
    """1.3.2 (C52, retour du testeur Mac) : pendant la lecture, la position affichée ne recule jamais d'un
    petit pas (les relevés du lecteur oscillent de quelques ms : la forme d'onde faisait des retours en
    arrière). Un vrai saut (retour en arrière voulu, boucle, autre son) passe tout de suite."""

    JITTER_MS = 300.0

    def __init__(self) -> None:
        self.last: Optional[float] = None

    def __call__(self, ms: float) -> float:
        if self.last is not None and 0 < self.last - ms < self.JITTER_MS:
            return self.last
        self.last = ms
        return ms

    def reset(self) -> None:
        self.last = None
