"""Vue Recherche : recherche pendant la frappe, filtres, tableau de résultats.

Chaque ligne a sa propre flèche « ↓ » (télécharger ce son) ; le bouton du bas télécharge la
sélection. Double-clic / Entrée : préécoute ; la file d'écoute suit les résultats (Suivant).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox

from ...i18n import plural, t
from ...models import SEARCH_MODE_LABELS, SearchMode, TrackResult
from ..dialogs import FiltersPopup
from .. import theme
from ..icons import qicon
from ..widgets import TrackTable, button, hbox, label, line_edit, restyle
from .common import focus_list, View, ask_and_download, result_columns, result_row

DEBOUNCE_MS = 450      # pause de frappe avant de lancer la recherche
MIN_CHARS = 2


class SearchView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._tracks: Dict[str, TrackResult] = {}
        self._token = 0
        self._last_query = ""
        self._albums: List[TrackResult] = []          # 1.2.1 (C09) : liste d'albums sous un album ouvert
        self._album_open: Any = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._debounced)

        self.root.addLayout(self.header(t("tab.search")))
        bar = hbox(spacing=theme.px(8))
        # 1.2.1 (C08) : où chercher (Tout / Titre / Artiste / Album)
        self._field_labels = {"all": t("search.field_all"), "title": t("search.field_title"),
                              "artist": t("search.field_artist"), "album": t("search.field_album")}
        self.field_menu = QComboBox()
        self.field_menu.addItems(list(self._field_labels.values()))
        self.field_menu.setCurrentText(self._field_labels.get(controller.settings.search_field, self._field_labels["all"]))
        self.field_menu.setToolTip(t("search.field_tip"))
        self.field_menu.currentTextChanged.connect(self._field_changed)
        bar.addWidget(self.field_menu)
        self.entry = line_edit(t("search.placeholder"), "search", big=True)
        self.entry.returnPressed.connect(lambda: self.run_search(force=True))
        self.entry.textEdited.connect(lambda _t: self._debounce.start())
        bar.addWidget(self.entry, 1)
        self.filter_btn = button(t("search.filters_short"), self._open_filters, icon="filter",
                                 tooltip=t("search.filters"))
        self.filter_btn.setMinimumHeight(self.entry.sizeHint().height())
        bar.addWidget(self.filter_btn)
        self.field_menu.setMinimumHeight(self.entry.sizeHint().height())
        self.root.addLayout(bar)
        info_row = hbox(spacing=theme.px(8))
        self.back_btn = button(t("search.back_to_albums"), self._close_album, kind="flat", icon="back")
        self.back_btn.hide()
        info_row.addWidget(self.back_btn)
        self.info = label("", "dim")
        info_row.addWidget(self.info, 1)
        self.root.addLayout(info_row)

        self.table = TrackTable(self, result_columns(), loader=loader, show_covers=True, click_columns=("dl",))
        self.remember_layout(self.table, "search")
        self.table.set_empty("search", t("search.empty_title"))
        self.table.on_double = self._play
        self.table.on_select = lambda _ids: self._refresh_buttons()
        self.table.on_cell_click = self._cell_click
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)

        actions = hbox()
        self.preview_btn = button(t("action.listen"), self._preview, icon="play")
        actions.addWidget(self.preview_btn)
        actions.addStretch(1)
        self.dl_btn = button(t("action.download"), self._download, kind="primary", icon="download")
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
    def _field_changed(self, text: str) -> None:
        s = self.ctrl.settings
        s.search_field = next((k for k, v in self._field_labels.items() if v == text), "all")
        try:
            s.save()
        except OSError:
            pass
        if self.entry.text().strip():
            self.run_search(force=True)

    def _refresh_filter_label(self) -> None:
        s = self.ctrl.settings
        active = (bool(s.exclude_words.strip()) or s.search_mode != SearchMode.ALL.value or bool(s.search_max_minutes)
                  or s.search_hide_owned)
        self.filter_btn.setProperty("kind", "primary" if active else "")
        self.filter_btn.setIcon(qicon("filter", 16, theme.ON_ACCENT if active else theme.TEXT))
        restyle(self.filter_btn)

    def _open_filters(self) -> None:
        s = self.ctrl.settings

        def apply(words: str, mode: str, minutes: int = 0, hide_owned: bool = False) -> None:
            s.exclude_words, s.search_mode = words, mode
            s.search_max_minutes, s.search_hide_owned = minutes, hide_owned
            s.save()
            self._refresh_filter_label()
            if self.entry.text().strip():
                self.run_search(force=True)

        FiltersPopup(self, s.exclude_words, s.search_mode, apply, max_minutes=s.search_max_minutes,
                     hide_owned=s.search_hide_owned)
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
        if s.search_max_minutes:
            parts.append(t("filters.under_minutes", n=s.search_max_minutes))
        if s.search_hide_owned:
            parts.append(t("search.hiding_owned"))
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

        self._albums, self._album_open = [], None
        self.back_btn.hide()

        def ok(results: List[TrackResult]) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self._show_results(results)


        def err(exc: BaseException) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self._last_query = ""
            self.table.set_empty("warn", t("search.failed"), self.ctrl.error_text(exc))
            self.table.set_rows([], keep_selection=False)
            self.info.setText(t("search.failed"))

        self.ctrl.search(query, ok, err)

    def _show_results(self, results: List[TrackResult], summary: str = "") -> None:
        hidden = 0
        if self.ctrl.settings.search_hide_owned:          # 1.2.1 (C08)
            kept = [x for x in results if not x.is_duplicate]
            hidden, results = len(results) - len(kept), kept
        self._tracks = {x.video_id: x for x in results}
        self.table.set_empty("search", t("search.no_result_title"))
        self.table.set_rows([result_row(x) for x in results], reset_sort=True, keep_selection=False)
        dups = sum(1 for x in results if x.is_duplicate)
        tail = "  ·  " + t("search.in_library", n=dups) if dups else ""
        if hidden:
            tail += "  ·  " + t("search.hidden_owned", n=hidden)
        if summary:
            self.info.setText(summary + tail)
        elif results and all(x.is_album for x in results):
            self.info.setText(plural("search.albums_one", "search.albums_many", len(results)) + "  ·  "
                              + t("search.open_album_hint"))
        else:
            self.info.setText(plural("search.results_one", "search.results_many", len(results))
                              + self._filter_summary() + tail)
        self._refresh_buttons()
        self.ctrl.enrich_views([x for x in results if not x.is_album], self._on_views)

    # --------------------------------------------------------- albums (1.2.1, C09)
    def _open_album(self, album: TrackResult) -> None:
        if not self._albums:
            self._albums = [x for x in self._tracks.values() if x.is_album]
        self._album_open = album
        self._token += 1
        token = self._token
        self.info.setText(t("search.loading_album", name=album.title))
        self.table.show_skeleton()

        def ok(tracks: List[TrackResult]) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self.back_btn.show()
            self._show_results(tracks, t("search.album_summary", name=album.title, artist=album.artist,
                                         n=len(tracks)))
            self.table.select(self.table.displayed_iids())           # prêt pour « Tout télécharger »

        def err(exc: BaseException) -> None:
            if token != self._token or not self.winfo_exists():
                return
            self.back_btn.show()
            self.table.set_empty("warn", t("search.failed"), self.ctrl.error_text(exc))
            self.table.set_rows([], keep_selection=False)

        self.ctrl.album_tracks(album.video_id, ok, err)

    def _close_album(self) -> None:
        self._token += 1
        self._album_open = None
        self.back_btn.hide()
        albums, self._albums = self._albums, []
        self._show_results(albums)

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
        return [self._tracks[i] for i in self.table.selected_iids() if i in self._tracks and not self._tracks[i].is_album]

    def _refresh_buttons(self) -> None:
        n = len(self._selected())
        self.dl_btn.setText(t("action.download_n", n=n) if n else t("action.download"))
        self.dl_btn.setEnabled(bool(n))
        self.preview_btn.setEnabled(bool(self.table.selected_iids()))

    def _play(self, iid: str) -> None:
        target = self._tracks.get(iid)
        if target is not None and target.is_album:
            self._open_album(target)
            return
        shown = [self._tracks[i] for i in self.table.displayed_iids() if i in self._tracks and not self._tracks[i].is_album]
        if target is not None:
            self.ctrl.play_queue(shown, shown.index(target))
            focus_list(self.table)

    def _preview(self) -> None:
        sel = self.table.selected_iids()
        if sel:
            self._play(sel[0])

    def _download(self) -> None:
        # album ouvert : nom proposé pour une nouvelle playlist = nom de l'album
        ask_and_download(self, self.ctrl, self._selected(),
                         new_name=self._album_open.title if self._album_open is not None else "")

    def _cell_click(self, iid: str, key: str) -> None:
        if key == "dl" and iid in self._tracks and self._tracks[iid].is_album:
            self._open_album(self._tracks[iid])
            return
        if key == "dl" and iid in self._tracks:
            self.table.select([iid])
            ask_and_download(self, self.ctrl, [self._tracks[iid]])

    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        if len(iids) == 1 and iids[0] in self._tracks and self._tracks[iids[0]].is_album:
            return [(t("search.open_album"), lambda: self._open_album(self._tracks[iids[0]]), "go")]
        return [(t("action.listen"), self._preview, "play"), (t("dl.picker_title"), self._download, "download")]

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
