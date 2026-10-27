"""Vue Accueil : barre de recherche / lien (« omnibar ») et clés USB détectées.

Une ligne par clé : nom, chemin, espace libre, contenu (titres, playlists, non analysés),
export.pdb, et l'action utile (connecter, ouvrir la bibliothèque, analyser).
"""
from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QProgressBar, QWidget

from ...i18n import plural, t
from .. import theme
from ..ctrl.library_ops import DriveSummary
from ..icons import qicon
from ..widgets import button, chip, hbox, icon_label, label, line_edit, panel, vbox
from .common import View, human_size


class HomeView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._summaries: List[DriveSummary] = []
        self._pending_diag: str = ""          # bibliothèque à diagnostiquer dès qu'elle est ouverte
        self.root.setSpacing(theme.px(10))
        self.root.addWidget(label(t("home.title"), "title"))

        row = hbox(spacing=theme.px(8))
        self.omnibar = line_edit(t("home.omnibar"), "search", big=True)
        self.omnibar.returnPressed.connect(self._go)
        self.omnibar.textChanged.connect(lambda _t: self._typed())
        row.addWidget(self.omnibar, 1)
        self.go_btn = button("", self._go, kind="primary", icon="go", tooltip=t("action.search"))
        self.go_btn.setMinimumHeight(self.omnibar.sizeHint().height())
        row.addWidget(self.go_btn)
        self.root.addLayout(row)

        head = hbox()
        head.addWidget(label(t("home.drives"), "h2"))
        head.addStretch(1)
        head.addWidget(button(t("action.refresh"), self.ctrl.refresh_drives, kind="flat", icon="refresh"))
        self.root.addSpacing(theme.px(8))
        self.root.addLayout(head)
        self.cards = QWidget()
        self.cards_lay = vbox(self.cards, spacing=theme.px(8))
        self.root.addWidget(self.cards)

        self.root.addSpacing(theme.px(8))
        self.root.addWidget(label(t("home.tools"), "h2"))
        tools = hbox(spacing=theme.px(10))
        for key, icon, cmd in (("home.tool_analysis", "wave", self._analysis),
                               ("home.tool_duplicates", "duplicates", self._duplicates),
                               ("home.tool_uniformize", "tag", self._uniformize),
                               ("home.tool_import", "import", lambda: self.ctrl._emit("navigate", "import"))):
            b = button(t(key), cmd, kind="tile", icon=icon)
            b.setIconSize(QSize(theme.px(20), theme.px(20)))
            b.setIcon(qicon(icon, 20, theme.ACCENT))
            tools.addWidget(b, 1)
        self.root.addLayout(tools)
        self.root.addStretch(1)

        controller.on("drives", self.refresh)
        controller.on("drive", self.refresh)
        controller.on("library", self.refresh)

    # ------------------------------------------------------------------ omnibar
    def focus_omnibar(self) -> None:
        self.omnibar.setFocus()
        self.omnibar.selectAll()

    def _typed(self) -> None:
        url = self.ctrl.is_url(self.omnibar.text())
        self.go_btn.setIcon(qicon("import" if url else "go", 16, theme.ON_ACCENT))
        self.go_btn.setToolTip(t("import.read_link") if url else t("action.search"))

    def _go(self) -> None:
        text = self.omnibar.text().strip()
        if not text:
            return
        app = self.window()
        if self.ctrl.is_url(text):
            app.show_view("import")
            app.views["import"].open_url(text)
        else:
            app.show_view("search")
            app.views["search"].search_for(text)

    def open_space(self) -> None:
        app = self.window()
        app.show_view("settings")
        app.views["settings"].show_space()

    def open_settings(self, section: str) -> None:
        app = self.window()
        app.show_view("settings")
        app.views["settings"].show_section(section)

    # ------------------------------------------------------------------- clés
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.ctrl.drive_summaries(self._show)
        if self._pending_diag and self.ctrl.has_library and self.ctrl.drive is not None \
                and str(self.ctrl.drive.db_path) == self._pending_diag:
            self._pending_diag = ""
            self._open_diagnostic()

    def _show(self, summaries: List[DriveSummary]) -> None:
        if not self.winfo_exists():
            return
        self._summaries = summaries
        while self.cards_lay.count():
            item = self.cards_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        unprepared = list(getattr(self.ctrl, "unprepared", []) or [])
        if not summaries and not unprepared:
            box = panel()
            lay = hbox(box, margins=theme.px(14), spacing=theme.px(12))
            lay.addWidget(icon_label("usb", 28, theme.FAINT))
            text = vbox(spacing=theme.px(2))
            text.addWidget(label(t("home.no_drive_title"), "h2"))
            text.addWidget(label(t("home.no_drive_sub"), "dim", wrap=True))
            lay.addLayout(text, 1)
            self.cards_lay.addWidget(box)
            return
        for s in summaries:
            self.cards_lay.addWidget(self._card(s))
        for u in unprepared:                                   # T02 : après les bibliothèques utilisables
            self.cards_lay.addWidget(self._unprepared_card(u))

    def _unprepared_card(self, u: Any) -> QWidget:
        """1.2.4 (T02) : clé branchée sans bibliothèque, avec ce qu'il faut faire."""
        from ...db.usb import filesystem_compat

        box = panel()
        lay = hbox(box, margins=theme.px(14), spacing=theme.px(14))
        lay.addWidget(icon_label("usb", 28, theme.FAINT), 0, Qt.AlignTop)
        mid = vbox(spacing=theme.px(6))
        top = hbox(spacing=theme.px(8))
        top.addWidget(label(u.drive.label or str(u.drive.root), "h2"))
        top.addWidget(chip(t("home.unprepared_chip"), "chip_warn"))
        compat = filesystem_compat(u.filesystem)
        if u.filesystem:
            fs = chip(u.filesystem if compat == "ok" else f"{u.filesystem} ⚠", "chip" if compat == "ok" else "chip_warn")
            tips = {"ok": "home.fs_ok", "recent_only": "home.fs_recent_only", "unsupported": "home.fs_unsupported"}
            fs.setToolTip(t(tips.get(compat, "home.fs_ok"), fs=u.filesystem))
            top.addWidget(fs)
        top.addStretch(1)
        mid.addLayout(top)
        key = "home.unprepared_legacy" if u.kind == "legacy" else "home.unprepared_blank"
        mid.addWidget(label(t(key), "dim", wrap=True))
        if compat == "unsupported":
            mid.addWidget(label(t("home.unprepared_fs", fs=u.filesystem), "dim", wrap=True))
        lay.addLayout(mid, 1)
        return box

    def _card(self, s: DriveSummary) -> QWidget:
        box = panel()
        lay = hbox(box, margins=theme.px(14), spacing=theme.px(14))
        icon = "computer" if s.is_local else "usb"
        lay.addWidget(icon_label(icon, 28, theme.ACCENT if s.connected else theme.FAINT), 0, Qt.AlignTop)

        mid = vbox(spacing=theme.px(6))
        top = hbox(spacing=theme.px(8))
        top.addWidget(label(s.drive.label or str(s.drive.root), "h2"))
        top.addWidget(chip(t("home.connected") if s.connected else t("home.detected"),
                           "chip_ok" if s.connected else "chip"))
        if s.busy:
            busy = chip(t("local.rekordbox_open"), "chip_warn")
            busy.setToolTip(t("local.rekordbox_open_tip"))
            top.addWidget(busy)
        top.addStretch(1)
        mid.addLayout(top)
        chips = hbox(spacing=theme.px(6))
        stale_detail = None                         # 1.3.0-rc.3 (C36) : export.pdb pas à jour sur cette clé
        if s.tracks >= 0:
            chips.addWidget(chip(plural("lib.tracks_one", "lib.tracks_many", s.tracks)))
            chips.addWidget(chip(plural("home.playlists_one", "home.playlists_many", s.playlists)))
        if s.unanalysed > 0:
            chips.addWidget(chip(plural("home.unanalysed_one", "home.unanalysed_many", s.unanalysed), "chip_warn"))
        if s.is_local:
            chips.addWidget(chip(t("local.collection")))
        else:
            if not s.has_pdb:                       # 1.3.0 (T01) : anciennes platines sans playlists
                pdb = chip(t("home.pdb_short_no"), "chip_warn")
                pdb.setToolTip(t("home.pdb_no_tip"))
            elif s.connected and s.pdb_state == "stale":
                pdb = chip(t("home.pdb_stale"), "chip_warn")
                pdb.setToolTip(t("home.pdb_stale_tip", detail=s.pdb_problem or "?"))
                stale_detail = s.pdb_problem
            else:
                pdb = chip(t("home.pdb_short_yes"), "chip_good")          # C29
                pdb.setToolTip(t("home.pdb_yes"))
            pdb.setCursor(Qt.PointingHandCursor)              # 1.3.1 (C28) : ouvre la section des réglages
            pdb.mousePressEvent = lambda _e: self.open_settings("libraries")
            chips.addWidget(pdb)
            if s.filesystem:
                from ...db.usb import filesystem_compat

                compat = filesystem_compat(s.filesystem)
                fs = chip(s.filesystem if compat == "ok" else f"{s.filesystem} ⚠", "chip" if compat == "ok" else "chip_warn")
                tips = {"ok": "home.fs_ok", "recent_only": "home.fs_recent_only", "unsupported": "home.fs_unsupported"}
                fs.setToolTip(t(tips.get(compat, "home.fs_ok"), fs=s.filesystem))
                chips.addWidget(fs)
        chips.addStretch(1)
        mid.addLayout(chips)
        if stale_detail is not None:
            detail = label(t("home.pdb_detail", detail=stale_detail or "?"), "dim")
            detail.setWordWrap(True)
            mid.addWidget(detail)
        actions = hbox()
        if s.connected:
            actions.addWidget(button(t("home.open_library"), lambda: self.ctrl._emit("navigate", "library"),
                                     kind="primary", icon="library"))
            if s.unanalysed > 0:
                actions.addWidget(button(t("action.analyse"), lambda: self.ctrl._emit("show_unanalysed"), icon="wave"))
            if stale_detail is not None:
                upd = button(t("home.pdb_update"), icon="refresh")
                upd.setToolTip(t("home.pdb_update_tip"))
                upd.clicked.connect(lambda _c=False, b=upd: self._update_pdb(b))
                actions.addWidget(upd)
        else:
            actions.addWidget(button(t("action.connect"), lambda d=s.drive: self.ctrl.connect(d), kind="primary",
                                     icon=icon))
        diag = button(t("diag.button"), lambda d=s.drive, c=s.connected: self.diagnose(d, c), icon="diagnostic")
        diag.setToolTip(t("diag.button_tip"))
        actions.addWidget(diag)
        actions.addStretch(1)
        mid.addLayout(actions)
        lay.addLayout(mid, 1)

        if s.total:
            side = vbox(spacing=theme.px(6))
            used = 1 - s.free / s.total
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 1000)
            bar.setValue(int(used * 1000))
            bar.setFixedWidth(theme.px(200))
            free = label(t("nav.free_space", free=human_size(s.free), total=human_size(s.total)), "dim")
            if s.connected:                                   # 1.3.1 (C27) : détail de l'espace
                for w in (free, bar):
                    w.setCursor(Qt.PointingHandCursor)
                    w.setToolTip(t("home.space_tip"))
                    w.mousePressEvent = lambda _e: self.open_space()
            side.addWidget(free)
            side.addWidget(bar)
            side.addStretch(1)
            lay.addLayout(side)
        box.setToolTip(str(s.drive.db_dir) if s.is_local else str(s.drive.root))
        return box

    def _update_pdb(self, btn: Any) -> None:
        """1.3.0-rc.3 (C36) : « Mettre à jour export.pdb » depuis la carte de la clé."""
        btn.setEnabled(False)
        btn.setText(t("home.pdb_updating"))

        def restore(_x: Any = None) -> None:
            try:
                btn.setEnabled(True)
                btn.setText(t("home.pdb_update"))
            except RuntimeError:                    # carte déjà redessinée
                pass

        self.ctrl.pdb_sync_now(ok=restore, failed=restore)

    # ------------------------------------------------------------------- outils
    def diagnose(self, drive: Any, connected: bool) -> None:
        """Bouton « Diagnostic » d'une carte : ouvre d'abord cette bibliothèque si besoin."""
        if connected and self.ctrl.has_library:
            self._open_diagnostic()
            return
        self._pending_diag = str(drive.db_path)
        self.ctrl.connect(drive)

    def _open_diagnostic(self) -> None:
        self.window().open_diagnostic("missing")        # 1.3.1 (C41/C43) : Diagnostic en onglets

    def _analysis(self) -> None:
        self.ctrl._emit("show_unanalysed")

    def _uniformize(self) -> None:
        """1.3.0 (C25) : Uniformiser depuis l'Accueil, portée au choix."""
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        from ..uniformize_page import ScopeDialog

        ScopeDialog(self, self.ctrl)

    def _duplicates(self) -> None:
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        self.window().open_diagnostic("dup")

