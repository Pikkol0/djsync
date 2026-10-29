"""Vue d'ensemble du son en 3 bandes (1.3.0-rc.3, B17), dans la page « Grille et cues » depuis la 1.3.2
(C51), entre la forme d'onde zoomée et les hot cues. Dessinée comme la vue d'ensemble de Rekordbox :
fond noir, forme d'onde posée en bas et montant vers le haut (basses bleues dessous, médiums orange puis
aigus blancs par-dessus), étiquette carrée de la couleur de chaque hot cue avec sa lettre en haut,
petit triangle pour chaque mémoire en bas, curseur rouge (C52), zone affichée en grand juste cadrée.
Cliquer ou glisser déplace l'éditeur (et la lecture) dans le son."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from ..i18n import t
from . import theme

HEIGHT = 62
LABEL_H = 13                  # bande des étiquettes de hot cues (px logiques, avant zoom)
MARK_H = 7                    # bande des triangles de mémoires


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
        from .cue_pads import rgb_hex
        from .cursor import draw_cursor
        from .grid_editor import BAND_COLORS

        w, h = self.width(), self.height()
        p = QPainter(self)
        p.fillRect(0, 0, w, h, QColor("#000000"))          # 1.3.2 (C51) : fond noir, comme Rekordbox
        ed = self.editor
        if ed is None or w < 8:
            p.end()
            return
        dur = max(1.0, float(ed.duration_ms))
        top_band, low_band = theme.px(LABEL_H), theme.px(MARK_H)
        base = h - low_band                                 # la forme d'onde est posée sur cette ligne
        height = max(4.0, base - top_band - 1)
        cols = self._columns(w)
        if cols:
            p.setPen(Qt.NoPen)
            for k, color in enumerate(BAND_COLORS):         # basses, puis médiums, puis aigus par-dessus
                pts = [QPointF(0, base)] + [QPointF(x + 0.5, base - c[k] * height) for x, c in enumerate(cols)]
                pts.append(QPointF(w, base))
                p.setBrush(QColor(color))
                p.drawPolygon(QPolygonF(pts))
            p.setBrush(Qt.NoBrush)
        elif getattr(ed, "detail", None):            # analyse sans forme d'onde fine : ANLZ
            n = len(ed.detail)
            for x in range(w):
                a, b = int(x / w * n), max(int(x / w * n) + 1, int((x + 1) / w * n))
                v, color = max(ed.detail[a:min(n, b)] or [(0.0, "#000")], key=lambda d: d[0])
                bar = max(1.0, v * height)
                p.fillRect(QRectF(x, base - bar, 1, bar), QColor(color))
        # zone affichée en grand : cadre discret, la forme d'onde reste visible
        span = ed.view_s * 1000.0
        x0, x1 = ed.start_ms / dur * w, (ed.start_ms + span) / dur * w
        frame = QColor("#FFFFFF")
        frame.setAlpha(26)
        p.fillRect(QRectF(x0, top_band, max(2.0, x1 - x0), base - top_band), frame)
        frame.setAlpha(110)
        p.setPen(frame)
        p.drawRect(QRectF(x0, top_band, max(2.0, x1 - x0), base - top_band - 1))
        # mémoires : petit triangle en bas (orange pour une boucle, rouge sinon)
        tri = theme.px(MARK_H) - 1
        p.setPen(Qt.NoPen)
        for c in getattr(ed, "cues", []) or []:
            if c.slot:
                continue
            x = c.ms / dur * w
            p.setBrush(QColor("#FF8C00" if c.is_loop else "#E8202A"))
            p.drawPolygon(QPolygonF([QPointF(x - tri * 0.7, h), QPointF(x + tri * 0.7, h), QPointF(x, h - tri)]))
        # hot cues : étiquette carrée de la couleur du cue, avec sa lettre, en haut
        font = p.font()
        font.setBold(True)
        font.setPixelSize(max(8, top_band - theme.px(3)))
        p.setFont(font)
        for c in getattr(ed, "cues", []) or []:
            if not c.slot:
                continue
            x = c.ms / dur * w
            box = QRectF(x - top_band / 2, 0, top_band, top_band)
            color = QColor(rgb_hex(c.colour()))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRect(box)
            p.fillRect(QRectF(x - 0.5, top_band, 1, base - top_band), color)
            p.setPen(QColor(theme.on_color(color.name())))
            p.drawText(box, Qt.AlignCenter, c.label)
        p.setBrush(Qt.NoBrush)
        draw_cursor(p, ed.cursor_ms / dur * w, 0, h, glow=False)       # 1.3.2 (C52)
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
