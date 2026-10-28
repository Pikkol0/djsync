"""Diagnostic en onglets (1.3.1, C41/C43) : Fichiers introuvables · Doublons · Mauvaise qualité · Uniformiser.

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

TABS = ("missing", "dup", "quality", "uniformize")
ICONS = {"missing": "warn", "dup": "duplicates", "quality": "wave", "uniformize": "tag"}


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
        self.refresh()
        controller.on("diag_counts", self.refresh)

    def refresh(self) -> None:
        try:
            counts = self.ctrl.diag_counts
        except Exception:  # noqa: BLE001
            counts = {}
        for key, b in self.buttons.items():
            try:
                n = counts.get(key)
                b.setText(t(f"diagtab.{key}") + (f"  ({n})" if n is not None else ""))
            except RuntimeError:              # page détruite
                return

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
