"""Fenêtre principale (V0.3.0, Qt) : barre latérale (repliable), zone de contenu, barre d'état, lecteur.

Onglets, dans cet ordre : Accueil, Recherche, Bibliothèque, Téléchargements récents, Import URL,
Paramètres.
  * Le zoom (Paramètres) et la couleur d'accent s'appliquent à chaud : nouvelle feuille de style,
    sans reconstruire les vues (`restyle`). La taille de la fenêtre ne change PLUS le zoom.
  * La langue reconstruit les vues (`rebuild_ui`), sans redémarrer.
"""
from __future__ import annotations

import logging
import shutil
import sys
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QByteArray, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QWidget,
)

from .. import i18n
from ..i18n import t
from ..settings import Settings
from . import theme
from .controller import AppController
from .covers import CoverLoader
from .icons import qicon, reset_icons
from .logo import logo_pixmap
from .player_bar import PlayerBar
from .runner import UiDispatcher
from .views.common import View, human_size
from .views.feedback_view import FeedbackView
from .views.downloads_view import DownloadsView
from .views.home_view import HomeView
from .views.import_view import ImportView
from .views.library_view import LibraryView
from .views.search_view import SearchView
from .views.settings_view import SettingsView
from .widgets import button, hbox, icon_button, icon_label, label, panel, restyle, vbox

log = logging.getLogger(__name__)

SIDEBAR_WIDTH = 190
SIDEBAR_COMPACT = 52
COMPACT_BELOW = 1000            # largeur (pixels logiques) sous laquelle la barre latérale passe en icônes
MIN_W, MIN_H = 760, 500
DEFAULT_W, DEFAULT_H = 1240, 780
TABS = [  # (clé, clé i18n, icône, classe)
    ("home", "tab.home", "home", HomeView),
    ("search", "tab.search", "search", SearchView),
    ("library", "tab.library", "library", LibraryView),
    ("downloads", "tab.downloads", "downloads", DownloadsView),
    ("import", "tab.import", "import", ImportView),
    ("settings", "tab.settings", "settings", SettingsView),
    ("feedback", "tab.feedback", "chat", FeedbackView),         # 1.2.1 (C18)
]
_ROLE = {"info": "dim", "ok": "accent", "warn": "warn", "error": "err"}


def status_role(kind: str) -> str:
    return _ROLE.get(kind, "dim")


WINDOW_WATCH_S = 3.0            # 1.3.0-rc.9 (B32) : surveillance des fenêtres après l'ouverture d'une page
WINDOW_WATCH_TICK_MS = 40
_WINDOW_TYPES = {Qt.Window: "Window", Qt.Dialog: "Dialog", Qt.Sheet: "Sheet", Qt.Drawer: "Drawer",
                 Qt.Popup: "Popup", Qt.Tool: "Tool", Qt.ToolTip: "ToolTip", Qt.SplashScreen: "SplashScreen",
                 Qt.Desktop: "Desktop", Qt.SubWindow: "SubWindow", Qt.ForeignWindow: "ForeignWindow",
                 Qt.CoverWindow: "CoverWindow", Qt.Widget: "Widget"}


def window_type_name(flags: Any) -> str:
    kind = Qt.WindowType(int(flags) & int(Qt.WindowType_Mask))
    return _WINDOW_TYPES.get(kind, hex(int(kind)))


def window_state_name(state: Any) -> str:
    st = int(state.value if hasattr(state, "value") else state)
    names = [n for flag, n in ((Qt.WindowMinimized, "minimized"), (Qt.WindowMaximized, "maximized"),
                               (Qt.WindowFullScreen, "fullscreen"), (Qt.WindowActive, "active"))
             if st & int(flag.value if hasattr(flag, "value") else flag)]
    return "+".join(names) or "normal"


def stray_windows(main: Any) -> list:
    """1.3.0-rc.9 (B32) : fenêtres natives visibles autres que la fenêtre principale (les bulles d'aide
    exclues). Passe par QGuiApplication.allWindows() : couvre aussi les fenêtres qui ne sont pas des QWidget."""
    from PySide6.QtGui import QGuiApplication

    own = main.windowHandle()
    return [w for w in QGuiApplication.allWindows()
            if w is not own and w.isVisible() and window_type_name(w.flags()) != "ToolTip"]


def describe_window(win: Any) -> str:
    """Type, classe du widget, titre, taille, parent et premiers textes : de quoi reconnaître la fenêtre."""
    widget = next((w for w in QApplication.topLevelWidgets() if w.windowHandle() is win), None)
    parts = [window_type_name(win.flags()), type(widget).__name__ if widget is not None else type(win).__name__]
    if widget is not None and widget.objectName():
        parts.append(f"name={widget.objectName()}")
    if win.title():
        parts.append(f"title={win.title()[:40]!r}")
    parts.append(f"{win.width()}x{win.height()}")
    if widget is not None:
        parent = widget.parentWidget()
        if parent is not None:
            parts.append(f"parent={type(parent).__name__}")
        texts = [lbl.text()[:30] for lbl in widget.findChildren(QLabel) if lbl.text()][:2]
        if texts:
            parts.append(f"texts={texts!r}")
    return " ".join(parts)


