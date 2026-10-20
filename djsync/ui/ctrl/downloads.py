"""File de téléchargements : téléchargement natif -> tags -> ajout sur la clé (+ sauvegarde) -> playlists."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ...i18n import plural, t
from ...models import DownloadJob, TrackResult

log = logging.getLogger(__name__)


class DownloadsMixin:
    def enqueue(self, tracks: Sequence[TrackResult], playlist_ids: Sequence[int]) -> List[DownloadJob]:
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return []
        names = {p.playlist_id: p.name for p in self.playlists}
        self.last_playlist_ids = list(playlist_ids)
        created: List[DownloadJob] = []
        for track in tracks:
            self._job_seq += 1
            job = DownloadJob(
                id=self._job_seq, track=track, playlist_ids=list(playlist_ids),
                playlist_names=[names.get(pid, f"#{pid}") for pid in playlist_ids], library=lib,
            )
            self.jobs.append(job)
            created.append(job)
            self.dispatcher.submit(lambda j=job: self._run_job(j), pool="dl")
        self._emit("downloads")
        where = (t("msg.queued_to", names=", ".join(names.get(p, "?") for p in playlist_ids)) if playlist_ids
                 else t("msg.queued_library"))
        self.message("info", plural("msg.queued_one", "msg.queued_many", len(created), where=where))
        return created

    def _job_changed(self, job: DownloadJob) -> None:
        self._emit("download_update", job)

    def _run_job(self, job: DownloadJob) -> None:
        """Thread « dl » : téléchargement natif -> tags -> ajout en base (+ backup) -> playlists."""
        last: Dict[str, Any] = {}

        def progress(p: Any) -> None:
            key = (p.status, int(p.percent // 2))
            if last.get("key") == key:
                return
            last["key"] = key
            job.status = p.status if p.status in ("downloading", "converting", "tagging") else job.status
            job.percent = p.percent
            self.dispatcher.post(self._job_changed, job)

        job.status = "downloading"
        self.dispatcher.post(self._job_changed, job)
        try:
            lib = job.library
            track = job.track
            result = self.service.download(track, lib.default_download_dir(track.artist, track.album), on_progress=progress)
            job.status, job.percent = "adding", 100.0
            self.dispatcher.post(self._job_changed, job)
            added = lib.add_track(
                Path(result.file_path), track.title, track.artist, track.album, track.url, job.playlist_ids
            )
            self.service.refresh_library()
            job.file_path, job.content_id, job.status = result.file_path, added.content_id, "done"
            if lib.last_problems:
                self.dispatcher.post(self.message, "warn", t("msg.added_with_problems", title=track.title,
                                                             detail=" ; ".join(lib.last_problems)[:200]))
            if lib.pdb_state == "stale" and lib.pdb_problem:
                self.dispatcher.post(self.message, "warn", t("msg.pdb_not_updated_track", title=track.title,
                                                             detail=lib.pdb_problem))
        except Exception as exc:  # noqa: BLE001 - affiché dans la ligne du téléchargement
            log.warning("Download %s failed: %s", job.track.video_id, exc)
            job.status, job.message = "error", str(exc).replace("ERROR: ", "")[:300]
        self.dispatcher.post(self._job_changed, job)
        if job.status == "done":
            self.dispatcher.post(self._emit, "library")

    def retry(self, job: DownloadJob) -> None:
        if job.status != "error" or self.library is None:
            return
        job.status, job.percent, job.message, job.library = "queued", 0.0, "", self.library
        self._emit("download_update", job)
        self.dispatcher.submit(lambda: self._run_job(job), pool="dl")

    def remove_job(self, job: DownloadJob) -> None:
        if not job.is_active and job.status != "queued" and job in self.jobs:
            self.jobs.remove(job)
            self._emit("downloads")

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if not j.is_finished]
        self._emit("downloads")

    @property
    def active_jobs(self) -> int:
        return sum(1 for j in self.jobs if not j.is_finished)
