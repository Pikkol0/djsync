"""Vue Import URL : un lien Spotify, YouTube ou SoundCloud (titre unique ou playlist).

  * Spotify    -> liste des morceaux + correspondance YouTube Music (Titre prioritaire / Vidéo
                  prioritaire / Automatique), autre candidat, préécoute, cases à cocher.
  * YouTube / SoundCloud -> téléchargement DIRECT à la source (yt-dlp), sans recherche.
"""
from __future__ import annotations

import logging

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QPlainTextEdit

from ...core.matcher import apply_preference
from ...i18n import LazyLabels, plural, t
from ...models import (
    PREFERENCE_LABELS, Candidate, MatchPreference, MatchResult, ResolvedUrl, SpotifyPlaylist, TrackResult,
    UrlKind, format_duration,
)
from ..dialogs import BaseDialog
from .. import theme
from ..widgets import Column, Row, TrackTable, button, chip, hbox, icon_label, label, line_edit, panel
from .common import CHECKED, UNCHECKED, View, ask_and_download, result_columns, result_row

log = logging.getLogger(__name__)

STATUS_TEXT = LazyLabels(lambda: {"ok": "import.st_ok", "review": "import.st_review", "missing": "import.st_missing",
                                  "duplicate": "import.st_duplicate"})
STATUS_TAG = {"ok": (), "review": ("dim",), "missing": ("err",), "duplicate": ("dup",)}
# 1.4.2 (C209) : un son déjà là a 3 états, un clic passe au suivant : ajouté aux playlists (défaut) ->
# retéléchargé (deuxième exemplaire) -> ignoré (décoché) -> ajouté.
DUP_ADD, DUP_REDL, DUP_SKIP = "add", "redl", "skip"
DUP_NEXT = {DUP_ADD: DUP_REDL, DUP_REDL: DUP_SKIP, DUP_SKIP: DUP_ADD}
DUP_TEXT = LazyLabels(lambda: {DUP_ADD: "import.dup_add", DUP_REDL: "import.dup_redl", DUP_SKIP: "import.dup_skip"})


class PasteListDialog(BaseDialog):
    """Repli quand Spotify refuse la lecture : une ligne par morceau « Artiste - Titre »."""

    def __init__(self, parent: Any, on_ok: Any) -> None:
        super().__init__(parent, t("import.paste_list_title"), 500, 420)
        self._on_ok = on_ok
        self.heading(t("import.paste_list_title"))
        self.box = QPlainTextEdit()
        self.box.setPlaceholderText(t("import.paste_list_hint"))
        self.body.addWidget(self.box, 1)
        self.footer(t("import.analyse_list"), self._ok)
        self.show_dialog()
        self.box.setFocus()

    def _ok(self) -> None:
        text = self.box.toPlainText().strip()
        if text:
            self.close()
            self._on_ok(text)


