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
from typing import Any, Dict, Optional

from PySide6.QtCore import QByteArray, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QWidget,
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
from .views.downloads_view import DownloadsView
from .views.home_view import HomeView
from .views.import_view import ImportView
from .views.library_view import LibraryView
from .views.search_view import SearchView
from .views.settings_view import SettingsView
from .widgets import button, hbox, icon_button, label, panel, restyle, vbox

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
]
_ROLE = {"info": "dim", "ok": "accent", "warn": "warn", "error": "err"}


def status_role(kind: str) -> str:
    return _ROLE.get(kind, "dim")


def qt_app() -> QApplication:
    """L'application Qt (créée au besoin, style Fusion : rendu identique sur tous les systèmes)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setApplicationName("DJSync")
    return app  # type: ignore[return-value]


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
        self._status_timer.timeout.connect(lambda: self.status.setText(""))

        # écouteurs de la FENÊTRE d'abord : ceux des vues (ajoutés ensuite) sont oubliés à chaque
        # reconstruction de l'interface (langue)
        self.ctrl.on("message", self._message)
        self.ctrl.on("navigate", self.show_view)
        self.ctrl.on("drive", self._drive_changed)
        self.ctrl.on("drives", self._drive_changed)
        self.ctrl.on("downloads", self._badge)
        self.ctrl.on("download_update", lambda _j: self._badge())
        self.ctrl.on("library", self._library_changed)
        self.ctrl.on("rebuild_ui", self.rebuild_ui)
        self.ctrl.on("restyle", self.restyle)
        self.ctrl.on("zoom", self.restyle)
        self.ctrl.on("analysis", self._analysis_changed)
        self._listener_mark = self.ctrl.listener_mark()
        self._build()
        self._bind_shortcuts()
        self._place_window(settings)

        self.show_view("home")
        self._drive_changed()
        self._splash = splash
        QTimer.singleShot(150, self.ctrl.startup)

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
        right = vbox(spacing=0)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.status = label("", "dim")
        self.status.setContentsMargins(theme.px(18), theme.px(2), theme.px(18), theme.px(4))
        right.addWidget(self.status)
        body.addLayout(right, 1)
        self.views = {}
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
        lay = vbox(bar, margins=theme.px(8), spacing=theme.px(2))
        head = hbox(spacing=theme.px(8))
        self.logo = label()
        self.logo.setPixmap(logo_pixmap(theme.px(24), theme.ACCENT))
        head.addWidget(self.logo)
        self.logo_text = label("DJSync", "h2")
        head.addWidget(self.logo_text)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(theme.px(12))

        for key, text_key, icon_name, _cls in TABS:
            b = button(t(text_key), lambda k=key: self.show_view(k), kind="nav")
            b.setCheckable(True)
            b.setIcon(qicon(icon_name, 16, theme.DIM))
            b.setIconSize(QSize(theme.px(16), theme.px(16)))
            b._icon_name = icon_name  # type: ignore[attr-defined]
            lay.addWidget(b)
            self._nav[key] = b
        lay.addStretch(1)

        # ---- analyse en arrière-plan (visible depuis tous les onglets)
        an = panel()
        self.an_box = an
        al = vbox(an, margins=theme.px(6), spacing=theme.px(3))
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
        self.an_open = icon_button("go", lambda: self.ctrl._emit("show_unanalysed"), t("lib.unanalysed"), size=12)
        ah.insertWidget(1, self.an_open)
        an.hide()
        lay.addWidget(an)

        # ---- clé active + remplissage
        usb = panel()
        self.usb_box = usb
        ul = vbox(usb, margins=theme.px(6), spacing=theme.px(3))
        self.usb_title = label(t("nav.active_drive").upper(), "section")
        self.usb_label = label("", wrap=True)
        self.usb_bar = QProgressBar()
        self.usb_bar.setRange(0, 1000)
        self.usb_bar.setTextVisible(False)
        self.usb_free = label("", "dim")
        for w in (self.usb_title, self.usb_label, self.usb_bar, self.usb_free):
            ul.addWidget(w)
        lay.addSpacing(theme.px(6))
        lay.addWidget(usb)

        self.help_btn = button(t("help.button"), self.open_help, kind="nav")
        self.help_btn.setIcon(qicon("help", 16, theme.DIM))
        lay.addSpacing(theme.px(4))
        lay.addWidget(self.help_btn)
        return bar

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
        theme.apply(self.qapp, s.zoom)
        self.setWindowIcon(QIcon(logo_pixmap(64, theme.ACCENT)))
        self.logo.setPixmap(logo_pixmap(theme.px(24), theme.ACCENT))
        for b in list(self._nav.values()) + [self.help_btn]:
            b.setIconSize(QSize(theme.px(16), theme.px(16)))
        for view in self.views.values():
            view.on_scale()
        self.player_bar.on_scale()
        self._compact = None
        self._update_compact()
        if self._current:
            self.show_view(self._current)

    def _analysis_changed(self) -> None:
        """Carte « Analyse » de la barre latérale : visible tant que la file d'analyse tourne."""
        q = self.ctrl.analysis
        if not q.running:
            self.an_box.hide()
            return
        self.an_box.show()
        self.an_bar.setValue(int(1000 * q.done / max(1, q.total)))
        compact = bool(self._compact)
        name = q.current if len(q.current) <= 40 else q.current[:39] + "…"
        self.an_label.setText("" if compact else f"{q.done} / {q.total}" + (f"  ·  {name}" if name else ""))
        self.an_label.setVisible(not compact)
        self.an_title.setText("" if compact else (t("analysis.stopping") if q.cancelled else t("nav.analysing")).upper())
        self.an_stop.setEnabled(not q.cancelled)

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
        for w in (self.usb_title, self.usb_label, self.usb_free):
            w.setVisible(not compact)
        self._analysis_changed()
        self._drive_changed()

    def resizeEvent(self, e: Any) -> None:     # noqa: N802
        super().resizeEvent(e)
        if self._nav:
            self._update_compact()

    # --------------------------------------------------------------------- navigation
    def _nav_text(self, key: str, text_key: str) -> str:
        text = t(text_key)
        if key == "downloads" and self.ctrl.active_jobs:
            text += f"  ({self.ctrl.active_jobs})"
        return text

    def show_view(self, key: str) -> None:
        if key not in self.views:
            return
        self._current = key
        for k, b in self._nav.items():
            active = k == key
            b.setChecked(active)
            b.setIcon(qicon(b._icon_name, 16, theme.ACCENT if active else theme.DIM))  # type: ignore[attr-defined]
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
        if drive:
            self.usb_label.setText(drive.label or str(drive.root))
            self.usb_label.setProperty("role", "accent")
            try:
                usage = shutil.disk_usage(drive.root)
                used = 1 - usage.free / max(usage.total, 1)
                self.usb_bar.setValue(int(used * 1000))
                self.usb_free.setText(t("nav.free_space", free=human_size(usage.free), total=human_size(usage.total)))
                show_bar = True
            except OSError:
                self.usb_free.setText("")
        elif self.ctrl.drives:
            self.usb_label.setText(t("nav.drive_not_connected"))
            self.usb_label.setProperty("role", "warn")
        else:
            self.usb_label.setText(t("nav.no_drive"))
            self.usb_label.setProperty("role", "dim")
        restyle(self.usb_label)
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

    def open_help(self) -> None:
        from .help_dialog import HelpDialog

        HelpDialog(self)

    # ------------------------------------------------------------------- état
    def _message(self, kind: str, text: str) -> None:
        self.status.setText(text)
        self.status.setProperty("role", status_role(kind))
        restyle(self.status)
        self._status_timer.start(12000 if kind in ("error", "warn") else 6000)

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
