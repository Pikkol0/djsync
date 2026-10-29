"""Zoom de l'interface au clavier et à la molette (1.4.0, C102), à la place du curseur des Paramètres.

* Ctrl + « + » (ou « = », pavé numérique), Ctrl + « − », Ctrl + 0 : 100 %. Sur Mac, Qt traduit « Ctrl »
  en Cmd (⌘) : mêmes raccourcis avec Cmd.
* Ctrl / Cmd + molette, ou pincement du pavé tactile : zoom de l'interface, SAUF au-dessus d'une forme
  d'onde qui s'en sert déjà pour zoomer dans le son (C03) : elle garde ce rôle.
* Un petit badge « 110 % » s'affiche une seconde au centre de la fenêtre ; le zoom est appliqué après une
  courte pause (la feuille de style n'est pas reconstruite à chaque cran de molette) et gardé.
Bornes inchangées : 80 à 200 %, pas de 10 %.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLabel

from ..settings import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP
from . import theme

APPLY_DELAY_MS = 250
BADGE_MS = 1000
PINCH_STEP = 0.12            # pincement cumulé pour un cran de zoom


def clamp(percent: int) -> int:
    step = int(round(percent / ZOOM_STEP)) * ZOOM_STEP
    return max(ZOOM_MIN, min(ZOOM_MAX, step))


def owns_ctrl_wheel(widget: Any) -> bool:
    """Vrai si ce widget (ou un parent) zoome lui-même à Ctrl + molette : la forme d'onde de Grille et cues."""
    from .grid_editor import GridCanvas

    w = widget
    while w is not None:
        if isinstance(w, GridCanvas) or getattr(w, "handles_ctrl_wheel", False):
            return True
        w = w.parentWidget() if hasattr(w, "parentWidget") else None
    return False


class ZoomKeys(QObject):
    """Installée sur la fenêtre principale : raccourcis, molette, pincement, badge."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window
        self.ctrl = window.ctrl
        self.pending: Optional[int] = None
        self._pinch = 0.0
        seen = set()
        self.shortcuts = []
        # Une même séquence ne doit être déclarée qu'une fois (sinon Qt la juge ambiguë et n'en déclenche
        # aucune) : ZoomIn vaut déjà « Ctrl++ » sur la plupart des systèmes.
        for seq, delta in ((QKeySequence.ZoomIn, 1), ("Ctrl++", 1), ("Ctrl+=", 1),
                           (QKeySequence.ZoomOut, -1), ("Ctrl+-", -1), ("Ctrl+0", 0)):
            key = QKeySequence(seq)
            text = key.toString()
            if not text or text in seen:
                continue
            seen.add(text)
            sc = QShortcut(key, window)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(lambda d=delta: self.step(d))
            self.shortcuts.append((text, delta))
        self._apply = QTimer(self)
        self._apply.setSingleShot(True)
        self._apply.setInterval(APPLY_DELAY_MS)
        self._apply.timeout.connect(self.apply)
        self._badge_timer = QTimer(self)
        self._badge_timer.setSingleShot(True)
        self._badge_timer.setInterval(BADGE_MS)
        self._badge_timer.timeout.connect(self._hide_badge)
        self.badge: Optional[QLabel] = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ------------------------------------------------------------------ zoom
    @property
    def current(self) -> int:
        return int(self.pending if self.pending is not None else self.ctrl.settings.zoom)

    def step(self, delta: int) -> int:
        """+1 / −1 cran, 0 : 100 %. Renvoie le zoom visé."""
        target = 100 if delta == 0 else clamp(self.current + delta * ZOOM_STEP)
        self.set(target)
        return target

    def set(self, percent: int) -> None:
        percent = clamp(percent)
        self.pending = percent
        self._show_badge(percent)
        self.ctrl._emit("zoom_preview", percent)            # Paramètres : la valeur affichée suit
        self._apply.start()

    def apply(self) -> None:
        if self.pending is None:
            return
        z, self.pending = self.pending, None
        if z != self.ctrl.settings.zoom:
            self.ctrl.settings.zoom = z
            self.ctrl.settings.save()
            self.ctrl._emit("restyle")

    # ------------------------------------------------------------------ badge
    def _show_badge(self, percent: int) -> None:
        if self.badge is None:
            self.badge = QLabel(self.window)
            self.badge.setObjectName("zoomBadge")
            self.badge.setAlignment(Qt.AlignCenter)
            self.badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.badge.setStyleSheet(
            f"#zoomBadge {{ background: {theme.TEXT}; color: {theme.SURFACE}; border-radius: {theme.px(10)}px;"
            f" padding: {theme.px(10)}px {theme.px(18)}px; font-size: {theme.font_pt(4):.1f}pt; font-weight: 600; }}")
        self.badge.setText(f"{percent} %")
        self.badge.adjustSize()
        r = self.window.rect()
        self.badge.move((r.width() - self.badge.width()) // 2, (r.height() - self.badge.height()) // 2)
        self.badge.show()
        self.badge.raise_()
        self._badge_timer.start()

    def _hide_badge(self) -> None:
        if self.badge is not None:
            self.badge.hide()

    # ------------------------------------------------------------------ molette, pincement
    def eventFilter(self, obj: Any, ev: Any) -> bool:   # noqa: N802
        t = ev.type()
        if t == QEvent.Wheel:
            if ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier) and self._in_window(obj) \
                    and not owns_ctrl_wheel(obj):
                dy = ev.angleDelta().y()
                if dy:
                    self.step(1 if dy > 0 else -1)
                return True
        elif t == QEvent.NativeGesture and ev.gestureType() == Qt.ZoomNativeGesture:
            if self._in_window(obj) and not owns_ctrl_wheel(obj):
                self._pinch += float(ev.value())
                while abs(self._pinch) >= PINCH_STEP:
                    self.step(1 if self._pinch > 0 else -1)
                    self._pinch -= PINCH_STEP if self._pinch > 0 else -PINCH_STEP
                return True
        return False

    def _in_window(self, obj: Any) -> bool:
        try:
            return hasattr(obj, "window") and obj.window() is self.window
        except RuntimeError:
            return False
