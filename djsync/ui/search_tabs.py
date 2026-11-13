"""« Rechercher » en onglets (1.4.2, C182, reste d'A06) : Recherche · Haute qualité · Lien ou playlist.

Les trois pages restent celles d'avant (D9 : une seule page Haute qualité) ; seule leur entrée change : une
entrée « Rechercher » dans le volet, et cette barre d'onglets en haut de chacune des trois pages.
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import QPushButton, QWidget

from ..i18n import t
from . import theme
from .widgets import hbox

TABS = ("search", "hq", "import")
LABELS = {"search": "searchtab.search", "hq": "searchtab.hq", "import": "searchtab.import"}
ICONS = {"search": "search", "hq": "gem", "import": "import"}


class SearchTabs(QWidget):
    def __init__(self, view: Any, current: str) -> None:
        super().__init__(view)
        from .icons import qicon

        self.view, self.current = view, current
        row = hbox(self, spacing=theme.px(4))
        self.buttons: Dict[str, QPushButton] = {}
        for key in TABS:
            b = QPushButton(t(LABELS[key]))
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setProperty("kind", "tab")
            b.setIcon(qicon(ICONS[key], 16, theme.ACCENT if key == current else theme.DIM))
            b.clicked.connect(lambda _c=False, k=key: self._go(k))
            b.setMinimumWidth(b.sizeHint().width())
            row.addWidget(b)
            self.buttons[key] = b
        row.addStretch(1)

    def _go(self, key: str) -> None:
        self.buttons[key].setChecked(key == self.current)
        if key == self.current:
            return
        query = ""
        entry = getattr(self.view, "entry", None)
        if entry is not None and key != "import":
            query = entry.text().strip()
        win = self.view.window()
        if hasattr(win, "show_view"):
            win.show_view(key)
            target = getattr(win, "views", {}).get(key)
            other = getattr(target, "entry", None)
            # le texte déjà tapé suit d'un onglet à l'autre, et la recherche part (comme l'ancien menu de mode)
            if query and other is not None and not other.text().strip() and key != "import":
                if hasattr(target, "search_for"):
                    target.search_for(query)
                else:
                    other.setText(query)


def add_search_tabs(view: Any, current: str) -> SearchTabs:
    """Titre « Rechercher » puis la barre d'onglets, en haut de la page."""
    from .widgets import label

    view.root.addWidget(label(t("nav.find"), "title"))
    tabs = SearchTabs(view, current)
    view.root.addWidget(tabs)
    view.search_tabs = tabs
    return tabs
