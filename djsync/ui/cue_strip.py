"""1.3.2 (C79) : aperçu discret des cues d'un son, dans l'outil Doublons.

Une fine barre de la durée du son (sans forme d'onde) : hot cues avec leur lettre et leur couleur,
mémoires en petit triangle, boucles en segment (début → fin). Le survol d'un repère donne sa lettre ou
son nom, sa position et la longueur de la boucle."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF
from PySide6.QtWidgets import QToolTip, QWidget

from ..i18n import t
from . import theme

HEIGHT = 24


def mmss(ms: int) -> str:
    s = max(0, int(ms)) // 1000
    return f"{s // 60}:{s % 60:02d}"


def cue_summary(cues: Sequence[Any]) -> Tuple[int, int, int]:
    """(hot cues, dont boucles, mémoires)."""
    hot = [c for c in cues if c.slot]
    return len(hot), sum(1 for c in hot if c.is_loop), sum(1 for c in cues if not c.slot)


class CueStrip(QWidget):
    def __init__(self, duration_ms: int, parent: Any = None) -> None:
        super().__init__(parent)
        self.duration_ms = max(1, int(duration_ms or 0))
        self.cues: List[Any] = []
        self.loaded = False
        self.highlight = False
        self.setFixedHeight(theme.px(HEIGHT))
        self.setMinimumWidth(theme.px(120))
        self.setMouseTracking(True)
        self.setToolTip(t("dup.cues_loading"))

    def set_cues(self, cues: Sequence[Any]) -> None:
        self.cues = sorted(cues or [], key=lambda c: c.ms)
        self.loaded = True
        hot, loops, mem = cue_summary(self.cues)
        self.setToolTip(t("dup.cues_strip_tip", hot=hot, loops=loops, mem=mem) if self.cues
                        else t("dup.cues_none"))
        self.update()

    def set_highlight(self, on: bool) -> None:
        if on != self.highlight:
            self.highlight = on
            self.update()

    # ------------------------------------------------------------------ géométrie
    def _x(self, ms: int) -> float:
        m = theme.px(5)
        return m + (self.width() - 2 * m) * min(1.0, max(0.0, ms / self.duration_ms))

    def marker_at(self, x: float) -> Optional[Any]:
        best, dist = None, theme.px(6)
        for c in self.cues:
            d = abs(self._x(c.ms) - x)
            if c.is_loop and self._x(c.ms) <= x <= self._x(c.loop_ms):
                d = min(d, theme.px(3))
            if d <= dist:
                best, dist = c, d
        return best

    def describe(self, c: Any) -> str:
        name = c.label or t("dup.cue_memory")
        if c.name:
            name += f" · {c.name}"
        text = f"{name} — {mmss(c.ms)}"
        if c.is_loop:
            text += " · " + (t("dup.cue_loop_beats", n=c.loop_beats) if c.loop_beats
                             else t("dup.cue_loop_to", end=mmss(c.loop_ms)))
        return text

    # ------------------------------------------------------------------ Qt
    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt
        c = self.marker_at(event.position().x())
        if c is not None:
            QToolTip.showText(event.globalPosition().toPoint(), self.describe(c), self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        mid = h * 0.70
        x0, x1 = self._x(0), self._x(self.duration_ms)
        if self.highlight and theme.ACCENT:           # version dont les cues seront gardées
            p.fillRect(QRectF(x0, mid - 1.5, x1 - x0, 3), QColor(theme.ACCENT))
        else:
            p.fillRect(QRectF(x0, mid - 0.5, x1 - x0, 1), QColor(theme.FAINT))
        if not self.loaded:
            p.end()
            return
        font = QFont(self.font())
        font.setPointSizeF(max(6.0, theme.font_pt(-3)))
        font.setBold(True)
        p.setFont(font)
        flag_h = mid - theme.px(4)
        flag_w = theme.px(11)
        for c in self.cues:                            # boucles et mémoires d'abord, lettres par-dessus
            r, g, b = c.colour()
            col = QColor(r, g, b)
            x = self._x(c.ms)
            if c.is_loop:
                p.fillRect(QRectF(x, mid - 3, max(2.0, self._x(c.loop_ms) - x), 6), col)
            if not c.slot:
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawPolygon(QPolygonF([QPointF(x - 4, h - 1), QPointF(x + 4, h - 1), QPointF(x, mid + 1)]))
        for c in self.cues:
            if not c.slot:
                continue
            r, g, b = c.colour()
            col = QColor(r, g, b)
            x = self._x(c.ms)
            p.fillRect(QRectF(x - 0.75, 0, 1.5, mid + 3), col)
            p.fillRect(QRectF(x, 0, flag_w, flag_h), col)       # petit drapeau avec la lettre
            p.setPen(QColor(theme.on_color(col.name())))
            p.drawText(QRectF(x, 0, flag_w, flag_h), Qt.AlignCenter, c.label)
        p.end()
