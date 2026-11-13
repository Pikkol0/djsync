"""1.4.1 (C133) : page « Haute qualité » du volet, seule page de la recherche haute qualité (D9).

Trois zones : recherche et résultats (sources libres Internet Archive, Audius ; Soulseek s'il est activé),
bandeau d'état de Soulseek avec « Réglages Soulseek », transferts pair-à-pair (P2PPanel, tel quel).
Dans Rechercher, le mode « Haute qualité » ouvre cette page avec le texte déjà tapé.

* C134 : un seul filtre (`core.search.ResultFilter`), mémorisé à part ; tri d'un clic sur la valeur brute.
* C170 + C175 : métadonnées des sources (année, licence, pochette, dossier du pair) et qualité annoncée en
  texte doré ou argenté (« annoncé, vérifié après téléchargement ») ; la qualité mesurée vient après.
* C171 : progression « 2 / 3 sources terminées · 54 résultats · 12 s », délai de Soulseek à part.
* C167 : une ligne Soulseek ne s'écoute pas : « Écouter un équivalent (YouTube Music) ».
* C147 : un élément Internet Archive à plusieurs titres est une ligne d'album, dépliée en place (▸).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.search import ResultFilter, announced, passes
from ...i18n import t
from ...models import TrackResult
from .. import theme
from ..icons import qicon
from ..search_progress import SearchProgress
from ..table import Column, Row
from ..widgets import TrackTable, button, hbox, label, line_edit, panel, restyle
from .common import View, ask_and_download, focus_list, result_row

SLSK_WAIT_S = 8.0             # délai d'écoute des réponses Soulseek (core.soulseek.SEARCH_SECONDS)


def hq_columns() -> List[Column]:
    """Colonnes de la page ; tri sur la valeur brute (débit en nombre, durée en secondes, taille en octets)."""
    def quality_key(r: Row) -> Any:
        a = announced(r.data) if r.data is not None else None
        return None if a is None or not a.fmt else (a.lossless, a.kbps or 0)

    def kbps_key(r: Row) -> Any:
        a = announced(r.data) if r.data is not None else None
        return None if a is None or not a.kbps else a.kbps

    return [
        Column("title", t("track.title"), 300, stretch=True, min_width=170),
        Column("artist", t("track.artist"), 170, priority=1),
        Column("type", t("track.type"), 80, priority=4, tip=t("hq.type_tip"),
               sort=lambda r: (0 if r.data is not None and r.data.is_album else 1)),
        Column("duration", t("track.duration"), 92, "e", priority=2,
               sort=lambda r: r.data.duration_seconds if r.data is not None and r.data.duration_seconds else None),
        Column("quality", t("hq.col_quality"), 120, priority=2, tip=t("hq.announced_tip"), sort=quality_key),
        Column("bitrate", t("hq.col_kbps"), 70, "e", priority=6, sort=kbps_key),
        Column("size", t("track.size"), 76, "e", priority=5, tip=t("track.size_tip"),
               sort=lambda r: r.data.slsk.size if r.data is not None and r.data.slsk is not None else None),
        Column("year", t("hq.col_year"), 56, "e", priority=5,
               sort=lambda r: r.data.year if r.data is not None and r.data.year else None),
        Column("license", t("hq.col_license"), 110, priority=6),
        Column("source", t("track.source"), 120, priority=3),
        Column("peer", t("hq.col_peer"), 120, priority=5, tip=t("hq.peer_tip"),
               sort=lambda r: r.data.slsk.speed if r.data is not None and r.data.slsk is not None else None),
        Column("lib", t("track.in_library"), 80, "center", priority=5),
        Column("dl", "", 36, "center", sortable=False, min_width=30),
    ]


def hq_row(track: TrackResult, parent: Optional[str] = None, expanded: bool = False) -> Row:
    """Ligne d'un résultat (ou d'un titre déplié sous son album, `parent`)."""
    from ...models import format_duration

    row = result_row(track)
    v = row.values
    a = announced(track)
    r = track.slsk
    v["source"] = "Soulseek" if r is not None else track.source_label
    v["quality"] = a.label
    if a.level:                                     # C175 : texte doré / argenté = qualité ANNONCÉE (D14)
        v["quality__color"] = theme.GOLD if a.level == "gold" else theme.SILVER
    v["quality__tip"] = t("hq.announced_tip")
    v["bitrate"] = str(a.kbps) if a.kbps else ""
    v["year"] = str(track.year) if track.year else ""
    v["license"] = track.license or ""
    v["peer"] = ""
    if r is not None:                               # C170 : attributs du protocole, dossier parent
        v["peer"] = v.get("type", "")
        if r.folder:
            v["title__tip"] = t("hq.folder", name=r.folder)
    v.pop("source__color", None)
    if track.is_album:                              # C147 : un album se repère d'un coup d'œil
        n = track.track_count or len(track.tracks)
        v["type"], v["type__icon"] = t("hq.type_album"), "disc"
        v["title"] = ("▾ " if expanded else "▸ ") + track.title
        v["artist"] = track.artist
        v["duration"] = t("hq.album_count", n=n) if n else t("hq.type_album")
        if track.duration_seconds:
            v["duration__tip"] = t("hq.album_length", length=format_duration(track.duration_seconds))
        v["dl"] = "›"
        row.tags = tuple(row.tags) + ("album",)
    else:
        v["type"], v["type__icon"] = t("hq.type_track"), "music"
    if parent is not None:                          # titre déplié : en retrait, avec son numéro
        no = f"{track.track_no}. " if track.track_no else ""
        v["title"] = "      " + no + track.title
        v["_parent"] = parent
        row.iid = f"{parent}#{track.video_id}"
    return row


class HqView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._results: List[TrackResult] = []
        self._tracks: Dict[str, TrackResult] = {}       # iid -> son (titres dépliés compris)
        self._expanded: set = set()
        self._token = 0
        self._query = ""
        self._filter = ResultFilter.from_dict(controller.settings.hq_filters)

        self.root.addLayout(self.header(t("tab.hq")))
        bar = hbox(spacing=theme.px(8))
        self.entry = line_edit(t("search.placeholder_hq"), "search", big=True)
        self.entry.returnPressed.connect(lambda: self.run_search(force=True))
        bar.addWidget(self.entry, 1)
        self.filter_btn = button(t("search.filters_short"), self._open_filters, icon="filter",
                                 tooltip=t("search.filters"))
        self.filter_btn.setMinimumHeight(self.entry.sizeHint().height())
        bar.addWidget(self.filter_btn)
        self.root.addLayout(bar)
        self.progress = SearchProgress()                 # C171
        self.root.addWidget(self.progress)
        info_row = hbox(spacing=theme.px(8))
        self.info = label(t("hq.intro"), "dim", wrap=True)
        info_row.addWidget(self.info, 1)
        self.root.addLayout(info_row)
        self.equiv = label("", "accent", wrap=True)       # C167 : « Version approchante : … »
        self.equiv.hide()
        self.root.addWidget(self.equiv)

        self.table = TrackTable(self, hq_columns(), loader=loader, show_covers=True, click_columns=("dl",))
        self.table.fit_content = True
        self.remember_layout(self.table, "hq")
        self.table.row_filter = self._row_passes
        self.table.parent_of = lambda r: r.values.get("_parent")
        self.table.set_empty("search", t("hq.empty_title"), t("hq.empty_sub"))
        self.table.on_double = self._play
        self.table.on_select = lambda _ids: self._refresh_buttons()
        self.table.on_cell_click = self._cell_click
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)
        self.limits = label(t("hq.archive_limits"), "faint", wrap=True)      # C147 : dit à l'écran
        self.limits.hide()
        self.root.addWidget(self.limits)

        actions = hbox()
        self.preview_btn = button(t("action.listen"), self._preview, icon="play")
        actions.addWidget(self.preview_btn)
        self.equiv_btn = button(t("hq.equivalent"), self._equivalent, icon="play", tooltip=t("hq.equivalent_tip"))
        actions.addWidget(self.equiv_btn)
        actions.addStretch(1)
        self.album_btn = button(t("hq.download_album"), self._download_album, icon="download")
        actions.addWidget(self.album_btn)
        self.dl_btn = button(t("action.download"), self._download, kind="primary", icon="download")
        actions.addWidget(self.dl_btn)
        self.root.addLayout(actions)

        # zone 2 : état de Soulseek (les réglages restent dans Paramètres)
        self.slsk_box = panel()
        sl = hbox(self.slsk_box, margins=theme.px(10), spacing=theme.px(8))
        self.slsk_state = label("", "dim", wrap=True)
        sl.addWidget(self.slsk_state, 1)
        self.slsk_btn = button(t("hq.slsk_settings"), lambda: self.ctrl._emit("open_settings_section", "download"),
                               kind="flat", icon="settings")
        sl.addWidget(self.slsk_btn)
        self.root.addWidget(self.slsk_box)
        # zone 3 : transferts pair-à-pair (composant de Téléchargements, réutilisé tel quel)
        from ..p2p_panel import P2PPanel

        self.p2p = P2PPanel(controller)
        self.root.addWidget(self.p2p)

        controller.on("slsk", self._refresh_slsk)
        controller.on("settings_saved", self._refresh_slsk)
        controller.on("slsk_search", self.search_for)
        self._refresh_filter_label()
        self._refresh_slsk()
        self._refresh_buttons()

    # ------------------------------------------------------------------ zone 2 : Soulseek
    def _refresh_slsk(self) -> None:
        if not self.winfo_exists():
            return
        c, s = self.ctrl, self.ctrl.settings
        if not c.slsk_ready:
            text = t("hq.slsk_off")
        elif c.slsk is not None and getattr(c.slsk, "connected", False):
            port = s.soulseek_port or t("hq.port_default")
            share = t("slsk.sharing_on") if s.soulseek_share else t("slsk.sharing_off")
            text = t("hq.slsk_on", user=s.soulseek_user, port=port, share=share)
        else:
            text = t("hq.slsk_ready")
        self.slsk_state.setText(text)

    # ------------------------------------------------------------------ filtres (C134)
    def _row_passes(self, row: Row) -> bool:
        track = row.data
        if track is None:
            return True
        if row.values.get("_parent"):
            from ...core.search import replace_kind

            return passes(track, replace_kind(self._filter))
        return passes(track, self._filter)

    def _refresh_filter_label(self) -> None:
        active = self._filter.active
        self.filter_btn.setText(t("hq.filters_on") if active else t("search.filters_short"))
        self.filter_btn.setProperty("kind", "primary" if active else "")
        self.filter_btn.setIcon(qicon("filter", 16, theme.ON_ACCENT if active else theme.TEXT))
        restyle(self.filter_btn)

    def _open_filters(self) -> None:
        from ..dialogs import HqFiltersPopup

        HqFiltersPopup(self, self._filter, self.set_filter, self.ctrl.free_sources_list(), self.ctrl.slsk_ready)

    def set_filter(self, f: ResultFilter) -> None:
        """Appliqué tout de suite, aussi aux résultats qui arrivent ensuite (sources au fil de l'eau)."""
        self._filter = f
        self.ctrl.settings.hq_filters = f.to_dict()
        self.ctrl.save_settings_quiet()
        self._refresh_filter_label()
        self.table.refilter()
        self._show_summary()

    # ------------------------------------------------------------------ recherche
    def on_show(self) -> None:
        self._refresh_slsk()
        self.entry.setFocus()

    def search_for(self, query: str) -> None:
        """Depuis Rechercher (mode Haute qualité), le Diagnostic, ou un faux sans perte signalé (C46)."""
        self.ctrl._emit("navigate", "hq")
        self.entry.setText(query)
        self.run_search(force=True)

    def run_search(self, force: bool = False) -> None:
        from ..ctrl.soulseek import track_of

        query = self.entry.text().strip()
        if not query or (query == self._query and not force):
            return
        self._query = query
        self._token += 1
        token = self._token
        self._results, self._expanded = [], set()
        self.equiv.hide()
        free: List[TrackResult] = []
        slsk: List[TrackResult] = []
        sources = self.ctrl.free_sources_list() + (["soulseek"] if self.ctrl.slsk_ready else [])
        self.progress.start(sources, SLSK_WAIT_S)
        self.table.show_skeleton()

        def live() -> bool:
            return token == self._token and self.winfo_exists()

        def show() -> None:
            if not live():
                return
            self._results = self._ordered(slsk + free, query)
            self.progress.set_results(len(self._results))
            if not self._results and self.progress.running:
                self.table.show_skeleton()           # B59 : pas « Aucun résultat » tant que ça cherche
                return
            self._fill()

        def got_free(rs: List[TrackResult]) -> None:
            free[:] = rs
            if live():
                for name in self.ctrl.free_sources_list():
                    self.progress.source_done(name)
            show()

        def got_free_part(rs: List[TrackResult]) -> None:
            if live() and not all(self.progress.finished.get(n) for n in self.ctrl.free_sources_list()):
                free[:] = rs
                show()

        def source_done(name: str) -> None:
            if live():
                self.progress.source_done(name)

        def got_slsk(rs: List[Any], final: bool) -> None:
            slsk[:] = [track_of(r) for r in rs]
            if final and live():
                self.progress.source_done("soulseek")
            show()

        self.ctrl.free_search(query, got_free, got_free_part, source_done)
        if self.ctrl.slsk_ready:
            self.ctrl.slsk_search(query, lambda rs: got_slsk(rs, True), lambda rs: got_slsk(rs, False))
        if not sources:
            self.progress.finish()
            show()

    @staticmethod
    def _ordered(results: List[TrackResult], query: str) -> List[TrackResult]:
        """C147 : la recherche d'un artiste montre ses albums d'abord."""
        from ...core.soulseek import _plain

        q = _plain(query)
        first = [x for x in results if x.is_album and _plain(x.artist) == q]
        return first + [x for x in results if x not in first]

    def _fill(self) -> None:
        rows: List[Row] = []
        self._tracks = {}
        for x in self._results:
            open_ = x.video_id in self._expanded
            rows.append(hq_row(x, expanded=open_))
            self._tracks[x.video_id] = x
            if x.is_album and open_:
                for c in x.tracks:
                    row = hq_row(c, parent=x.video_id)
                    rows.append(row)
                    self._tracks[row.iid] = c
        self.table.set_empty("search", t("search.no_result_title"))
        self.table.set_rows(rows, keep_selection=True)
        self.limits.setVisible(any(x.source == "archive" for x in self._results))
        self._show_summary()
        self._refresh_buttons()

    def _show_summary(self) -> None:
        if not self._query:
            return
        shown = [i for i in self.table.displayed_iids() if self.table.row(i) is not None
                 and not self.table.row(i).values.get("_parent")]
        total = len(self._results)
        lossless = sum(1 for x in self._results if announced(x).lossless)
        text = t("hq.results", n=total, lossless=lossless)
        if len(shown) != total:
            text += "  ·  " + t("hq.filtered", n=total - len(shown))
        self.info.setText(text)

    # ------------------------------------------------------------------ albums (C147)
    def toggle_album(self, album_id: str) -> None:
        if album_id in self._expanded:
            self._expanded.discard(album_id)
        else:
            self._expanded.add(album_id)
        self._fill()

    # ------------------------------------------------------------------ actions
    def _selected_rows(self) -> List[TrackResult]:
        return [self._tracks[i] for i in self.table.selected_iids() if i in self._tracks]

    def _selected(self) -> List[TrackResult]:
        return [x for x in self._selected_rows() if not x.is_album]

    def _refresh_buttons(self) -> None:
        sel = self._selected_rows()
        tracks = [x for x in sel if not x.is_album]
        n = len(tracks)
        self.dl_btn.setText(t("action.download_n", n=n) if n else t("action.download"))
        self.dl_btn.setEnabled(bool(n))
        first = sel[0] if sel else None
        slsk = first is not None and first.slsk is not None
        self.preview_btn.setEnabled(first is not None and not slsk and not first.is_album)
        self.preview_btn.setToolTip(t("slsk.no_preview") if slsk else "")
        self.equiv_btn.setVisible(slsk)
        self.album_btn.setVisible(first is not None and first.is_album)

    def _play(self, iid: str) -> None:
        target = self._tracks.get(iid)
        if target is None:
            return
        if target.is_album:
            self.toggle_album(target.video_id)
            return
        if target.slsk is not None:                    # C167 : un équivalent à la place
            self._equivalent()
            return
        shown = [self._tracks[i] for i in self.table.displayed_iids()
                 if i in self._tracks and not self._tracks[i].is_album and self._tracks[i].slsk is None]
        self.ctrl.play_queue(shown, shown.index(target) if target in shown else 0)
        focus_list(self.table)

    def _preview(self) -> None:
        sel = self.table.selected_iids()
        if sel:
            self._play(sel[0])

    def _equivalent(self) -> None:
        sel = [x for x in self._selected_rows() if x.slsk is not None]
        if not sel:
            return

        def played(found: Optional[TrackResult]) -> None:
            if not self.winfo_exists():
                return
            if found is None:
                self.equiv.hide()
                return
            self.equiv.setText(t("hq.equivalent_playing", title=f"{found.artist} - {found.title}".strip(" -")))
            self.equiv.show()

        self.ctrl.play_equivalent(sel[0], played)

    def _download(self) -> None:
        ask_and_download(self, self.ctrl, self._selected())

    def _download_album(self) -> None:
        """Tous les titres ; une playlist au nom de l'album est proposée, jamais créée d'office."""
        album = next((x for x in self._selected_rows() if x.is_album), None)
        if album is not None and album.tracks:
            ask_and_download(self, self.ctrl, list(album.tracks), new_name=album.title)

    def _cell_click(self, iid: str, key: str) -> None:
        x = self._tracks.get(iid)
        if key != "dl" or x is None:
            return
        if x.is_album:
            self.toggle_album(x.video_id)
            return
        self.table.select([iid])
        ask_and_download(self, self.ctrl, [x])

    def _menu(self, iids: List[str]) -> list:
        rows = [self._tracks[i] for i in iids if i in self._tracks]
        if not rows:
            return []
        x = rows[0]
        if len(rows) == 1 and x.is_album:
            label_ = t("hq.collapse") if x.video_id in self._expanded else t("hq.expand")
            return [(label_, lambda: self.toggle_album(x.video_id), "go"),
                    (t("hq.download_album"), self._download_album, "download")]
        entries: list = []
        if x.slsk is not None:
            entries.append((t("hq.equivalent"), self._equivalent, "play"))
        else:
            entries.append((t("action.listen"), self._preview, "play"))
        entries.append((t("dl.picker_title"), self._download, "download"))
        if len(rows) == 1:                                           # 1.4.0 (C10.3) : acheter en WAV
            from .common import buy_entry

            entries += [None, buy_entry(self.ctrl, x.artist, x.title)]
        return entries

    def refresh_duplicates(self) -> None:
        """Re-marque les doublons après un téléchargement ou un changement de bibliothèque."""
        tracks = [x for x in self._results if not x.is_album]
        if not tracks:
            return

        def done(annotated: List[TrackResult]) -> None:
            if not self.winfo_exists():
                return
            by_id = {x.video_id: x for x in annotated}
            self._results = [by_id.get(x.video_id, x) for x in self._results]
            self._fill()

        self.ctrl.reannotate(tracks, done)
