"""Vue Accueil : barre de recherche / lien (« omnibar ») et clés USB détectées.

Une ligne par clé : nom, chemin, espace libre, contenu (titres, playlists, non analysés),
export.pdb, et l'action utile (connecter, ouvrir la bibliothèque, analyser).
"""
from __future__ import annotations

from typing import Any, List

from PySide6.QtWidgets import QGridLayout, QLineEdit, QProgressBar, QWidget

from ...i18n import plural, t
from .. import theme
from ..ctrl.library_ops import DriveSummary
from ..widgets import button, hbox, label, panel, vbox
from .common import View, human_size


class HomeView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._summaries: List[DriveSummary] = []
        self.root.addWidget(label(t("home.title"), "title"))
        self.root.addWidget(label(t("home.subtitle"), "dim"))

        row = hbox()
        self.omnibar = QLineEdit()
        self.omnibar.setPlaceholderText(t("home.omnibar"))
        self.omnibar.returnPressed.connect(self._go)
        self.omnibar.textEdited.connect(lambda _t: self._typed())
        row.addWidget(self.omnibar, 1)
        row.addWidget(button("→", self._go, kind="primary"))
        self.root.addLayout(row)
        self.omni_hint = label(t("home.omnibar_hint"), "faint")
        self.root.addWidget(self.omni_hint)

        head = hbox()
        head.addWidget(label(t("home.drives"), "h2"))
        head.addStretch(1)
        head.addWidget(button(t("action.refresh"), self.ctrl.refresh_drives, kind="flat"))
        self.root.addSpacing(theme.px(10))
        self.root.addLayout(head)
        self.cards = QWidget()
        self.cards_lay = vbox(self.cards, spacing=theme.px(6))
        self.root.addWidget(self.cards)

        self.root.addSpacing(theme.px(10))
        self.root.addWidget(label(t("home.tools"), "h2"))
        tools = hbox()
        for key, cmd in (("home.tool_analysis", self._analysis),
                         ("home.tool_duplicates", self._duplicates),
                         ("home.tool_import", lambda: self.ctrl._emit("navigate", "import")),
                         ("home.tool_help", self._help)):
            tools.addWidget(button(t(key), cmd))
        tools.addStretch(1)
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
        self.omni_hint.setText(t("home.omnibar_hint_url") if url else t("home.omnibar_hint"))

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

    # ------------------------------------------------------------------- clés
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.ctrl.drive_summaries(self._show)

    def _show(self, summaries: List[DriveSummary]) -> None:
        if not self.winfo_exists():
            return
        self._summaries = summaries
        while self.cards_lay.count():
            item = self.cards_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not summaries:
            box = panel()
            lay = vbox(box, margins=theme.px(12))
            lay.addWidget(label(t("home.no_drive_title"), "h2"))
            lay.addWidget(label(t("home.no_drive_sub"), "dim", wrap=True))
            self.cards_lay.addWidget(box)
            return
        for s in summaries:
            self.cards_lay.addWidget(self._card(s))

    def _card(self, s: DriveSummary) -> QWidget:
        box = panel()
        grid = QGridLayout(box)
        m = theme.px(10)
        grid.setContentsMargins(m, m, m, m)
        grid.setHorizontalSpacing(theme.px(14))
        name = label(s.drive.label or str(s.drive.root), "h2")
        grid.addWidget(name, 0, 0)
        state = t("home.connected") if s.connected else t("home.detected")
        grid.addWidget(label(f"{s.drive.root}  ·  {state}", "accent" if s.connected else "dim"), 1, 0)
        info = []
        if s.tracks >= 0:
            info.append(plural("lib.tracks_one", "lib.tracks_many", s.tracks) + "  ·  "
                        + plural("home.playlists_one", "home.playlists_many", s.playlists))
        info.append(t("home.pdb_yes") if s.has_pdb else t("home.pdb_no"))
        grid.addWidget(label("\n".join(info), "dim"), 2, 0)
        if s.unanalysed > 0:
            grid.addWidget(label(plural("home.unanalysed_one", "home.unanalysed_many", s.unanalysed), "warn"), 3, 0)
        if s.total:
            used = 1 - s.free / s.total
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 1000)
            bar.setValue(int(used * 1000))
            bar.setFixedWidth(theme.px(180))
            grid.addWidget(bar, 0, 1)
            grid.addWidget(label(t("nav.free_space", free=human_size(s.free), total=human_size(s.total)), "dim"), 1, 1)
        actions = hbox()
        if s.connected:
            actions.addWidget(button(t("home.open_library"), lambda: self.ctrl._emit("navigate", "library"),
                                     kind="primary"))
            if s.unanalysed > 0:
                actions.addWidget(button(t("action.analyse"), lambda: self.ctrl._emit("show_unanalysed")))
        else:
            actions.addWidget(button(t("action.connect"), lambda d=s.drive: self.ctrl.connect(d), kind="primary"))
        actions.addStretch(1)
        grid.addLayout(actions, 4, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        return box

    # ------------------------------------------------------------------- outils
    def _analysis(self) -> None:
        self.ctrl._emit("show_unanalysed")

    def _duplicates(self) -> None:
        if not self.ctrl.has_library:
            self.ctrl.message("error", t("msg.no_drive"))
            return
        from ..duplicates_dialog import DuplicatesDialog

        DuplicatesDialog(self, self.ctrl)

    def _help(self) -> None:
        self.window().open_help()
