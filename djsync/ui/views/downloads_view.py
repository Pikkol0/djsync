"""Vue Téléchargements récents : historique de la session (file d'attente, progression, erreurs)."""
from __future__ import annotations

from typing import Any, List

import customtkinter as ctk

from ...models import DownloadJob
from .. import theme
from ..covers import url_cover
from ..widgets import Column, Row, TrackTable
from .common import View


class DownloadsView(View):
    title = "Téléchargements récents"

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.header("Téléchargements récents", "session en cours").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        self.summary = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.summary.grid(row=1, column=0, sticky="w", padx=26)

        cols = [
            Column("title", "Titre", 280, stretch=True),
            Column("artist", "Artiste", 180),
            Column("dest", "Playlists", 190),
            Column("state", "État", 170),
            Column("time", "Heure", 70, "center"),
        ]
        self.table = TrackTable(self, cols, loader)
        self.table.grid(row=2, column=0, sticky="nsew", padx=24, pady=(6, 10))
        self.table.set_empty_text("Les téléchargements de cette session apparaîtront ici.")
        self.table.on_select = lambda _i: self._refresh()
        self.table.on_double = self._play
        self.table.menu_builder = self._menu

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 6))
        self.play_btn = theme.button(bar, "▶  Écouter", lambda: self._play(None), kind="ghost", width=theme.px(110))
        self.play_btn.pack(side="left")
        self.retry_btn = theme.button(bar, "Réessayer", self._retry, kind="ghost", width=theme.px(100))
        self.retry_btn.pack(side="left", padx=(8, 0))
        self.clear_btn = theme.button(bar, "Vider les terminés", self.ctrl.clear_finished, kind="ghost", width=theme.px(150))
        self.clear_btn.pack(side="right")
        self.detail = theme.label(self, "", 11, theme.ERR, anchor="w", justify="left", wraplength=theme.px(800))
        self.detail.grid(row=4, column=0, sticky="ew", padx=26, pady=(0, 14))

        controller.on("downloads", self.rebuild)
        controller.on("download_update", self._update)
        self.rebuild()

    @staticmethod
    def _tag(job: DownloadJob) -> tuple:
        return ("err",) if job.status == "error" else ()

    def _row(self, job: DownloadJob) -> Row:
        t = job.track
        return Row(str(job.id), {
            "title": t.title, "artist": t.artist,
            "dest": ", ".join(job.playlist_names) or "Bibliothèque seule",
            "state": job.status_label, "time": job.created_at.strftime("%H:%M"),
        }, url_cover(t.thumbnail_url), self._tag(job), job)

    def rebuild(self) -> None:
        self.table.set_rows([self._row(j) for j in reversed(self.ctrl.jobs)], keep_selection=True)
        self._refresh()

    def _update(self, job: DownloadJob) -> None:
        iid = str(job.id)
        if self.table.row(iid) is None:
            return
        self.table.update_values(iid, state=job.status_label)
        self.table.set_tags(iid, *self._tag(job))
        self._refresh()

    def _selected_jobs(self) -> List[DownloadJob]:
        return [r.data for r in self.table.selected_rows() if r.data is not None]

    def _refresh(self) -> None:
        jobs = self.ctrl.jobs
        done = sum(1 for j in jobs if j.status == "done")
        err = sum(1 for j in jobs if j.status == "error")
        active = self.ctrl.active_jobs
        parts = [f"{len(jobs)} téléchargement(s)", f"{done} terminé(s)"]
        if active:
            parts.append(f"{active} en cours / en attente")
        if err:
            parts.append(f"{err} en erreur")
        self.summary.configure(text=" · ".join(parts) if jobs else "")
        sel = self._selected_jobs()
        self.play_btn.configure(state="normal" if any(j.status == "done" for j in sel) else "disabled")
        self.retry_btn.configure(state="normal" if any(j.status == "error" for j in sel) else "disabled")
        self.clear_btn.configure(state="normal" if any(j.is_finished for j in jobs) else "disabled")
        bad = next((j for j in sel if j.status == "error"), None)
        self.detail.configure(text=f"Erreur : {bad.message}" if bad and bad.message else "")

    def _play(self, _iid: Any) -> None:
        for job in self._selected_jobs():
            if job.status == "done":
                self.ctrl.play_job(job)
                return

    def _retry(self) -> None:
        for job in self._selected_jobs():
            self.ctrl.retry(job)

    def _menu(self, iids: List[str]) -> list:
        return [("Écouter", lambda: self._play(None)), ("Réessayer", self._retry)] if iids else []