class ImportView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.mode: Optional[str] = None            # "spotify" | "direct"
        self.matches: List[MatchResult] = []
        self.playlist: Optional[SpotifyPlaylist] = None
        self.resolved: Optional[ResolvedUrl] = None
        self._tracks = {}                           # mode direct : iid -> TrackResult
        self._handle: Any = None
        self._searched: set = set()
        self._token = 0
        try:
            self.preference = MatchPreference(controller.settings.spotify_preference)
        except ValueError:
            self.preference = MatchPreference.AUTO

        from ..search_tabs import add_search_tabs

        add_search_tabs(self, "import")                 # 1.4.2 (C182) : onglets de « Rechercher »
        bar = hbox(spacing=theme.px(8))
        from ...core.urlimport import source_names

        self.url = line_edit(t("import.placeholder", names=source_names()), "import", big=True)
        self.url.returnPressed.connect(self.analyse)
        bar.addWidget(self.url, 1)
        paste = button(t("action.paste"), self._paste_clipboard, icon="clipboard")
        self.go = button(t("import.read_link"), self.analyse, kind="primary", icon="go")
        for b in (paste, self.go):
            b.setMinimumHeight(self.url.sizeHint().height())
            bar.addWidget(b)
        self.root.addLayout(bar)
        self.root.addLayout(self._sources_row())

        # 1.4.3-rc.2 (C206) : limite de Spotify sur sa propre ligne, au-dessus (plus coupée entre les réglages)
        self.note_lbl = label("", "dim", wrap=True)
        self.note_lbl.hide()
        self.root.addWidget(self.note_lbl)
        opts = hbox()
        self.info = label("", "dim")
        opts.addWidget(self.info, 1)
        self.pref_label = label(t("import.matching"), "dim")
        opts.addWidget(self.pref_label)
        self.pref_menu = QComboBox()
        self.pref_menu.addItems(list(PREFERENCE_LABELS.values()))
        self.pref_menu.setCurrentText(PREFERENCE_LABELS[self.preference])
        self.pref_menu.currentTextChanged.connect(self._pref_changed)
        opts.addWidget(self.pref_menu)
        self.paste_list = button(t("import.paste_list"), self._paste_list, kind="flat", icon="playlist")
        opts.addWidget(self.paste_list)
        self.root.addLayout(opts)
        # 1.4.2 (C172) : longue playlist : « 200 premiers titres sur 534 » et « Charger les 200 suivants »
        self.more_box = panel(role="banner")
        more = hbox(self.more_box, margins=theme.px(8), spacing=theme.px(8))
        more.addWidget(icon_label("info", 16, theme.ACCENT))
        self.more_lbl = label("", wrap=True)
        more.addWidget(self.more_lbl, 1)
        self.more_btn = button("", self.load_more, icon="download")
        more.addWidget(self.more_btn)
        self.more_box.hide()
        self.root.addWidget(self.more_box)

        spotify_cols = [
            Column("chk", "", 36, "center", sortable=False, min_width=34),
            Column("source", t("import.col_source"), 240, stretch=True, min_width=140),
            Column("match", t("import.col_match"), 280, stretch=True, min_width=140, priority=1),
            Column("type", t("track.type"), 70, "center", priority=4),
            Column("score", t("import.col_score"), 56, "e", priority=3,
                   sort=lambda r: r.data.candidate.score if r.data and r.data.candidate else None),
            Column("duration", t("track.duration"), 64, "e", priority=2),
            Column("status", t("import.col_status"), 150),
        ]
        self.sp_table = TrackTable(self, spotify_cols, click_columns=("chk",))
        self.sp_table._dup_status_col = True                 # type: ignore[attr-defined]  # C209 : état dans « Statut »
        self.dl_table = TrackTable(self, result_columns(with_check=True, with_download=False), click_columns=("chk",))
        for table in (self.sp_table, self.dl_table):
            table.fit_content = True                         # 1.4.0-rc.4 (C150)
            table.on_cell_click = lambda iid, _k, tb=table: self._toggle(tb, iid)
            table.on_select = lambda _i: self._refresh_buttons()
            table.on_double = lambda _i: self._preview()
            table.menu_builder = self._menu
            from PySide6.QtGui import QKeySequence, QShortcut

            sc = QShortcut(QKeySequence(Qt.Key_Space), table)       # 1.4.0-rc.4 (C148)
            sc.setContext(Qt.WidgetShortcut)
            sc.activated.connect(lambda tb=table: self._toggle_selected(tb))
            self.root.addWidget(table, 1)
        # 1.4.0-rc.2 (B65) : colonnes réglables et retenues, comme dans Rechercher
        self.remember_layout(self.sp_table, "import_match")
        self.remember_layout(self.dl_table, "import")
        self.sp_table.columns[0].on_header = lambda: self._toggle_all(self.sp_table)
        self.dl_table.columns[0].on_header = lambda: self._toggle_all(self.dl_table)
        self.dl_table.set_empty("import", t("import.empty_title"), t("import.empty_sub", names=source_names()))

        actions = hbox()
        self.preview_btn = button(t("action.listen"), self._preview, icon="play")
        actions.addWidget(self.preview_btn)
        self.other_btn = button(t("import.other_match"), self._cycle, icon="refresh")
        actions.addWidget(self.other_btn)
        # 1.4.0-rc.4 (C151) : bouton visible pour le « Free Download » de l'artiste
        self.free_btn = button(t("sc.free_button"), self._open_free, icon="download")
        self.free_btn.setToolTip(t("sc.free_open_tip"))
        self.free_btn.hide()
        actions.addWidget(self.free_btn)
        # 1.4.0-rc.5 (B93) : la page du morceau, toujours proposée : un lien gratuit placé seulement dans la
        # description (ou un « Buy » vers un autre site) n'est pas détecté ; l'utilisateur voit par lui-même
        self.page_btn = button(t("sc.page_button"), self._open_pages, kind="flat", icon="go")
        self.page_btn.setToolTip(t("sc.page_tip"))
        self.page_btn.hide()
        actions.addWidget(self.page_btn)
        actions.addStretch(1)
        self.count_lbl = label("", "dim")                           # 1.4.0-rc.4 (C148) : « 12 / 200 cochés »
        actions.addWidget(self.count_lbl)
        self.dl_btn = button(t("import.download_selection"), self._download, kind="primary", icon="download")
        actions.addWidget(self.dl_btn)
        self.root.addLayout(actions)
        self._show_mode(None)
        self.ctrl.on("library", self._library_changed)

    # ------------------------------------------------------------------ mode
    def _show_mode(self, mode: Optional[str]) -> None:
        self.mode = mode
        self._dup: Dict[Tuple[str, str], str] = {}                      # C209 : état des sons déjà là
        spotify = mode == "spotify"
        self.sp_table.setVisible(spotify)
        self.dl_table.setVisible(not spotify)
        self.pref_menu.setVisible(spotify)
        self.pref_label.setVisible(spotify)
        self.other_btn.setVisible(spotify)
        if mode != "direct":
            self.more_box.hide()                           # C172 : seulement pour une playlist YouTube / SoundCloud
        self._refresh_buttons()

    @property
    def table(self) -> TrackTable:
        return self.sp_table if self.mode == "spotify" else self.dl_table

    def on_show(self) -> None:
        self.url.setFocus()

    # --------------------------------------------------------------- analyse
    def _paste_clipboard(self) -> None:
        try:
            text = QApplication.clipboard().text().strip()
        except Exception:  # noqa: BLE001 - presse-papiers vide/inaccessible
            log.debug("Handled error in _paste_clipboard", exc_info=True)  # 1.4.3 (A3-4)
            return
        self.url.setText(text)
        if text:
            self.analyse()

    def open_url(self, url: str) -> None:
        """Depuis l'omnibar de l'Accueil."""
        self.url.setText(url)
        self.analyse()

    def _set_go(self, enabled: bool) -> None:
        self.go.setEnabled(enabled)
        self.go.setText(t("import.read_link") if enabled else t("import.reading"))

    def analyse(self) -> None:
        url = self.url.text().strip()
        if not url:
            return
        self._cancel_matching()
        self._token += 1
        token = self._token
        self._set_go(False)
        self.info.setText(t("import.reading_link"))
        self.note_lbl.hide()
        self.table.show_skeleton(6)

        def ok(kind: str, data: Any) -> None:
            if token != self._token:
                return
            self._set_go(True)
            if kind == "spotify":
                self._load_spotify(data)
            else:
                self._load_direct(data)

        def err(exc: BaseException) -> None:
            if token != self._token:
                return
            self._set_go(True)
            self.table.set_rows([])
            self.info.setText(t("import.unreadable"))
            self.ctrl._on_error(exc)

        self.ctrl.import_url(url, ok, err)

    def _sources_row(self) -> Any:
        """1.3.2 (C101) : sources acceptées sous le champ de lien, une pastille par service (point de sa
        couleur, sans logo) ; la bulle dit ce qui est lu, la limite et un exemple de lien."""
        from PySide6.QtCore import Qt

        from ...core.urlimport import SOURCES

        from ..widgets import FlowLayout, vbox

        box = vbox(spacing=theme.px(4))
        row = FlowLayout(spacing=theme.px(6))          # 1.4.2 (A2-3) : pastilles à la ligne si besoin
        head = label(t("import.sources"), "dim")
        head.setToolTip(t("import.src_list"))
        row.addWidget(head)
        self.source_chips = []
        for src in SOURCES:
            c = chip("")
            c.setTextFormat(Qt.RichText)
            c.setText(f'<span style="color:{src.color}">●</span> {src.name}')
            c.setToolTip(t(f"import.src_{src.key}", n=src.limit) + "\n" + t("import.src_example", ex=src.example))
            row.addWidget(c)
            self.source_chips.append(c)
        box.addLayout(row)
        tail = label(t("import.src_list"), "faint", wrap=True)     # 1.4.2 (A2-3) : sur sa ligne, plus coupé
        box.addWidget(tail)
        return box

    def _paste_list(self) -> None:
        def run(text: str) -> None:
            try:
                playlist = self.ctrl.parse_pasted_list(text)
            except Exception as exc:  # noqa: BLE001
                self.ctrl._on_error(exc)
                return
            self._cancel_matching()
            self._load_spotify(playlist)

        PasteListDialog(self, run)

    # ----------------------------------------------------------- mode Spotify
    def _cancel_matching(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None

    def _load_spotify(self, playlist: SpotifyPlaylist) -> None:
        self.playlist, self.resolved = playlist, None
        self.matches = [MatchResult(source=tr) for tr in playlist.tracks]
        self._searched = set()
        self._show_mode("spotify")
        self.sp_table.set_empty_text("")
        self.sp_table.set_rows([self._sp_row(i, m) for i, m in enumerate(self.matches)], reset_sort=True,
                               keep_selection=False)
        n = len(self.matches)
        if "spotify" in (playlist.source_url or ""):
            note = ""
            if playlist.truncated:                                  # 1.4.3 (C206) : « 100 premiers sur n » + quoi faire
                total = getattr(playlist, "total", 0) or 0
                self.note_lbl.setText((t("import.spotify_truncated_of", n=total) if total > len(playlist.tracks)
                                       else t("import.spotify_truncated")) + " " + t("import.spotify_rest"))
                self.note_lbl.show()                                # 1.4.3-rc.2 : sur sa propre ligne
        else:                                                       # 1.4.0 (C86) : Deezer
            note = "  ·  " + t("import.list_truncated", n=len(playlist.tracks)) if playlist.truncated else ""
        self.info.setText(t("import.matching_progress", name=playlist.name, n=n, done=0) + note)

        def on_item(i: int, cands: List[Candidate]) -> None:
            m = self.matches[i]
            m.candidates = cands
            self._searched.add(i)
            apply_preference(m, self.preference)
            self._refresh_sp_row(i, auto_check=True)
            done = self._handle.done if self._handle else n
            self.info.setText(t("import.matching_progress", name=playlist.name, n=n, done=done) + note)
            self._refresh_buttons()

        def on_done() -> None:
            self.info.setText(t("import.summary", name=playlist.name, summary=self._summary()) + note)
            self._refresh_buttons()

        self._handle = self.ctrl.match_spotify(playlist.tracks, on_item, on_done)

    def _summary(self) -> str:
        counts = {"ok": 0, "review": 0, "missing": 0, "duplicate": 0}
        for m in self.matches:
            counts[m.status] += 1
        parts = [plural("lib.tracks_one", "lib.tracks_many", len(self.matches)), plural("import.sum_found", "import.sum_found_many", counts["ok"])]
        if counts["review"]:
            parts.append(t("import.sum_review", n=counts["review"]))
        if counts["missing"]:
            parts.append(plural("import.sum_missing", "import.sum_missing_many", counts["missing"]))
        if counts["duplicate"]:
            parts.append(t("import.sum_duplicate", n=counts["duplicate"]))
        return " · ".join(parts)

    def _sp_values(self, i: int, m: MatchResult) -> dict:
        c = m.candidate
        pending = i not in self._searched
        if c is None:
            match, kind, score, dur = (t("import.searching") if pending else "—"), "", "", ""
            status = "…" if pending else STATUS_TEXT["missing"]
        else:
            manual = "  " + t("import.manual") if m.manual else ""
            match = f"{c.track.title} — {c.track.artist}{manual}"
            kind, score, dur = c.track.kind_label, f"{c.score:.0f}", c.track.duration_str
            status = STATUS_TEXT[m.status]
        from .. import levels

        return {
            "score__level": levels.match_score(c.score) if c is not None else "",     # C29
            "source": m.source.display, "match": match, "type": kind, "score": score,
            "duration": dur or (format_duration(m.source.duration_seconds) if m.source.duration_seconds else ""),
            "status": status,
        }

    def _sp_row(self, i: int, m: MatchResult) -> Row:
        values = self._sp_values(i, m)
        values["chk"] = UNCHECKED
        return Row(str(i), values, (), m)

    def _refresh_sp_row(self, i: int, auto_check: bool = False) -> None:
        m, iid = self.matches[i], str(i)
        row = self.sp_table.row(iid)
        if row is None:
            return
        row.data = m
        vals = self._sp_values(i, m)
        row.values.update(vals)
        self.sp_table.update_values(iid, **vals)
        self.sp_table.set_tags(iid, *STATUS_TAG[m.status])
        if m.status == "duplicate" and m.candidate is not None:          # C209 : état choisi gardé
            self._set_dup(self.sp_table, iid, self._dup.get(("spotify", iid), DUP_ADD))
        elif auto_check or m.status in ("missing", "duplicate"):
            checked = m.status in ("ok", "review", "duplicate") and (auto_check or row.values.get("chk") == CHECKED)
            self.sp_table.update_values(iid, chk=CHECKED if checked else UNCHECKED)


    def _pref_changed(self, label: str) -> None:
        self.preference = next((p for p, text in PREFERENCE_LABELS.items() if text == label), MatchPreference.AUTO)
        self.ctrl.settings.spotify_preference = self.preference.value
        self.ctrl.settings.save()
        if self.mode != "spotify":
            return
        for i, m in enumerate(self.matches):
            if m.candidates:
                apply_preference(m, self.preference)  # ignore les choix manuels
                self._refresh_sp_row(i, auto_check=not m.manual)
        self._refresh_buttons()

    def _cycle(self) -> None:
        for iid in self.sp_table.selected_iids():
            m = self.matches[int(iid)]
            m.cycle()
            self._refresh_sp_row(int(iid))
        self._refresh_buttons()

    # ------------------------------------------------------- mode direct
    def _load_direct(self, resolved: ResolvedUrl) -> None:
        self.resolved, self.playlist, self.matches = resolved, None, []
        self._show_mode("direct")
        self._tracks = {tr.video_id: tr for tr in resolved.tracks}
        self.dl_table.set_rows([result_row(tr, checked=False) for tr in resolved.tracks], reset_sort=True,
                               keep_selection=False)
        self._apply_direct_checks(resolved.tracks)
        source = "SoundCloud" if resolved.kind == UrlKind.SOUNDCLOUD else "YouTube"
        extra = [resolved.note] if resolved.note else []
        self._show_more(resolved)                                        # 1.4.2 (C172)
        protected = sum(1 for tr in resolved.tracks if tr.protected)         # 1.4.0-rc.2 (B64)
        if protected:
            extra.append(plural("sc.protected_one", "sc.protected_many", protected))
        tail = ("  ·  " + "  ·  ".join(extra)) if extra else ""
        self.info.setText(t("import.direct_info", source=source, name=resolved.name,
                            tracks=plural("lib.tracks_one", "lib.tracks_many", len(resolved.tracks))) + tail)
        self.ctrl.reannotate(resolved.tracks, self._direct_annotated)
        if resolved.kind == UrlKind.SOUNDCLOUD:                         # 1.4.0 (C10.1)
            self.ctrl.check_originals(resolved.tracks, self._originals_checked)

    # ------------------------------------------------- 1.4.2 (C172) : longues playlists, page par page
    def _show_more(self, resolved: ResolvedUrl, failed: bool = False) -> None:
        """1.4.3 (C185) : une longue playlist se charge toute seule, page après page, jusqu'à 2 000 sons (le
        tableau défile, sans pages) ; le bandeau dit où en est le chargement. Le bouton « Charger les suivants »
        ne revient qu'après une erreur réseau (nouvel essai à la main)."""
        from ...core.urlimport import MAX_ENTRIES, PLAYLIST_CAP

        n = len(resolved.tracks)
        if not resolved.truncated:
            self.more_box.hide()
            return
        if n >= PLAYLIST_CAP:
            self.more_lbl.setText(t("import.first_of", n=n, total=resolved.total) if resolved.total
                                  else t("import.first_n", n=n))
            self.more_btn.hide()
            self.more_box.show()
            return
        if failed:
            self.more_lbl.setText(t("import.first_of", n=n, total=resolved.total) if resolved.total
                                  else t("import.first_n", n=n))
            left = resolved.total - n if resolved.total else MAX_ENTRIES
            self.more_btn.setText(t("import.load_more", n=min(MAX_ENTRIES, max(1, left))))
            self.more_btn.setEnabled(True)
            self.more_btn.show()
            self.more_box.show()
            return
        total = min(resolved.total, PLAYLIST_CAP) if resolved.total else 0
        self.more_lbl.setText(t("import.loading_progress", n=n, total=total) if total
                              else t("import.loading_progress_n", n=n))
        self.more_btn.hide()
        self.more_box.show()
        from PySide6.QtCore import QTimer

        token = self._token
        QTimer.singleShot(0, lambda: token == self._token and self.load_more())

    def load_more(self) -> None:
        from ...core.urlimport import PLAYLIST_CAP

        resolved = self.resolved
        if resolved is None or not resolved.truncated or getattr(self, "_loading_more", None) is resolved:
            return
        self._loading_more = resolved
        token = self._token
        self.more_btn.setEnabled(False)
        self.more_btn.setText(t("import.loading_more"))
        start = resolved.start + len(resolved.tracks)

        def ok(more: ResolvedUrl) -> None:
            self._loading_more = None
            if token != self._token or not self.winfo_exists() or self.resolved is not resolved:
                return
            known = {tr.video_id for tr in resolved.tracks}
            added = [tr for tr in more.tracks if tr.video_id not in known]
            from dataclasses import replace

            room = max(0, PLAYLIST_CAP - len(resolved.tracks))
            whole = replace(resolved, tracks=resolved.tracks + added[:room], total=more.total or resolved.total,
                            truncated=(more.truncated and bool(added)) or len(added) > room)
            off = [r.iid for r in self.dl_table.all_rows() if r.values.get("chk") == UNCHECKED]
            dup = dict(self._dup)
            self._load_direct(whole)
            self._dup.update(dup)
            for iid in off:                                  # les choix déjà faits sont gardés
                if not self._is_dup(self.dl_table, iid):
                    self.dl_table.update_values(iid, chk=UNCHECKED)
            for (_mode, iid), state in dup.items():
                if self.dl_table.row(iid) is not None:
                    self._set_dup(self.dl_table, iid, state)
            self._refresh_buttons()

        def err(exc: BaseException) -> None:
            self._loading_more = None
            if token == self._token and self.winfo_exists():
                self._show_more(resolved, failed=True)
            self.ctrl._on_error(exc)

        self.ctrl.import_more(resolved.source_url, start, ok, err)

    def _originals_checked(self, tracks: List[TrackResult]) -> None:
        if self.mode != "direct" or not self.winfo_exists():
            return
        from dataclasses import replace

        for tr in tracks:
            old = self._tracks.get(tr.video_id)
            if old is None:
                continue
            new = replace(old, original_available=tr.original_available, free_download_url=tr.free_download_url)
            self._tracks[tr.video_id] = new
            row = self.dl_table.row(tr.video_id)
            if row is not None:
                row.data = new
                fresh = result_row(new)
                self.dl_table.update_values(tr.video_id, source=fresh.values["source"],
                                            source__color=fresh.values.get("source__color"))
        n = sum(1 for tr in tracks if tr.original_available)
        if n:
            self.info.setText(self.info.text() + "  ·  " + plural("sc.originals_one", "sc.originals_many", n))
        n = sum(1 for tr in tracks if tr.free_download_url and not tr.original_available)
        if n:
            self.info.setText(self.info.text() + "  ·  " + plural("sc.free_one", "sc.free_many", n))

    def _apply_direct_checks(self, tracks: List[TrackResult]) -> None:
        for tr in tracks:                                    # 1.4.2 (C201) : déjà là = coché aussi (pastille)
            if tr.is_duplicate:                              # C209 : selon l'état choisi (défaut : ajouté)
                self._set_dup(self.dl_table, tr.video_id, self._dup.get(("direct", tr.video_id), DUP_ADD))
            else:
                self.dl_table.update_values(tr.video_id, chk=CHECKED)
        self._refresh_buttons()

    def _here_values(self, tr: TrackResult) -> dict:
        """1.4.2 (C201, C209) : pastille « déjà là » dans la colonne Bibliothèque, selon l'état choisi."""
        if not tr.is_duplicate:
            return {"lib": "", "lib__color": None}
        return self._dup_values(self.dl_table, self._dup.get(("direct", tr.video_id), DUP_ADD))

    # ------------------------------------------------- 1.4.2 (C209) : sons déjà là, 3 états
    def _is_dup(self, table: TrackTable, iid: str) -> bool:
        if table is self.sp_table:
            m = self.matches[int(iid)] if iid.isdigit() and int(iid) < len(self.matches) else None
            return bool(m is not None and m.status == "duplicate" and m.candidate is not None)
        tr = self._tracks.get(iid)
        return bool(tr is not None and tr.is_duplicate)

    def _dup_state(self, table: TrackTable, iid: str) -> str:
        row = table.row(iid)
        if row is None or row.values.get("chk") != CHECKED:
            return DUP_SKIP
        return self._dup.get((self.mode or "", iid), DUP_ADD)

    @staticmethod
    def _dup_values(table: Any, state: str) -> dict:
        color = {DUP_ADD: theme.ACCENT, DUP_REDL: theme.WARN, DUP_SKIP: None}.get(state)
        key = "status" if getattr(table, "_dup_status_col", False) else "lib"
        return {key: DUP_TEXT[state], f"{key}__color": color}

    def _set_dup(self, table: TrackTable, iid: str, state: str) -> None:
        self._dup[(self.mode or "", iid)] = state
        table.update_values(iid, chk=UNCHECKED if state == DUP_SKIP else CHECKED, **self._dup_values(table, state))

    def _check(self, table: TrackTable, iid: str, on: bool) -> None:
        """Coche ou décoche une ligne ; un son déjà là passe à « ajouté » ou « ignoré »."""
        if self._is_dup(table, iid):
            self._set_dup(table, iid, DUP_ADD if on else DUP_SKIP)
        else:
            table.update_values(iid, chk=CHECKED if on else UNCHECKED)

    def _direct_annotated(self, tracks: List[TrackResult]) -> None:
        if self.mode != "direct":
            return
        for tr in tracks:
            if tr.video_id not in self._tracks:
                continue
            self._tracks[tr.video_id] = tr
            row = self.dl_table.row(tr.video_id)
            if row is not None:
                row.data = tr
                self.dl_table.update_values(tr.video_id, **self._here_values(tr))
                self.dl_table.set_tags(tr.video_id, *(("dup",) if tr.is_duplicate else ()))
        self._apply_direct_checks(tracks)

    # -------------------------------------------------------------- cases
    def _checkable(self, table: TrackTable, iid: str) -> bool:
        return not (table is self.sp_table and self.matches[int(iid)].candidate is None)

    def _toggle(self, table: TrackTable, iid: str) -> None:
        row = table.row(iid)
        if row is None or not self._checkable(table, iid):
            return                                                   # rien à cocher
        target = UNCHECKED if row.values.get("chk") == CHECKED else CHECKED
        ids = [iid]
        last = getattr(table, "_last_check", None)
        from PySide6.QtWidgets import QApplication

        # 1.4.0-rc.4 (C148) : Maj + clic coche (ou décoche) toute la plage depuis la dernière case
        if last and QApplication.keyboardModifiers() & Qt.ShiftModifier:
            shown = table.displayed_iids()
            if last in shown and iid in shown:
                a, b = sorted((shown.index(last), shown.index(iid)))
                ids = shown[a:b + 1]
        if ids == [iid] and self._is_dup(table, iid):                  # C209 : clic = état suivant
            self._set_dup(table, iid, DUP_NEXT[self._dup_state(table, iid)])
            ids = []
        for i in ids:
            if self._checkable(table, i):
                self._check(table, i, target == CHECKED)
        table._last_check = iid                                     # type: ignore[attr-defined]
        self._refresh_buttons()

    def _toggle_selected(self, table: TrackTable) -> None:
        """1.4.0-rc.4 (C148) : Espace coche ou décoche les lignes sélectionnées."""
        ids = [i for i in table.selected_iids() if self._checkable(table, i)]
        if not ids:
            return
        target = UNCHECKED if all(table.row(i).values.get("chk") == CHECKED for i in ids) else CHECKED
        for i in ids:
            self._check(table, i, target == CHECKED)
        self._refresh_buttons()

    def _toggle_all(self, table: TrackTable) -> None:
        rows = [r for r in table.all_rows() if not (table is self.sp_table and self.matches[int(r.iid)].candidate is None)]
        target = CHECKED if any(r.values.get("chk") != CHECKED for r in rows) else UNCHECKED
        for r in rows:
            self._check(table, r.iid, target == CHECKED)
        self._refresh_buttons()

    def _free_urls(self) -> List[str]:
        """1.4.0-rc.4 (C151) : liens « Free Download » des lignes sélectionnées (sans fichier d'origine)."""
        if self.mode != "direct":
            return []
        out = []
        for i in self.dl_table.selected_iids():
            tr = self._tracks.get(i)
            if tr is not None and tr.free_download_url and tr.free_download_url not in out:
                out.append(tr.free_download_url)
        return out

    def _page_urls(self) -> List[str]:
        """1.4.0-rc.5 (B93) : pages SoundCloud des lignes sélectionnées (import d'une adresse)."""
        if self.mode != "direct":
            return []
        out = []
        for i in self.dl_table.selected_iids():
            tr = self._tracks.get(i)
            url = (tr.source_url or "") if tr is not None and tr.source == "soundcloud" else ""
            if url.startswith(("https://soundcloud.com/", "https://m.soundcloud.com/")) and url not in out:
                out.append(url)
        return out

    def _open_pages(self) -> None:
        for url in self._page_urls()[:10]:
            self.ctrl._emit("open_url", url)

    def _open_free(self) -> None:
        for url in self._free_urls()[:10]:
            self.ctrl._emit("open_url", url)

    def _checked_tracks(self) -> List[TrackResult]:
        if self.mode == "spotify":
            out = []
            for r in self.sp_table.all_rows():
                m = self.matches[int(r.iid)]
                if r.values.get("chk") == CHECKED and m.candidate is not None and (
                        m.status != "duplicate" or self._dup_state(self.sp_table, r.iid) == DUP_REDL):
                    out.append(m.candidate.track)
            return out
        return [self._tracks[r.iid] for r in self.dl_table.all_rows()       # 1.4.2 (C201) : à télécharger
                if r.values.get("chk") == CHECKED and r.iid in self._tracks and (
                    not self._tracks[r.iid].is_duplicate or self._dup_state(self.dl_table, r.iid) == DUP_REDL)]

    def _redl_tracks(self) -> List[TrackResult]:
        """1.4.2 (C209) : sons déjà là à retélécharger (deuxième exemplaire, rien n'est effacé)."""
        table = self.table
        out = []
        for r in table.all_rows():
            if self._is_dup(table, r.iid) and self._dup_state(table, r.iid) == DUP_REDL:
                out.append(self.matches[int(r.iid)].candidate.track if table is self.sp_table else self._tracks[r.iid])
        return out

    # ------------------------------------------------------------- actions
    def _refresh_buttons(self) -> None:
        r = len(self._redl_tracks()) if self.mode else 0                # 1.4.2 (C209)
        n = (len(self._checked_tracks()) - r) if self.mode else 0
        present = len(self._present_tracks()) if self.mode else 0       # 1.4.2 (C186, C201)
        # C209 : « Télécharger n · Retélécharger r · Ajouter m » (parties non nulles seulement)
        parts = [t(key, n=k) for key, k in (("import.btn_download", n), ("import.btn_redownload", r),
                                            ("import.btn_add", present)) if k]
        text = (t("import.download_selection_n", n=n) if parts and not (r or present) else
                " · ".join(parts) if parts else t("import.download_selection"))
        self.dl_btn.setText(text)
        self.dl_btn.setEnabled(bool(n or r or present))
        total = sum(1 for row in self.table.all_rows() if self._checkable(self.table, row.iid)) if self.mode else 0
        self.count_lbl.setText(t("import.checked_count", n=n + r + present, total=total) if total else "")
        sel = self.table.selected_iids() if self.mode else []
        free = self._free_urls()
        self.free_btn.setVisible(bool(free))
        self.free_btn.setText(t("sc.free_button_n", n=len(free)) if len(free) > 1 else t("sc.free_button"))
        pages = self._page_urls()
        self.page_btn.setVisible(bool(pages))
        self.page_btn.setText(t("sc.page_button_n", n=len(pages)) if len(pages) > 1 else t("sc.page_button"))
        self.preview_btn.setEnabled(bool(sel))
        self.other_btn.setEnabled(bool(sel) and self.mode == "spotify")

    def _preview_target(self) -> Optional[TrackResult]:
        sel = self.table.selected_iids()
        if not sel:
            return None
        if self.mode == "spotify":
            c = self.matches[int(sel[0])].candidate
            return c.track if c else None
        return self._tracks.get(sel[0])

    def _preview(self) -> None:
        track = self._preview_target()
        if track:
            self.ctrl.preview(track)

    def _download(self) -> None:
        tracks = self._checked_tracks()
        if self.mode == "spotify":
            name = self.playlist.name if self.playlist else ""
        else:
            name = self.resolved.name if self.resolved and self.resolved.is_playlist else ""
        present, redl = self._present_tracks(), self._redl_tracks()
        if not redl:
            ask_and_download(self, self.ctrl, tracks, new_name=name, existing=present)
            return
        # 1.4.2 (C209) : retélécharger un son déjà là est confirmé (deuxième exemplaire)
        fresh = [x for x in tracks if not any(x is y for y in redl)]
        RedownloadDialog(self, len(redl),
                         go=lambda: ask_and_download(self, self.ctrl, tracks, new_name=name, existing=present),
                         add_only=lambda: ask_and_download(self, self.ctrl, fresh, new_name=name,
                                                           existing=present + redl))

    def _present_tracks(self) -> List[TrackResult]:
        """1.4.2 (C186) : sons du lot déjà dans la bibliothèque : ajoutés à la playlist choisie au lieu d'être
        sautés. C201 : ceux qui sont cochés (cochés d'office, avec la pastille « déjà là »)."""
        if self.mode == "spotify":
            out = []
            for r in self.sp_table.all_rows():
                m = self.matches[int(r.iid)]
                if m.status == "duplicate" and m.candidate is not None and \
                        self._dup_state(self.sp_table, r.iid) == DUP_ADD:
                    out.append(m.candidate.track)
            return out
        return [self._tracks[r.iid] for r in self.dl_table.all_rows()
                if r.iid in self._tracks and self._tracks[r.iid].is_duplicate
                and self._dup_state(self.dl_table, r.iid) == DUP_ADD]

    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        entries: list = [(t("action.listen"), self._preview)]
        if self.mode == "spotify":
            entries.append((t("import.other_match"), self._cycle))
        picked = [self._tracks[i] for i in iids if i in self._tracks] if self.mode == "direct" else []
        if any(x.source == "soundcloud" for x in picked):                 # 1.4.0 (C10.1) : au choix
            name = self.resolved.name if self.resolved and self.resolved.is_playlist else ""
            if any(x.original_available for x in picked):
                entries.append((t("sc.download_original"),
                                lambda: ask_and_download(self, self.ctrl, picked, new_name=name, original=True)))
            entries.append((t("sc.download_stream"),
                            lambda: ask_and_download(self, self.ctrl, picked, new_name=name, original=False)))
            if len(picked) == 1 and picked[0].free_download_url:        # 1.4.0 (C45)
                url = picked[0].free_download_url
                entries.append((t("sc.free_open"), lambda: self.ctrl._emit("open_url", url), "download"))
        pages = self._page_urls()
        if pages:                                                   # 1.4.0-rc.5 (B93)
            entries.append((t("sc.page_button_n", n=len(pages)) if len(pages) > 1 else t("sc.page_open"),
                            self._open_pages, "go"))
        if len(picked) == 1:
            from .common import buy_entry

            entries.append(buy_entry(self.ctrl, picked[0].artist, picked[0].title))
        return entries

    def _library_changed(self) -> None:
        """Après un téléchargement : marque les nouveaux doublons dans la liste affichée."""
        if self.mode == "direct" and self._tracks:
            self.ctrl.reannotate(list(self._tracks.values()), self._direct_annotated_keep_checks)
        elif self.mode == "spotify":
            tracks = [c.track for m in self.matches for c in m.candidates]
            if tracks:
                self.ctrl.reannotate(tracks, self._sp_annotated)

    def _direct_annotated_keep_checks(self, tracks: List[TrackResult]) -> None:
        for tr in tracks:
            self._tracks[tr.video_id] = tr
            row = self.dl_table.row(tr.video_id)
            if row is not None:
                row.data = tr
                self.dl_table.update_values(tr.video_id, **self._here_values(tr))
                self.dl_table.set_tags(tr.video_id, *(("dup",) if tr.is_duplicate else ()))
        self._refresh_buttons()

    def _sp_annotated(self, tracks: List[TrackResult]) -> None:
        by_id = {tr.video_id: tr for tr in tracks}
        for i, m in enumerate(self.matches):
            m.candidates = [Candidate(by_id.get(c.track.video_id, c.track), c.score) for c in m.candidates]
            if self.sp_table.row(str(i)) is not None:
                self._refresh_sp_row(i)
        self._refresh_buttons()


class RedownloadDialog(BaseDialog):
    """1.4.2 (C209) : « r sons déjà là seront retéléchargés » : Continuer / Les ajouter seulement.
    Fermer la fenêtre n'envoie rien."""

    def __init__(self, parent: Any, n: int, go: Any, add_only: Any) -> None:
        super().__init__(parent, t("import.redl_title"), 440)
        self._go, self._add_only = go, add_only
        self.heading(t("import.redl_title"))
        self.body.addWidget(label(plural("import.redl_msg_one", "import.redl_msg_many", n), wrap=True))
        self.body.addWidget(label(t("import.redl_detail"), "dim", wrap=True))
        self.body.addStretch(1)
        row = hbox(spacing=theme.px(6))
        row.addStretch(1)
        self.add_btn = button(t("import.redl_add_only"), self._add)
        self.go_btn = button(t("import.redl_continue"), self._continue, kind="primary")
        self.go_btn.setDefault(True)
        row.addWidget(self.add_btn)
        row.addWidget(self.go_btn)
        self.body.addLayout(row)
        self.show_dialog()

    def _continue(self) -> None:
        self.close()
        self._go()

    def _add(self) -> None:
        self.close()
        self._add_only()
