"""1.4.4 (C223) : liste « Sons supprimés » (Bibliothèque ▸ ☰), avec recherche, « Retélécharger »,
« Retirer de la liste » et « Vider la liste ». Retélécharger : par le lien d'origine s'il y en a un (un son), sinon
« Artiste - Titre » cherchés comme une playlist (Rechercher ▸ Lien ou playlist, C216)."""
from __future__ import annotations

import logging
from typing import Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from ..core.deleted_log import DeletedLog, DeletedTrack, search
from ..i18n import plural, t
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import button, hbox, label, line_edit

log = logging.getLogger(__name__)


class DeletedTracksDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("deleted.title"), 560, 520)
        self.ctrl = controller
        lib = controller.library
        self.log = DeletedLog(lib.backup_dir) if lib is not None else None
        self.heading(t("deleted.title"), t("deleted.sub"))
        self.search = line_edit(t("deleted.search"), "search")
        self.search.textChanged.connect(lambda _t: self._fill())
        self.body.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._refresh)
        self.list.itemDoubleClicked.connect(lambda _i: self.redownload())
        self.body.addWidget(self.list, 1)
        self.empty = label(t("deleted.empty"), "dim", wrap=True)
        self.body.addWidget(self.empty)
        row = hbox(spacing=theme.px(6))
        self.clear_btn = button(t("deleted.clear"), self._ask_clear, kind="flat", icon="trash")
        row.addWidget(self.clear_btn)
        row.addStretch(1)
        self.remove_btn = button(t("deleted.remove"), self.remove, icon="close")
        row.addWidget(self.remove_btn)
        self.redl_btn = button(t("deleted.redownload"), self.redownload, kind="primary", icon="download")
        row.addWidget(self.redl_btn)
        self.body.addLayout(row)
        self._items: List[DeletedTrack] = []
        self._fill()
        self.show_dialog()

    def _fill(self) -> None:
        self._items = search(self.log.entries() if self.log else [], self.search.text())
        self.list.clear()
        for x in self._items:
            it = QListWidgetItem(f"{x.query}\n{x.date.replace('T', ' ')}" + ("  ·  " + t("deleted.has_link")
                                                                             if x.url else ""))
            it.setToolTip(x.url or t("deleted.no_link"))
            self.list.addItem(it)
        self.empty.setVisible(not self._items)
        self.clear_btn.setEnabled(bool(self.log and self.log.entries()))
        self._refresh()

    def selected(self) -> List[DeletedTrack]:
        return [self._items[self.list.row(it)] for it in self.list.selectedItems()]

    def _refresh(self) -> None:
        n = len(self.selected())
        self.redl_btn.setEnabled(n > 0)
        self.remove_btn.setEnabled(n > 0)
        self.redl_btn.setText(plural("deleted.redownload_one", "deleted.redownload_many", n) if n > 1
                              else t("deleted.redownload"))

    def redownload(self) -> None:
        sel = self.selected()
        if not sel:
            return
        win = self.parent()                                   # fenêtre principale
        self.close()
        win.show_view("import")
        view = win.views["import"]
        if len(sel) == 1 and sel[0].url:
            view.open_url(sel[0].url)
            return
        view.url.setText("\n".join(x.query for x in sel))
        view.analyse()

    def remove(self) -> None:
        sel = self.selected()
        if sel and self.log:
            self.log.remove(sel)
            self._fill()

    def _ask_clear(self) -> None:
        if not self.log:
            return
        ConfirmDialog(self, t("deleted.clear"), t("deleted.clear_confirm"), self._clear,
                      confirm_text=t("deleted.clear"), danger=True)

    def _clear(self) -> None:
        self.log.clear()
        self._fill()
