"""Vue Import URL : un lien Spotify, YouTube ou SoundCloud (titre unique ou playlist).

  * Spotify    -> liste des morceaux + correspondance YouTube Music (Titre prioritaire / Vidéo
                  prioritaire / Automatique), autre candidat, préécoute, cases à cocher.
  * YouTube / SoundCloud -> téléchargement DIRECT à la source (yt-dlp), sans recherche.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtWidgets import QApplication, QComboBox, QPlainTextEdit

from ...core.matcher import apply_preference
from ...i18n import LazyLabels, plural, t
from ...models import (
    PREFERENCE_LABELS, Candidate, MatchPreference, MatchResult, ResolvedUrl, SpotifyPlaylist, TrackResult,
    UrlKind, format_duration,
)
from ..dialogs import BaseDialog
from .. import theme
from ..widgets import Column, Row, TrackTable, button, hbox, label, line_edit
from .common import CHECKED, UNCHECKED, View, ask_and_download, result_columns, result_row

STATUS_TEXT = LazyLabels(lambda: {"ok": "import.st_ok", "review": "import.st_review", "missing": "import.st_missing",
                                  "duplicate": "import.st_duplicate"})
STATUS_TAG = {"ok": (), "review": ("dim",), "missing": ("err",), "duplicate": ("dup",)}


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

        self.root.addLayout(self.header(t("tab.import")))
        bar = hbox(spacing=theme.px(8))
        self.url = line_edit(t("import.placeholder"), "import", big=True)
        self.url.returnPressed.connect(self.analyse)
        bar.addWidget(self.url, 1)
        paste = button(t("action.paste"), self._paste_clipboard, icon="clipboard")
        self.go = button(t("import.read_link"), self.analyse, kind="primary", icon="go")
        for b in (paste, self.go):
            b.setMinimumHeight(self.url.sizeHint().height())
            bar.addWidget(b)
        self.root.addLayout(bar)

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

        spotify_cols = [
            Column("chk", "", 30, "center", sortable=False),
            Column("source", t("import.col_source"), 240, stretch=True, min_width=140),
            Column("match", t("import.col_match"), 280, stretch=True, min_width=140, priority=1),
            Column("type", t("track.type"), 70, "center", priority=4),
            Column("score", t("import.col_score"), 56, "e", priority=3,
                   sort=lambda r: r.data.candidate.score if r.data and r.data.candidate else None),
            Column("duration", t("track.duration"), 64, "e", priority=2),
            Column("status", t("import.col_status"), 150),
        ]
        self.sp_table = TrackTable(self, spotify_cols, click_columns=("chk",))
        self.dl_table = TrackTable(self, result_columns(with_check=True, with_download=False), click_columns=("chk",))
        for table in (self.sp_table, self.dl_table):
            table.on_cell_click = lambda iid, _k, tb=table: self._toggle(tb, iid)
            table.on_select = lambda _i: self._refresh_buttons()
            table.on_double = lambda _i: self._preview()
            table.menu_builder = self._menu
            self.root.addWidget(table, 1)
        self.sp_table.columns[0].on_header = lambda: self._toggle_all(self.sp_table)
        self.dl_table.columns[0].on_header = lambda: self._toggle_all(self.dl_table)
        self.dl_table.set_empty("import", t("import.empty_title"))

        actions = hbox()
        self.preview_btn = button(t("action.listen"), self._preview, icon="play")
        actions.addWidget(self.preview_btn)
        self.other_btn = button(t("import.other_match"), self._cycle, icon="refresh")
        actions.addWidget(self.other_btn)
        actions.addStretch(1)
        self.dl_btn = button(t("import.download_selection"), self._download, kind="primary", icon="download")
        actions.addWidget(self.dl_btn)
        self.root.addLayout(actions)
        self._show_mode(None)
        self.ctrl.on("library", self._library_changed)

    # ------------------------------------------------------------------ mode
    def _show_mode(self, mode: Optional[str]) -> None:
        self.mode = mode
        spotify = mode == "spotify"
        self.sp_table.setVisible(spotify)
        self.dl_table.setVisible(not spotify)
        self.pref_menu.setVisible(spotify)
        self.pref_label.setVisible(spotify)
        self.other_btn.setVisible(spotify)
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
        note = "  ·  " + t("import.spotify_truncated") if playlist.truncated else ""
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
        parts = [plural("lib.tracks_one", "lib.tracks_many", len(self.matches)), t("import.sum_found", n=counts["ok"])]
        if counts["review"]:
            parts.append(t("import.sum_review", n=counts["review"]))
        if counts["missing"]:
            parts.append(t("import.sum_missing", n=counts["missing"]))
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
        if auto_check or m.status in ("missing", "duplicate"):
            checked = m.status in ("ok", "review") and (auto_check or row.values.get("chk") == CHECKED)
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
        if resolved.truncated:
            extra.append(t("import.truncated"))
        tail = ("  ·  " + "  ·  ".join(extra)) if extra else ""
        self.info.setText(t("import.direct_info", source=source, name=resolved.name,
                            tracks=plural("lib.tracks_one", "lib.tracks_many", len(resolved.tracks))) + tail)
        self.ctrl.reannotate(resolved.tracks, self._direct_annotated)

    def _apply_direct_checks(self, tracks: List[TrackResult]) -> None:
        for tr in tracks:
            self.dl_table.update_values(tr.video_id, chk=UNCHECKED if tr.is_duplicate else CHECKED)
        self._refresh_buttons()

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
                self.dl_table.update_values(tr.video_id, lib=t("track.already") if tr.is_duplicate else "")
                self.dl_table.set_tags(tr.video_id, *(("dup",) if tr.is_duplicate else ()))
        self._apply_direct_checks(tracks)

    # -------------------------------------------------------------- cases
    def _toggle(self, table: TrackTable, iid: str) -> None:
        row = table.row(iid)
        if row is None:
            return
        if table is self.sp_table and self.matches[int(iid)].candidate is None:
            return  # rien à cocher
        table.update_values(iid, chk=UNCHECKED if row.values.get("chk") == CHECKED else CHECKED)
        self._refresh_buttons()

    def _toggle_all(self, table: TrackTable) -> None:
        rows = [r for r in table.all_rows() if not (table is self.sp_table and self.matches[int(r.iid)].candidate is None)]
        target = CHECKED if any(r.values.get("chk") != CHECKED for r in rows) else UNCHECKED
        for r in rows:
            table.update_values(r.iid, chk=target)
        self._refresh_buttons()

    def _checked_tracks(self) -> List[TrackResult]:
        if self.mode == "spotify":
            out = []
            for r in self.sp_table.all_rows():
                m = self.matches[int(r.iid)]
                if r.values.get("chk") == CHECKED and m.candidate is not None:
                    out.append(m.candidate.track)
            return out
        return [self._tracks[r.iid] for r in self.dl_table.all_rows()
                if r.values.get("chk") == CHECKED and r.iid in self._tracks]

    # ------------------------------------------------------------- actions
    def _refresh_buttons(self) -> None:
        n = len(self._checked_tracks()) if self.mode else 0
        self.dl_btn.setText(t("import.download_selection_n", n=n) if n else t("import.download_selection"))
        self.dl_btn.setEnabled(bool(n))
        sel = self.table.selected_iids() if self.mode else []
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
        ask_and_download(self, self.ctrl, tracks, new_name=name)

    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        entries: list = [(t("action.listen"), self._preview)]
        if self.mode == "spotify":
            entries.append((t("import.other_match"), self._cycle))
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
                self.dl_table.update_values(tr.video_id, lib=t("track.already") if tr.is_duplicate else "")
                self.dl_table.set_tags(tr.video_id, *(("dup",) if tr.is_duplicate else ()))
        self._refresh_buttons()

    def _sp_annotated(self, tracks: List[TrackResult]) -> None:
        by_id = {tr.video_id: tr for tr in tracks}
        for i, m in enumerate(self.matches):
            m.candidates = [Candidate(by_id.get(c.track.video_id, c.track), c.score) for c in m.candidates]
            if self.sp_table.row(str(i)) is not None:
                self._refresh_sp_row(i)
        self._refresh_buttons()
