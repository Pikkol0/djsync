"""Petits éléments d'interface Qt partagés (V0.3.0) : boutons, libellés, pastille Camelot.

Rien de décoratif : un bouton est un QPushButton stylé par la feuille de style du thème
(`kind` = primary / danger / flat / nav), un libellé un QLabel avec un `role` (title, dim…).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QSize, Qt
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
