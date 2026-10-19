"""Vue Paramètres : clé active, dossier de destination, FFmpeg, recherche, sauvegardes."""
from __future__ import annotations

from tkinter import filedialog
from typing import Any, Dict

import customtkinter as ctk

from ...db import UsbDrive
from .. import theme
from .common import View

BACKUP_CHOICES = ["5", "10", "20", "50"]


class SettingsView(View):
    title = "Paramètres"

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._drives: Dict[str, UsbDrive] = {}
        self.grid_columnconfigure(0, weight=1)
        self.header("Paramètres").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        page = ctk.CTkScrollableFrame(self, fg_color="transparent")
        page.grid(row=1, column=0, sticky="nsew", padx=(14, 14))
        self.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        s = controller.settings

        # ---- clé USB
        card = self._card(page, "Clé USB Rekordbox", "Clés contenant PIONEER/rekordbox/exportLibrary.db (détection automatique).")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        self.drive_menu = theme.option_menu(row, ["—"], width=theme.px(320))
        self.drive_menu.pack(side="left")
        theme.button(row, "Actualiser", self.ctrl.refresh_drives, kind="ghost", width=theme.px(90)).pack(side="left", padx=8)
        self.connect_btn = theme.button(row, "Connecter", self._connect, kind="primary", width=theme.px(100))
        self.connect_btn.pack(side="left")
        theme.button(row, "Déconnecter", lambda: self.ctrl.disconnect(True), kind="ghost", width=theme.px(110)).pack(side="left", padx=8)
        self.drive_state = theme.label(card, "", 11, theme.DIM, anchor="w")
        self.drive_state.pack(fill="x", padx=18, pady=(0, 6))
        theme.label(card, "Lettre de lecteur forcée (optionnel, ex. E) :", 11, theme.DIM, anchor="w").pack(fill="x", padx=18)
        self.forced = theme.entry(card, "laisser vide = détection automatique", width=theme.px(260))
        self.forced.pack(anchor="w", padx=18, pady=(4, 16))
        self.forced.insert(0, s.forced_drive)

        # ---- dossier de destination
        card = self._card(page, "Dossier de destination", "Où les sons téléchargés sont rangés sur la clé (relatif à la racine, ex. Contents).")
        self.contents = theme.entry(card, "Contents", width=theme.px(260))
        self.contents.pack(anchor="w", padx=18, pady=(0, 16))
        self.contents.insert(0, s.contents_dir)

        # ---- FFmpeg
        card = self._card(page, "FFmpeg", "Dossier contenant ffmpeg(.exe). Vide = utiliser le PATH. Requis pour le téléchargement et la lecture m4a.")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18)
        self.ffmpeg = theme.entry(row, "ex. C:\\ffmpeg\\bin")
        self.ffmpeg.pack(side="left", fill="x", expand=True)
        self.ffmpeg.insert(0, s.ffmpeg_location)
        theme.button(row, "Parcourir…", self._browse_ffmpeg, kind="ghost", width=theme.px(100)).pack(side="left", padx=(8, 0))
        self.ffmpeg_state = theme.label(card, "", 11, theme.DIM, anchor="w")
        self.ffmpeg_state.pack(fill="x", padx=18, pady=(6, 16))
        self.ffmpeg.bind("<KeyRelease>", lambda _e: self._ffmpeg_status())

        # ---- recherche
        card = self._card(page, "Recherche", "")
        self.views_var = ctk.BooleanVar(value=s.fetch_views)
        theme.checkbox(card, "Charger le nombre de vues des Titres (requêtes supplémentaires en arrière-plan)",
                       variable=self.views_var).pack(anchor="w", padx=18, pady=(0, 16))

        # ---- sauvegardes
        card = self._card(page, "Sauvegardes de la base", "Avant chaque modification de exportLibrary.db, une copie est faite dans le dossier DJSync_Backups de la clé.")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 16))
        theme.label(row, "Copies automatiques conservées :", 12, theme.TEXT).pack(side="left")
        self.keep = theme.option_menu(row, BACKUP_CHOICES, width=theme.px(80))
        self.keep.set(str(s.backup_keep) if str(s.backup_keep) in BACKUP_CHOICES else "10")
        self.keep.pack(side="left", padx=10)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 16))
        theme.button(bottom, "Enregistrer", self._save, kind="primary", width=theme.px(130)).pack(side="right")
        self.saved = theme.label(bottom, "", 11, theme.ACCENT)
        self.saved.pack(side="right", padx=12)

        controller.on("drives", self._refresh_drives)
        controller.on("drive", self._refresh_drives)
        self._refresh_drives()
        self._ffmpeg_status()

    def _card(self, parent: Any, title: str, hint: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=8)
        card.pack(fill="x", padx=10, pady=(0, 12))
        theme.label(card, title, 13, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        if hint:
            theme.label(card, hint, 11, theme.DIM, anchor="w", justify="left", wraplength=theme.px(720)).pack(
                fill="x", padx=18, pady=(0, 10))
        else:
            ctk.CTkFrame(card, fg_color="transparent", height=6).pack()
        return card

    def on_show(self) -> None:
        self.ctrl.refresh_drives()

    # ------------------------------------------------------------------ clé
    def _refresh_drives(self) -> None:
        self._drives = {str(d): d for d in self.ctrl.drives}
        values = list(self._drives) or ["Aucune clé détectée"]
        self.drive_menu.configure(values=values)
        current = str(self.ctrl.drive) if self.ctrl.drive else None
        self.drive_menu.set(current if current in self._drives else values[0])
        self.connect_btn.configure(state="normal" if self._drives else "disabled")
        if self.ctrl.drive:
            self.drive_state.configure(text=f"Connectée : {self.ctrl.drive}", text_color=theme.ACCENT)
        else:
            self.drive_state.configure(text="Aucune clé connectée.", text_color=theme.WARN)

    def _connect(self) -> None:
        drive = self._drives.get(self.drive_menu.get())
        if drive is not None:
            self.ctrl.connect(drive)

    def _browse_ffmpeg(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Dossier contenant ffmpeg")
        if folder:
            self.ffmpeg.delete(0, "end")
            self.ffmpeg.insert(0, folder)
            self._ffmpeg_status()

    def _ffmpeg_status(self) -> None:
        text = self.ctrl.ffmpeg_status(self.ffmpeg.get().strip())
        self.ffmpeg_state.configure(text=text, text_color=theme.DIM if "trouvé" in text and "introuvable" not in text else theme.WARN)

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
        self.ctrl.apply_settings()
        if forced and changed_forced:
            self.ctrl.connect(forced, remember=False)
        self.saved.configure(text="✓ Enregistré")
        self.after(2500, lambda: self.saved.configure(text=""))
