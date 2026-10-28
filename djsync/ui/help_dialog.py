"""Aide (F1 ou bouton « Aide ») : raccourcis clavier et mode d'emploi rapide."""
from __future__ import annotations

from typing import Any, List, Tuple

from PySide6.QtWidgets import QGridLayout, QScrollArea, QTabWidget, QWidget

from .. import full_version
from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .widgets import label, vbox

SHORTCUTS: List[Tuple[str, str]] = [
    ("Ctrl + K", "help.sc_omnibar"),
    ("Ctrl + 1 … 7", "help.sc_tabs"),
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
          "help.topic_duplicates", "help.topic_diagnostic", "help.topic_harmonic", "help.topic_safety"]


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(inner)
    return area


class HelpDialog(BaseDialog):
    modal = False

    def __init__(self, parent: Any, start: bool = False) -> None:
        super().__init__(parent, t("help.title"), 720, 680)
        self.heading(t("help.title"), f"DJSync {full_version()}")
        tabs = QTabWidget()
        self.tabs = tabs

        first = QWidget()                                   # 1.3.2 (C68) : premiers pas + FAQ
        lay = vbox(first, margins=theme.px(8), spacing=theme.px(4))
        lay.addWidget(label(t("start.intro"), "dim", wrap=True))
        for k in range(1, 7):
            title = label(t(f"start.s{k}_title"))
            title.setStyleSheet("font-weight:600;")
            lay.addSpacing(theme.px(6))
            lay.addWidget(title)
            lay.addWidget(label(t(f"start.s{k}"), "dim", wrap=True))
        lay.addSpacing(theme.px(10))
        lay.addWidget(label(t("start.faq"), "h2"))
        for k in range(1, 6):
            lay.addWidget(label("• " + t(f"start.q{k}"), "dim", wrap=True))
        lay.addStretch(1)
        tabs.addTab(_scroll(first), t("start.tab"))

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

        tabs.setCurrentIndex(0 if start else 1)
        self.body.addWidget(tabs, 1)
        self.footer(t("action.close"), self.close, show_cancel=False, stretch=False)
        self.show_dialog()


class TextDialog(BaseDialog):
    """Texte long en lecture seule (licence, composants tiers) : 1.2.0-rc.4, C19."""
    modal = False

    def __init__(self, parent: Any, title: str, text: str) -> None:
        from PySide6.QtWidgets import QPlainTextEdit

        super().__init__(parent, title, 720, 620)
        self.heading(title)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        self.body.addWidget(view, 1)
        self.footer(t("action.close"), self.close, show_cancel=False, stretch=False)
        self.show_dialog()
