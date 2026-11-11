"""Petits éléments d'interface Qt partagés (V0.3.0) : boutons, libellés, pastille Camelot.

Rien de décoratif : un bouton est un QPushButton stylé par la feuille de style du thème
(`kind` = primary / danger / flat / nav), un libellé un QLabel avec un `role` (title, dim…).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget

from . import theme
from .icons import qicon
from .table import Column, MenuEntry, Row, TrackTable, popup_menu  # noqa: F401 (ré-export)


def label(text: str = "", role: str = "", parent: Any = None, wrap: bool = False) -> QLabel:
    w = QLabel(text, parent)
    if role:
        w.setProperty("role", role)
    if wrap:
        w.setWordWrap(True)
    return w


def button(text: str, command: Optional[Callable[[], None]] = None, kind: str = "", parent: Any = None,
           icon: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(text.replace("&", "&&"), parent)       # « & » : pas de raccourci clavier Qt
    if kind:
        b.setProperty("kind", kind)
    if command is not None:
        b.clicked.connect(lambda _=False: command())
    if icon:
        color = {"primary": theme.ON_ACCENT, "danger": theme.ERR, "flat": theme.DIM}.get(kind, theme.TEXT)
        b.setIcon(qicon(icon, 16, color))
        b.setIconSize(QSize(theme.px(16), theme.px(16)))
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def icon_button(icon: str, command: Optional[Callable[[], None]] = None, tooltip: str = "", parent: Any = None,
                size: int = 16, color: str = "") -> QToolButton:
    b = QToolButton(parent)
    b.setIcon(qicon(icon, size, color or theme.TEXT))
    b.setIconSize(QSize(theme.px(size), theme.px(size)))
    if command is not None:
        b.clicked.connect(lambda _=False: command())
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def line_edit(placeholder: str = "", icon: str = "", big: bool = False, parent: Any = None) -> QLineEdit:
    """Champ de saisie, avec une icône à gauche (recherche, lien…) et un bouton d'effacement."""
    e = QLineEdit(parent)
    e.setPlaceholderText(placeholder)
    e.setClearButtonEnabled(True)
    if icon:
        e.addAction(qicon(icon, 16, theme.FAINT), QLineEdit.LeadingPosition)
    if big:
        e.setProperty("role", "big")
    return e


def chip(text: str, role: str = "chip") -> QLabel:
    """Petite étiquette arrondie (« 12 titres », « connectée »…)."""
    return label(text, role)


def icon_label(icon: str, size: int = 16, color: str = "") -> QLabel:
    w = QLabel()
    w.setPixmap(qicon(icon, size, color or theme.DIM).pixmap(QSize(theme.px(size), theme.px(size))))
    return w


def panel(parent: Any = None, role: str = "panel") -> QFrame:
    f = QFrame(parent)
    f.setProperty("role", role)
    return f


def hbox(parent: Any = None, margins: int = 0, spacing: int = 6) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return lay


def vbox(parent: Any = None, margins: int = 0, spacing: int = 6) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return lay


def restyle(w: QWidget) -> None:
    """Après un changement de propriété (role, kind) : la feuille de style est réappliquée."""
    w.style().unpolish(w)
    w.style().polish(w)


