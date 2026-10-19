"""Vue Recherche : barre + bouton Filtres, tableau (pochette asynchrone, type, vues, durée, doublon)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

import customtkinter as ctk

from ...models import SEARCH_MODE_LABELS, SearchMode, TrackResult
from .. import theme
from ..dialogs import FiltersPopup
from ..widgets import TrackTable
from .common import View, ask_and_download, result_columns, result_row


class SearchView(View):
    title = "Recherche"

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._tracks: Dict[str, TrackResult] = {}
        self._token = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header("Recherche", "YouTube Music").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=24)
        bar.grid_columnconfigure(0, weight=1)
        self.entry = theme.entry(bar, "Titre, artiste… (Entrée pour chercher)")
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self.run_search())
        self.filter_btn = theme.button(bar, "Filtres", self._open_filters, kind="ghost", width=theme.px(90))
        self.filter_btn.grid(row=0, column=1, padx=(8, 0))
        self.search_btn = theme.button(bar, "Rechercher", self.run_search, kind="primary", width=theme.px(110))
        self.search_btn.grid(row=0, column=2, padx=(8, 0))

        self.info = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.info.grid(row=2, column=0, sticky="nw", padx=26, pady=(8, 0))
        # le tableau occupe la ligne 3 (la ligne 2 ne sert qu'à l'info)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)

        self.table = TrackTable(self, result_columns(), loader)
        self.table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(6, 10))
        self.table.set_empty_text("Tapez une recherche pour trouver des morceaux.")
        self.table.on_double = lambda iid: self._preview()
        self.table.on_select = lambda _ids: self._refresh_buttons()
        self.table.menu_builder = self._menu

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        self.preview_btn = theme.button(actions, "▶  Écouter", self._preview, kind="ghost", width=theme.px(110))
        self.preview_btn.pack(side="left")
        self.dl_btn = theme.button(actions, "Télécharger", self._download, kind="primary", width=theme.px(170))
        self.dl_btn.pack(side="right")
        self._refresh_filter_label()
        self._refresh_buttons()

    def on_show(self) -> None:
        self.entry.focus_set()

    # --------------------------------------------------------------- filtres
    def _refresh_filter_label(self) -> None:
        s = self.ctrl.settings
        active = bool(s.exclude_words.strip()) or s.search_mode != SearchMode.ALL.value
        self.filter_btn.configure(text="Filtres •" if active else "Filtres",
                                  text_color=theme.ACCENT if active else theme.TEXT)

    def _open_filters(self) -> None:
        def apply(words: str, mode: str) -> None:
            self.ctrl.settings.exclude_words, self.ctrl.settings.search_mode = words, mode
            self.ctrl.settings.save()
            self._refresh_filter_label()
            if self.entry.get().strip():
                self.run_search()

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
            parts.append(f"sans : {s.exclude_words.strip()}")
        return "  ·  " + "  ·  ".join(parts) if parts else ""

    # -------------------------------------------------------------- recherche
    def run_search(self) -> None:
        query = self.entry.get().strip()
        if not query:
            return
        self._token += 1
        token = self._token
        self.search_btn.configure(state="disabled", text="Recherche…")
        self.info.configure(text="Recherche en cours…", text_color=theme.DIM)
        self.table.set_empty_text("")

        def ok(results: List[TrackResult]) -> None:
            if token != self._token:
                return
            self._finish()
            self._tracks = {t.video_id: t for t in results}
            self.table.set_rows([result_row(t) for t in results], reset_sort=True, keep_selection=False)
            self.table.set_empty_text("Aucun résultat. Essayez d'autres mots ou assouplissez les filtres.")
            dups = sum(1 for t in results if t.is_duplicate)
            tail = f"  ·  {dups} déjà en bibliothèque" if dups else ""
            self.info.configure(text=f"{len(results)} résultat(s){self._filter_summary()}{tail}", text_color=theme.DIM)
            self._refresh_buttons()
            self.ctrl.enrich_views(results, self._on_views)

        def err(exc: BaseException) -> None:
            if token != self._token:
                return
            self._finish()
            self.info.configure(text="La recherche a échoué.", text_color=theme.ERR)
            self.ctrl._on_error(exc)

        self.ctrl.search(query, ok, err)

    def _finish(self) -> None:
        self.search_btn.configure(state="normal", text="Rechercher")

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
        self.dl_btn.configure(text=f"Télécharger ({n})" if n else "Télécharger", state="normal" if n else "disabled")
        self.preview_btn.configure(state="normal" if n else "disabled")

    def _preview(self) -> None:
        sel = self._selected()
        if sel:
            self.ctrl.preview(sel[0])

    def _download(self) -> None:
        ask_and_download(self, self.ctrl, self._selected())

    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        return [("Écouter", self._preview), ("Télécharger vers…", self._download)]

    def refresh_duplicates(self) -> None:
        """Re-marque les doublons après un téléchargement ou un changement de clé."""
        tracks = list(self._tracks.values())
        if not tracks:
            return

        def done(annotated: List[TrackResult]) -> None:
            for t in annotated:
                self._tracks[t.video_id] = t
                row = self.table.row(t.video_id)
                if row is not None:
                    row.data = t
                    self.table.update_values(t.video_id, lib="✓ déjà" if t.is_duplicate else "")
                    self.table.set_tags(t.video_id, *(("dup",) if t.is_duplicate else ()))

        self.ctrl.reannotate(tracks, done)
