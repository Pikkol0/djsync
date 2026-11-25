"""Petits éléments d'interface Qt partagés (V0.3.0) : boutons, libellés, pastille Camelot.

Rien de décoratif : un bouton est un QPushButton stylé par la feuille de style du thème
(`kind` = primary / danger / flat / nav), un libellé un QLabel avec un `role` (title, dim…).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QPlainTextEdit, QPushButton,
    QRadioButton, QSizePolicy, QToolButton, QTreeWidget, QVBoxLayout, QWidget,
)

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
        if not text.strip():
            b.setAccessibleName(tooltip)                  # 1.4.3 (A2-20) : nom lu par les lecteurs d'écran
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.TabFocus)                         # 1.4.3 (A2-19) : contour de focus au clavier seulement
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
        b.setAccessibleName(tooltip)                      # 1.4.3 (A2-20) : la bulle sert aussi de nom accessible
    b.setCursor(Qt.PointingHandCursor)
    return b


def name_icon_buttons(root: Any) -> int:
    """1.4.3 (A2-20) : tout bouton sans texte reçoit sa bulle comme nom accessible (boutons créés hors
    `icon_button`, bulles posées après coup). Renvoie le nombre de boutons nommés."""
    from PySide6.QtWidgets import QAbstractButton

    n = 0
    for b in root.findChildren(QAbstractButton):
        if not b.text().strip() and b.toolTip() and b.accessibleName() != b.toolTip():
            b.setAccessibleName(b.toolTip())
            n += 1
    return n


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

    def showEvent(self, e: Any) -> None:         # noqa: N802
        """1.4.2 (A2-3) : fenêtre redimensionnée pendant que la page était cachée : la barre reçoit sa
        nouvelle largeur avant d'être visible (palier remis à 0) et rien ne refaisait le calcul ensuite
        (boutons qui se chevauchaient à 860 px)."""
        super().showEvent(e)
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._refit_shown)

    def _refit_shown(self) -> None:
        try:
            self.fit()
        except RuntimeError:                    # barre détruite entre-temps
            pass

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


class FlowLayout(QLayout):
    """1.4.2 (C149) : éléments en ligne, qui passent à la ligne suivante quand la largeur manque (pastilles)."""

    def __init__(self, parent: Any = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: Any) -> None:  # noqa: N802 (API Qt)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> Any:  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> Any:  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Any:  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._place(0, 0, width, apply=False)

    def setGeometry(self, rect: Any) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._place(rect.x(), rect.y(), rect.width(), apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        return size

    def _place(self, x0: int, y0: int, width: int, apply: bool) -> int:
        from PySide6.QtCore import QPoint, QRect

        x, y, line = x0, y0, 0
        for item in self._items:
            if item.isEmpty():                  # 1.4.2 (A2-1) : élément masqué, sans place ni espacement
                continue
            hint = item.sizeHint()
            if x > x0 and x + hint.width() > x0 + width:
                x, y, line = x0, y + line + self._space, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._space
            line = max(line, hint.height())
        return y + line - y0


class RowTree(QTreeWidget):
    """1.4.3-rc.2 (B114) : arbre dont la ligne choisie est surlignée d'un seul tenant, zone de la flèche
    comprise (la feuille de style ne peut pas colorer cette zone sans effacer les flèches)."""

    def drawBranches(self, painter: Any, rect: Any, index: Any) -> None:  # noqa: N802
        from PySide6.QtGui import QColor

        model = self.selectionModel()
        if model is not None and model.isSelected(index):
            painter.fillRect(rect, QColor(theme.ACCENT_DIM))
        super().drawBranches(painter, rect, index)


class _WrapText:
    """1.4.2 (A2-1), 1.4.3-rc.2 (B119) : bouton à cocher (case ou bouton radio) dont le texte passe à la ligne
    quand la largeur manque, au lieu d'imposer sa largeur (ou d'être coupé)."""

    MIN_TEXT = 140          # px à 100 % : largeur minimale réservée au texte
    _CONTENTS = "SE_CheckBoxContents"
    _CONTROL = "CE_CheckBox"

    def _setup(self) -> None:
        from PySide6.QtWidgets import QSizePolicy

        pol = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)

    def _opt(self, width: int = 0) -> Any:
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QStyleOptionButton

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        if width:
            opt.rect = QRect(0, 0, width, max(self.height(), 1))
        return opt

    def _text_rect(self, width: int) -> Any:
        from PySide6.QtWidgets import QStyle

        return self.style().subElementRect(getattr(QStyle, self._CONTENTS), self._opt(width), self)

    def _indicator_width(self) -> int:
        return max(0, super().sizeHint().width() - self.fontMetrics().horizontalAdvance(self.text()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        base = super().minimumSizeHint()
        return QSize(self._indicator_width() + theme.px(self.MIN_TEXT), base.height())

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        from PySide6.QtCore import QRect

        rect = self._text_rect(width)
        tw = max(1, rect.width())
        text_h = self.fontMetrics().boundingRect(QRect(0, 0, tw, 100000), Qt.TextWordWrap, self.text()).height()
        return max(super().sizeHint().height(), text_h + 2)

    def paintEvent(self, _e: Any) -> None:  # noqa: N802
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QStyle, QStylePainter

        p = QStylePainter(self)
        opt = self._opt()
        text = opt.text
        opt.text = ""
        p.drawControl(getattr(QStyle, self._CONTROL), opt)
        rect = self.style().subElementRect(getattr(QStyle, self._CONTENTS), self._opt(), self)
        role = QPalette.WindowText
        p.drawItemText(rect, int(Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap), self.palette(),
                       self.isEnabled(), text, role)

    def hitButton(self, pos: Any) -> bool:  # noqa: N802
        return self.rect().contains(pos)


class WrapCheckBox(_WrapText, QCheckBox):
    """1.4.2 (A2-1) : case à cocher dont le texte passe à la ligne quand la largeur manque (une QCheckBox
    garde son texte sur une ligne et imposait sa largeur à toute la page des Paramètres). Même API que
    QCheckBox (text, isChecked, toggled…)."""

    def __init__(self, text: str = "", parent: Any = None) -> None:
        QCheckBox.__init__(self, text, parent)
        self._setup()


class WrapRadioButton(_WrapText, QRadioButton):
    """1.4.3-rc.2 (B119) : bouton radio dont le texte passe à la ligne (choix de la suppression d'une playlist)."""

    _CONTENTS = "SE_RadioButtonContents"
    _CONTROL = "CE_RadioButton"

    def __init__(self, text: str = "", parent: Any = None) -> None:
        QRadioButton.__init__(self, text, parent)
        self._setup()


def flow_row(*widgets: Any, spacing: int = 6) -> "FlowLayout":
    """1.4.2 (A2-1) : rangée de contrôles qui passe à la ligne quand la carte est trop étroite."""
    lay = FlowLayout(spacing=theme.px(spacing))
    for w in widgets:
        lay.addWidget(w)
    return lay


class ShrinkCombo(QComboBox):
    """1.4.2 (A2-1) : liste déroulante qui garde sa largeur naturelle quand la place le permet, mais peut
    rétrécir (texte choisi raccourci par Qt) au lieu d'imposer la largeur de son plus long choix à la page."""

    MIN = 120               # px à 100 %

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(super().minimumSizeHint().width(), theme.px(self.MIN)), super().minimumSizeHint().height())


