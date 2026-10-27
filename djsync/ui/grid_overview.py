"""Vue d'ensemble du son en 3 bandes, dans la barre du lecteur, pendant la page « Grille et cues »
(1.3.0-rc.3, B17). Mêmes couleurs que l'éditeur ; la zone affichée par l'éditeur est encadrée, le
curseur et les hot cues sont marqués ; cliquer ou glisser déplace l'éditeur (et la lecture) dans le son.
Ailleurs, le lecteur garde sa forme d'onde habituelle."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from ..i18n import t
from . import theme

HEIGHT = 46


class GridOverview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.editor: Any = None
        self.setFixedHeight(theme.px(HEIGHT))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(t("grid.overview_tip"))
        self._cache_key: Any = None
        self._cache: Optional[list] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)

    def set_editor(self, editor: Any) -> None:
        self.editor = editor
        self._cache_key = self._cache = None
        if editor is not None:
            self._timer.start(80)
        else:
            self._timer.stop()
        self.update()

    # ------------------------------------------------------------------ dessin
    def _columns(self, w: int) -> Optional[list]:
        """(bas, médium, aigu) par pixel, de 0 à 1 ; recalculé seulement si la largeur ou les données changent."""
        ed = self.editor
        wave = getattr(ed, "wave", None)
        key = (w, id(wave), len(getattr(ed, "detail", []) or []), getattr(ed, "duration_ms", 0))
        if key == self._cache_key:
            return self._cache
        cols = None
        if wave is not None and getattr(wave, "low", None) is not None and wave.low.size:
            import numpy as np

            n = wave.low.size
            total_s = max(1e-3, ed.duration_ms / 1000.0)
            edges = np.clip((np.arange(w + 1) / w * total_s * wave.rate).astype(np.int64), 0, n)
            starts = np.minimum(edges[:-1], n - 1)
            cols = []
            out = []
            for band in (wave.low, wave.mid, wave.high):
                vals = np.maximum.reduceat(np.append(band, 0), np.append(starts, n))[:-1]
                out.append(vals.astype(float) / 127.0)
            cols = list(zip(*out))
        self._cache_key, self._cache = key, cols
        return cols

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        from .grid_editor import BAND_COLORS
        from .cue_pads import rgb_hex

        w, h = self.width(), self.height()
        p = QPainter(self)
        p.fillRect(0, 0, w, h, QColor(theme.mix(theme.SURFACE, "#000000", 0.35)))
        ed = self.editor
        if ed is None or w < 8:
            p.end()
            return
        dur = max(1.0, float(ed.duration_ms))
        mid = h / 2
        cols = self._columns(w)
        if cols:
            p.setPen(Qt.NoPen)
            for k, color in enumerate(BAND_COLORS):
                top = [QPointF(x + 0.5, mid - c[k] * (h / 2 - 2)) for x, c in enumerate(cols)]
                bottom = [QPointF(x + 0.5, mid + c[k] * (h / 2 - 2)) for x, c in reversed(list(enumerate(cols)))]
                p.setBrush(QColor(color))
                p.drawPolygon(QPolygonF(top + bottom))
            p.setBrush(Qt.NoBrush)
        elif getattr(ed, "detail", None):            # analyse sans forme d'onde fine : ANLZ
            n = len(ed.detail)
            for x in range(w):
                a, b = int(x / w * n), max(int(x / w * n) + 1, int((x + 1) / w * n))
                v, color = max(ed.detail[a:min(n, b)] or [(0.0, "#000")], key=lambda d: d[0])
                half = max(1.0, v * (h / 2 - 2))
                p.fillRect(x, int(mid - half), 1, max(1, int(2 * half)), QColor(color))
        # zone affichée par l'éditeur
        span = ed.view_s * 1000.0
        x0, x1 = ed.start_ms / dur * w, (ed.start_ms + span) / dur * w
        frame = QColor(theme.TEXT)
        frame.setAlpha(40)
        p.fillRect(QRectF(x0, 0, max(2.0, x1 - x0), h), frame)
        # hot cues
        for c in getattr(ed, "cues", []) or []:
            if c.slot:
                p.fillRect(QRectF(c.ms / dur * w - 1, 0, 2, theme.px(8)), QColor(rgb_hex(c.colour())))
        xc = ed.cursor_ms / dur * w
        p.fillRect(QRectF(xc - 1, 0, 2, h), QColor(theme.ACCENT))
        p.end()

    # ---------------------------------------------------------------- navigation
    def _go(self, x: float) -> None:
        ed = self.editor
        if ed is None or not ed.winfo_exists():
            return
        ms = max(0.0, min(1.0, x / max(1, self.width()))) * ed.duration_ms
        ed.go_to(ms)
        if ed.beats:
            from ..analysis import grid as G

            ed.selected = G.nearest(ed.beats, ed.cursor_ms)
            ed._refresh_info()

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        if e.button() == Qt.LeftButton:
            self._go(e.position().x())

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        if e.buttons() & Qt.LeftButton:
            self._go(e.position().x())
