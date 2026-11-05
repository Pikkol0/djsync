"""1.4.0-rc.3 (B73) : volet gauche replié : une icône centrée entourée d'un anneau de progression,
à la place des cartes larges (bibliothèque active, analyse, téléchargements) qui y étaient coupées."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme


class MiniRing(QWidget):
    def __init__(self, icon: str, on_click: Optional[Callable[[], None]] = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.icon = icon
        self.value = 0.0                      # 0..1
        self.color = theme.ACCENT
        self.on_click = on_click
        side = theme.px(32)
        self.setFixedSize(QSize(side, side))
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)

    def set(self, value: float, icon: Optional[str] = None, tip: str = "", color: Optional[str] = None) -> None:
        self.value = max(0.0, min(1.0, float(value)))
        if icon:
            self.icon = icon
        if color:
            self.color = color
        self.setToolTip(tip)
        self.update()

    def mousePressEvent(self, e: Any) -> None:  # noqa: N802
        if self.on_click is not None:
            self.on_click()

    def paintEvent(self, _e: Any) -> None:  # noqa: N802
        from .icons import qicon

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = theme.px(3)
        r = QRectF(w, w, self.width() - 2 * w, self.height() - 2 * w)
        p.setPen(QPen(QColor(theme.BORDER), w))
        p.drawEllipse(r)
        if self.value > 0:
            pen = QPen(QColor(self.color), w)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -int(360 * 16 * self.value))
        s = theme.px(14)
        pix = qicon(self.icon, 14, theme.DIM).pixmap(QSize(s, s))
        p.drawPixmap((self.width() - s) // 2, (self.height() - s) // 2, pix)
        p.end()