class SideBar(QWidget):
    """1.4.2 (A2-4) : barre d'actions « à gauche … à droite » qui passe sur deux lignes (gauche au-dessus,
    droite en dessous, alignée à droite) quand la largeur manque, au lieu de couper les textes des boutons."""

    def __init__(self, parent: Any = None, spacing: int = 6) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QSizePolicy

        self.left, self.right = QWidget(), QWidget()
        self.left_lay = hbox(self.left, spacing=theme.px(spacing))
        self.right_lay = hbox(self.right, spacing=theme.px(spacing))
        lay = vbox(self, spacing=theme.px(4))
        self._top, self._bottom = hbox(spacing=0), hbox(spacing=0)
        lay.addLayout(self._top)
        lay.addLayout(self._bottom)
        self._top.addWidget(self.left)
        self._top.addStretch(1)
        self._top.addWidget(self.right)
        self._bottom.addStretch(1)
        self.two_lines = False
        lay.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def add_left(self, w: QWidget) -> QWidget:
        self.left_lay.addWidget(w)
        return w

    def add_right(self, w: QWidget) -> QWidget:
        self.right_lay.addWidget(w)
        return w

    def _need(self) -> int:
        return self.left.sizeHint().width() + self.right.sizeHint().width() + theme.px(16)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(max(self.left.sizeHint().width(), self.right.sizeHint().width()), super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802
        h = self.left.sizeHint().height()
        if self.two_lines:
            h += self.right.sizeHint().height() + theme.px(4)
        return QSize(self._need(), max(h, self.right.sizeHint().height()))

    def resizeEvent(self, e: Any) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._arrange()

    def showEvent(self, e: Any) -> None:  # noqa: N802
        super().showEvent(e)
        self._arrange()

    def _arrange(self) -> None:
        two = self.width() < self._need()
        if two == self.two_lines:
            return
        self.two_lines = two
        (self._top if two else self._bottom).removeWidget(self.right)
        if two:
            self._bottom.addWidget(self.right)
        else:
            self._top.addWidget(self.right)
        self.updateGeometry()


class ColumnsBox(QWidget):
    """1.4.2 (A2-17) : rangée de tuiles de même largeur qui passe sur 2 colonnes (puis 1) quand la largeur
    manque, au lieu de couper les textes ou de déborder (Accueil à 860 × 560)."""

    def __init__(self, parent: Any = None, spacing: int = 8) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout

        self._items: list = []
        self._cols = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(theme.px(spacing))

    def add(self, w: QWidget) -> QWidget:
        self._items.append(w)
        self._cols = 0
        self._arrange(self.width() or 10000)
        return w

    def _need(self, cols: int) -> int:
        """Largeur de la ligne la plus large avec `cols` colonnes (la grille ne descend pas sous le minimum)."""
        hints = [w.sizeHint().width() for w in self._items]
        rows = [hints[i:i + cols] for i in range(0, len(hints), cols)]
        return max((sum(r) + self.grid.spacing() * (len(r) - 1) for r in rows), default=0)

    def _arrange(self, width: int) -> None:
        n = len(self._items) or 1
        cols = n
        while cols > 1 and self._need(cols) > width:
            cols = max(1, cols // 2) if cols > 2 else 1
        if cols == self._cols:
            return
        self._cols = cols
        for w in self._items:
            self.grid.removeWidget(w)
        for i, w in enumerate(self._items):
            self.grid.addWidget(w, i // cols, i % cols)
        for c in range(n):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        widest = max((w.minimumSizeHint().width() for w in self._items), default=0)
        return QSize(widest, super().minimumSizeHint().height())

    def resizeEvent(self, e: Any) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._arrange(self.width())


class ShrinkLabel(QLabel):
    """1.4.2 (A2-1) : libellé sur une ligne quand la place le permet, à la ligne sinon (titre de carte) :
    largeur naturelle = son texte, largeur minimale réduite, hauteur selon la largeur."""

    MIN = 120

    def __init__(self, text: str, role: str = "") -> None:
        super().__init__(text)
        from PySide6.QtWidgets import QSizePolicy

        if role:
            self.setProperty("role", role)
        self.setWordWrap(True)
        pol = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)

    def sizeHint(self) -> QSize:  # noqa: N802
        one = self.fontMetrics().horizontalAdvance(self.text()) + 2 * self.margin() + 4
        return QSize(one, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(theme.px(self.MIN), self.sizeHint().width()), super().minimumSizeHint().height())


class LinkOrListEdit(QPlainTextEdit):
    """1.4.4 (C216) : champ « Lien ou playlist » qui accepte aussi une liste de sons, un par ligne.

    Un lien seul : Entrée lit le lien (comme un QLineEdit). Sinon Entrée passe à la ligne, le champ grandit
    jusqu'à `max_lines` lignes puis défile ; Ctrl+Entrée lance la recherche. Garde l'interface utile d'un
    QLineEdit (`text`, `setText`, `returnPressed`, `placeholderText`)."""

    returnPressed = Signal()
    contentChanged = Signal()

    def __init__(self, placeholder: str = "", is_link: Optional[Callable[[str], bool]] = None,
                 max_lines: int = 8, parent: Any = None) -> None:
        super().__init__(parent)
        self._is_link = is_link or (lambda s: s.lower().startswith(("http://", "https://")))
        self._max_lines = max_lines
        self.setPlaceholderText(placeholder)
        self.setProperty("role", "big")
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(theme.px(4))
        self.textChanged.connect(self._grow)
        self.textChanged.connect(self.contentChanged)
        self._grow()

    # -- interface de QLineEdit
    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        self.setPlainText(text or "")
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.setTextCursor(cur)

    # -- contenu
    def lines(self) -> list:
        """Lignes non vides (espaces retirés)."""
        return [ln.strip() for ln in self.toPlainText().splitlines() if ln.strip()]

    def is_link(self) -> bool:
        """Un seul lien (une ligne) : lecture du lien ; sinon liste de sons."""
        ls = self.lines()
        return len(ls) == 1 and bool(self._is_link(ls[0]))

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 (Qt)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            ctrl = bool(event.modifiers() & Qt.ControlModifier)
            shift = bool(event.modifiers() & Qt.ShiftModifier)
            if ctrl or (not shift and (not self.lines() or self.is_link())):
                self.returnPressed.emit()
                return
        super().keyPressEvent(event)

    def _line_height(self) -> int:
        return self.fontMetrics().lineSpacing()

    def _grow(self) -> None:
        n = max(1, min(self._max_lines, self.document().blockCount()))
        m = self.contentsMargins()
        pad = int(self.document().documentMargin() * 2) + m.top() + m.bottom() + theme.px(10)
        self.setFixedHeight(n * self._line_height() + pad)
