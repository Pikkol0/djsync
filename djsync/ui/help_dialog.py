"""Aide (F1 ou bouton « Aide ») : raccourcis clavier et mode d'emploi rapide."""
from __future__ import annotations

from typing import Any, List, Tuple

from PySide6.QtWidgets import QGridLayout, QScrollArea, QTabWidget, QWidget

from .. import __version__
from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .widgets import label, vbox

SHORTCUTS: List[Tuple[str, str]] = [
    ("Ctrl + K", "help.sc_omnibar"),
    ("Ctrl + 1 … 6", "help.sc_tabs"),
    ("Ctrl + F", "help.sc_filter"),
    ("Space", "help.sc_play"),
    ("Ctrl + →", "help.sc_next"),
    ("Ctrl + ←", "help.sc_previous"),
    ("Enter", "help.sc_enter"),
    ("Delete", "help.sc_delete"),
    ("Ctrl + A", "help.sc_select_all"),
    ("Ctrl + ,", "help.sc_settings"),
    ("F1", "help.sc_help"),
]
TOPICS = ["help.topic_search", "help.topic_library", "help.topic_analysis", "help.topic_grid",
          "help.topic_duplicates", "help.topic_harmonic", "help.topic_safety"]


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(inner)
    return area


class HelpDialog(BaseDialog):
    modal = False

    def __init__(self, parent: Any) -> None:
        super().__init__(parent, t("help.title"), 600, 540)
        self.heading(t("help.title"), f"DJSync {__version__}")
        tabs = QTabWidget()

        sc = QWidget()
        grid = QGridLayout(sc)
        grid.setHorizontalSpacing(theme.px(16))
        for i, (keys, key) in enumerate(SHORTCUTS):
            k = label(t("help.key_space") if keys == "Space" else keys, "accent")
            k.setStyleSheet("font-family: monospace;")
            grid.addWidget(k, i, 0)
            grid.addWidget(label(t(key), "dim"), i, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(len(SHORTCUTS), 1)
        tabs.addTab(_scroll(sc), t("help.shortcuts"))

        guide = QWidget()
        lay = vbox(guide, margins=theme.px(8), spacing=theme.px(4))
        for key in TOPICS:
            title = label(t(key + "_title"))
            title.setStyleSheet("font-weight:600;")
            lay.addSpacing(theme.px(6))
            lay.addWidget(title)
            lay.addWidget(label(t(key), "dim", wrap=True))
        lay.addStretch(1)
        tabs.addTab(_scroll(guide), t("help.guide"))

        self.body.addWidget(tabs, 1)
        self.footer(t("action.close"), self.close, show_cancel=False)
        self.show_dialog()
