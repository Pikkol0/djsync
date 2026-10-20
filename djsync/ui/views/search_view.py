"""Vue Recherche : recherche pendant la frappe, filtres, tableau de résultats.

Chaque ligne a sa propre flèche « ↓ » (télécharger ce son) ; le bouton du bas télécharge la
sélection. Double-clic / Entrée : préécoute ; la file d'écoute suit les résultats (Suivant).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from ...i18n import plural, t
from ...models import SEARCH_MODE_LABELS, SearchMode, TrackResult
from ..dialogs import FiltersPopup
from ..widgets import TrackTable, button, hbox, icon_button, label, restyle
from .common import View, ask_and_download, result_columns, result_row

DEBOUNCE_MS = 450      # pause de frappe avant de lancer la recherche
MIN_CHARS = 2


class SearchView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._tracks: Dict[str, TrackResult] = {}
        self._token = 0
        self._last_query = ""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._debounced)

        self.root.addLayout(self.header(t("tab.search"), "YouTube Music"))
        bar = hbox()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(t("search.placeholder"))
        self.entry.returnPressed.connect(lambda: self.run_search(force=True))
        self.entry.textEdited.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.entry, 1)
        self.filter_btn = icon_button("filter", self._open_filters, t("search.filters"))
        bar.addWidget(self.filter_btn)
        self.search_btn = button(t("action.search"), lambda: self.run_search(force=True), kind="primary")
        bar.addWidget(self.search_btn)
        self.root.addLayout(bar)
        self.info = label("", "dim")
        self.root.addWidget(self.info)

        self.table = TrackTable(self, result_columns(), click_columns=("dl",))
        self.table.set_empty("", t("search.empty_title"), t("search.empty_sub"))
        self.table.on_double = self._play
        self.table.on_select = lambda _ids: self._refresh_buttons()
        self.table.on_cell_click = self._cell_click
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)

        actions = hbox()
        self.preview_btn = button(t("action.listen"), self._preview)
        actions.addWidget(self.preview_btn)
        actions.addStretch(1)
        self.dl_btn = button(t("action.download"), self._download, kind="primary")
        actions.addWidget(self.dl_btn)
        self.root.addLayout(actions)
        self._refresh_filter_label()
        self._refresh_buttons()

    def on_show(self) -> None:
        self.entry.setFocus()

    def search_for(self, query: str) -> None:
        """Depuis l'omnibar de l'Accueil."""
        self.entry.setText(query)
        self.run_search(force=True)

    # --------------------------------------------------------------- filtres
    def _refresh_filter_label(self) -> None:
        s = self.ctrl.settings
        active = bool(s.exclude_words.strip()) or s.search_mode != SearchMode.ALL.value
        self.filter_btn.setCheckable(True)
        self.filter_btn.setChecked(active)
        restyle(self.filter_btn)

    def _open_filters(self) -> None:
        def apply(words: str, mode: str) -> None:
            self.ctrl.settings.exclude_words, self.ctrl.settings.search_mode = words, mode
            self.ctrl.settings.save()
            self._refresh_filter_label()
            if self.entry.text().strip():
                self.run_search(force=True)

        FiltersPopup(self, self.ctrl.settings.exclude_words, self.ctrl.settings.search_mode, apply)
        self._refresh_filter_label()

    def _filter_summary(self) -> str:
        s = self.ctrl.settings
        parts = []
        try:
            mode = SearchMode(s.search_mode)
        except ValueError:
            mode = SearchMode.ALL
        if mode != SearchMode.ALL:
            parts.append(SEARCH_MODE_LABELS[mode])
        if s.exclude_words.strip():
            parts.append(t("search.without", words=s.exclude_words.strip()))
        return "  ·  " + "  ·  ".join(parts) if parts else ""

    # -------------------------------------------------------------- recherche
    def _debounced(self) -> None:
        query = self.entry.text().strip()
        if len(query) >= MIN_CHARS and query != self._last_query:
            self.run_search()

    def run_search(self, force: bool = False) -> None:
        self._debounce.stop()
        query = self.entry.text().strip()
        if not query or (query == self._last_query and not force and self.table.total):
            return
        self._last_query = query
        self._token += 1
        token = self._token
        self.info.setText(t("search.running"))
        self.table.show_skeleton()

        def ok(results: List[TrackResult]) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self._tracks = {x.video_id: x for x in results}
            self.table.set_empty("", t("search.no_result_title"), t("search.no_result_sub"))
            self.table.set_rows([result_row(x) for x in results], reset_sort=True, keep_selection=False)
            dups = sum(1 for x in results if x.is_duplicate)
            tail = "  ·  " + t("search.in_library", n=dups) if dups else ""
            self.info.setText(plural("search.results_one", "search.results_many", len(results))
                              + self._filter_summary() + tail)
            self._refresh_buttons()
            self.ctrl.enrich_views(results, self._on_views)

        def err(exc: BaseException) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self._last_query = ""
            self.table.set_empty("", t("search.failed"), self.ctrl.error_text(exc))
            self.table.set_rows([], keep_selection=False)
            self.info.setText(t("search.failed"))

        self.ctrl.search(query, ok, err)

    def _on_views(self, video_id: str, views: int) -> None:
        track = self._tracks.get(video_id)
        if track is None or not self.winfo_exists():
            return
        track = replace(track, views=views)
        self._tracks[video_id] = track
        row = self.table.row(video_id)
        if row is not None:
            row.data = track
            self.table.update_values(video_id, views=track.views_str)

    # ---------------------------------------------------------------- actions
    def _selected(self) -> List[TrackResult]:
        return [self._tracks[i] for i in self.table.selected_iids() if i in self._tracks]

    def _refresh_buttons(self) -> None:
        n = len(self.table.selected_iids())
        self.dl_btn.setText(t("action.download_n", n=n) if n else t("action.download"))
        self.dl_btn.setEnabled(bool(n))
        self.preview_btn.setEnabled(bool(n))

    def _play(self, iid: str) -> None:
        shown = [self._tracks[i] for i in self.table.displayed_iids() if i in self._tracks]
        target = self._tracks.get(iid)
        if target is not None:
            self.ctrl.play_queue(shown, shown.index(target))

    def _preview(self) -> None:
        sel = self.table.selected_iids()
        if sel:
            self._play(sel[0])

    def _download(self) -> None:
        ask_and_download(self, self.ctrl, self._selected())

    def _cell_click(self, iid: str, key: str) -> None:
        if key == "dl" and iid in self._tracks:
            self.table.select([iid])
            ask_and_download(self, self.ctrl, [self._tracks[iid]])

    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        return [(t("action.listen"), self._preview), (t("dl.picker_title"), self._download)]

    def refresh_duplicates(self) -> None:
        """Re-marque les doublons après un téléchargement ou un changement de clé."""
        tracks = list(self._tracks.values())
        if not tracks:
            return

        def done(annotated: List[TrackResult]) -> None:
            if not self.winfo_exists():
                return
            for x in annotated:
                self._tracks[x.video_id] = x
                row = self.table.row(x.video_id)
                if row is not None:
                    row.data = x
                    row.tags = ("dup",) if x.is_duplicate else ()
                    self.table.update_values(x.video_id, lib=t("track.already") if x.is_duplicate else "")

        self.ctrl.reannotate(tracks, done)