def qt_app() -> QApplication:
    """L'application Qt (créée au besoin, style Fusion : rendu identique sur tous les systèmes)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setApplicationName("DJSync")
    return app  # type: ignore[return-value]


DIAG_PAGE_TYPES = ("DiagnosticDialog", "DuplicatesDialog", "MissingFilesDialog")   # 1.3.1 (C41)


class DJSyncApp(QMainWindow):
    def __init__(self, settings: Optional[Settings] = None, controller: Optional[AppController] = None,
                 splash: Any = None) -> None:
        self.qapp = qt_app()
        settings = settings or Settings.load()
        i18n.set_language(settings.language)
        theme.apply_palette(settings.theme)
        theme.apply(self.qapp, settings.zoom)
        reset_icons()
        super().__init__()
        self.setWindowTitle("DJSync")
        self.setWindowIcon(QIcon(logo_pixmap(64, theme.ACCENT)))

        self.dispatcher = UiDispatcher()
        self.ctrl = controller or AppController(settings, self.dispatcher)
        self.loader = CoverLoader(self.dispatcher)
        self._current: Optional[str] = None
        self._compact: Optional[bool] = None
        self._nav: Dict[str, QPushButton] = {}
        self.views: Dict[str, View] = {}
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._hide_toast)

        # écouteurs de la FENÊTRE d'abord : ceux des vues (ajoutés ensuite) sont oubliés à chaque
        # reconstruction de l'interface (langue)
        self.ctrl.on("message", self._message)
        self.ctrl.on("message_action", self._message_action)
        self.ctrl.on("open_diagnostic", lambda tab: self.open_diagnostic(tab))
        self.ctrl.on("navigate", self.show_view)
        self.ctrl.on("drive", self._drive_changed)
        self.ctrl.on("drives", self._drive_changed)
        self.ctrl.on("downloads", self._badge)
        self.ctrl.on("download_update", lambda _j: self._badge())
        self.ctrl.on("downloads", self._analysis_changed)
        self.ctrl.on("download_update", lambda _j: self._analysis_changed())
        self.ctrl.on("library", self._library_changed)
        self.ctrl.on("rebuild_ui", self.rebuild_ui)
        self.ctrl.on("restyle", self.restyle)
        self.ctrl.on("zoom", self.restyle)
        self.ctrl.on("analysis", self._analysis_changed)
        self.ctrl.on("open_grid", self.open_grid_editor)
        self.ctrl.on("open_uniformize", self.open_uniformize)
        self.ctrl.on("error_report_ask", self._ask_error_report)
        self.ctrl.on("engine_offer", self._engine_offer)
        self.ctrl.on("app_update", self._app_update)
        self.ctrl.on("app_update_ready", self._app_update_ready)
        self.ctrl.on("open_url", self._open_url)
        self.ctrl.on("local_offer", self._local_offer)
        self.ctrl.on("eject_own", self._eject_own)
        self.ctrl.on("quit", self.close)
        self._listener_mark = self.ctrl.listener_mark()
        self._build()
        self._built_accent = theme.ACCENT          # 1.3.0-rc.4 (B23)
        self._bind_shortcuts()
        self._place_window(settings)

        self.show_view("home")
        self._drive_changed()
        self._splash = splash
        QTimer.singleShot(150, self.ctrl.startup)
        if getattr(self.ctrl.settings, "first_run", False) and not self.ctrl.settings.welcome_done:
            QTimer.singleShot(400, self._welcome)          # 1.3.2 (C54) : tout premier lancement

    # ----------------------------------------------------------------- fenêtre à l'écran
    def _place_window(self, settings: Settings) -> None:
        """Taille et position de départ TOUJOURS dans l'écran : la géométrie enregistrée est
        réduite/recentrée si besoin (autre écran, autre DPI) ; sinon 1240 x 780 au plus, 90 % de
        la largeur et 85 % de la hauteur de l'écran disponible, centrée."""
        screen = self.qapp.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        max_w, max_h = int(area.width() * 0.9), int(area.height() * 0.85)
        self.setMinimumSize(min(MIN_W, max_w), min(MIN_H, max_h))
        restored = False
        if settings.geometry and not settings.geometry[0].isdigit():
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(settings.geometry.encode()))
            except Exception:  # noqa: BLE001 - ancienne valeur (format Tk)
                restored = False
        if restored:
            g = self.geometry()
            if not any(s.availableGeometry().intersects(g) for s in self.qapp.screens()):
                restored = False
        if not restored:
            w, h = min(DEFAULT_W, max_w), min(DEFAULT_H, max_h)
            self.resize(w, h)
            self.move(area.x() + (area.width() - w) // 2, area.y() + max(0, (area.height() - h) // 3))
        self._start_maximized = bool(settings.maximized)

    def reveal(self) -> None:
        """Affiche la fenêtre (agrandie si elle l'était) puis ferme l'écran de démarrage."""
        if self._start_maximized:
            self.showMaximized()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if not getattr(self, "_app_state_watched", False):     # 1.3.0-rc.9 (B32)
            self._app_state_watched = True
            self._watch_app_state()
        splash, self._splash = self._splash, None
        if splash is not None:
            splash.close()
        from .splash import close_native

        close_native()

    # ------------------------------------------------------------------ construction
    def _build(self) -> None:
        central = QWidget()
        outer = vbox(central, spacing=0)
        body = hbox(spacing=0)
        outer.addLayout(body, 1)
        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        # messages : petite bulle en bas à droite de la page, qui disparaît seule
        self.toast = panel(self.stack, role="toast")
        tl = hbox(self.toast, margins=theme.px(10), spacing=theme.px(8))
        self.toast_icon = label()
        self.status = label("", "dim")
        self.status.setWordWrap(True)
        self.status.setMaximumWidth(theme.px(520))
        tl.addWidget(self.toast_icon)
        tl.addWidget(self.status, 1)
        self.toast_action = button("", lambda: self._toast_clicked(), kind="flat")   # 1.3.1 : lien d'un message
        self.toast_action.hide()
        self._toast_fn: Optional[Callable[[], None]] = None
        tl.addWidget(self.toast_action)
        # 1.3.1 (C61) : une erreur reste affichée (bulle plus large, texte entier) : Copier et Fermer
        self.toast_copy = button(t("toast.copy"), self._copy_toast, kind="flat")
        self.toast_copy.hide()
        tl.addWidget(self.toast_copy)
        self.toast_close = icon_button("close", self._hide_toast, t("toast.close"))
        tl.addWidget(self.toast_close)
        self.toast.hide()
        self.views = {}
        self.grid_editor: Any = None
        self._grid_return: Any = None                     # nom d'onglet, ou page d'origine (B29)
        for key, _label, _icon, cls in TABS:
            view = cls(self.stack, self.ctrl, self.loader)
            self.stack.addWidget(view)
            self.views[key] = view
        self.player_bar = PlayerBar(central, self.ctrl, self.loader)
        outer.addWidget(self.player_bar)
        self.setCentralWidget(central)
        self._compact = None
        self._update_compact()

    def _build_sidebar(self) -> QWidget:
        bar = panel(role="sidebar")
        lay = vbox(bar, margins=theme.px(10), spacing=theme.px(3))
        head = hbox(spacing=theme.px(10))
        head.setContentsMargins(theme.px(6), theme.px(6), 0, 0)
        self.logo = label()
        self.logo.setPixmap(logo_pixmap(theme.px(28), theme.ACCENT))
        head.addWidget(self.logo)
        self.logo_text = label("DJSync", "h2")
        head.addWidget(self.logo_text)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(theme.px(18))

        for key, text_key, icon_name, _cls in TABS:
            b = button(t(text_key), lambda k=key: self.show_view(k), kind="nav")
            b.setCheckable(True)
            b.setIcon(qicon(icon_name, 18, theme.DIM))
            b.setIconSize(QSize(theme.px(18), theme.px(18)))
            b._icon_name = icon_name  # type: ignore[attr-defined]
            lay.addWidget(b)
            self._nav[key] = b
        lay.addStretch(1)

        # ---- analyse en arrière-plan (visible depuis tous les onglets)
        an = panel()
        self.an_box = an
        al = vbox(an, margins=theme.px(10), spacing=theme.px(4))
        ah = hbox(spacing=theme.px(4))
        self.an_title = label(t("nav.analysing").upper(), "section")
        ah.addWidget(self.an_title, 1)
        self.an_stop = icon_button("stop", self.ctrl.stop_analysis, t("lib.analyse_stop"), size=12)
        ah.addWidget(self.an_stop)
        al.addLayout(ah)
        self.an_label = label("", "dim", wrap=True)
        al.addWidget(self.an_label)
        self.an_bar = QProgressBar()
        self.an_bar.setRange(0, 1000)
        self.an_bar.setTextVisible(False)
        al.addWidget(self.an_bar)
        # 1.2.1 (C21) : la même carte montre aussi les téléchargements en cours (« Activité »)
        self.dl_label = label("", "dim", wrap=True)
        al.addWidget(self.dl_label)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 1000)
        self.dl_bar.setTextVisible(False)
        al.addWidget(self.dl_bar)
        self.an_open = icon_button("go", lambda: self.ctrl._emit("show_unanalysed"), t("lib.unanalysed"), size=12)
        ah.insertWidget(1, self.an_open)
        an.hide()
        lay.addWidget(an)

        # ---- clé active + remplissage
        usb = panel()
        self.usb_box = usb
        ul = vbox(usb, margins=theme.px(10), spacing=theme.px(4))
        uh = hbox(spacing=theme.px(6))
        self.usb_icon = icon_label("usb", 14, theme.FAINT)
        uh.addWidget(self.usb_icon)
        self.usb_title = label(t("nav.active_drive").upper(), "section")
        uh.addWidget(self.usb_title, 1)
        self.eject_btn = icon_button("eject", self.ctrl.eject, t("eject.hint"), size=12)
        self.eject_btn.hide()
        uh.addWidget(self.eject_btn)
        ul.addLayout(uh)
        self.usb_label = label("", wrap=True)
        self.usb_bar = QProgressBar()
        self.usb_bar.setRange(0, 1000)
        self.usb_bar.setTextVisible(False)
        self.usb_free = label("", "dim", wrap=True)
        for w in (self.usb_label, self.usb_bar, self.usb_free):
            ul.addWidget(w)
        lay.addSpacing(theme.px(6))
        lay.addWidget(usb)

        self.help_btn = button(t("help.button"), self.open_help, kind="nav")
        self.help_btn.setIcon(qicon("help", 18, theme.DIM))
        self.help_btn.setIconSize(QSize(theme.px(18), theme.px(18)))
        lay.addSpacing(theme.px(4))
        lay.addWidget(self.help_btn)
        # 1.2.0-rc.4 (B09) : la barre se replie seule quand la fenêtre est étroite ; ce bouton la
        # déplie ou la replie à la demande (choix retenu dans les réglages).
        self.fold_btn = button("", self._toggle_sidebar, kind="nav")
        self.fold_btn.setIconSize(QSize(theme.px(18), theme.px(18)))
        lay.addWidget(self.fold_btn)
        return bar

    def _toggle_sidebar(self) -> None:
        s = self.ctrl.settings
        s.sidebar_compact = "off" if self._compact else "on"
        try:
            s.save()
        except OSError:
            pass
        self._compact = None
        self._update_compact()

    def rebuild_ui(self) -> None:
        """Reconstruit toute l'interface (changement de langue), sans redémarrer.
        La clé, la file de téléchargements et la lecture en cours sont conservées (contrôleur)."""
        current = self._current or "home"
        i18n.set_language(self.ctrl.settings.language)
        theme.apply_palette(self.ctrl.settings.theme)
        theme.apply(self.qapp, self.ctrl.settings.zoom)
        self.ctrl.reset_listeners(self._listener_mark)
        old = self.centralWidget()
        self._nav = {}
        self._build()
        self._built_accent = theme.ACCENT          # 1.3.0-rc.4 (B23)
        if old is not None:
            old.deleteLater()
        self.show_view(current)
        self._drive_changed()
        self._badge()
        self._analysis_changed()

    def restyle(self) -> None:
        """Couleur d'accent, zoom ou barre latérale changés : nouvelle feuille de style, sans
        reconstruire les vues."""
        s = self.ctrl.settings
        theme.apply_palette(s.theme)
        if theme.ACCENT != getattr(self, "_built_accent", theme.ACCENT):
            # 1.3.0-rc.4 (B23) : nouvelle couleur -> toutes les vues sont reconstruites, comme pour un
            # changement de langue. Icônes, pastilles, formes d'onde, logo… sont dessinés à leur création
            # dans la couleur du moment : les reprendre une à une en oubliait (Outils de l'Accueil).
            self.setWindowIcon(QIcon(logo_pixmap(64, theme.ACCENT)))
            self.rebuild_ui()
            return
        theme.apply(self.qapp, s.zoom)
        self.setWindowIcon(QIcon(logo_pixmap(64, theme.ACCENT)))
        self.logo.setPixmap(logo_pixmap(theme.px(24), theme.ACCENT))
        for b in list(self._nav.values()) + [self.help_btn]:
            b.setIconSize(QSize(theme.px(18), theme.px(18)))
        for view in self.views.values():
            view.on_scale()
        self.player_bar.on_scale()
        self._compact = None
        self._update_compact()
        if self._current:
            self.show_view(self._current)

    def _analysis_changed(self) -> None:
        """Carte « Activité » de la barre latérale : analyse et/ou téléchargements en cours
        (1.2.1, C21 : une seule carte quand les deux tournent)."""
        q = self.ctrl.analysis
        b_done, b_total, frac = self.ctrl.download_progress()
        downloading = b_total > 0
        if not q.running and not downloading:
            self.an_box.hide()
            return
        self.an_box.show()
        compact = bool(self._compact)
        both = q.running and downloading
        for w in (self.an_bar, self.an_stop, self.an_open):
            w.setVisible(q.running)
        self.an_label.setVisible(q.running and not compact)
        self.dl_bar.setVisible(downloading)
        self.dl_label.setVisible(downloading and not compact)
        if q.running:
            self.an_bar.setValue(int(1000 * q.done / max(1, q.total)))
            name = q.current if len(q.current) <= 40 else q.current[:39] + "…"
            prefix = t("nav.analysing") + " " if both else ""
            self.an_label.setText("" if compact else prefix + f"{q.done} / {q.total}" + (f"  ·  {name}" if name else ""))
            self.an_stop.setEnabled(not q.cancelled)
        if downloading:
            self.dl_bar.setValue(int(1000 * frac))
            self.dl_label.setText(t("nav.downloading") + f" {b_done} / {b_total}")
        if compact:
            title = ""
        elif both:
            title = t("nav.activity")
        elif q.running:
            title = t("analysis.stopping") if q.cancelled else t("nav.analysing")
        else:
            title = t("nav.downloading")
        self.an_title.setText(title.upper())

    # --------------------------------------------------------------- barre repliable
    def _update_compact(self) -> None:
        width = self.width() if self.isVisible() else DEFAULT_W
        mode = self.ctrl.settings.sidebar_compact
        compact = mode == "on" or (mode == "auto" and width < COMPACT_BELOW)
        if compact == self._compact:
            return
        self._compact = compact
        labels = {k: l for k, l, *_ in TABS}
        for key, b in self._nav.items():
            b.setText("" if compact else self._nav_text(key, labels[key]))
            b.setToolTip(t(labels[key]) if compact else "")
        width = theme.px(SIDEBAR_COMPACT)
        if not compact:          # au moins le plus long libellé (langue, zoom)
            width = max([theme.px(SIDEBAR_WIDTH)] + [b.sizeHint().width() + theme.px(24) for b in self._nav.values()])
        self.sidebar.setFixedWidth(width)
        self.logo_text.setVisible(not compact)
        self.help_btn.setText("" if compact else t("help.button").replace("&", "&&"))
        self.fold_btn.setIcon(qicon("go" if compact else "back", 18, theme.DIM))
        self.fold_btn.setText("" if compact else t("nav.collapse"))
        self.fold_btn.setToolTip(t("nav.expand") if compact else "")
        for w in (self.usb_title, self.usb_label, self.usb_free):
            w.setVisible(not compact)
        self._analysis_changed()
        self._drive_changed()

    def resizeEvent(self, e: Any) -> None:     # noqa: N802
        super().resizeEvent(e)
        if getattr(self, "toast", None) is not None:
            self._place_toast()
        if self._nav:
            self._update_compact()

    # --------------------------------------------------------------------- navigation
    def _nav_text(self, key: str, text_key: str) -> str:
        text = t(text_key).replace("&", "&&")          # « & » affiché tel quel (pas de raccourci Qt)
        if key == "downloads" and self.ctrl.active_jobs:
            text += f"  ({self.ctrl.active_jobs})"
        return text

    def show_view(self, key: str) -> None:
        if key not in self.views:
            return
        if self._current and self._current != key:
            self._previous = self._current                     # capture d'écran de l'onglet Retours
        self._current = key
        for k, b in self._nav.items():
            active = k == key
            b.setChecked(active)
            b.setIcon(qicon(b._icon_name, 18, theme.ACCENT if active else theme.DIM))  # type: ignore[attr-defined]
        self.stack.setCurrentWidget(self.views[key])
        self.views[key].on_show()
        self._badge()

    @property
    def current(self) -> Optional[str]:
        return self._current

    def _badge(self) -> None:
        if self._compact or "downloads" not in self._nav:
            return
        self._nav["downloads"].setText(self._nav_text("downloads", "tab.downloads"))

    def _drive_changed(self) -> None:
        drive = self.ctrl.drive
        show_bar = False
        local = bool(getattr(drive, "is_local", False))
        self.usb_icon.setPixmap(qicon("computer" if local else "usb", 14, theme.FAINT)
                                .pixmap(QSize(theme.px(14), theme.px(14))))
        if drive:
            # 1.2.0-rc.4 (B06) : le nom de la bibliothèque du PC suit la langue de l'interface
            self.usb_label.setText(t("local.name") if local else (drive.label or str(drive.root)))
            self.usb_label.setProperty("role", "accent")
            try:
                from .ctrl.library_ops import existing_parent

                usage = shutil.disk_usage(existing_parent(drive.root))
                used = 1 - usage.free / max(usage.total, 1)
                self.usb_bar.setValue(int(used * 1000))
                self.usb_free.setText(t("nav.free_space", free=human_size(usage.free), total=human_size(usage.total)))
                show_bar = True
            except OSError:
                self.usb_free.setText("")
        elif self.ctrl.drives or self.ctrl.local is not None:
            self.usb_label.setText(t("nav.drive_not_connected"))
            self.usb_label.setProperty("role", "warn")
        else:
            self.usb_label.setText(t("nav.no_drive"))
            self.usb_label.setProperty("role", "dim")
        restyle(self.usb_label)
        self.eject_btn.setVisible(bool(drive) and not local and not self._compact)
        self.usb_bar.setVisible(show_bar)
        self.usb_free.setVisible(show_bar and not self._compact)
        self.usb_box.setToolTip(str(drive) if drive else self.usb_label.text())
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
        return isinstance(self.qapp.focusWidget(), (QLineEdit, QPlainTextEdit))

    def _shortcut(self, seq: Any, fn: Any) -> None:
        sc = QShortcut(QKeySequence(seq), self)
        sc.setContext(Qt.ApplicationShortcut)
        sc.activated.connect(fn)

    def _bind_shortcuts(self) -> None:
        for i, (key, *_rest) in enumerate(TABS, start=1):
            self._shortcut(f"Ctrl+{i}", lambda k=key: self.show_view(k))
        self._shortcut("Ctrl+K", self.focus_omnibar)
        self._shortcut("Ctrl+F", self._focus_filter)
        self._shortcut("Ctrl+,", lambda: self.show_view("settings"))
        self._shortcut("F1", self.open_help)
        self._shortcut("Ctrl+Right", self.ctrl.play_next)
        self._shortcut("Ctrl+Left", self.ctrl.play_previous)
        sc = QShortcut(QKeySequence(Qt.Key_Space), self)
        sc.activated.connect(self._space)
        # 1.2.0-rc.4 (B07) : touches multimédia du clavier quand DJSync est au premier plan (sur Mac,
        # F7-F9 sont pris par le système tant qu'une autre app joue du son).
        for key, fn in ((Qt.Key_MediaTogglePlayPause, self.ctrl.toggle_play), (Qt.Key_MediaPlay, self.ctrl.toggle_play),
                        (Qt.Key_MediaPause, self.ctrl.toggle_play), (Qt.Key_MediaNext, self.ctrl.play_next),
                        (Qt.Key_MediaPrevious, self.ctrl.play_previous)):
            self._shortcut(key, fn)

    def _space(self) -> None:
        if not self._typing():
            self.ctrl.toggle_play()

    def focus_omnibar(self) -> None:
        self.show_view("home")
        self.views["home"].focus_omnibar()

    def _focus_filter(self) -> None:
        view = self.views.get(self._current or "")
        if view is not None:
            view.focus_filter()

    # ----------------------------------------------------------- éditeur de grille : une page
    def open_grid_editor(self, track: Any) -> None:
        """Ouvre la page « Grille de temps » dans la zone de contenu. Changer d'onglet la cache sans la
        fermer : la rouvrir pour le même son retrouve les modifications en cours."""
        from .grid_editor import GridEditor

        ed = self.grid_editor
        if ed is not None and ed.winfo_exists():
            if ed.track.content_id == track.content_id:
                self._show_page(ed)
                return
            if ed.is_dirty():                 # 1.3.0 : modifications en cours -> on demande d'abord
                self._show_page(ed)
                ed._on_close = lambda: (self._grid_closed(), self.open_grid_editor(track))
                ed.close()
                return
            ed._on_close = None
            ed.close()
        self._grid_return = self._return_target("library")          # 1.3.1 (B29) : page d'origine
        self.grid_editor = GridEditor(self.stack, self.ctrl, track, on_close=self._grid_closed)
        self.stack.addWidget(self.grid_editor)
        self._show_page(self.grid_editor)

    def _ask_error_report(self, summary: str, answer: Any) -> None:
        """1.2.3 : proposer d'envoyer le rapport d'une erreur inattendue (une fenêtre à la fois)."""
        from .dialogs import ErrorReportDialog

        current = getattr(self, "_error_report_dialog", None)
        if current is not None and current.winfo_exists():
            answer(False)
            return

        def always() -> None:
            self.ctrl.settings.error_reports = "always"
            self.ctrl.save_settings_quiet()

        self._error_report_dialog = ErrorReportDialog(self, summary, answer, on_always=always)

    def open_uniformize(self, tracks: Any, scope: str) -> None:
        """1.2.2 (C14) : page « Uniformiser » dans la zone de contenu (comme l'éditeur de grille)."""
        from .uniformize_page import UniformizePage

        page = getattr(self, "uniformize_page", None)
        if page is not None and page.winfo_exists():
            page._leaving = True
            page.close()
        self._uni_return = self._current or "library"
        for old in self._diag_pages():                  # 1.3.1 (C41) : onglet Uniformiser du Diagnostic
            self._drop_diag_page(old)
        self.uniformize_page = UniformizePage(self.stack, self.ctrl, list(tracks), scope, on_close=self._uni_closed)
        self.stack.addWidget(self.uniformize_page)
        self._show_page(self.uniformize_page)

    def _uni_closed(self) -> None:
        page, self.uniformize_page = getattr(self, "uniformize_page", None), None
        if page is not None:
            self.stack.removeWidget(page)
            page.deleteLater()
        self.show_view(getattr(self, "_uni_return", None) or "library")

    # ------------------------------------------------- 1.3.1 (C41/C43) : Diagnostic en onglets
    def open_diagnostic(self, tab: str = "missing", from_page: Optional[QWidget] = None) -> None:
        """Ouvre un onglet du Diagnostic. `from_page` : l'onglet quitté (fermé sans revenir à la vue
        d'origine ; le bouton Retour du nouvel onglet y ramène)."""
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return

        def go() -> None:
            if tab == "uniformize":
                from .uniformize_page import ScopeDialog

                ScopeDialog(self, self.ctrl)
                return
            if tab == "dup":
                from .duplicates_dialog import DuplicatesDialog as page_cls

                if self.reopen_dialog_page(page_cls) is not None:      # 1.3.2 (C95) : reprise, pas de zéro
                    return
            elif tab == "quality":
                from .diagnostic_dialog import DiagnosticDialog as page_cls
            else:
                from .missing_dialog import MissingFilesDialog as page_cls
            page_cls(self, self.ctrl)

        self.ctrl.diag_quick_counts()
        if from_page is None or tab == "uniformize":
            go()                      # Uniformiser : la page actuelle reste tant que la portée n'est pas choisie
            return
        self._drop_diag_page(from_page, then=go)

    def _drop_diag_page(self, page: QWidget, then: Optional[Callable[[], None]] = None) -> None:
        """Ferme une page du Diagnostic sans revenir à la vue d'origine (changement d'onglet)."""
        if page is getattr(self, "uniformize_page", None):
            def closed() -> None:                       # après la question « enregistrer ? » éventuelle
                self.uniformize_page = None
                self.stack.removeWidget(page)
                page.deleteLater()
                if then:
                    then()
            page._on_close = closed                     # type: ignore[attr-defined]
            page.close()
            return
        self.__dict__.setdefault("_page_returns", {}).pop(id(page), None)
        page._host = None                               # type: ignore[attr-defined]
        try:
            self.stack.removeWidget(page)
        except RuntimeError:
            pass
        page.close()
        if then:
            then()

    def _diag_pages(self) -> List[QWidget]:
        from .diagnostic_dialog import DiagnosticDialog
        from .duplicates_dialog import DuplicatesDialog
        from .missing_dialog import MissingFilesDialog

        kinds = (DiagnosticDialog, DuplicatesDialog, MissingFilesDialog)
        return [w for w in (self.stack.widget(i) for i in range(self.stack.count())) if isinstance(w, kinds)]

    # ------------------------------------------------- 1.2.3 : Doublons, Diagnostic, Analyse en pages
    def reopen_dialog_page(self, page_cls: type) -> Optional[QWidget]:
        """1.3.2 (C95) : une page de cette sorte encore ouverte (cachée derrière l'Accueil, la Bibliothèque,
        Grille et cues…) revient au premier plan telle quelle, avec son travail en cours (la vérification
        des doublons a continué en arrière-plan) ; None s'il n'y en a pas."""
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            if type(page) is page_cls and getattr(page, "_host", None) is self and page.winfo_exists():
                self.__dict__.setdefault("_page_returns", {})[id(page)] = self._return_target("home", exclude=page)
                self._show_page(page)
                return page
        return None

    def open_dialog_page(self, page: QWidget) -> None:
        returns = self.__dict__.setdefault("_page_returns", {})
        diag = type(page).__name__ in DIAG_PAGE_TYPES             # un seul onglet du Diagnostic à la fois
        for i in reversed(range(self.stack.count())):            # une seule page de chaque sorte
            old = self.stack.widget(i)
            if old is not page and (type(old) is type(page) or (diag and old in self._diag_pages())):
                returns.pop(id(old), None)
                old._host = None                                  # type: ignore[attr-defined]
                self.stack.removeWidget(old)
                old.close()
        returns[id(page)] = self._return_target("home", exclude=page)
        self.stack.addWidget(page)
        self._show_page(page)
        self.watch_windows(type(page).__name__)

    # ------------------------------------------- 1.3.0-rc.9 (B32) : quelle fenêtre s'ouvre en trop ?
    def watch_windows(self, what: str, seconds: float = WINDOW_WATCH_S) -> None:
        """Pendant `seconds` après l'ouverture d'une page, regarde toutes les 40 ms les fenêtres visibles
        autres que la fenêtre principale, et journalise chacune à son apparition et à sa disparition (avec
        le délai en ms). L'enregistrement d'écran du testeur Mac (rc.8) montre une fenêtre ouverte puis
        refermée en ~0,3 s, environ 0,4 s après l'ouverture de Doublons : en plein écran, macOS lui crée un
        espace (écran noir) puis retombe sur le bureau. Le contrôle unique à 400 ms de la rc.8 la ratait.
        Une surveillance limitée dans le temps plutôt qu'un filtre sur tous les événements Qt : celui-ci
        chargerait le thread Python en permanence (et donc le son, B33)."""
        from PySide6.QtCore import QElapsedTimer

        old = getattr(self, "_win_watch", None)
        if old is not None:
            old[0].stop()
        clock = QElapsedTimer()
        clock.start()
        timer = QTimer(self)
        timer.setInterval(WINDOW_WATCH_TICK_MS)
        seen: Dict[int, tuple] = {}
        self._win_watch = (timer, what, clock)
        self._win_watch_last = (what, clock)
        timer.timeout.connect(lambda: self._watch_tick(timer, what, clock, seen, seconds))
        timer.start()
        self._watch_tick(timer, what, clock, seen, seconds)

    def _watch_tick(self, timer: QTimer, what: str, clock: Any, seen: Dict[int, tuple], seconds: float) -> None:
        ms = clock.elapsed()
        try:
            visible = {id(w): w for w in stray_windows(self)}
        except RuntimeError:
            visible = {}
        for key, w in visible.items():
            if key not in seen:
                seen[key] = (ms, describe_window(w))
                log.info("Page %s: window shown after %d ms: %s", what, ms, seen[key][1])
        for key in [k for k in seen if k not in visible and seen[k][0] >= 0]:
            start, desc = seen[key]
            log.info("Page %s: window gone after %d ms (visible %d ms): %s", what, ms, ms - start, desc)
            seen[key] = (-1, desc)
        if ms >= seconds * 1000:
            timer.stop()
            timer.deleteLater()
            if getattr(self, "_win_watch", (None,))[0] is timer:
                self._win_watch = None

    def _watch_app_state(self) -> None:
        """1.3.0-rc.9 (B32) : journalise quand DJSync passe au second plan, quelle fenêtre prend le focus,
        et les entrées / sorties du plein écran (signaux de Qt : rien ne tourne entre deux)."""
        from PySide6.QtGui import QGuiApplication

        def since() -> str:
            last = getattr(self, "_win_watch_last", None)
            return f" ({last[1].elapsed()} ms after opening {last[0]})" if last is not None else ""

        def watching() -> bool:
            # 1.3.1-rc.2 (B38) : lignes « App state » / « Focus » seulement pendant les 3 s qui suivent
            # l'ouverture d'une page (ce qui sert pour B32) : sinon elles remplissaient le journal.
            last = getattr(self, "_win_watch_last", None)
            return last is not None and last[1].elapsed() <= WINDOW_WATCH_S * 1000

        def state(st: Any) -> None:
            name = {Qt.ApplicationActive: "active", Qt.ApplicationInactive: "inactive",
                    Qt.ApplicationHidden: "hidden", Qt.ApplicationSuspended: "suspended"}.get(st, str(st))
            if watching():
                log.info("App state: %s%s", name, since())

        def focus(win: Any) -> None:
            if win is None or win is self.windowHandle() or not watching():
                return
            log.info("Focus to another window: %s%s", describe_window(win), since())

        QGuiApplication.instance().applicationStateChanged.connect(state)
        QGuiApplication.instance().focusWindowChanged.connect(focus)
        handle = self.windowHandle()
        if handle is not None:
            handle.windowStateChanged.connect(
                lambda st: log.info("Main window state: %s%s", window_state_name(st), since()))

    def close_dialog_page(self, page: QWidget) -> None:
        back = self.__dict__.setdefault("_page_returns", {}).pop(id(page), None) or "home"
        try:
            self.stack.removeWidget(page)
        except RuntimeError:
            pass
        self._go_back(back)

    # 1.3.1 (B29) : Retour revient à la page d'où l'on vient, même si c'est une page ouverte par-dessus
    # un onglet (Doublons, Diagnostic, Analyser…), dans l'état où on l'a laissée ; sinon à l'onglet.
    def _return_target(self, default: str, exclude: Any = None) -> Any:
        cur = self.stack.currentWidget()
        if cur is not None and cur is not exclude and cur is not self.grid_editor \
                and cur not in self.views.values() and self.stack.indexOf(cur) >= 0:
            return cur
        return self._current or default

    def _go_back(self, target: Any) -> None:
        if isinstance(target, QWidget):
            try:
                alive = self.stack.indexOf(target) >= 0
            except RuntimeError:                                  # page détruite entre-temps
                alive = False
            if alive:
                self._show_page(target)
                return
            target = self._current or "home"
        self.show_view(target)

    def _show_page(self, page: QWidget) -> None:
        for b in self._nav.values():
            b.setChecked(False)
        self.stack.setCurrentWidget(page)
        page.setFocus()

    def _grid_closed(self) -> None:
        ed, self.grid_editor = self.grid_editor, None
        if ed is not None:
            self.stack.removeWidget(ed)
        self._go_back(self._grid_return or "library")

    # ------------------------------------------------------------ questions (V0.5.0)
    def _engine_offer(self, release: Any, current: str) -> None:
        from .dialogs import ConfirmDialog

        ConfirmDialog(self, t("engine.offer_title"), t("engine.offer_msg", version=release.version),
                      lambda: self.ctrl.engine_install(release), confirm_text=t("engine.offer_ok"),
                      detail=t("engine.offer_detail", current=current or "?"))

    def _app_update(self, update: Any, current: str) -> None:
        """Nouvelle version : 1.2.0-rc.4, installée depuis l'application quand c'est possible."""
        from .dialogs import ConfirmDialog

        if self.ctrl.can_self_update() and update.asset:
            ConfirmDialog(self, t("update.title"), t("update.msg", version=update.version),
                          lambda: self.ctrl.app_update_install(update), confirm_text=t("update.install"),
                          detail=t("update.detail_install_test" if update.prerelease else "update.detail_install",
                                   current=current))
            return
        ConfirmDialog(self, t("update.title"), t("update.msg", version=update.version),
                      lambda: self._open_url(update.url), confirm_text=t("update.ok"),
                      detail=t("update.detail_test" if update.prerelease else "update.detail", current=current))

    def _app_update_ready(self, version: str) -> None:
        from .dialogs import ConfirmDialog

        ConfirmDialog(self, t("update.ready_title"), t("update.ready_msg", version=version),
                      self.ctrl.app_update_restart, confirm_text=t("update.restart"),
                      detail=t("update.ready_detail"))

    def _open_url(self, url: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

    def _local_offer(self, local: Any, host: str) -> None:
        from .dialogs import ConfirmDialog

        ConfirmDialog(self, t("local.offer_title"), t("local.offer_msg", host=host), self.ctrl.connect_local,
                      confirm_text=t("local.offer_ok"), detail=t("local.offer_detail"))

    def _eject_own(self, drive: Any) -> None:
        from .dialogs import ConfirmDialog

        ConfirmDialog(self, t("eject.own_title"), t("eject.own_msg", drive=drive.label or str(drive.root)),
                      self.close, confirm_text=t("eject.own_ok"))

    def _welcome(self) -> None:
        from .welcome import WelcomeDialog

        WelcomeDialog(self, self.ctrl)

    def open_help(self) -> None:
        from .help_dialog import HelpDialog

        HelpDialog(self)

    # ------------------------------------------------------------------- état
    def _message(self, kind: str, text: str) -> None:
        self.toast_action.hide()
        self._toast_fn = None
        self.status.setText(text)
        self.status.setProperty("role", "" if kind == "info" else status_role(kind))
        error = kind == "error"
        width = self.stack.width() or theme.px(900)
        self.status.setMaximumWidth(int(width * 0.7) if error else theme.px(520))   # C61 : ~70 % pour une erreur
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse if error else Qt.NoTextInteraction)
        self.toast_copy.setVisible(error)
        restyle(self.status)
        icon, color = {"ok": ("check", theme.ACCENT), "warn": ("warn", theme.WARN),
                       "error": ("warn", theme.ERR)}.get(kind, ("info", theme.DIM))
        self.toast_icon.setPixmap(qicon(icon, 16, color).pixmap(QSize(theme.px(16), theme.px(16))))
        self.toast.show()
        self.toast.raise_()
        self._place_toast()
        if error:
            self._status_timer.stop()                  # C61 : reste jusqu'à « Fermer »
        else:
            self._status_timer.start(12000 if kind == "warn" else 5000)

    def _message_action(self, text: str, fn: Callable[[], None]) -> None:
        """Bouton dans la bulle du dernier message (ex. « Voir dans le Diagnostic »)."""
        self._toast_fn = fn
        self.toast_action.setText(text)
        self.toast_action.show()
        self._place_toast()
        if self._status_timer.isActive():                # 1.3.2 (C82) : le temps de cliquer (Annuler…)
            self._status_timer.start(max(self._status_timer.remainingTime(), 11000))

    def _toast_clicked(self) -> None:
        fn, self._toast_fn = self._toast_fn, None
        self._hide_toast()
        if fn:
            fn()

    def _copy_toast(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.status.text())
        self.toast_copy.setText(t("toast.copied"))
        QTimer.singleShot(1500, lambda: self.toast_copy.setText(t("toast.copy")))

    def _hide_toast(self) -> None:
        self.status.setText("")
        self.toast.hide()

    def _place_toast(self) -> None:
        if not self.toast.isVisible():
            return
        self.toast.adjustSize()
        m = theme.px(16)
        area = self.stack.rect()
        # au-dessus de la rangée de boutons du bas des pages
        self.toast.move(area.right() - self.toast.width() - m, area.bottom() - self.toast.height() - theme.px(64))

    def closeEvent(self, e: Any) -> None:      # noqa: N802
        s = self.ctrl.settings
        try:
            s.maximized = self.isMaximized()
            s.geometry = bytes(self.saveGeometry().toBase64()).decode()
        except Exception:  # noqa: BLE001
            pass
        self.ctrl.shutdown()
        super().closeEvent(e)

    # compatibilité (tests, anciens appels)
    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return isValid(self)


def main() -> None:
    """Compatibilité : le lancement normal passe par ui/launcher.py (écran de démarrage)."""
    from .launcher import main as launch

    launch()


if __name__ == "__main__":
    sys.exit(main())
