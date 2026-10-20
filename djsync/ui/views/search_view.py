"""Vue Recherche : recherche dynamique (pendant la frappe), filtres, tableau de résultats.

Chaque ligne a sa propre icône « ↓ » (télécharger ce son) ; le bouton global télécharge la
sélection. Double-clic / Entrée : préécoute ; la file d'écoute suit les résultats (Suivant).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from ...i18n import plural, t
from ...models import SEARCH_MODE_LABELS, SearchMode, TrackResult
from .. import theme
from ..dialogs import FiltersPopup
from ..widgets import TrackTable, icon_button
from .common import View, ask_and_download, result_columns, result_row

DEBOUNCE_MS = 450      # pause de frappe avant de lancer la recherche
MIN_CHARS = 2


class SearchView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._tracks: Dict[str, TrackResult] = {}
        self._token = 0
        self._after: Optional[str] = None
        self._last_query = ""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.header(t("tab.search"), "YouTube Music").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=24)
        bar.grid_columnconfigure(0, weight=1)
        self.entry = theme.entry(bar, t("search.placeholder"))
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self.run_search())
        self.entry.bind("<KeyRelease>", self._typed)
        self.filter_btn = icon_button(bar, "filter", self._open_filters, t("search.filters"))
        self.filter_btn.grid(row=0, column=1, padx=(8, 0))
        self.search_btn = icon_button(bar, "search", self.run_search, t("action.search"), kind="primary")
        self.search_btn.grid(row=0, column=2, padx=(8, 0))

        self.info = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.info.grid(row=2, column=0, sticky="ew", padx=26, pady=(8, 0))

        self.table = TrackTable(self, result_columns(), loader, click_columns=("dl",))
        self.table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(6, 10))
        self.table.set_empty("search", t("search.empty_title"), t("search.empty_sub"))
        self.table.on_double = self._play
        self.table.on_select = lambda _ids: self._refresh_buttons()
        self.table.on_cell_click = self._cell_click
        self.table.menu_builder = self._menu

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        self.preview_btn = theme.button(actions, t("action.listen"), self._preview, kind="ghost", width=110)
        self.preview_btn.pack(side="left")
        self.dl_btn = theme.button(actions, t("action.download"), self._download, kind="primary", width=170)
        self.dl_btn.pack(side="right")
        self._refresh_filter_label()
        self._refresh_buttons()

    def on_show(self) -> None:
        self.entry.focus_set()

    def search_for(self, query: str) -> None:
        """Depuis l'omnibar de l'Accueil."""
        self.entry.delete(0, "end")
        self.entry.insert(0, query)
        self.run_search()

    # --------------------------------------------------------------- filtres
    def _refresh_filter_label(self) -> None:
        s = self.ctrl.settings
        active = bool(s.exclude_words.strip()) or s.search_mode != SearchMode.ALL.value
        self.filter_btn.configure(border_color=theme.ACCENT if active else theme.BORDER)

    def _open_filters(self) -> None:
        def apply(words: str, mode: str) -> None:
            self.ctrl.settings.exclude_words, self.ctrl.settings.search_mode = words, mode
            self.ctrl.settings.save()
            self._refresh_filter_label()
            if self.entry.get().strip():
                self.run_search(force=True)

        FiltersPopup(self, self.ctrl.settings.exclude_words, self.ctrl.settings.search_mode, apply)

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
    def _typed(self, e: Any) -> None:
        if e.keysym in ("Return", "KP_Enter", "Up", "Down", "Left", "Right", "Escape", "Tab"):
            return
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(DEBOUNCE_MS, self._debounced)

    def _debounced(self) -> None:
        self._after = None
        query = self.entry.get().strip()
        if len(query) >= MIN_CHARS and query != self._last_query:
            self.run_search()

    def run_search(self, force: bool = False) -> None:
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        query = self.entry.get().strip()
        if not query or (query == self._last_query and not force and self.table.total):
            return
        self._last_query = query
        self._token += 1
        token = self._token
        self.info.configure(text=t("search.running"), text_color=theme.DIM)
        self.table.show_skeleton(8)

        def ok(results: List[TrackResult]) -> None:
            if token != self._token:
                return
            self._tracks = {x.video_id: x for x in results}
            self.table.set_rows([result_row(x) for x in results], reset_sort=True, keep_selection=False)
            self.table.set_empty("search", t("search.no_result_title"), t("search.no_result_sub"))
            dups = sum(1 for x in results if x.is_duplicate)
            tail = "  ·  " + t("search.in_library", n=dups) if dups else ""
            self.info.configure(text=plural("search.results_one", "search.results_many", len(results))
                                + self._filter_summary() + tail, text_color=theme.DIM)
            self._refresh_buttons()
            self.ctrl.enrich_views(results, self._on_views)

        def err(exc: BaseException) -> None:
            if token != self._token:
                return
            self._last_query = ""
            self.table.set_rows([], keep_selection=False)
            self.table.set_empty("search", t("search.failed"), self.ctrl.error_text(exc))
            self.info.configure(text=t("search.failed"), text_color=theme.ERR)

        self.ctrl.search(query, ok, err)

    def _on_views(self, video_id: str, views: int) -> None:
        track = self._tracks.get(video_id)
        if track is None:
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
        self.dl_btn.configure(text=t("action.download_n", n=n) if n else t("action.download"),
                              state="normal" if n else "disabled")
        self.preview_btn.configure(state="normal" if n else "disabled")

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
            for x in annotated:
                self._tracks[x.video_id] = x
                row = self.table.row(x.video_id)
                if row is not None:
                    row.data = x
                    self.table.update_values(x.video_id, lib=t("track.already") if x.is_duplicate else "")
                    self.table.set_tags(x.video_id, *(("dup",) if x.is_duplicate else ()))

        self.ctrl.reannotate(tracks, done)
