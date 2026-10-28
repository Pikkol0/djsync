"""Vue « Téléchargements & analyse » (V0.3.1) : deux tableaux.

  * Téléchargements de la session : file d'attente, progression, erreurs, réessayer.
  * Analyse : tous les sons non analysés + ceux analysés pendant la session (état en direct) ; une
    recherche dans toute la bibliothèque permet de choisir un son à (ré)analyser. À droite de chaque
    son analysé, une icône ouvre l'éditeur de grille (recaler le BPM / la grille à la main).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QProgressBar, QSplitter, QWidget

from ...i18n import plural, t
from ...models import DownloadJob, LibraryTrack
from .. import theme
from ..icons import qicon
from ..table import camelot_sort
from ..widgets import Column, Row, TrackTable, button, hbox, icon_label, label, line_edit, restyle, vbox
from .common import focus_list, View


class DownloadsView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._tracks: Dict[str, LibraryTrack] = {}
        self._loaded_for = None
        self.root.addLayout(self.header(t("tab.downloads")))
        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        self.root.addWidget(split, 1)

        # ------------------------------------------------------------ téléchargements
        top = QWidget()
        tv = vbox(top, spacing=theme.px(6))
        head = hbox(spacing=theme.px(8))
        head.addWidget(icon_label("download", 18, theme.ACCENT))
        head.addWidget(label(t("dl.section"), "h2"))
        self.summary = label("", "dim")
        head.addWidget(self.summary)
        self.dl_bar = QProgressBar()                     # 1.2.1 (C21) : avancement de la série en cours
        self.dl_bar.setRange(0, 1000)
        self.dl_bar.setTextVisible(False)
        self.dl_bar.setFixedWidth(theme.px(140))
        self.dl_bar.hide()
        head.addWidget(self.dl_bar)
        head.addStretch(1)
        self.play_btn = button(t("action.listen"), lambda: self._play(None), icon="play")
        self.retry_btn = button(t("action.retry"), self._retry, icon="refresh")
        self.clear_btn = button(t("dl.clear_finished"), self.ctrl.clear_finished, kind="flat", icon="trash")
        for b in (self.play_btn, self.retry_btn, self.clear_btn):
            head.addWidget(b)
        tv.addLayout(head)
        cols = [
            Column("title", t("track.title"), 260, stretch=True, min_width=160),
            Column("artist", t("track.artist"), 170, priority=2),
            Column("dest", t("dl.playlists"), 180, priority=3),
            Column("state", t("dl.state"), 150),
            Column("time", t("dl.time"), 60, "center", priority=1),
        ]
        self.table = TrackTable(self, cols)
        self.remember_layout(self.table, "downloads")
        self.table.set_empty("downloads", t("dl.empty_title"))
        self.table.on_select = lambda _i: self._refresh()
        self.table.on_double = self._play
        self.table.menu_builder = self._menu
        tv.addWidget(self.table, 1)
        self.detail = label("", "err", wrap=True)
        self.detail.hide()
        tv.addWidget(self.detail)
        split.addWidget(top)

        # ------------------------------------------------------------------- analyse
        bottom = QWidget()
        bv = vbox(bottom, spacing=theme.px(6))
        bv.setContentsMargins(0, theme.px(10), 0, 0)
        head = hbox(spacing=theme.px(8))
        head.addWidget(icon_label("wave", 18, theme.ACCENT))
        head.addWidget(label(t("an.section"), "h2"))
        self.an_summary = label("", "dim")
        head.addWidget(self.an_summary)
        head.addStretch(1)
        self.an_bar = QProgressBar()
        self.an_bar.setRange(0, 1000)
        self.an_bar.setTextVisible(False)
        self.an_bar.setFixedWidth(theme.px(140))
        head.addWidget(self.an_bar)
        self.search = line_edit(t("an.search"), "search")
        self.search.setMinimumWidth(theme.px(240))
        self.search.textChanged.connect(lambda _t: self._fill())
        head.addWidget(self.search)
        self.analyse_sel_btn = button(t("action.analyse"), self._analyse_selection, icon="wave")
        head.addWidget(self.analyse_sel_btn)
        self.analyse_btn = button("", self._analyse_toggle, kind="primary", icon="wave")
        head.addWidget(self.analyse_btn)
        bv.addLayout(head)
        an_cols = [
            Column("key", t("track.key"), 44, "center", sort=camelot_sort),
            Column("title", t("track.title"), 260, stretch=True, min_width=160),
            Column("artist", t("track.artist"), 170, priority=2),
            Column("bpm", t("track.bpm"), 56, "e", priority=1,
                   sort=lambda r: r.data.bpm or None if r.data else None),
            Column("state", t("dl.state"), 130),
            Column("grid", "", 40, "center", sortable=False, min_width=34),
        ]
        self.an_table = TrackTable(self, an_cols, click_columns=("grid",))
        self.remember_layout(self.an_table, "unanalysed")
        self.an_table.set_empty("check", t("lib.empty_todo_title"))
        self.an_table.on_select = lambda _i: self._refresh_analysis()
        self.an_table.on_double = self._play_track
        self.an_table.on_cell_click = self._cell_click
        self.an_table.menu_builder = self._an_menu
        bv.addWidget(self.an_table, 1)
        split.addWidget(bottom)
        split.setSizes([theme.px(300), theme.px(360)])

        controller.on("downloads", self.rebuild)
        controller.on("download_update", self._update)
        controller.on("library", lambda: self.reload())
        controller.on("drive", lambda: self.reload())
        controller.on("analysis", self._analysis_changed)
        # 1.2.1 (C21) : avancement estimé du son en cours d'analyse (durée moyenne des précédents)
        self._an_cur: Any = None
        self._an_started = 0.0
        self._an_t0 = 0.0
        self._an_done0 = 0
        self._an_timer = QTimer(self)
        self._an_timer.setInterval(300)
        self._an_timer.timeout.connect(self._an_tick)
        self.rebuild()
        self._refresh_analysis()

    # ================================================================ téléchargements
    @staticmethod
    def _tag(job: DownloadJob) -> tuple:
        return ("err",) if job.status == "error" else (("ok",) if job.status == "done" else ())

    def _row(self, job: DownloadJob) -> Row:
        x = job.track
        return Row(str(job.id), {
            "title": x.title, "artist": x.artist,
            "dest": ", ".join(job.playlist_names) or t("dl.library_only"),
            "state": job.status_label, "time": job.created_at.strftime("%H:%M"),
            "_progress": job.progress if not job.is_finished else None,
        }, self._tag(job), job)

    def rebuild(self) -> None:
        self.table.set_rows([self._row(j) for j in reversed(self.ctrl.jobs)], keep_selection=True)
        self._refresh()

    def _update(self, job: DownloadJob) -> None:
        iid = str(job.id)
        row = self.table.row(iid)
        if row is None:
            return
        row.tags = self._tag(job)
        self.table.update_values(iid, state=job.status_label, _progress=None if job.is_finished else job.progress)
        self._refresh()

    def _selected_jobs(self) -> List[DownloadJob]:
        return [r.data for r in self.table.selected_rows() if r.data is not None]

    def _refresh(self) -> None:
        jobs = self.ctrl.jobs
        done = sum(1 for j in jobs if j.status == "done")
        err = sum(1 for j in jobs if j.status == "error")
        active = self.ctrl.active_jobs
        parts = [t("dl.done_n", n=done)]
        if active:
            parts.append(t("dl.active_n", n=active))
        if err:
            parts.append(t("dl.error_n", n=err))
        self.summary.setText(" · ".join(parts) if jobs else "")
        b_done, b_total, frac = self.ctrl.download_progress()
        self.dl_bar.setVisible(b_total > 0)
        self.dl_bar.setValue(int(1000 * frac))
        self.dl_bar.setToolTip(t("dl.batch_progress", done=b_done, n=b_total) if b_total else "")
        sel = self._selected_jobs()
        self.play_btn.setEnabled(any(j.status == "done" for j in sel))
        self.retry_btn.setEnabled(any(j.status == "error" for j in sel))
        self.clear_btn.setEnabled(any(j.is_finished for j in jobs))
        bad = next((j for j in sel if j.status == "error"), None)
        self.detail.setText(t("dl.error_detail", detail=bad.message) if bad and bad.message else "")
        self.detail.setVisible(bool(self.detail.text()))

    def _play(self, iid: Any) -> None:
        done = [r.data for r in self.table.displayed_rows() if r.data is not None and r.data.status == "done"]
        if iid is not None:
            row = self.table.row(iid)
            target = row.data if row is not None else None
        else:
            target = next((j for j in self._selected_jobs() if j.status == "done"), None)
        if target in done:
            self.ctrl.play_queue(done, done.index(target))
            focus_list(self.table)

    def _retry(self) -> None:
        for job in self._selected_jobs():
            self.ctrl.retry(job)

    def _menu(self, iids: List[str]) -> list:
        return [(t("action.listen"), lambda: self._play(None), "play"),
                (t("action.retry"), self._retry, "refresh")] if iids else []

    # ======================================================================= analyse
    def on_show(self) -> None:
        if self._loaded_for != self._drive_key():
            self.reload()

    def _drive_key(self) -> str:
        return str(self.ctrl.drive.root) if self.ctrl.drive else ""

    def reload(self) -> None:
        if not self.winfo_exists():
            return
        if not self.ctrl.has_library:
            self._tracks, self._loaded_for = {}, ""
            self._fill()
            return
        key = self._drive_key()

        def ok(data: Dict[str, Any]) -> None:
            if key != self._drive_key() or not self.winfo_exists():
                return
            self._loaded_for = key
            self._tracks = {str(x.content_id): x for x in data["tracks"]}
            self._fill()

        self.ctrl.load_library(ok)

    def _state(self, x: LibraryTrack) -> tuple:
        """(texte, étiquette de couleur) de l'analyse d'un son."""
        q = self.ctrl.analysis
        cid = x.content_id
        if q.running and cid in q.ids and cid not in self.ctrl.analysis_results:
            if cid in q.pending:
                return t("an.queued"), ("dim",)
            return t("an.running"), ("playing",)
        result = self.ctrl.analysis_results.get(cid)
        if result == "failed":
            return t("an.failed"), ("err",)
        if result == "ok" and not x.is_analysed:
            # calculé, pas encore écrit : l'analyse enregistre par lots de 8 sons (une seule sauvegarde
            # et réécriture d'export.pdb par lot) ; la ligne passe à « Analysé » dès le lot écrit
            return t("an.saving"), ("playing",)
        if x.is_analysed:
            return t("an.done"), ()
        return t("lib.unanalysed"), ()

    def _an_row(self, x: LibraryTrack) -> Row:
        text, tags = self._state(x)
        return Row(str(x.content_id), {
            "key": x.camelot or "", "title": x.title, "artist": x.artist,
            "bpm": f"{x.bpm:.0f}" if x.bpm else "—", "state": text, "grid": "1" if x.is_analysed else "",
        }, tags, x)

    def _fill(self) -> None:
        """Sans recherche : sons non analysés + sons analysés (ou en file) pendant la session.
        Avec recherche : toute la bibliothèque, filtrée."""
        query = self.search.text().strip()
        q = self.ctrl.analysis
        if query:
            tracks = list(self._tracks.values())
            self.an_table.set_empty("search", t("search.no_result_title"))
        else:
            session = set(self.ctrl.analysis_results) | (set(q.ids) if q.running else set())
            tracks = [x for x in self._tracks.values() if not x.is_analysed or x.content_id in session]
            queued = set(q.ids) if q.running else set()                  # 1.3.1 (B30) : la file en haut
            tracks.sort(key=lambda x: 0 if x.content_id in queued else 1)
            self.an_table.set_empty("check" if self.ctrl.has_library else "usb",
                                    t("lib.empty_todo_title") if self.ctrl.has_library else t("lib.no_drive_title"))
        self.an_table.set_rows([self._an_row(x) for x in tracks], keep_selection=True)
        self.an_table.set_filter(query)
        self._refresh_analysis()

    def _analysis_changed(self) -> None:
        if not self.winfo_exists():
            return
        # 1.3.1 (B30) : une analyse lancée ailleurs (Bibliothèque, page Analyser, Doublons) peut contenir
        # des sons déjà analysés, donc absents de la liste : on les ajoute au lieu de ne rien montrer
        q = self.ctrl.analysis
        if q.running and not self.search.text().strip():
            if any(str(cid) in self._tracks and self.an_table.row(str(cid)) is None for cid in tuple(q.ids)):
                self._fill()
                return
        for row in self.an_table.all_rows():
            if row.data is not None:
                text, tags = self._state(row.data)
                if row.values.get("state") != text:
                    row.tags = tags
                    self.an_table.update_values(row.iid, state=text)
        self._refresh_analysis()

    def _an_set_progress(self, cid: Any, value: Optional[float] = None) -> None:
        for row in self.an_table.all_rows():
            want = value if (cid is not None and row.iid == str(cid)) else None
            if row.values.get("_progress") != want:
                self.an_table.update_values(row.iid, _progress=want)

    def _an_tick(self) -> None:
        import time

        if not self.winfo_exists():
            return
        q = self.ctrl.analysis
        cid = self.ctrl.analysis_current_id()
        now = time.monotonic()
        if cid != self._an_cur:
            self._an_cur, self._an_started = cid, now
        done = q.done - self._an_done0
        avg = (now - self._an_t0) / done if done > 0 else 12.0
        value = min(0.95, (now - self._an_started) / max(1.0, avg)) if cid is not None else None
        self._an_set_progress(cid, value)

    def _selected_tracks(self) -> List[LibraryTrack]:
        return [r.data for r in self.an_table.selected_rows() if r.data is not None]

    def _unanalysed(self) -> List[LibraryTrack]:
        return [x for x in self._tracks.values() if not x.is_analysed]

    def _refresh_analysis(self) -> None:
        q = self.ctrl.analysis
        todo = len(self._unanalysed())
        parts = [plural("home.unanalysed_one", "home.unanalysed_many", todo)] if todo else []
        if q.running:
            parts.append(t("lib.analysing", i=q.done, n=q.total))
        self.an_summary.setText("  ·  ".join(parts))
        self.an_bar.setVisible(q.running)
        self.an_bar.setValue(int(1000 * q.done / max(1, q.total)))
        if q.running and not self._an_timer.isActive():
            import time

            self._an_t0, self._an_done0 = time.monotonic(), q.done
            self._an_timer.start()
        elif not q.running and self._an_timer.isActive():
            self._an_timer.stop()
            self._an_set_progress(None)
        sel = self._selected_tracks()
        self.analyse_sel_btn.setEnabled(bool(sel) and self.ctrl.has_library)
        self.analyse_sel_btn.setText(t("lib.analyse_selection", n=len(sel)) if sel else t("action.analyse"))
        if q.running:
            self.analyse_btn.setText(t("lib.analyse_stop"))
            self.analyse_btn.setProperty("kind", "danger")
            self.analyse_btn.setIcon(qicon("stop", 16, theme.ERR))
            self.analyse_btn.setEnabled(not q.cancelled)
        else:
            self.analyse_btn.setText(t("lib.analyse_all", n=todo))
            self.analyse_btn.setProperty("kind", "primary")
            self.analyse_btn.setIcon(qicon("wave", 16, theme.ON_ACCENT))
            self.analyse_btn.setEnabled(bool(todo) and self.ctrl.has_library)
        restyle(self.analyse_btn)

    def _analyse_toggle(self) -> None:
        if self.ctrl.analysis.running:
            self.ctrl.stop_analysis()
            return
        todo = self._unanalysed()
        if todo:
            self.ctrl.analyze([x.content_id for x in todo])

    def _analyse_selection(self) -> None:
        """Sélection : les sons déjà analysés (par DJSync) sont réanalysés, les autres analysés."""
        sel = self._selected_tracks()
        new = [x.content_id for x in sel if not x.is_analysed]
        again = [x.content_id for x in sel if x.is_analysed]
        if new:
            self.ctrl.analyze(new)
        if again:
            self.ctrl.analyze(again, force=True)

    def _edit_grid(self, x: LibraryTrack) -> None:
        if x.is_analysed:
            self.ctrl._emit("open_grid", x)
        else:
            self.ctrl.message("info", t("grid.not_analysed"))

    def _cell_click(self, iid: str, key: str) -> None:
        x = self._tracks.get(iid)
        if key == "grid" and x is not None and x.is_analysed:
            self._edit_grid(x)

    def _play_track(self, iid: str) -> None:
        shown = [r.data for r in self.an_table.displayed_rows() if r.data is not None]
        x = self._tracks.get(iid)
        if x in shown:
            self.ctrl.play_queue(shown, shown.index(x))
            focus_list(self.an_table)

    def _an_menu(self, iids: List[str]) -> list:
        sel = self._selected_tracks()
        if not sel:
            return []
        entries: list = [(t("action.listen"), lambda: self._play_track(iids[0]), "play"),
                         (t("lib.analyse_selection", n=len(sel)), self._analyse_selection, "wave")]
        if len(sel) == 1 and sel[0].is_analysed:
            entries.append((t("lib.edit_grid"), lambda: self._edit_grid(sel[0]), "grid"))
        return entries
