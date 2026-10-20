"""Fenêtre principale : barre latérale fixe (5 onglets), zone de contenu, barre d'état, lecteur."""
from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

import customtkinter as ctk

from .. import i18n
from ..settings import Settings
from . import theme
from .controller import AppController
from .covers import CoverLoader
from .player_bar import PlayerBar
from .runner import UiDispatcher
from .views.common import View
from .views.downloads_view import DownloadsView
from .views.import_view import ImportView
from .views.library_view import LibraryView
from .views.search_view import SearchView
from .views.settings_view import SettingsView

log = logging.getLogger(__name__)

SIDEBAR_WIDTH = 224
TABS = [  # (clé, libellé, classe)
    ("search", "Recherche", SearchView),
    ("import", "Import URL", ImportView),
    ("library", "Bibliothèque", LibraryView),
    ("downloads", "Téléchargements récents", DownloadsView),
    ("settings", "Paramètres", SettingsView),
]


def status_color(kind: str) -> str:
    """Couleur d'un message d'état (lue à l'appel : dépend du thème actif)."""
    return {"info": theme.DIM, "ok": theme.ACCENT, "warn": theme.WARN, "error": theme.ERR}.get(kind, theme.DIM)


class DJSyncApp(ctk.CTk):
    def __init__(self, settings: Optional[Settings] = None, controller: Optional[AppController] = None) -> None:
        settings = settings or Settings.load()
        # Langue, couleur et zoom DOIVENT être appliqués avant la création du moindre widget.
        i18n.set_language(settings.language)
        theme.apply_palette(settings.theme)
        theme.set_zoom(settings.zoom)
        super().__init__(fg_color=theme.BG)
        ctk.set_appearance_mode("dark")
        try:
            theme.set_scale(self._get_window_scaling())
        except Exception:  # noqa: BLE001 - ancienne/nouvelle version de customtkinter
            theme.set_scale(1.0)
        theme.apply_ttk_style(self)

        self.title("DJSync")
        self.minsize(theme.px(1020), theme.px(640))
        self.geometry(settings.geometry or f"{theme.px(1240)}x{theme.px(780)}")

        self.dispatcher = UiDispatcher(self)
        self.ctrl = controller or AppController(settings, self.dispatcher)
        self.loader = CoverLoader(self.dispatcher)
        self._status_after: Optional[str] = None
        self._current: Optional[str] = None
        self._nav: Dict[str, ctk.CTkButton] = {}
        self.views: Dict[str, View] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        for key, _label, cls in TABS:
            view = cls(self.content, self.ctrl, self.loader)
            view.grid(row=0, column=0, sticky="nsew")
            self.views[key] = view

        self.status = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.status.grid(row=1, column=1, sticky="ew", padx=24, pady=(0, 4))
        self.player_bar = PlayerBar(self, self.ctrl, self.loader)
        self.player_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.ctrl.on("message", self._message)
        self.ctrl.on("navigate", self.show)
        self.ctrl.on("drive", self._drive_changed)
        self.ctrl.on("drives", self._drive_changed)
        self.ctrl.on("downloads", self._badge)
        self.ctrl.on("download_update", lambda _j: self._badge())
        self.ctrl.on("library", self._library_changed)
        for i, (key, *_rest) in enumerate(TABS, start=1):
            self.bind(f"<Control-Key-{i}>", lambda _e, k=key: self.show(k))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.show("search")
        self._drive_changed()
        self.after(150, self.ctrl.startup)

    # -------------------------------------------------------------- barre latérale
    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, width=theme.px(SIDEBAR_WIDTH))
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(10, weight=1)

        logo = ctk.CTkFrame(bar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="w", padx=20, pady=(22, 22))
        theme.label(logo, "●", 14, theme.ACCENT).pack(side="left")
        theme.label(logo, " DJSync", 18, theme.TEXT, "bold").pack(side="left")

        for i, (key, label, _cls) in enumerate(TABS, start=1):
            btn = ctk.CTkButton(
                bar, text=label, anchor="w", height=theme.px(38), corner_radius=6, fg_color="transparent",
                hover_color=theme.ELEV, text_color=theme.DIM, font=theme.font(13),
                command=lambda k=key: self.show(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=12, pady=2)
            self._nav[key] = btn

        usb = ctk.CTkFrame(bar, fg_color=theme.ELEV, corner_radius=8)
        usb.grid(row=11, column=0, sticky="ew", padx=12, pady=14)
        theme.label(usb, "CLÉ ACTIVE", 9, theme.FAINT, "bold", anchor="w").pack(fill="x", padx=12, pady=(10, 0))
        self.usb_label = theme.label(usb, "", 11, theme.TEXT, anchor="w", justify="left", wraplength=theme.px(180))
        self.usb_label.pack(fill="x", padx=12, pady=(2, 10))

    def show(self, key: str) -> None:
        if key not in self.views:
            return
        self._current = key
        for k, btn in self._nav.items():
            active = k == key
            btn.configure(fg_color=theme.ACCENT_DIM if active else "transparent",
                          text_color=theme.ACCENT if active else theme.DIM)
        self.views[key].tkraise()
        self.views[key].on_show()
        self._badge()

    def _badge(self) -> None:
        n = self.ctrl.active_jobs
        label = dict((k, l) for k, l, _c in TABS)["downloads"]
        self._nav["downloads"].configure(text=f"{label}  ({n})" if n else label)

    def _drive_changed(self) -> None:
        if self.ctrl.drive:
            self.usb_label.configure(text=str(self.ctrl.drive), text_color=theme.ACCENT)
        elif self.ctrl.drives:
            self.usb_label.configure(text="Clé détectée, non connectée", text_color=theme.WARN)
        else:
            self.usb_label.configure(text="Aucune clé détectée", text_color=theme.DIM)
        search = self.views.get("search")
        if search is not None:
            search.refresh_duplicates()

    def _library_changed(self) -> None:
        search = self.views.get("search")
        if search is not None:
            search.refresh_duplicates()

    # ------------------------------------------------------------------- état
    def _message(self, kind: str, text: str) -> None:
        self.status.configure(text=text, text_color=status_color(kind))
        if self._status_after:
            self.after_cancel(self._status_after)
        delay = 12000 if kind in ("error", "warn") else 6000
        self._status_after = self.after(delay, lambda: self.status.configure(text=""))

    def _close(self) -> None:
        try:
            self.ctrl.settings.geometry = self.geometry().split("+")[0] if self.state() == "zoomed" else self.geometry()
        except Exception:  # noqa: BLE001
            pass
        self.ctrl.shutdown()
        self.destroy()


def main() -> None:
    from .. import portable
    portable.prepare_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = DJSyncApp()
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
