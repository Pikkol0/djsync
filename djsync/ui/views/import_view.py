"""Vue Import URL : un lien Spotify, YouTube ou SoundCloud (titre unique ou playlist).

  * Spotify    -> liste des morceaux + correspondance YouTube Music (Titre prioritaire / Vidéo
                  prioritaire / Automatique), autre candidat, préécoute, cases à cocher.
  * YouTube / SoundCloud -> téléchargement DIRECT à la source (yt-dlp), sans recherche.
"""
from __future__ import annotations

from typing import Any, List, Optional

import customtkinter as ctk

from ...core.matcher import apply_preference
from ...models import (
    PREFERENCE_LABELS, Candidate, MatchPreference, MatchResult, ResolvedUrl, SpotifyPlaylist, TrackResult,
    UrlKind, format_duration,
)
from .. import theme
from ..covers import url_cover
from ..dialogs import BaseDialog
from ..widgets import Column, Row, TrackTable
from .common import CHECKED, UNCHECKED, View, ask_and_download, result_columns, result_row

STATUS_TEXT = {"ok": "✓ Trouvé", "review": "⚠ À vérifier", "missing": "✗ Introuvable", "duplicate": "✓ Déjà en bibliothèque"}
STATUS_TAG = {"ok": (), "review": ("dim",), "missing": ("err",), "duplicate": ("dup",)}


class PasteListDialog(BaseDialog):
    """Repli quand Spotify refuse la lecture : une ligne par morceau « Artiste - Titre »."""

    def __init__(self, parent: Any, on_ok: Any) -> None:
        super().__init__(parent, "Coller une liste", 520, 420)
        self._on_ok = on_ok
        self.footer("Analyser la liste", self._ok)
        theme.label(self, "Coller une liste de morceaux", 15, theme.TEXT, "bold", anchor="w").pack(
            fill="x", padx=theme.px(20), pady=(theme.px(18), 2))
        theme.label(self, "Une ligne par morceau : « Artiste - Titre ». Chaque ligne sera cherchée sur YouTube Music.",
                    11, theme.DIM, anchor="w", wraplength=theme.px(470), justify="left").pack(fill="x", padx=theme.px(20))
        self.box = ctk.CTkTextbox(self, fg_color=theme.SURFACE, text_color=theme.TEXT, border_color=theme.BORDER,
                                  border_width=1, font=theme.font(12), corner_radius=8)
        self.box.pack(fill="both", expand=True, padx=theme.px(20), pady=10)
        self.after(150, self.box.focus_set)

    def _ok(self) -> None:
        text = self.box.get("1.0", "end").strip()
        if text:
            self.close()
            self._on_ok(text)


