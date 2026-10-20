"""Vue Paramètres : apparence (langue, couleur + logo, zoom), clé, destination, FFmpeg, analyse,
export.pdb, recherche, sauvegardes.

Apparence : appliquée immédiatement (langue et couleur reconstruisent l'interface sans
redémarrer ; le zoom suit le curseur en direct). Le reste : bouton « Enregistrer ».
"""
from __future__ import annotations

from tkinter import filedialog
from typing import Any, Dict, Optional

import customtkinter as ctk

from ...db import UsbDrive
from ...i18n import LANGUAGES, t
from ...settings import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP
from .. import theme
from ..logo import logo_image
from .common import View

BACKUP_CHOICES = ["5", "10", "20", "50"]
KEY_NOTATIONS = ("auto", "camelot", "musical")
SIDEBAR_MODES = ("auto", "on", "off")


class SettingsView(View):
    SWATCH = 30

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._drives: Dict[str, UsbDrive] = {}
        self._zoom_after: Optional[str] = None
        self._swatches: Dict[str, Any] = {}
        self.grid_columnconfigure(0, weight=1)
        self.header(t("tab.settings")).grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        page = ctk.CTkScrollableFrame(self, fg_color="transparent")
        page.grid(row=1, column=0, sticky="nsew", padx=(14, 14))
        self.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        self.page = page
        s = controller.settings

        # ---- apparence
        card = self._card(page, t("settings.appearance"), t("settings.appearance_hint"))
        row = self._row(card)
        theme.label(row, t("settings.language"), 12, theme.TEXT, width=150, anchor="w").pack(side="left")
        self.lang_menu = theme.option_menu(row, list(LANGUAGES.values()), self._language_changed, width=160)
        self.lang_menu.set(LANGUAGES.get(s.language, "English"))
        self.lang_menu.pack(side="left")

        theme.label(card, t("settings.theme"), 12, theme.TEXT, anchor="w").pack(fill="x", padx=18, pady=(10, 4))
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 4))
        self._swatch_grid = grid
        self._build_swatches()
        self.theme_name = theme.label(card, t(f"theme.{theme.CURRENT_THEME}"), 11, theme.DIM, anchor="w")
        self.theme_name.pack(fill="x", padx=18, pady=(0, 6))

        row = self._row(card, pady=(8, 2))
        theme.label(row, t("settings.zoom"), 12, theme.TEXT, width=150, anchor="w").pack(side="left")
        self.zoom = theme.slider(row, from_=ZOOM_MIN, to=ZOOM_MAX, number_of_steps=(ZOOM_MAX - ZOOM_MIN) // ZOOM_STEP,
                                 width=240, command=self._zoom_moved)
        self.zoom.set(s.zoom)
        self.zoom.pack(side="left")
        self.zoom_val = theme.label(row, f"{s.zoom} %", 12, theme.ACCENT, width=60)
        self.zoom_val.pack(side="left", padx=8)
        theme.button(row, t("settings.zoom_reset"), lambda: self._set_zoom(100), kind="flat", width=80).pack(side="left")
        self.auto_var = ctk.BooleanVar(value=s.zoom_auto)
        theme.checkbox(card, t("settings.zoom_auto"), variable=self.auto_var, command=self._zoom_auto_changed).pack(
            anchor="w", padx=18, pady=(6, 2))
        theme.label(card, t("settings.zoom_hint"), 10, theme.FAINT, anchor="w", justify="left", wraplength=640).pack(
            fill="x", padx=18)
        row = self._row(card, pady=(10, 16))
        theme.label(row, t("settings.sidebar"), 12, theme.TEXT, width=150, anchor="w").pack(side="left")
        self._sidebar_labels = {m: t(f"settings.sidebar_{m}") for m in SIDEBAR_MODES}
        self.sidebar_menu = theme.option_menu(row, list(self._sidebar_labels.values()), self._sidebar_changed, width=220)
        self.sidebar_menu.set(self._sidebar_labels.get(s.sidebar_compact, self._sidebar_labels["auto"]))
        self.sidebar_menu.pack(side="left")

        # ---- clé USB
        card = self._card(page, t("settings.drive"), t("settings.drive_hint"))
        row = self._row(card)
        self.drive_menu = theme.option_menu(row, ["—"], width=300)
        self.drive_menu.pack(side="left")
        theme.button(row, t("action.refresh"), self.ctrl.refresh_drives, kind="ghost", width=90).pack(side="left", padx=8)
        self.connect_btn = theme.button(row, t("action.connect"), self._connect, kind="primary", width=100)
        self.connect_btn.pack(side="left")
        theme.button(row, t("action.disconnect"), lambda: self.ctrl.disconnect(True), kind="ghost", width=110).pack(
            side="left", padx=8)
        self.drive_state = theme.label(card, "", 11, theme.DIM, anchor="w")
        self.drive_state.pack(fill="x", padx=18, pady=(0, 6))
        theme.label(card, t("settings.forced_drive"), 11, theme.DIM, anchor="w").pack(fill="x", padx=18)
        self.forced = theme.entry(card, t("settings.forced_placeholder"), width=260)
        self.forced.pack(anchor="w", padx=18, pady=(4, 16))
        self.forced.insert(0, s.forced_drive)

        # ---- dossier de destination
        card = self._card(page, t("settings.destination"), t("settings.destination_hint"))
        self.contents = theme.entry(card, "Contents", width=260)
        self.contents.pack(anchor="w", padx=18, pady=(0, 16))
        self.contents.insert(0, s.contents_dir)

        # ---- FFmpeg
        card = self._card(page, "FFmpeg", t("settings.ffmpeg_hint"))
        row = self._row(card, pady=(0, 0))
        self.ffmpeg = theme.entry(row, t("settings.ffmpeg_placeholder"))
        self.ffmpeg.pack(side="left", fill="x", expand=True)
        self.ffmpeg.insert(0, s.ffmpeg_location)
        theme.button(row, t("action.browse"), self._browse_ffmpeg, kind="ghost", width=100).pack(side="left", padx=(8, 0))
        self.ffmpeg_state = theme.label(card, "", 11, theme.DIM, anchor="w")
        self.ffmpeg_state.pack(fill="x", padx=18, pady=(6, 16))
        self.ffmpeg.bind("<KeyRelease>", lambda _e: self._ffmpeg_status())

        # ---- analyse
        card = self._card(page, t("settings.analysis"), t("settings.analysis_hint"))
        self.analyze_var = ctk.BooleanVar(value=s.analyze_on_add)
        theme.checkbox(card, t("settings.analyze_on_add"), variable=self.analyze_var).pack(anchor="w", padx=18, pady=(0, 6))
        row = self._row(card, pady=(0, 6))
        theme.label(row, t("settings.key_notation"), 12, theme.TEXT, width=150, anchor="w").pack(side="left")
        self._notation_labels = {k: t(f"settings.notation_{k}") for k in KEY_NOTATIONS}
        self.notation = theme.option_menu(row, list(self._notation_labels.values()), width=260)
        self.notation.set(self._notation_labels.get(s.key_notation, self._notation_labels["auto"]))
        self.notation.pack(side="left")
        row = self._row(card, pady=(4, 16))
        theme.button(row, t("settings.analyse_now"), self._analyse_now, kind="ghost", width=200).pack(side="left")

        # ---- anciennes platines : export.pdb
        card = self._card(page, t("settings.pdb"), t("settings.pdb_hint"))
        self.pdb_var = ctk.BooleanVar(value=s.pdb_sync == "auto")
        theme.checkbox(card, t("settings.pdb_sync"), variable=self.pdb_var).pack(anchor="w", padx=18, pady=(0, 4))
        self.pdb_growth_var = ctk.BooleanVar(value=s.pdb_allow_growth)
        theme.checkbox(card, t("settings.pdb_growth"), variable=self.pdb_growth_var).pack(anchor="w", padx=18, pady=(0, 6))
        row = self._row(card, pady=(0, 4))
        theme.button(row, t("settings.check"), self._pdb_refresh, kind="ghost", width=90).pack(side="left")
        self.pdb_sync_btn = theme.button(row, t("settings.sync_now"), self.ctrl.pdb_sync_now, kind="primary", width=190)
        self.pdb_sync_btn.pack(side="left", padx=8)
        self.pdb_state = theme.label(card, "", 11, theme.DIM, anchor="w", justify="left", wraplength=640)
        self.pdb_state.pack(fill="x", padx=18, pady=(2, 16))

        # ---- recherche
        card = self._card(page, t("tab.search"), "")
        self.views_var = ctk.BooleanVar(value=s.fetch_views)
        theme.checkbox(card, t("settings.fetch_views"), variable=self.views_var).pack(anchor="w", padx=18, pady=(0, 16))

        # ---- sauvegardes
        card = self._card(page, t("settings.backups"), t("settings.backups_hint"))
        row = self._row(card, pady=(0, 16))
        theme.label(row, t("settings.backups_keep"), 12, theme.TEXT).pack(side="left")
        self.keep = theme.option_menu(row, BACKUP_CHOICES, width=80)
        self.keep.set(str(s.backup_keep) if str(s.backup_keep) in BACKUP_CHOICES else "10")
        self.keep.pack(side="left", padx=10)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 16))
        theme.button(bottom, t("action.save"), self._save, kind="primary", width=130).pack(side="right")
        self.saved = theme.label(bottom, "", 11, theme.ACCENT)
        self.saved.pack(side="right", padx=12)

        controller.on("drive", lambda: self.after(300, self._pdb_refresh))
        controller.on("drives", self._refresh_drives)
        controller.on("drive", self._refresh_drives)
        self._refresh_drives()
        self._ffmpeg_status()

    def _card(self, parent: Any, title: str, hint: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=8)
        card.pack(fill="x", padx=10, pady=(0, 12))
        theme.label(card, title, 13, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        if hint:
            lbl = theme.label(card, hint, 11, theme.DIM, anchor="w", justify="left", wraplength=640)
            lbl.pack(fill="x", padx=18, pady=(0, 10))
            card.bind("<Configure>", lambda e, w=lbl: w.configure(
                wraplength=max(200, e.width / max(theme.ui_factor() * theme._DPI, 0.1) - 40)), add="+")
        else:
            ctk.CTkFrame(card, fg_color="transparent", height=6).pack()
        return card

    @staticmethod
    def _row(card: Any, pady: Any = (0, 6)) -> ctk.CTkFrame:
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=pady)
        return row

    def on_show(self) -> None:
        self.ctrl.refresh_drives()

    # --------------------------------------------------------------- apparence
    def _build_swatches(self) -> None:
        """Une pastille par couleur, avec la variante du logo à cette couleur."""
        for w in self._swatch_grid.winfo_children():
            w.destroy()
        per_row = 10
        size = self.SWATCH
        for i, (name, accent) in enumerate(theme.PALETTES.items()):
            img = logo_image(size * 2, accent)
            image = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
            active = name == theme.CURRENT_THEME
            b = ctk.CTkButton(self._swatch_grid, text="", image=image, width=size + 10, height=size + 10, corner_radius=10,
                              fg_color=theme.ELEV if active else "transparent", hover_color=theme.ELEV,
                              border_width=2, border_color=accent if active else theme.SURFACE,
                              command=lambda n=name: self._theme_changed(n))
            b.grid(row=i // per_row, column=i % per_row, padx=2, pady=2)
            b.bind("<Enter>", lambda _e, n=name: self.theme_name.configure(text=t(f"theme.{n}")), add="+")
            b.bind("<Leave>", lambda _e: self.theme_name.configure(text=t(f"theme.{theme.CURRENT_THEME}")), add="+")
            self._swatches[name] = b

    def _language_changed(self, label: str) -> None:
        code = next((c for c, n in LANGUAGES.items() if n == label), "en")
        if code == self.ctrl.settings.language:
            return
        self.ctrl.settings.language = code
        self.ctrl.settings.save()
        self.after(20, lambda: self.ctrl._emit("rebuild_ui"))

    def _theme_changed(self, name: str) -> None:
        if name == self.ctrl.settings.theme:
            return
        self.ctrl.settings.theme = name
        self.ctrl.settings.save()
        self.after(20, lambda: self.ctrl._emit("rebuild_ui"))

    def _zoom_moved(self, value: float) -> None:
        z = int(round(float(value) / ZOOM_STEP) * ZOOM_STEP)
        self.zoom_val.configure(text=f"{z} %")
        if self._zoom_after:
            self.after_cancel(self._zoom_after)
        self._zoom_after = self.after(250, lambda: self._set_zoom(z))

    def _set_zoom(self, z: int) -> None:
        self._zoom_after = None
        self.zoom.set(z)
        self.zoom_val.configure(text=f"{z} %")
        if z != self.ctrl.settings.zoom:
            self.ctrl.settings.zoom = z
            self.ctrl.settings.save()
            self.ctrl._emit("zoom")

    def _zoom_auto_changed(self) -> None:
        self.ctrl.settings.zoom_auto = bool(self.auto_var.get())
        self.ctrl.settings.save()
        self.ctrl._emit("zoom")

    def _sidebar_changed(self, label: str) -> None:
        mode = next((m for m, text in self._sidebar_labels.items() if text == label), "auto")
        self.ctrl.settings.sidebar_compact = mode
        self.ctrl.settings.save()
        self.ctrl._emit("zoom")

    # ------------------------------------------------------------------ clé
    def _refresh_drives(self) -> None:
        self._drives = {str(d): d for d in self.ctrl.drives}
        values = list(self._drives) or [t("nav.no_drive")]
        self.drive_menu.configure(values=values)
        current = str(self.ctrl.drive) if self.ctrl.drive else None
        self.drive_menu.set(current if current in self._drives else values[0])
        self.connect_btn.configure(state="normal" if self._drives else "disabled")
        if self.ctrl.drive:
            self.drive_state.configure(text=t("settings.connected", drive=str(self.ctrl.drive)), text_color=theme.ACCENT)
        else:
            self.drive_state.configure(text=t("msg.no_drive_short"), text_color=theme.WARN)

    def _connect(self) -> None:
        drive = self._drives.get(self.drive_menu.get())
        if drive is not None:
            self.ctrl.connect(drive)

    def _pdb_refresh(self) -> None:
        if not self.winfo_exists():
            return
        if self.ctrl.library is None:
            self.pdb_state.configure(text=t("msg.no_drive_short"), text_color=theme.DIM)
            return
        self.ctrl.pdb_status(self._pdb_show)

    def _pdb_show(self, st: Any) -> None:
        if not self.winfo_exists():
            return
        text, color = {
            "off": (t("pdb.off"), theme.DIM),
            "absent": (t("pdb.absent"), theme.DIM),
            "ok": (t("pdb.ok", n=st.pdb_tracks), theme.ACCENT),
            "stale": (t("pdb.stale", tracks=st.missing_tracks, playlists=st.missing_playlists)
                      + (f"  [{st.detail}]" if st.detail else ""), theme.WARN),
            "unsupported": (t("pdb.unsupported", detail=st.detail), theme.WARN),
        }.get(st.state, (t("pdb.unknown"), theme.DIM))
        self.pdb_state.configure(text=text, text_color=color)
        self.pdb_sync_btn.configure(state="normal" if st.state == "stale" else "disabled")

    def _browse_ffmpeg(self) -> None:
        folder = filedialog.askdirectory(parent=self, title=t("settings.ffmpeg_browse_title"))
        if folder:
            self.ffmpeg.delete(0, "end")
            self.ffmpeg.insert(0, folder)
            self._ffmpeg_status()

    def _ffmpeg_status(self) -> None:
        found, text = self.ctrl.ffmpeg_status(self.ffmpeg.get().strip())
        self.ffmpeg_state.configure(text=text, text_color=theme.DIM if found else theme.WARN)

    def _analyse_now(self) -> None:
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        from ..analysis_dialog import AnalysisDialog

        AnalysisDialog(self, self.ctrl, None)

    # --------------------------------------------------------------- enregistrer
    def _save(self) -> None:
        s = self.ctrl.settings
        forced = self.forced.get().strip()
        changed_forced = forced != s.forced_drive
        s.forced_drive = forced
        s.contents_dir = self.contents.get().strip().strip("/\\") or "Contents"
        s.ffmpeg_location = self.ffmpeg.get().strip()
        s.fetch_views = bool(self.views_var.get())
        s.backup_keep = int(self.keep.get())
        s.pdb_sync = "auto" if self.pdb_var.get() else "off"
        s.pdb_allow_growth = bool(self.pdb_growth_var.get())
        s.analyze_on_add = bool(self.analyze_var.get())
        s.key_notation = next((k for k, v in self._notation_labels.items() if v == self.notation.get()), "auto")
        self.ctrl.apply_settings()
        if forced and changed_forced:
            self.ctrl.connect(forced, remember=False)
        self.saved.configure(text="✓ " + t("settings.saved"))
        self.after(2500, lambda: self.saved.winfo_exists() and self.saved.configure(text=""))
