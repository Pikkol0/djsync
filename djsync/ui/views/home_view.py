"""Vue Accueil : omnibar (chercher un son OU coller un lien) et aperçu des clés USB détectées.

Chaque carte de clé : nom, espace libre (barre de remplissage), contenu (sons, playlists, sons
non analysés), présence d'export.pdb (anciennes platines) et l'action utile (connecter, ouvrir
la bibliothèque, analyser).
"""
from __future__ import annotations

from typing import Any, List

import customtkinter as ctk

from ...i18n import plural, t
from .. import theme
from ..ctrl.library_ops import DriveSummary
from ..icons import ctk_icon
from .common import View, human_size


class HomeView(View):
    CARD_W = 300

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._summaries: List[DriveSummary] = []
        self._cols = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 0))
        top.grid_columnconfigure(0, weight=1)
        theme.label(top, t("home.title"), 22, theme.TEXT, "bold", anchor="w").grid(row=0, column=0, sticky="w")
        theme.label(top, t("home.subtitle"), 12, theme.DIM, anchor="w").grid(row=1, column=0, sticky="w", pady=(2, 14))

        omni = ctk.CTkFrame(top, fg_color=theme.SURFACE, corner_radius=12, border_width=1, border_color=theme.BORDER)
        omni.grid(row=2, column=0, sticky="ew")
        omni.grid_columnconfigure(1, weight=1)
        self.omni_icon = ctk.CTkLabel(omni, text="", image=ctk_icon("search", 20, theme.DIM))
        self.omni_icon.grid(row=0, column=0, padx=(14, 4), pady=8)
        self.omnibar = ctk.CTkEntry(
            omni, placeholder_text=t("home.omnibar"), fg_color="transparent", border_width=0, text_color=theme.TEXT,
            placeholder_text_color=theme.FAINT, height=40, font=theme.font(14))
        self.omnibar.grid(row=0, column=1, sticky="ew", pady=4)
        self.omnibar.bind("<Return>", lambda _e: self._go())
        self.omnibar.bind("<KeyRelease>", lambda _e: self._typed())
        self.go_btn = ctk.CTkButton(omni, text="", image=ctk_icon("go", 18, theme.ON_ACCENT), width=40, height=36,
                                    corner_radius=9, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                    command=self._go)
        self.go_btn.grid(row=0, column=2, padx=6)
        self.omni_hint = theme.label(top, t("home.omnibar_hint"), 10, theme.FAINT, anchor="w")
        self.omni_hint.grid(row=3, column=0, sticky="w", pady=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=(14, 14), pady=(14, 10))
        body.grid_columnconfigure(0, weight=1)
        self.body = body

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 8))
        theme.label(head, t("home.drives"), 14, theme.TEXT, "bold").pack(side="left")
        theme.button(head, t("action.refresh"), self.ctrl.refresh_drives, kind="flat", width=90).pack(side="right")
        self.cards = ctk.CTkFrame(body, fg_color="transparent")
        self.cards.grid(row=1, column=0, sticky="ew", padx=4)

        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.grid(row=2, column=0, sticky="ew", padx=10, pady=(18, 6))
        theme.label(tools, t("home.tools"), 14, theme.TEXT, "bold").pack(anchor="w", pady=(0, 8))
        row = ctk.CTkFrame(tools, fg_color="transparent")
        row.pack(fill="x")
        for icon, key, cmd in (("wave", "home.tool_analysis", self._analysis),
                               ("duplicates", "home.tool_duplicates", self._duplicates),
                               ("import", "home.tool_import", lambda: self.ctrl._emit("navigate", "import")),
                               ("help", "home.tool_help", self._help)):
            ctk.CTkButton(row, text=t(key), image=ctk_icon(icon, 18, theme.TEXT), compound="left", anchor="w",
                          height=40, corner_radius=10, fg_color=theme.SURFACE, hover_color=theme.ELEV,
                          text_color=theme.TEXT, font=theme.font(12), command=cmd).pack(
                side="left", padx=(0, 8), pady=4)

        controller.on("drives", self.refresh)
        controller.on("drive", self.refresh)
        controller.on("library", self.refresh)
        self.cards.bind("<Configure>", lambda _e: self._layout())

    # ------------------------------------------------------------------ omnibar
    def focus_omnibar(self) -> None:
        self.omnibar.focus_set()
        self.omnibar.select_range(0, "end")

    def _typed(self) -> None:
        url = self.ctrl.is_url(self.omnibar.get())
        self.omni_icon.configure(image=ctk_icon("import" if url else "search", 20, theme.ACCENT if url else theme.DIM))
        self.omni_hint.configure(text=t("home.omnibar_hint_url") if url else t("home.omnibar_hint"))

    def _go(self) -> None:
        text = self.omnibar.get().strip()
        if not text:
            return
        app = self.winfo_toplevel()
        if self.ctrl.is_url(text):
            app.show("import")
            app.views["import"].open_url(text)
        else:
            app.show("search")
            app.views["search"].search_for(text)

    # ------------------------------------------------------------------- clés
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.ctrl.drive_summaries(self._show)

    def _show(self, summaries: List[DriveSummary]) -> None:
        if not self.winfo_exists():
            return
        self._summaries = summaries
        self._cols = 0
        self._layout(force=True)

    def _layout(self, force: bool = False) -> None:
        width = max(1, self.cards.winfo_width()) / max(theme.ui_factor() * theme._DPI, 0.1)
        cols = max(1, min(3, int(width // (self.CARD_W + 16)) or 1))
        if cols == self._cols and not force:
            return
        self._cols = cols
        for w in self.cards.winfo_children():
            w.destroy()
        for c in range(3):
            self.cards.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="cards" if c < cols else "")
        if not self._summaries:
            self._empty_card()
            return
        for i, s in enumerate(self._summaries):
            self._card(s).grid(row=i // cols, column=i % cols, sticky="nsew", padx=6, pady=6)

    def _empty_card(self) -> None:
        box = ctk.CTkFrame(self.cards, fg_color=theme.SURFACE, corner_radius=12)
        box.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(box, text="", image=ctk_icon("usb", 40, theme.FAINT)).pack(pady=(22, 6))
        theme.label(box, t("home.no_drive_title"), 14, theme.DIM, "bold").pack()
        theme.label(box, t("home.no_drive_sub"), 11, theme.FAINT, justify="center", wraplength=460).pack(
            pady=(4, 22), padx=20)

    def _card(self, s: DriveSummary) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.cards, fg_color=theme.SURFACE, corner_radius=12,
                            border_width=1, border_color=theme.ACCENT if s.connected else theme.BORDER)
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="", image=ctk_icon("usb", 26, theme.ACCENT if s.connected else theme.DIM)).grid(
            row=0, column=0, rowspan=2, padx=(14, 10), pady=(14, 0), sticky="n")
        theme.label(card, s.drive.label or str(s.drive.root), 14, theme.TEXT, "bold", anchor="w").grid(
            row=0, column=1, sticky="ew", pady=(14, 0))
        state = t("home.connected") if s.connected else t("home.detected")
        root = str(s.drive.root)
        if len(root) > 34:
            root = "…" + root[-33:]
        theme.label(card, f"{root}  ·  {state}", 10, theme.ACCENT if s.connected else theme.DIM,
                    anchor="w").grid(row=1, column=1, sticky="ew", padx=(0, 12))

        if s.total:
            used = 1 - s.free / s.total
            bar = ctk.CTkProgressBar(card, height=6, corner_radius=3, fg_color=theme.BORDER,
                                     progress_color=theme.WARN if used > 0.9 else theme.ACCENT)
            bar.set(used)
            bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
            theme.label(card, t("nav.free_space", free=human_size(s.free), total=human_size(s.total)), 10, theme.DIM,
                        anchor="w").grid(row=3, column=0, columnspan=2, sticky="ew", padx=14)

        lines = []
        if s.tracks >= 0:
            lines.append(plural("lib.tracks_one", "lib.tracks_many", s.tracks) + "  ·  "
                         + plural("home.playlists_one", "home.playlists_many", s.playlists))
        lines.append(t("home.pdb_yes") if s.has_pdb else t("home.pdb_no"))
        theme.label(card, "\n".join(lines), 11, theme.TEXT, anchor="w", justify="left").grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 0))
        if s.unanalysed > 0:
            theme.label(card, plural("home.unanalysed_one", "home.unanalysed_many", s.unanalysed), 11, theme.WARN,
                        anchor="w").grid(row=5, column=0, columnspan=2, sticky="ew", padx=14)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=6, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 14))
        if s.connected:
            theme.button(actions, t("home.open_library"), lambda: self.ctrl._emit("navigate", "library"),
                         kind="primary", width=130).pack(side="left")
            if s.unanalysed > 0:
                theme.button(actions, t("action.analyse"), self._analysis, kind="ghost", width=90).pack(
                    side="left", padx=(8, 0))
        else:
            theme.button(actions, t("action.connect"), lambda d=s.drive: self.ctrl.connect(d), kind="primary",
                         width=110).pack(side="left")
        return card

    # ------------------------------------------------------------------- outils
    def _analysis(self) -> None:
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        self.ctrl._emit("show_unanalysed")      # V0.2.3 : Bibliothèque ▸ « À analyser »

    def _duplicates(self) -> None:
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        from ..duplicates_dialog import DuplicatesDialog

        DuplicatesDialog(self, self.ctrl)

    def _help(self) -> None:
        self.winfo_toplevel().open_help()