class CamelotPill(QLabel):
    """Tonalité en notation Camelot, sur fond de sa couleur (lecteur, doublons)."""

    def __init__(self, code: Optional[str] = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.set(code)

    def set(self, code: Optional[str]) -> None:
        if code:
            color = theme.camelot_color(code)
            self.setText(code)
            self.setStyleSheet(f"background:{color}; color:{theme.on_color(color)}; padding:0 {theme.px(5)}px;"
                               f"border-radius:{theme.px(3)}px; font-weight:600;")
            # 1.3.0 (B32) : jamais show() tant que la pastille n'est pas dans une page. Créée sans parent
            # (Doublons, Diagnostic) puis placée dans sa ligne, elle était un instant une vraie fenêtre de
            # 26x16 : sur Mac en plein écran, macOS lui créait un espace et affichait le bureau. Sans
            # parent, elle s'affiche d'elle-même une fois placée dans un layout (pas cachée exprès).
            if not self.isWindow():
                self.show()
        else:
            self.setText("")
            self.hide()


class _ClickFilter(QObject):
    """1.4.0-rc.4 (C153) : rend un cadre cliquable (clic gauche relâché dessus)."""

    def __init__(self, widget: Any, action: Any) -> None:
        super().__init__(widget)
        self._action = action

    def eventFilter(self, obj: Any, e: Any) -> bool:   # noqa: N802 (API Qt)
        from PySide6.QtCore import QEvent

        if e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton \
                and obj.rect().contains(e.position().toPoint()):
            self._action()
            return True
        return False


def clickable(widget: Any, action: Any) -> Any:
    """Le clic n'importe où sur le cadre lance l'action ; curseur main."""
    widget.installEventFilter(_ClickFilter(widget, action))
    widget.setCursor(Qt.PointingHandCursor)
    return widget


class FitBar(QWidget):
    """1.4.0-rc.5 (B85) : barre de boutons qui s'adapte à sa largeur, sans jamais couper un texte.

    Les boutons gardent leur largeur naturelle (jamais écrasés par Qt). Quand tout ne tient pas, par paliers :
    1) les boutons « secondaires » passent en icône seule (texte dans la bulle) ; 2) ils sortent de la barre
    (la vue les reprend dans son menu ☰ via `overflow`) ; 3) les boutons à texte restants passent aussi en
    icône seule. La barre elle-même n'impose aucune largeur minimale à la fenêtre."""

    def __init__(self, parent: Any = None, spacing: int = 6) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lay = hbox(self, spacing=spacing)
        self._items: list = []          # [(widget, secondaire ?, texte, bulle)]
        self.level = 0
        self._refit_pending = False

    def add(self, w: QWidget, secondary: bool = False) -> QWidget:
        from PySide6.QtWidgets import QSizePolicy

        w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        text = w.text() if isinstance(w, QPushButton) else ""
        self._items.append((w, secondary, text, w.toolTip()))
        self.lay.addWidget(w)
        return w

    def add_stretch(self) -> None:
        self.lay.addStretch(1)

    def set_text(self, w: QWidget, text: str) -> None:
        """Change le texte d'un bouton de la barre (le palier en cours est réappliqué)."""
        self._items = [(x, sec, text if x is w else txt, tip) for x, sec, txt, tip in self._items]
        self.fit()

    @property
    def overflow(self) -> list:
        """Boutons secondaires sortis de la barre (palier 2 et plus) et qui seraient visibles."""
        return [w for w, sec, _t, _b in self._items if sec and self.level >= 2 and not w.property("fitHidden")
                and w.property("fitWanted") is not False]

    def setVisibleItem(self, w: QWidget, on: bool) -> None:      # noqa: N802
        """À utiliser à la place de `setVisible` pour un bouton de la barre."""
        w.setProperty("fitWanted", bool(on))
        self.fit()

    def _apply(self, level: int) -> int:
        """Applique un palier ; renvoie la largeur nécessaire."""
        need, n = 0, 0
        for w, sec, text, tip in self._items:
            wanted = w.property("fitWanted") is not False
            show = wanted and not (sec and level >= 2)
            icon_only = (sec and level >= 1) or level >= 3
            if isinstance(w, QPushButton) and text:
                if icon_only and not w.icon().isNull():
                    w.setText("")
                    w.setToolTip(tip or text.replace("&&", "&"))
                else:
                    w.setText(text)
                    w.setToolTip(tip)
            w.setVisible(show)
            if show:
                hint = w.sizeHint().width()
                # largeur minimale explicite : la mise en page de Qt gardait parfois une taille d'avant le
                # changement de zoom ou de texte et écrasait le bouton (texte coupé)
                if w.minimumWidth() != w.maximumWidth():          # largeur fixe (barre de progression) : gardée
                    w.setMinimumWidth(hint)
                else:
                    hint = w.width() or hint
                need += hint
                n += 1
        return need + n * self.lay.spacing()          # n - 1 intervalles + celui de l'espace extensible

    def fit(self) -> None:
        avail = self.width()
        for level in range(4):
            if self._apply(level) <= avail or level == 3:
                self.level = level
                break
        self.lay.invalidate()

    def resizeEvent(self, e: Any) -> None:       # noqa: N802
        super().resizeEvent(e)
        self.fit()

    def event(self, e: Any) -> bool:
        """Zoom, police ou texte d'un bouton changés : le palier est recalculé (une fois, juste après)."""
        from PySide6.QtCore import QEvent, QTimer

        if e.type() in (QEvent.LayoutRequest, QEvent.StyleChange, QEvent.FontChange) and not self._refit_pending:
            self._refit_pending = True

            def refit() -> None:
                self._refit_pending = False
                try:
                    self.fit()
                except RuntimeError:            # barre détruite entre-temps
                    pass

            QTimer.singleShot(0, refit)
        return super().event(e)

    def sizeHint(self) -> QSize:                 # noqa: N802
        return QSize(0, max((w.sizeHint().height() for w, *_r in self._items), default=0))
