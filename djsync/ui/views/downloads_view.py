"""Vue Téléchargements récents : historique de la session (file d'attente, progression, erreurs)."""
from __future__ import annotations

from typing import Any, List

from ...i18n import plural, t
from ...models import DownloadJob
from ..widgets import Column, Row, TrackTable, button, hbox, label
from .common import View


class DownloadsView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.root.addLayout(self.header(t("tab.downloads"), t("dl.session")))
        self.summary = label("", "dim")
        self.root.addWidget(self.summary)
        cols = [
            Column("title", t("track.title"), 260, stretch=True, min_width=160),
            Column("artist", t("track.artist"), 170, priority=2),
            Column("dest", t("dl.playlists"), 180, priority=3),
            Column("state", t("dl.state"), 150),
            Column("time", t("dl.time"), 60, "center", priority=1),
        ]
        self.table = TrackTable(self, cols)
        self.table.set_empty("", t("dl.empty_title"), t("dl.empty_sub"))
        self.table.on_select = lambda _i: self._refresh()
        self.table.on_double = self._play
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)

        bar = hbox()
        self.play_btn = button(t("action.listen"), lambda: self._play(None))
        bar.addWidget(self.play_btn)
        self.retry_btn = button(t("action.retry"), self._retry)
        bar.addWidget(self.retry_btn)
        bar.addStretch(1)
        self.clear_btn = button(t("dl.clear_finished"), self.ctrl.clear_finished)
        bar.addWidget(self.clear_btn)
        self.root.addLayout(bar)
        self.detail = label("", "err", wrap=True)
        self.root.addWidget(self.detail)

        controller.on("downloads", self.rebuild)
        controller.on("download_update", self._update)
        self.rebuild()

    @staticmethod
    def _tag(job: DownloadJob) -> tuple:
        return ("err",) if job.status == "error" else (("ok",) if job.status == "done" else ())

    def _row(self, job: DownloadJob) -> Row:
        x = job.track
        return Row(str(job.id), {
            "title": x.title, "artist": x.artist,
            "dest": ", ".join(job.playlist_names) or t("dl.library_only"),
            "state": job.status_label, "time": job.created_at.strftime("%H:%M"),
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
        self.table.update_values(iid, state=job.status_label)
        self._refresh()

    def _selected_jobs(self) -> List[DownloadJob]:
        return [r.data for r in self.table.selected_rows() if r.data is not None]

    def _refresh(self) -> None:
        jobs = self.ctrl.jobs
        done = sum(1 for j in jobs if j.status == "done")
        err = sum(1 for j in jobs if j.status == "error")
        active = self.ctrl.active_jobs
        parts = [plural("dl.count_one", "dl.count_many", len(jobs)), t("dl.done_n", n=done)]
        if active:
            parts.append(t("dl.active_n", n=active))
        if err:
            parts.append(t("dl.error_n", n=err))
        self.summary.setText(" · ".join(parts) if jobs else "")
        sel = self._selected_jobs()
        self.play_btn.setEnabled(any(j.status == "done" for j in sel))
        self.retry_btn.setEnabled(any(j.status == "error" for j in sel))
        self.clear_btn.setEnabled(any(j.is_finished for j in jobs))
        bad = next((j for j in sel if j.status == "error"), None)
        self.detail.setText(t("dl.error_detail", detail=bad.message) if bad and bad.message else "")

    def _play(self, iid: Any) -> None:
        done = [r.data for r in self.table.displayed_rows() if r.data is not None and r.data.status == "done"]
        if iid is not None:
            row = self.table.row(iid)
            target = row.data if row is not None else None
        else:
            target = next((j for j in self._selected_jobs() if j.status == "done"), None)
        if target in done:
            self.ctrl.play_queue(done, done.index(target))

    def _retry(self) -> None:
        for job in self._selected_jobs():
            self.ctrl.retry(job)

    def _menu(self, iids: List[str]) -> list:
        return [(t("action.listen"), lambda: self._play(None)), (t("action.retry"), self._retry)] if iids else []
