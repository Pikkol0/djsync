"""Diagnostic en onglets (1.3.1, C41/C43) : Un son (1.4.1, C140) · Fichiers introuvables · Doublons ·
Mauvaise qualité · Améliorer · Uniformiser.

1.4.1 (C140) : quand la largeur manque (zoom, fenêtre étroite), les onglets autres que celui ouvert ne gardent que
leur icône et leur compteur, nom dans la bulle ; jamais de texte coupé.

Chaque onglet reste l'outil existant (page de la fenêtre principale) ; la barre d'onglets, en haut de
chacun, passe de l'un à l'autre sans revenir à la vue d'origine (le bouton Retour y ramène). Le
nombre de sons concernés s'affiche quand il est connu (`controller.diag_counts`).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import QPushButton, QWidget

from ..i18n import t
from . import theme
from .widgets import hbox

# 1.4.0 (C47) : « Améliorer » ; 1.4.1 (C140, D19) : premier onglet « Un son » (sans compteur)
TABS = ("one", "missing", "dup", "quality", "improve", "uniformize")
ICONS = {"one": "search", "missing": "warn", "dup": "duplicates", "quality": "wave", "improve": "download", "uniformize": "tag"}


class DiagTabs(QWidget):
    """Barre d'onglets du Diagnostic, placée en haut de chaque page d'outil."""

    def __init__(self, page: Any, controller: Any, current: str) -> None:
        super().__init__(page)
        from .icons import qicon

        self.page, self.ctrl, self.current = page, controller, current
        row = hbox(self, spacing=theme.px(4))
        self.buttons: Dict[str, QPushButton] = {}
        for key in TABS:
            b = QPushButton()
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setProperty("kind", "tab")
            b.setIcon(qicon(ICONS[key], 16, theme.ACCENT if key == current else theme.DIM))
            b.clicked.connect(lambda _c=False, k=key: self._go(k))
            row.addWidget(b)
            self.buttons[key] = b
        row.addStretch(1)
        self.short = False
        self.shorts: set = set()
        self.refresh()
        controller.on("diag_counts", self.refresh)

    def refresh(self) -> None:
        try:
            counts = self.ctrl.diag_counts
        except Exception:  # noqa: BLE001
            counts = {}
        self._full: Dict[str, str] = {}
        for key, b in self.buttons.items():
            n = counts.get(key)
            self._full[key] = t(f"diagtab.{key}") + (f"  ({n})" if n is not None else "")
        try:
            self._apply()
        except RuntimeError:              # page détruite
            return

    def _text(self, key: str, short: bool) -> str:
        if not short or key == self.current:
            return self._full[key]
        n = self.ctrl.diag_counts.get(key) if hasattr(self.ctrl, "diag_counts") else None
        return f"{n}" if n is not None else ""

    def _width(self, b: QPushButton, text: str) -> int:
        old = b.text()
        b.setText(text)
        w = b.sizeHint().width()
        b.setText(old)
        return w

    def _apply(self) -> None:
        """Onglets raccourcis un à un, le plus long d'abord, juste assez pour tenir dans la largeur. La décision
        ne dépend que de la largeur : aucun aller-retour."""
        avail = self.width()
        shorts: set = set()
        if self.isVisible() and avail > 0:
            full = {k: self._width(b, self._text(k, False)) for k, b in self.buttons.items()}
            brief = {k: self._width(b, self._text(k, True)) for k, b in self.buttons.items()}
            total = sum(full.values()) + self.layout().spacing() * len(self.buttons)
            for k in sorted((k for k in self.buttons if k != self.current), key=lambda k: brief[k] - full[k]):
                if total <= avail:
                    break
                shorts.add(k)
                total -= full[k] - brief[k]
        self.short = bool(shorts)
        self.shorts = shorts
        for key, b in self.buttons.items():
            text = self._text(key, key in shorts)
            if b.text() != text:
                b.setText(text)
            b.setToolTip(self._full[key] if key in shorts else "")
            b.setMinimumWidth(b.sizeHint().width())               # jamais écrasé (texte coupé)

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(e)
        if getattr(self, "_full", None):
            self._apply()

    def showEvent(self, e: Any) -> None:  # noqa: N802
        super().showEvent(e)
        if getattr(self, "_full", None):
            self._apply()

    def _go(self, key: str) -> None:
        self.buttons[key].setChecked(key == self.current)
        if key == self.current:
            return
        self.buttons[key].setChecked(False)
        self.buttons[self.current].setChecked(True)
        app = self.page.window()
        if hasattr(app, "open_diagnostic"):
            app.open_diagnostic(key, from_page=self.page)


def add_tabs(dialog: Any, controller: Any, current: str) -> Optional[DiagTabs]:
    """Ajoute la barre en haut d'une page d'outil (seulement affichée comme page de la fenêtre)."""
    if getattr(dialog, "_host", None) is None:
        return None
    tabs = DiagTabs(dialog, controller, current)
    dialog.body.insertWidget(1, tabs)
    return tabs
