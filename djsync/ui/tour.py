"""Visite guidée (1.4.2, C178, fusion de C122) : un projecteur éclaire chaque partie de la fenêtre, une bulle
explique à quoi elle sert.

* Proposée une seule fois au lancement (après l'accueil du premier lancement) : « Commencer la visite »,
  « Plus tard » (proposée de nouveau au lancement suivant), « Ne plus montrer ». Réglage `tour_state` :
  "" (jamais proposée), "later", "done" (faite ou passée), "never".
* Relancée à tout moment depuis Aide ▸ « Visite guidée ».
* Pendant la visite : Suivant, Précédent, Passer, et Échap. Rien n'est modifié : la visite ne fait que montrer.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..i18n import t
from . import theme
from .widgets import button, hbox, label, panel, vbox

OFFER_AT_START = True          # les tests le coupent (conftest) : aucune fenêtre de plus au démarrage

# (clé du texte, cible) ; la cible est trouvée dans la fenêtre au moment de l'étape (volet replié ou non)
STEPS: Tuple[Tuple[str, Callable[[Any], Optional[QWidget]]], ...] = (
    ("home", lambda w: w._nav.get("home")),
    ("search", lambda w: w._nav.get("search")),
    ("library", lambda w: w._nav.get("library")),
    ("downloads", lambda w: w._nav.get("downloads")),
    ("diagnostic", lambda w: w._nav.get("diagnostic")),
    ("settings", lambda w: w._nav.get("settings")),
    ("drive", lambda w: getattr(w, "usb_box", None)),
    ("player", lambda w: getattr(w, "player_bar", None)),
    ("help", lambda w: getattr(w, "help_btn", None)),
)


def should_offer(settings: Any) -> bool:
    return OFFER_AT_START and getattr(settings, "tour_state", "") in ("", "later")


class TourOverlay(QWidget):
    """Voile sombre sur toute la fenêtre, percé autour de la partie expliquée, et une bulle."""

    def __init__(self, win: Any, on_end: Optional[Callable[[bool], None]] = None) -> None:
        super().__init__(win)
        self.win, self.on_end = win, on_end
        self.index = 0
        self.hole = QRect()
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bubble = panel(self, role="panel")
        lay = vbox(self.bubble, margins=theme.px(14), spacing=theme.px(8))
        self.count = label("", "faint")
        lay.addWidget(self.count)
        self.title = label("", "h2")
        lay.addWidget(self.title)
        self.text = label("", wrap=True)
        self.text.setMinimumWidth(theme.px(300))
        self.text.setMaximumWidth(theme.px(360))
        lay.addWidget(self.text)
        row = hbox(spacing=theme.px(6))
        self.skip_btn = button(t("tour.skip"), self.skip, kind="flat")
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        self.prev_btn = button(t("tour.previous"), self.previous)
        row.addWidget(self.prev_btn)
        self.next_btn = button(t("tour.next"), self.next, kind="primary")
        row.addWidget(self.next_btn)
        lay.addLayout(row)
        self.steps: List[Tuple[str, Callable[[Any], Optional[QWidget]]]] = list(STEPS)
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._show_step()

    # ------------------------------------------------------------------ étapes
    def _target(self) -> Optional[QWidget]:
        try:
            w = self.steps[self.index][1](self.win)
        except Exception:  # noqa: BLE001
            return None
        return w if w is not None and w.isVisible() else None

    def _show_step(self) -> None:
        key = self.steps[self.index][0]
        n = len(self.steps)
        self.count.setText(t("tour.count", i=self.index + 1, n=n))
        self.title.setText(t(f"tour.{key}_title"))
        self.text.setText(t(f"tour.{key}"))
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setText(t("tour.finish") if self.index == n - 1 else t("tour.next"))
        self._place()

    def _place(self) -> None:
        self.setGeometry(self.win.rect())
        target = self._target()
        m = theme.px(6)
        if target is not None:
            top_left = target.mapTo(self.win, target.rect().topLeft())
            self.hole = QRect(top_left, target.size()).adjusted(-m, -m, m, m)
        else:
            self.hole = QRect()
        self.bubble.adjustSize()
        bw, bh = self.bubble.width(), self.bubble.height()
        r = self.rect()
        gap = theme.px(16)
        if self.hole.isNull():
            x, y = (r.width() - bw) // 2, (r.height() - bh) // 2
        elif self.hole.right() + gap + bw <= r.width():              # à droite (volet)
            x, y = self.hole.right() + gap, self.hole.center().y() - bh // 2
        elif self.hole.top() - gap - bh >= 0:                         # au-dessus (lecteur)
            x, y = self.hole.center().x() - bw // 2, self.hole.top() - gap - bh
        else:
            x, y = self.hole.center().x() - bw // 2, self.hole.bottom() + gap
        x = max(gap, min(x, r.width() - bw - gap))
        y = max(gap, min(y, r.height() - bh - gap))
        self.bubble.move(x, y)
        self.bubble.raise_()
        self.update()

    def next(self) -> None:
        if self.index >= len(self.steps) - 1:
            self._end(True)
            return
        self.index += 1
        self._show_step()

    def previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._show_step()

    def skip(self) -> None:
        self._end(False)

    def _end(self, finished: bool) -> None:
        try:
            self.win.removeEventFilter(self)
        except RuntimeError:
            pass
        self.hide()
        self.deleteLater()
        if self.win.__dict__.get("tour") is self:
            self.win.tour = None
        if self.on_end is not None:
            self.on_end(finished)

    # ------------------------------------------------------------------ Qt
    def paintEvent(self, _e: Any) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRect(self.rect())
        if not self.hole.isNull():
            hole = QPainterPath()
            hole.addRoundedRect(self.hole, theme.px(8), theme.px(8))
            path = path.subtracted(hole)
        p.fillPath(path, QColor(0, 0, 0, 170))
        if not self.hole.isNull():
            pen = p.pen()
            pen.setColor(QColor(theme.ACCENT))
            pen.setWidth(max(2, theme.px(2)))
            p.setPen(pen)
            p.drawRoundedRect(self.hole, theme.px(8), theme.px(8))
        p.end()

    def keyPressEvent(self, e: Any) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.skip()
        elif e.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.next()
        elif e.key() == Qt.Key_Left:
            self.previous()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e: Any) -> None:  # noqa: N802 - le voile bloque les clics (la visite montre seulement)
        e.accept()

    def eventFilter(self, obj: Any, e: Any) -> bool:  # noqa: N802
        if obj is self.win and e.type() in (QEvent.Resize, QEvent.LayoutRequest):
            self._place()
        return False


def start(win: Any) -> TourOverlay:
    """Lance la visite (Aide ▸ Visite guidée, ou « Commencer la visite »)."""
    old = win.__dict__.get("tour")
    if old is not None:
        try:
            old._end(False)
        except RuntimeError:
            pass
    if getattr(win, "current", None) != "home":
        win.show_view("home")

    def ended(_finished: bool) -> None:
        s = win.ctrl.settings
        if s.tour_state != "never":
            s.tour_state = "done"
            win.ctrl.save_settings_quiet()

    win.tour = TourOverlay(win, on_end=ended)
    return win.tour


def offer(win: Any) -> Any:
    """Fenêtre du lancement : Commencer la visite, Plus tard, Ne plus montrer."""
    from .dialogs import BaseDialog

    s = win.ctrl.settings
    dlg = BaseDialog(win, t("tour.offer_title"), 460)
    dlg.heading(t("tour.offer_title"))
    dlg.body.addWidget(label(t("tour.offer_text"), wrap=True))
    dlg.body.addStretch(1)

    def choose(state: str, go: bool = False) -> None:
        s.tour_state = state
        win.ctrl.save_settings_quiet()
        dlg.close()
        if go:
            start(win)

    row = hbox(spacing=theme.px(6))
    dlg.never_btn = button(t("tour.never"), lambda: choose("never"), kind="flat")
    row.addWidget(dlg.never_btn)
    row.addStretch(1)
    dlg.later_btn = button(t("tour.later"), lambda: choose("later"))
    row.addWidget(dlg.later_btn)
    dlg.start_btn = button(t("tour.start"), lambda: choose("done", go=True), kind="primary")
    dlg.start_btn.setDefault(True)
    row.addWidget(dlg.start_btn)
    dlg.body.addLayout(row)
    dlg.show_dialog()
    return dlg
