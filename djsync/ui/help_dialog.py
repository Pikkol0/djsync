"""Aide (F1 ou bouton « Aide ») : raccourcis clavier et mode d'emploi rapide."""
from __future__ import annotations

from typing import Any, List, Tuple

import customtkinter as ctk

from .. import __version__
from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .icons import ctk_icon

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


class HelpDialog(BaseDialog):
    def __init__(self, parent: Any) -> None:
        super().__init__(parent, t("help.title"), 640, 600)
        self.footer(t("action.close"), self.close, show_cancel=False)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 6))
        ctk.CTkLabel(head, text="", image=ctk_icon("help", 24, theme.ACCENT)).pack(side="left")
        theme.label(head, t("help.title"), 16, theme.TEXT, "bold").pack(side="left", padx=(10, 0))
        theme.label(head, f"DJSync {__version__}", 11, theme.FAINT).pack(side="right")

        tabs = ctk.CTkTabview(self, fg_color=theme.SURFACE, segmented_button_fg_color=theme.ELEV,
                              segmented_button_selected_color=theme.ACCENT_DIM,
                              segmented_button_selected_hover_color=theme.BORDER,
                              segmented_button_unselected_color=theme.ELEV, text_color=theme.TEXT, corner_radius=8)
        tabs.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        sc = tabs.add(t("help.shortcuts"))
        guide = tabs.add(t("help.guide"))

        box = ctk.CTkScrollableFrame(sc, fg_color="transparent")
        box.pack(fill="both", expand=True)
        box.grid_columnconfigure(1, weight=1)
        for i, (keys, key) in enumerate(SHORTCUTS):
            pill = ctk.CTkLabel(box, text=t("help.key_space") if keys == "Space" else keys, fg_color=theme.ELEV,
                                corner_radius=6, text_color=theme.TEXT, font=theme.font(11, "bold"), height=26)
            pill.grid(row=i, column=0, sticky="w", padx=(6, 14), pady=4, ipadx=6)
            theme.label(box, t(key), 12, theme.DIM, anchor="w").grid(row=i, column=1, sticky="w")

        gbox = ctk.CTkScrollableFrame(guide, fg_color="transparent")
        gbox.pack(fill="both", expand=True)
        for key in TOPICS:
            theme.label(gbox, t(key + "_title"), 13, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=6, pady=(10, 2))
            theme.label(gbox, t(key), 11, theme.DIM, anchor="w", justify="left", wraplength=540).pack(fill="x", padx=6)
