"""1.4.4 (C15) : page « Mode live » (compacte) et pas à pas de la première fois.

Champ unique recherche / lien (même moteur que Rechercher, sources et qualité des réglages), résultats avec
« Ajouter au live », sons du live avec leur état et l'heure, « Terminer le live ». Le travail est dans
`live_service.LiveService` (`ctrl.live`).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from PySide6.QtWidgets import QApplication, QCheckBox, QStackedWidget, QTreeWidget, QTreeWidgetItem, QWidget

from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label, line_edit, panel, vbox

log = logging.getLogger(__name__)

STATE_ROLE = {"queued": "dim", "downloading": "accent", "analysing": "accent", "ready": "ok", "error": "err"}


class LiveGuide(BaseDialog):
    """Pas à pas en 3 écrans : XML importé dans Rekordbox, arbre « rekordbox xml » affiché, tonalité."""

    def __init__(self, parent: Any, controller: Any, then: Optional[Any] = None) -> None:
        super().__init__(parent, t("live.guide_title"), 560)
        self.ctrl, self._then = controller, then
        self.heading(t("live.guide_title"))
        self.pages = QStackedWidget()
        path = str(controller.live.xml_path())
        for i in (1, 2, 3):
            page = QWidget()
            v = vbox(page, spacing=theme.px(8))
            v.addWidget(label(t("live.guide_step", n=i, total=3), "dim"))
            v.addWidget(label(t(f"live.guide_{i}_title"), "section"))
            v.addWidget(label(t(f"live.guide_{i}", path=path), "", wrap=True))
            if i == 1:
                row = hbox(spacing=theme.px(6))
                row.addWidget(label(path, "dim", wrap=True), 1)
                row.addWidget(button(t("live.copy_path"), self.copy_path, icon="copy"))
                v.addLayout(row)
            v.addStretch(1)
            self.pages.addWidget(page)
        self.body.addWidget(self.pages, 1)
        self.never = QCheckBox(t("live.guide_never"))
        self.body.addWidget(self.never)
        row = hbox(spacing=theme.px(6))
        self.prev_btn = button(t("live.guide_prev"), lambda: self.go(-1), kind="flat", icon="back")
        row.addWidget(self.prev_btn)
        row.addStretch(1)
        self.next_btn = button(t("live.guide_next"), lambda: self.go(1), kind="primary")
        row.addWidget(self.next_btn)
        self.body.addLayout(row)
        self.go(0)
        self.show_dialog()

    def copy_path(self) -> None:
        QApplication.clipboard().setText(str(self.ctrl.live.xml_path()))
        self.ctrl.message("ok", t("live.path_copied"))

    def go(self, step: int) -> None:
        i = self.pages.currentIndex() + step
        if i >= self.pages.count():
            self.finish()
            return
        i = max(0, i)
        self.pages.setCurrentIndex(i)
        self.prev_btn.setEnabled(i > 0)
        self.next_btn.setText(t("live.guide_done") if i == self.pages.count() - 1 else t("live.guide_next"))

    def finish(self) -> None:
        s = self.ctrl.settings
        if self.never.isChecked() and not getattr(s, "live_guide_done", False):
            s.live_guide_done = True
            self.ctrl.save_settings_quiet()
        then, self._then = self._then, None
        self.close()
        if then is not None:
            then()


class LivePage(BaseDialog):
    as_page = True
    modal = False
    back_keeps_page = True

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("live.title"), 720, 560)
        self.ctrl = controller
        self.results: List[Any] = []
        self.session = controller.live.ensure()
        self.heading(t("live.title"), t("live.sub", date=self.session.date))
        # champ unique : recherche ou lien
        row = hbox(spacing=theme.px(6))
        self.entry = line_edit(t("live.placeholder"), "search", big=True)
        self.entry.returnPressed.connect(self.search)
        row.addWidget(self.entry, 1)
        self.search_btn = button(t("live.search"), self.search, kind="primary", icon="search")
        row.addWidget(self.search_btn)
        self.body.addLayout(row)
        self.found = QTreeWidget()
        self.found.setObjectName("live_found")
        self.found.setRootIsDecorated(False)
        self.found.setHeaderLabels([t("live.col_title"), t("live.col_artist"), t("live.col_length")])
        self.found.setMinimumHeight(theme.px(120))
        self.found.itemDoubleClicked.connect(lambda *_a: self.add_selected())
        self.body.addWidget(self.found, 1)
        add_row = hbox(spacing=theme.px(6))
        self.status = label("", "dim", wrap=True)
        add_row.addWidget(self.status, 1)
        self.add_btn = button(t("live.add"), self.add_selected, kind="primary", icon="plus")
        add_row.addWidget(self.add_btn)
        self.body.addLayout(add_row)
        # sons du live
        card = panel()
        cv = vbox(card, margins=theme.px(10), spacing=theme.px(6))
        cv.addWidget(label(t("live.list_title"), "section"))
        self.tracks = QTreeWidget()
        self.tracks.setObjectName("live_tracks")
        self.tracks.setRootIsDecorated(False)
        self.tracks.setHeaderLabels([t("live.col_time"), t("live.col_title"), t("live.col_state")])
        self.tracks.setMinimumHeight(theme.px(120))
        cv.addWidget(self.tracks, 1)
        bottom = hbox(spacing=theme.px(6))
        self.retry_btn = button(t("live.retry"), self.retry_selected, kind="flat", icon="refresh")
        bottom.addWidget(self.retry_btn)
        bottom.addWidget(button(t("live.guide"), lambda: LiveGuide(self, self.ctrl), kind="flat", icon="help"))
        bottom.addWidget(button(t("live.copy_path"), self.copy_path, kind="flat", icon="copy"))
        bottom.addStretch(1)
        self.finish_btn = button(t("live.finish"), self.finish, icon="check", tooltip=t("live.finish_tip"))
        bottom.addWidget(self.finish_btn)
        cv.addLayout(bottom)
        self.body.addWidget(card, 1)
        controller.on("live", self._live_changed)
        self.refresh()

    # ------------------------------------------------------------------ recherche / lien
    def search(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        self.status.setText(t("live.searching"))
        self.search_btn.setEnabled(False)
        if text.lower().startswith(("http://", "https://")):
            self.ctrl.import_url(text, self._link_found, self._failed)
        else:
            self.ctrl.search(text, self._found, self._failed)

    def _link_found(self, kind: str, data: Any) -> None:
        if kind != "direct":
            self._failed(RuntimeError(t("live.link_kind")))
            return
        self._found(list(getattr(data, "tracks", []) or []))

    def _found(self, results: Any) -> None:
        if self._closed:
            return
        self.search_btn.setEnabled(True)
        self.results = list(results or [])
        self.found.clear()
        for r in self.results:
            secs = int(getattr(r, "duration_seconds", 0) or 0)
            it = QTreeWidgetItem([r.title, r.artist, f"{secs // 60}:{secs % 60:02d}" if secs else ""])
            self.found.addTopLevelItem(it)
        if self.results:
            self.found.setCurrentItem(self.found.topLevelItem(0))
        self.status.setText(t("live.found", n=len(self.results)) if self.results else t("live.nothing"))

    def _failed(self, exc: BaseException) -> None:
        if self._closed:
            return
        self.search_btn.setEnabled(True)
        self.status.setText(t("live.search_failed", error=str(exc)[:200]))

    def add_selected(self) -> None:
        it = self.found.currentItem()
        if it is None:
            return
        i = self.found.indexOfTopLevelItem(it)
        if 0 <= i < len(self.results):
            self._results_by_key = getattr(self, "_results_by_key", {})
            r = self.results[i]
            tr = self.ctrl.live.add(r)
            if tr is not None:
                self._results_by_key[tr.key] = r

    def retry_selected(self) -> None:
        it = self.tracks.currentItem()
        if it is None:
            return
        i = self.tracks.indexOfTopLevelItem(it)
        s = self.ctrl.live.session
        if s is None or not 0 <= i < len(s.tracks):
            return
        tr = s.tracks[i]
        if tr.status == "error":
            self.ctrl.live.retry(tr, getattr(self, "_results_by_key", {}).get(tr.key))

    def copy_path(self) -> None:
        QApplication.clipboard().setText(str(self.ctrl.live.xml_path()))
        self.ctrl.message("ok", t("live.path_copied"))

    def finish(self) -> None:
        from .dialogs import ConfirmDialog

        ConfirmDialog(self, t("live.finish"), t("live.finish_confirm"), lambda: self.ctrl.live.finish(),
                      confirm_text=t("live.finish"), detail=t("live.finish_detail"))

    # ------------------------------------------------------------------ état
    def _live_changed(self, *_a: Any) -> None:
        if self._closed:
            return
        try:
            self.refresh()
        except RuntimeError:                       # page détruite
            pass

    def refresh(self) -> None:
        s = self.ctrl.live.session
        self.tracks.clear()
        if s is None:
            self.finish_btn.setEnabled(False)
            return
        for tr in s.tracks:
            state = t(f"live.state_{tr.status}")
            if tr.status == "ready" and tr.seconds:
                state += f" ({tr.seconds:.0f} s)"
            if tr.status == "error" and tr.error:
                state += f" : {tr.error}"
            it = QTreeWidgetItem([tr.added_at, f"{tr.artist} - {tr.title}" if tr.artist else tr.title, state])
            it.setToolTip(2, state)
            color = {"ready": theme.GOOD, "error": theme.ERR}.get(tr.status, theme.DIM)
            from PySide6.QtGui import QBrush, QColor

            it.setForeground(2, QBrush(QColor(color)))
            self.tracks.addTopLevelItem(it)
        self.finish_btn.setEnabled(any(tr.ready for tr in s.tracks))


def open_live(parent: Any, controller: Any) -> Optional[LivePage]:
    """« Mode live » : la première fois, le pas à pas d'abord (sauf « ne plus afficher »)."""
    win = parent.window() if parent is not None else None

    def go() -> Optional[LivePage]:
        if win is not None and hasattr(win, "reopen_dialog_page"):
            page = win.reopen_dialog_page(LivePage)
            if page is not None:
                return page
        page = LivePage(parent, controller)
        page.show_dialog()
        return page

    if not getattr(controller.settings, "live_guide_done", False) and not getattr(controller, "_live_guided", False):
        controller._live_guided = True
        LiveGuide(parent, controller, then=go)
        return None
    return go()

