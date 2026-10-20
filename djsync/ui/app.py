"""Fenêtre principale (V0.2.0) : barre latérale (repliable), zone de contenu, barre d'état, lecteur.

Onglets, dans cet ordre : Accueil, Recherche, Bibliothèque, Téléchargements récents, Import URL,
Paramètres. Toute l'interface suit :
  * l'échelle (zoom des Paramètres x taille de la fenêtre), appliquée à chaud (theme.update_auto) ;
  * la langue et la couleur d'accent : `rebuild_ui()` reconstruit les vues sans redémarrer.
"""
from __future__ import annotations

import logging
import shutil
import sys
from typing import Any, Dict, Optional

import customtkinter as ctk

from .. import i18n
from ..i18n import t
from ..settings import Settings
from . import theme
from .controller import AppController
from .covers import CoverLoader
from .icons import ctk_icon, reset_icons
from .logo import LogoCanvas, logo_image
from .player_bar import PlayerBar
from .runner import UiDispatcher
from .views.common import View, human_size
from .views.downloads_view import DownloadsView
from .views.home_view import HomeView
from .views.import_view import ImportView
from .views.library_view import LibraryView
from .views.search_view import SearchView
from .views.settings_view import SettingsView

log = logging.getLogger(__name__)

SIDEBAR_WIDTH = 216
SIDEBAR_COMPACT = 64
COMPACT_BELOW = 1000            # largeur logique sous laquelle la barre latérale passe en icônes
MIN_W, MIN_H = 760, 500         # fenêtre minimale (pixels logiques) : utilisable en petit
TABS = [  # (clé, clé i18n, icône, classe)
    ("home", "tab.home", "home", HomeView),
    ("search", "tab.search", "search", SearchView),
    ("library", "tab.library", "library", LibraryView),
    ("downloads", "tab.downloads", "downloads", DownloadsView),
    ("import", "tab.import", "import", ImportView),
    ("settings", "tab.settings", "settings", SettingsView),
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
        super().__init__(fg_color=theme.BG)
        theme.reset_fonts()                 # polices et icônes partagées : liées à CETTE fenêtre racine
        reset_icons()
        ctk.set_appearance_mode("dark")
        try:
            theme.set_scale(self._get_window_scaling())
        except Exception:  # noqa: BLE001 - ancienne/nouvelle version de customtkinter
            theme.set_scale(1.0)
        theme.set_zoom(settings.zoom, settings.zoom_auto)
        theme.apply_ttk_style(self)

        self.title("DJSync")
        self.minsize(MIN_W, MIN_H)
        self.geometry(settings.geometry or "1240x780")
        self._set_window_icon()

        self.dispatcher = UiDispatcher(self)
        self.ctrl = controller or AppController(settings, self.dispatcher)
        self.loader = CoverLoader(self.dispatcher)
        self._status_after: Optional[str] = None
        self._resize_after: Optional[str] = None
        self._current: Optional[str] = None
        self._compact: Optional[bool] = None
        self._nav: Dict[str, ctk.CTkButton] = {}
        self.views: Dict[str, View] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # écouteurs de la FENÊTRE d'abord : ceux des vues (ajoutés ensuite) sont oubliés à chaque
        # reconstruction de l'interface (langue, couleur)
        self.ctrl.on("message", self._message)
        self.ctrl.on("navigate", self.show)
        self.ctrl.on("drive", self._drive_changed)
        self.ctrl.on("drives", self._drive_changed)
        self.ctrl.on("downloads", self._badge)
        self.ctrl.on("download_update", lambda _j: self._badge())
        self.ctrl.on("library", self._library_changed)
        self.ctrl.on("rebuild_ui", self.rebuild_ui)
        self.ctrl.on("zoom", self._apply_zoom)
        self._listener_mark = self.ctrl.listener_mark()
        self._build()
        self._bind_shortcuts()
        self.bind("<Configure>", self._on_configure, add="+")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.show("home")
        self._drive_changed()
        self.after(150, self.ctrl.startup)

    # ------------------------------------------------------------------ construction
    def _set_window_icon(self) -> None:
        try:
            from PIL import ImageTk

            self._icon_img = ImageTk.PhotoImage(logo_image(64, theme.ACCENT))
            self.iconphoto(True, self._icon_img)
        except Exception:  # noqa: BLE001 - icône facultative (certains gestionnaires de fenêtres)
            pass

    def _build(self) -> None:
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.views = {}
        for key, _label, _icon, cls in TABS:
            view = cls(self.content, self.ctrl, self.loader)
            view.grid(row=0, column=0, sticky="nsew")
            self.views[key] = view
        self.status = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.status.grid(row=1, column=1, sticky="ew", padx=24, pady=(0, 4))
        self.player_bar = PlayerBar(self, self.ctrl, self.loader)
        self.player_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._compact = None
        self._update_compact()

    def rebuild_ui(self) -> None:
        """Reconstruit toute l'interface (changement de langue ou de couleur), sans redémarrer.
        La clé, la file de téléchargements et la lecture en cours sont conservées (contrôleur)."""
        current = self._current or "home"
        i18n.set_language(self.ctrl.settings.language)
        theme.apply_palette(self.ctrl.settings.theme)
        theme.apply_ttk_style(self)
        self.configure(fg_color=theme.BG)
        self.ctrl.reset_listeners(self._listener_mark)
        for w in (self.sidebar, self.content, self.status, self.player_bar):
            w.destroy()
        self.loader.clear()
        self._nav = {}
        self._set_window_icon()
        self._build()
        self.show(current)
        self._drive_changed()
        self._badge()

    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, width=SIDEBAR_WIDTH)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(20, weight=1)
        bar.grid_columnconfigure(0, weight=1)
        self.sidebar = bar

        head = ctk.CTkFrame(bar, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(18, 18))
        self.logo = LogoCanvas(head, theme.tkpx(30), theme.ACCENT, theme.SURFACE, theme.ELEV)
        self.logo.pack(side="left")
        self.logo_text = theme.label(head, "DJSync", 18, theme.TEXT, "bold")
        self.logo_text.pack(side="left", padx=(10, 0))

        for i, (key, label, icon_name, _cls) in enumerate(TABS, start=1):
            btn = ctk.CTkButton(
                bar, text=t(label), anchor="w", height=38, corner_radius=8, fg_color="transparent",
                hover_color=theme.ELEV, text_color=theme.DIM, font=theme.font(13),
                image=ctk_icon(icon_name, 18, theme.DIM), compound="left",
                command=lambda k=key: self.show(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=10, pady=2)
            btn._icon_name = icon_name  # type: ignore[attr-defined]
            self._nav[key] = btn

        # ---- clé active + remplissage (point 13)
        usb = ctk.CTkFrame(bar, fg_color=theme.ELEV, corner_radius=10)
        usb.grid(row=21, column=0, sticky="ew", padx=10, pady=(10, 6))
        self.usb_box = usb
        self.usb_title = theme.label(usb, t("nav.active_drive"), 10, theme.FAINT, "bold", anchor="w")
        self.usb_title.pack(fill="x", padx=12, pady=(10, 0))
        self.usb_label = theme.label(usb, "", 11, theme.TEXT, anchor="w", justify="left", wraplength=170)
        self.usb_label.pack(fill="x", padx=12, pady=(2, 4))
        self.usb_bar = ctk.CTkProgressBar(usb, height=6, corner_radius=3, fg_color=theme.BORDER,
                                          progress_color=theme.ACCENT)
        self.usb_bar.set(0)
        self.usb_free = theme.label(usb, "", 10, theme.DIM, anchor="w")
        self.usb_compact = ctk.CTkLabel(usb, text="", image=ctk_icon("usb", 18, theme.DIM))

        foot = ctk.CTkFrame(bar, fg_color="transparent")
        foot.grid(row=22, column=0, sticky="ew", padx=10, pady=(0, 12))
        self.help_btn = ctk.CTkButton(
            foot, text=t("help.button"), anchor="w", height=32, corner_radius=8, fg_color="transparent",
            hover_color=theme.ELEV, text_color=theme.DIM, font=theme.font(12),
            image=ctk_icon("help", 16, theme.DIM), compound="left", command=self.open_help)
        self.help_btn.pack(fill="x")

    # --------------------------------------------------------------- barre repliable
    def _logical_width(self) -> float:
        return self.winfo_width() / max(theme._DPI, 0.5)

    def _update_compact(self) -> None:
        width = self._logical_width() if self.winfo_ismapped() else 1240
        mode = self.ctrl.settings.sidebar_compact
        compact = mode == "on" or (mode == "auto" and width < COMPACT_BELOW)
        if compact == self._compact:
            return
        self._compact = compact
        self.sidebar.configure(width=SIDEBAR_COMPACT if compact else SIDEBAR_WIDTH)
        for key, btn in self._nav.items():
            label = dict((k, l) for k, l, *_ in TABS)[key]
            btn.configure(text="" if compact else self._nav_text(key, label), anchor="center" if compact else "w")
        self.logo_text.pack_forget() if compact else self.logo_text.pack(side="left", padx=(10, 0))
        self.help_btn.configure(text="" if compact else t("help.button"), anchor="center" if compact else "w")
        for w in (self.usb_title, self.usb_label, self.usb_bar, self.usb_free, self.usb_compact):
            w.pack_forget()
        if compact:
            self.usb_compact.pack(pady=8)
        else:
            self.usb_title.pack(fill="x", padx=12, pady=(10, 0))
            self.usb_label.pack(fill="x", padx=12, pady=(2, 4))
            self._drive_changed()

    def _on_configure(self, e: Any) -> None:
        if e.widget is not self:
            return
        if self._resize_after:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(220, self._resized)

    def _resized(self) -> None:
        self._resize_after = None
        self._update_compact()
        if theme.update_auto(self.winfo_width(), self.winfo_height(), self):
            self._after_scale()

    def _apply_zoom(self) -> None:
        s = self.ctrl.settings
        theme.set_zoom(s.zoom, s.zoom_auto)
        theme.update_auto(self.winfo_width(), self.winfo_height())
        theme.apply_ttk_style(self)
        self._after_scale()

    def _after_scale(self) -> None:
        """Tk brut (images, colonnes) : recalcul après un changement d'échelle."""
        self.logo.configure_logo(size=theme.tkpx(30))
        self.loader.clear()
        for view in self.views.values():
            view.on_scale()
        self.player_bar.on_scale()
        self._compact = None
        self._update_compact()

    # --------------------------------------------------------------------- navigation
    def _nav_text(self, key: str, label: str) -> str:
        text = t(label)
        if key == "downloads" and self.ctrl.active_jobs:
            text += f"  ({self.ctrl.active_jobs})"
        return text

    def show(self, key: str) -> None:
        if key not in self.views:
            return
        self._current = key
        for k, btn in self._nav.items():
            active = k == key
            color = theme.ACCENT if active else theme.DIM
            btn.configure(fg_color=theme.ACCENT_DIM if active else "transparent", text_color=color,
                          image=ctk_icon(btn._icon_name, 18, color))  # type: ignore[attr-defined]
        self.views[key].tkraise()
        self.views[key].on_show()
        self._badge()

    @property
    def current(self) -> Optional[str]:
        return self._current

    def _badge(self) -> None:
        if self._compact:
            return
        label = dict((k, l) for k, l, *_ in TABS)["downloads"]
        self._nav["downloads"].configure(text=self._nav_text("downloads", label))

    def _drive_changed(self) -> None:
        drive = self.ctrl.drive
        for w in (self.usb_bar, self.usb_free):
            w.pack_forget()
        if drive:
            self.usb_label.configure(text=str(drive), text_color=theme.ACCENT)
            try:
                usage = shutil.disk_usage(drive.root)
                used = 1 - usage.free / max(usage.total, 1)
                self.usb_bar.set(used)
                self.usb_bar.configure(progress_color=theme.WARN if used > 0.9 else theme.ACCENT)
                self.usb_free.configure(text=t("nav.free_space", free=human_size(usage.free),
                                               total=human_size(usage.total)))
                if not self._compact:
                    self.usb_bar.pack(fill="x", padx=12, pady=(2, 2))
                    self.usb_free.pack(fill="x", padx=12, pady=(0, 10))
            except OSError:
                pass
        elif self.ctrl.drives:
            self.usb_label.configure(text=t("nav.drive_not_connected"), text_color=theme.WARN)
        else:
            self.usb_label.configure(text=t("nav.no_drive"), text_color=theme.DIM)
        if not drive or self._compact:
            self.usb_label.pack_configure(pady=(2, 10)) if not self._compact else None
        search = self.views.get("search")
        if search is not None:
            search.refresh_duplicates()

    def _library_changed(self) -> None:
        search = self.views.get("search")
        if search is not None:
            search.refresh_duplicates()
        self._drive_changed()

    # ------------------------------------------------------------------- raccourcis
    def _typing(self) -> bool:
        w = self.focus_get()
        return w is not None and w.winfo_class() in ("Entry", "TEntry", "Text", "Spinbox")

    def _bind_shortcuts(self) -> None:
        for i, (key, *_rest) in enumerate(TABS, start=1):
            self.bind_all(f"<Control-Key-{i}>", lambda _e, k=key: self.show(k))
        self.bind_all("<Control-k>", lambda _e: self.focus_omnibar())
        self.bind_all("<Control-K>", lambda _e: self.focus_omnibar())
        self.bind_all("<Control-f>", lambda _e: self._focus_filter())
        self.bind_all("<Control-comma>", lambda _e: self.show("settings"))
        self.bind_all("<F1>", lambda _e: self.open_help())
        self.bind_all("<Control-Right>", lambda _e: self.ctrl.play_next())
        self.bind_all("<Control-Left>", lambda _e: self.ctrl.play_previous())
        self.bind_all("<space>", self._space, add="+")

    def _space(self, _e: Any) -> Optional[str]:
        if self._typing():
            return None
        self.ctrl.toggle_play()
        return "break"

    def focus_omnibar(self) -> None:
        self.show("home")
        self.views["home"].focus_omnibar()

    def _focus_filter(self) -> None:
        view = self.views.get(self._current or "")
        if view is not None:
            view.focus_filter()

    def open_help(self) -> None:
        from .help_dialog import HelpDialog

        HelpDialog(self)

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