class ImportView(View):
    title = "Import URL"

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

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.header("Import URL", "Spotify · YouTube · SoundCloud").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=24)
        bar.grid_columnconfigure(0, weight=1)
        self.url = theme.entry(bar, "Collez un lien : titre ou playlist (Spotify, YouTube, SoundCloud)")
        self.url.grid(row=0, column=0, sticky="ew")
        self.url.bind("<Return>", lambda _e: self.analyse())
        theme.button(bar, "Coller…", self._paste_clipboard, kind="ghost", width=theme.px(80)).grid(row=0, column=1, padx=(8, 0))
        self.go = theme.button(bar, "Analyser", self.analyse, kind="primary", width=theme.px(100))
        self.go.grid(row=0, column=2, padx=(8, 0))

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 0))
        self.info = theme.label(opts, "Collez un lien puis cliquez sur Analyser.", 11, theme.DIM, anchor="w")
        self.info.pack(side="left")
        self.paste_list = theme.button(opts, "Coller une liste…", self._paste_list, kind="flat", width=theme.px(130))
        self.paste_list.pack(side="right")
        self.pref_menu = theme.option_menu(opts, list(PREFERENCE_LABELS.values()), self._pref_changed, width=theme.px(160))
        self.pref_menu.set(PREFERENCE_LABELS[self.preference])
        self.pref_label = theme.label(opts, "Correspondance :", 11, theme.DIM)

        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=3, column=0, sticky="nsew", padx=24, pady=(6, 10))
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)

        spotify_cols = [
            Column("chk", "", 38, "center", sortable=False),
            Column("source", "Morceau Spotify", 260, stretch=True),
            Column("match", "Correspondance YouTube Music", 300, stretch=True),
            Column("type", "Type", 70, "center"),
            Column("score", "Score", 60, "e", sort=lambda r: r.data.candidate.score if r.data and r.data.candidate else None),
            Column("duration", "Durée", 70, "e"),
            Column("status", "Statut", 150),
        ]
        self.sp_table = TrackTable(holder, spotify_cols, loader, click_columns=("chk",))
        self.dl_table = TrackTable(holder, result_columns(with_check=True), loader, click_columns=("chk",))
        for table in (self.sp_table, self.dl_table):
            table.grid(row=0, column=0, sticky="nsew")
            table.on_cell_click = lambda iid, _k, t=table: self._toggle(t, iid)
            table.on_select = lambda _i: self._refresh_buttons()
            table.on_double = lambda _i: self._preview()
            table.menu_builder = self._menu
        self.sp_table.columns[0].on_header = lambda: self._toggle_all(self.sp_table)
        self.dl_table.columns[0].on_header = lambda: self._toggle_all(self.dl_table)
        self.sp_table.set_empty_text("")
        self.dl_table.set_empty_text("Le contenu du lien s'affichera ici.")
        self.sp_table.grid_remove()

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        self.preview_btn = theme.button(actions, "▶  Écouter", self._preview, kind="ghost", width=theme.px(110))
        self.preview_btn.pack(side="left")
        self.other_btn = theme.button(actions, "⟳  Autre correspondance", self._cycle, kind="ghost", width=theme.px(190))
        self.other_btn.pack(side="left", padx=(8, 0))
        self.dl_btn = theme.button(actions, "Télécharger", self._download, kind="primary", width=theme.px(200))
        self.dl_btn.pack(side="right")
        self._show_mode(None)
        self.ctrl.on("library", self._library_changed)

    # ------------------------------------------------------------------ mode
    def _show_mode(self, mode: Optional[str]) -> None:
        self.mode = mode
        spotify = mode == "spotify"
        if spotify:
            self.dl_table.grid_remove()
            self.sp_table.grid()
        else:
            self.sp_table.grid_remove()
            self.dl_table.grid()
        for w in (self.pref_menu, self.pref_label):
            w.pack_forget()
        if spotify:
            self.pref_menu.pack(side="right", padx=(0, 8))
            self.pref_label.pack(side="right", padx=(0, 6))
        self.other_btn.pack_forget()
        if spotify:
            self.other_btn.pack(side="left", padx=(8, 0), after=self.preview_btn)
        self._refresh_buttons()

    @property
    def table(self) -> TrackTable:
        return self.sp_table if self.mode == "spotify" else self.dl_table

    def on_show(self) -> None:
        self.url.focus_set()

    # --------------------------------------------------------------- analyse
    def _paste_clipboard(self) -> None:
        try:
            text = self.clipboard_get().strip()
        except Exception:  # noqa: BLE001 - presse-papiers vide/inaccessible
            return
        self.url.delete(0, "end")
        self.url.insert(0, text)
        if text:
            self.analyse()

    def analyse(self) -> None:
        url = self.url.get().strip()
        if not url:
            return
        self._cancel_matching()
        self._token += 1
        token = self._token
        self.go.configure(state="disabled", text="Analyse…")
        self.info.configure(text="Lecture du lien…", text_color=theme.DIM)

        def ok(kind: str, data: Any) -> None:
            if token != self._token:
                return
            self.go.configure(state="normal", text="Analyser")
            if kind == "spotify":
                self._load_spotify(data)
            else:
                self._load_direct(data)

        def err(exc: BaseException) -> None:
            if token != self._token:
                return
            self.go.configure(state="normal", text="Analyser")
            self.info.configure(text="Lien non lisible.", text_color=theme.ERR)
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
        self.matches = [MatchResult(source=t) for t in playlist.tracks]
        self._searched = set()
        self._show_mode("spotify")
        self.sp_table.set_empty_text("")
        self.sp_table.set_rows([self._sp_row(i, m) for i, m in enumerate(self.matches)], reset_sort=True,
                               keep_selection=False)
        n = len(self.matches)
        note = "  ·  Spotify ne fournit que les 100 premiers morceaux." if playlist.truncated else ""
        self.info.configure(text=f"« {playlist.name} » : {n} morceau(x). Recherche des correspondances 0/{n}…{note}",
                            text_color=theme.DIM)

        def on_item(i: int, cands: List[Candidate]) -> None:
            m = self.matches[i]
            m.candidates = cands
            self._searched.add(i)
            apply_preference(m, self.preference)
            self._refresh_sp_row(i, auto_check=True)
            done = self._handle.done if self._handle else n
            self.info.configure(text=f"« {playlist.name} » : {n} morceau(x). Correspondances {done}/{n}…{note}")
            self._refresh_buttons()

        def on_done() -> None:
            self.info.configure(text=f"« {playlist.name} » : {self._summary()}{note}")
            self._refresh_buttons()

        self._handle = self.ctrl.match_spotify(playlist.tracks, on_item, on_done)

    def _summary(self) -> str:
        counts = {"ok": 0, "review": 0, "missing": 0, "duplicate": 0}
        for m in self.matches:
            counts[m.status] += 1
        parts = [f"{len(self.matches)} morceau(x)", f"{counts['ok']} trouvé(s)"]
        if counts["review"]:
            parts.append(f"{counts['review']} à vérifier")
        if counts["missing"]:
            parts.append(f"{counts['missing']} introuvable(s)")
        if counts["duplicate"]:
            parts.append(f"{counts['duplicate']} déjà en bibliothèque")
        return " · ".join(parts)

    def _sp_values(self, i: int, m: MatchResult) -> dict:
        c = m.candidate
        pending = i not in self._searched
        if c is None:
            match, kind, score, dur = ("Recherche…" if pending else "—"), "", "", ""
            status = "…" if pending else STATUS_TEXT["missing"]
        else:
            manual = "  (choix manuel)" if m.manual else ""
            match = f"{c.track.title} — {c.track.artist}{manual}"
            kind, score, dur = c.track.kind_label, f"{c.score:.0f}", c.track.duration_str
            status = STATUS_TEXT[m.status]
        return {
            "source": m.source.display, "match": match, "type": kind, "score": score,
            "duration": dur or (format_duration(m.source.duration_seconds) if m.source.duration_seconds else ""),
            "status": status,
        }

    def _sp_row(self, i: int, m: MatchResult) -> Row:
        values = self._sp_values(i, m)
        values["chk"] = UNCHECKED
        c = m.candidate
        return Row(str(i), values, url_cover(c.track.thumbnail_url) if c else None, (), m)

    def _refresh_sp_row(self, i: int, auto_check: bool = False) -> None:
        m, iid = self.matches[i], str(i)
        row = self.sp_table.row(iid)
        if row is None:
            return
        row.data = m
        c = m.candidate
        row.cover = url_cover(c.track.thumbnail_url) if c else None
        vals = self._sp_values(i, m)
        row.values.update(vals)
        self.sp_table.update_values(iid, **vals)
        self.sp_table.set_tags(iid, *STATUS_TAG[m.status])
        if auto_check or m.status in ("missing", "duplicate"):
            checked = m.status in ("ok", "review") and (auto_check or row.values.get("chk") == CHECKED)
            self.sp_table.update_values(iid, chk=CHECKED if checked else UNCHECKED)
        # la pochette suit le candidat : on la recharge si la ligne est visible
        if row.cover is not None:
            self.sp_table._covered.discard(iid)
            self.sp_table._photos.pop(iid, None)
            self.sp_table._schedule_covers()

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
        self._tracks = {t.video_id: t for t in resolved.tracks}
        self.dl_table.set_rows([result_row(t, checked=False) for t in resolved.tracks], reset_sort=True,
                               keep_selection=False)
        self._apply_direct_checks(resolved.tracks)
        source = "SoundCloud" if resolved.kind == UrlKind.SOUNDCLOUD else "YouTube"
        extra = [resolved.note] if resolved.note else []
        if resolved.truncated:
            extra.append("liste tronquée aux premiers morceaux")
        tail = ("  ·  " + "  ·  ".join(extra)) if extra else ""
        self.info.configure(
            text=f"{source} : « {resolved.name} » — {len(resolved.tracks)} morceau(x), téléchargement direct{tail}",
            text_color=theme.DIM)
        self.ctrl.reannotate(resolved.tracks, self._direct_annotated)

    def _apply_direct_checks(self, tracks: List[TrackResult]) -> None:
        for t in tracks:
            self.dl_table.update_values(t.video_id, chk=UNCHECKED if t.is_duplicate else CHECKED)
        self._refresh_buttons()

    def _direct_annotated(self, tracks: List[TrackResult]) -> None:
        if self.mode != "direct":
            return
        for t in tracks:
            if t.video_id not in self._tracks:
                continue
            self._tracks[t.video_id] = t
            row = self.dl_table.row(t.video_id)
            if row is not None:
                row.data = t
                self.dl_table.update_values(t.video_id, lib="✓ déjà" if t.is_duplicate else "")
                self.dl_table.set_tags(t.video_id, *(("dup",) if t.is_duplicate else ()))
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
        self.dl_btn.configure(text=f"Télécharger la sélection ({n})" if n else "Télécharger la sélection",
                              state="normal" if n else "disabled")
        sel = self.table.selected_iids() if self.mode else []
        self.preview_btn.configure(state="normal" if sel else "disabled")
        self.other_btn.configure(state="normal" if sel and self.mode == "spotify" else "disabled")

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
        entries: list = [("Écouter", self._preview)]
        if self.mode == "spotify":
            entries.append(("Autre correspondance", self._cycle))
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
        for t in tracks:
            self._tracks[t.video_id] = t
            row = self.dl_table.row(t.video_id)
            if row is not None:
                row.data = t
                self.dl_table.update_values(t.video_id, lib="✓ déjà" if t.is_duplicate else "")
                self.dl_table.set_tags(t.video_id, *(("dup",) if t.is_duplicate else ()))
        self._refresh_buttons()

    def _sp_annotated(self, tracks: List[TrackResult]) -> None:
        by_id = {t.video_id: t for t in tracks}
        for i, m in enumerate(self.matches):
            m.candidates = [Candidate(by_id.get(c.track.video_id, c.track), c.score) for c in m.candidates]
            if self.sp_table.row(str(i)) is not None:
                self._refresh_sp_row(i)
        self._refresh_buttons()
