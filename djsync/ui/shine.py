"""1.4.1 (C141, D14) : or et argent « allumés ».

Un dégradé métallique (jamais un aplat : l'or ne se confond plus avec le jaune « ≈ 192 », l'argent avec le
gris) et un reflet qui traverse le texte environ toutes les 5 s, décalé d'une ligne à l'autre. Une seule
minuterie pour toute l'application ; elle ne redessine que les tableaux visibles qui ont des cellules or
ou argent, seulement pendant le passage du reflet, et s'arrête si la fenêtre est réduite ou inactive.
Sans animation (mode léger, « animations réduites » du système, `set_enabled(False)`), le dégradé reste.

Les cellules concernées sont celles dont la couleur imposée (`<colonne>__color`) est theme.GOLD ou
theme.SILVER : le texte de la qualité annoncée (résultats de recherche, Format, Débit, Source) comme la
qualité mesurée. Les pastilles (QLabel « chip_gold » / « chip_silver ») gardent leur dégradé du thème.
"""
from __future__ import annotations

import time
import weakref
from typing import Any, Optional

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from . import theme

PERIOD = 5.0          # s entre deux passages du reflet sur une même ligne
SWEEP = 0.9           # s que dure un passage
ROW_SHIFT = 0.35      # s de décalage d'une ligne à la suivante (fixe : pas de hasard au dessin)
FPS = 25

STOPS = {   # (sombre, clair, sombre) : métal, pas un aplat
    "gold": ("#9A7420", "#F3D27A", "#B8862B"),
    "silver": ("#4F7BAA", "#B9D6F5", "#5E8BBB"),     # 1.4.1-rc.2 (C190) : bleu acier
}
HIGHLIGHT = {"gold": "#FFF6D6", "silver": "#EAF5FF"}

_enabled = True


def set_enabled(on: bool) -> None:
    """Animation coupée (mode léger) : le dégradé fixe reste, plus aucun redessin."""
    global _enabled
    _enabled = bool(on)
    Clock.get().sync()


def kind_of(color: Any) -> Optional[str]:
    """« gold », « silver » ou None pour une couleur de cellule (#RRGGBB ou QColor)."""
    if color is None:
        return None
    name = QColor(color).name().upper() if not isinstance(color, str) else color.upper()
    if name == theme.GOLD.upper():
        return "gold"
    if name == theme.SILVER.upper():
        return "silver"
    return None


def reflection(now: float, row: int) -> Optional[float]:
    """Position du reflet (0 à 1 sur la largeur du texte) pour une ligne, None hors passage."""
    if not _enabled:
        return None
    t = (now + row * ROW_SHIFT) % PERIOD
    return t / SWEEP if t < SWEEP else None


def brush(kind: str, rect: QRectF, pos: Optional[float]) -> QBrush:
    """Dégradé métallique sur `rect`, avec le reflet à la position `pos` (0-1) s'il passe."""
    a, b, c = (QColor(s) for s in STOPS[kind])
    g = QLinearGradient(QPointF(rect.left(), rect.top()), QPointF(rect.right(), rect.bottom()))
    g.setColorAt(0.0, a)
    g.setColorAt(0.5, b)
    g.setColorAt(1.0, c)
    if pos is not None:
        p = min(0.94, max(0.06, pos))
        g.setColorAt(max(0.0, p - 0.06), b)
        g.setColorAt(p, QColor(HIGHLIGHT[kind]))
        g.setColorAt(min(1.0, p + 0.06), b)
    return QBrush(g)


class Clock(QObject):
    """Minuterie unique : redessine les tableaux inscrits, seulement pendant un passage du reflet."""

    _instance: Optional["Clock"] = None

    def __init__(self) -> None:
        super().__init__()
        self._views: "weakref.WeakSet[Any]" = weakref.WeakSet()
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / FPS))
        self._timer.timeout.connect(self._tick)
        self.ticks = 0

    @classmethod
    def get(cls) -> "Clock":
        if cls._instance is None:
            cls._instance = Clock()
        return cls._instance

    def watch(self, view: Any) -> None:
        self._views.add(view)
        self.sync()

    def sync(self) -> None:
        if _enabled and len(self._views):
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def _active(self, view: Any) -> bool:
        try:
            win = view.window()
            if not view.isVisible() or win.isMinimized():
                return False
            app = QApplication.instance()
            return app is not None and app.applicationState() == Qt.ApplicationActive
        except RuntimeError:                      # vue détruite
            return False

    def _tick(self) -> None:
        if not _enabled:
            self.sync()
            return
        now = time.monotonic()
        for view in list(self._views):
            if not self._active(view) or not getattr(view, "has_shine", lambda: False)():
                continue
            vp = view.viewport()
            first = max(0, view.rowAt(0))
            last = view.rowAt(vp.height() - 1)
            last = view.model().rowCount() - 1 if last < 0 else last
            # une ligne n'est redessinée que si son reflet passe (ou vient de finir)
            for row in range(first, last + 1):
                t = (now + row * ROW_SHIFT) % PERIOD
                if t < SWEEP + 1.0 / FPS:
                    vp.update(0, view.rowViewportPosition(row), vp.width(), view.rowHeight(row))
                    self.ticks += 1


class ShineDelegate(QStyledItemDelegate):
    """Délégué par défaut des tableaux : texte or / argent en dégradé, avec reflet ; le reste inchangé."""

    def paint(self, painter: Any, option: Any, index: Any) -> None:
        kind = kind_of(index.data(Qt.ForegroundRole))
        if kind is None:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        r = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
        shown = opt.fontMetrics.elidedText(text, Qt.ElideRight, max(0, r.width() - 4))
        width = opt.fontMetrics.horizontalAdvance(shown)
        align = int(opt.displayAlignment)
        x = r.left() + 2
        if align & int(Qt.AlignRight):
            x = r.right() - 2 - width
        elif align & int(Qt.AlignHCenter):
            x = r.left() + (r.width() - width) / 2
        box = QRectF(x, r.top(), max(1, width), r.height())
        painter.save()
        font = opt.font
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(brush(kind, box, reflection(time.monotonic(), index.row())), 1))
        painter.drawText(box.adjusted(-1, 0, 40, 0), int(Qt.AlignVCenter | Qt.AlignLeft), shown)
        painter.restore()
