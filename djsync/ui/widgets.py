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


class ElidedLabel(QLabel):
    """1.4.1 (C140, socle du volet) : libellé sur une seule ligne, coupé par « … » quand la place manque
    (le texte entier reste dans `full_text`, et dans la bulle si aucune autre n'est donnée)."""

    def __init__(self, text: str = "", role: str = "", parent: Any = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QSizePolicy

        if role:
            self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.full_text = ""
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (API Qt)
        self.full_text = text or ""
        self._elide()

    def _elide(self) -> None:
        w = max(1, self.width())
        QLabel.setText(self, self.fontMetrics().elidedText(self.full_text, Qt.ElideRight, w))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(theme.px(20), super().minimumSizeHint().height())

    def resizeEvent(self, e: Any) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._elide()


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
    icône seule. La barre elle-même n'impose aucune largeur minimale à la fenêtre.

    1.4.0-rc.6 (B85) : décision stable. Les largeurs de chaque bouton (avec texte, en icône seule) sont mesurées
    une fois (puis à chaque changement de zoom, de police ou de texte) ; le palier ne dépend plus que de la
    largeur disponible. On ne revient à un palier plus large qu'avec une marge (`MARGIN`, hystérésis), et rien
    n'est retouché tant que le palier ne change pas : plus de boucle de mise en page (boutons qui clignotaient)."""

    MARGIN = 24            # px à 100 % : marge demandée pour revenir à un palier plus large

    def __init__(self, parent: Any = None, spacing: int = 6) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lay = hbox(self, spacing=spacing)
        self._items: list = []          # [(widget, secondaire ?, texte, bulle)]
        self.level = 0
        self._widths: Optional[list] = None      # [(largeur avec texte, en icône seule)], dans l'ordre de _items
        self._applied: Optional[int] = None      # palier réellement appliqué (None : décision à refaire)
        self.applies = 0                         # nombre d'applications (tests : aucune oscillation)
        self._refit_pending = False

    def add(self, w: QWidget, secondary: bool = False, keep_text: bool = False) -> QWidget:
        """`keep_text` : action principale dont le texte reste toujours écrit (ex. « Arrêter l'analyse »)."""
        from PySide6.QtWidgets import QSizePolicy

        w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        w.setProperty("fitKeepText", bool(keep_text))
        text = w.text() if isinstance(w, QPushButton) else ""
        self._items.append((w, secondary, text, w.toolTip()))
        self.lay.addWidget(w)
        self._invalidate()
        return w

    def add_stretch(self) -> None:
        self.lay.addStretch(1)

    def set_text(self, w: QWidget, text: str) -> None:
        """Change le texte d'un bouton de la barre (le palier en cours est réappliqué)."""
        if all(txt == text for x, _s, txt, _b in self._items if x is w):
            return                                   # inchangé : rien à remesurer
        self._items = [(x, sec, text if x is w else txt, tip) for x, sec, txt, tip in self._items]
        self._invalidate()
        self.fit()

    @property
    def overflow(self) -> list:
        """Boutons secondaires sortis de la barre (palier 2 et plus) et qui seraient visibles."""
        return [w for w, sec, _t, _b in self._items if sec and self.level >= 2 and not w.property("fitHidden")
                and w.property("fitWanted") is not False]

    def setVisibleItem(self, w: QWidget, on: bool) -> None:      # noqa: N802
        """À utiliser à la place de `setVisible` pour un bouton de la barre."""
        if w.property("fitWanted") is not None and bool(w.property("fitWanted")) == bool(on):
            return                                   # inchangé (appelé à chaque changement de sélection)
        w.setProperty("fitWanted", bool(on))
        self._applied = None
        self.fit()

    # ------------------------------------------------------------------ 1.4.0-rc.6 (B85) : mesures
    def _invalidate(self) -> None:
        self._widths = None
        self._applied = None

    @staticmethod
    def _natural(w: QWidget) -> int:
        if w.minimumWidth() == w.maximumWidth():          # largeur fixe (barre de progression)
            return w.minimumWidth()
        return w.sizeHint().width()

    @staticmethod
    def _can_shrink(w: QWidget, text: str) -> bool:
        return (isinstance(w, QPushButton) and bool(text) and not w.icon().isNull()
                and not w.property("fitKeepText"))

    def _measure(self) -> list:
        """Largeur naturelle de chaque bouton, avec son texte et en icône seule (texte remis ensuite)."""
        widths = []
        for w, _sec, text, _tip in self._items:
            if isinstance(w, QPushButton) and text:
                old = w.text()
                w.setText(text)
                full = icon = w.sizeHint().width()
                if self._can_shrink(w, text):
                    w.setText("")
                    icon = w.sizeHint().width()
                if w.text() != old:
                    w.setText(old)
            else:
                full = icon = self._natural(w)
            widths.append((full, icon))
        return widths

    def _icon_only(self, w: QWidget, sec: bool, text: str, level: int) -> bool:
        return ((sec and level >= 1) or level >= 3) and self._can_shrink(w, text)

    def _need(self, level: int) -> int:
        """Largeur nécessaire au palier `level` (calcul seul : aucun bouton n'est touché)."""
        need, n = 0, 0
        for (w, sec, text, _tip), (full, icon) in zip(self._items, self._widths or []):
            if w.property("fitWanted") is False or (sec and level >= 2):
                continue
            need += icon if self._icon_only(w, sec, text, level) else full
            n += 1
        return need + n * self.lay.spacing()          # n - 1 intervalles + celui de l'espace extensible

    def _choose(self, avail: int) -> int:
        fits = next((lv for lv in range(4) if self._need(lv) <= avail), 3)
        if self._applied is None or fits >= self.level:
            return fits                                   # première décision, ou il faut réduire : tout de suite
        margin = theme.px(self.MARGIN)                    # plus large : seulement avec de la marge (hystérésis)
        return next((lv for lv in range(fits, self.level) if self._need(lv) + margin <= avail), self.level)

    def _apply(self, level: int) -> None:
        for (w, sec, text, tip), (full, icon) in zip(self._items, self._widths or []):
            show = w.property("fitWanted") is not False and not (sec and level >= 2)
            if isinstance(w, QPushButton) and text:
                short = self._icon_only(w, sec, text, level)
                if w.text() != ("" if short else text):
                    w.setText("" if short else text)
                w.setToolTip((tip or text.replace("&&", "&")) if short else tip)
                # largeur minimale explicite : Qt n'écrase jamais un bouton (texte coupé)
                w.setMinimumWidth(icon if short else full)
            if w.isHidden() == show:
                w.setVisible(show)
        self.level = level
        self._applied = level
        self.applies += 1
        self.lay.invalidate()

    def _stale(self) -> bool:
        """Un bouton affiché n'a plus la largeur mesurée (zoom, police, feuille de style) : à remesurer."""
        for (w, sec, text, _tip), (full, icon) in zip(self._items, self._widths or []):
            if w.isHidden():
                continue
            short = self._applied is not None and self._icon_only(w, sec, text, self._applied)
            if self._natural(w) != (icon if short else full):
                return True
        return False

    def fit(self) -> None:
        if self._widths is None or len(self._widths) != len(self._items):
            self._widths = self._measure()
            self._applied = None
        avail = self.width()
        if not self.isVisible() or avail <= 0:          # pas encore placée : textes complets, refait à l'affichage
            if self._applied != 0:
                self._apply(0)
            self._applied = None                        # première décision à l'affichage, sans hystérésis
            return
        if self._applied is not None and self._stale():
            self._widths = self._measure()
            self._applied = None
        level = self._choose(avail)
        if level != self._applied:
            self._apply(level)

    def resizeEvent(self, e: Any) -> None:       # noqa: N802
        super().resizeEvent(e)
        self.fit()

    def event(self, e: Any) -> bool:
        """Zoom, police ou texte d'un bouton changés : le palier est recalculé (une fois, juste après).
        1.4.0-rc.6 (B85) : sans changement de mesure ni de largeur, ce calcul ne touche à rien (pas de boucle)."""
        from PySide6.QtCore import QEvent, QTimer

        if e.type() in (QEvent.StyleChange, QEvent.FontChange):
            self._invalidate()
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
