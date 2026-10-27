"""File de téléchargements : téléchargement natif -> tags -> ajout sur la clé (+ sauvegarde) -> playlists."""
from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...i18n import plural, t
from ...models import DownloadJob, TrackResult
from .library_ops import pdb_warning

log = logging.getLogger(__name__)


class DownloadsMixin:
    def enqueue(self, tracks: Sequence[TrackResult], playlist_ids: Sequence[int],
                original: Optional[bool] = None) -> List[DownloadJob]:
        """`original` (1.4.0, C10.1) : fichier d'origine SoundCloud oui / non ; None = réglage."""
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return []
        names = {p.playlist_id: p.name for p in self.playlists}
        self.last_playlist_ids = list(playlist_ids)
        created: List[DownloadJob] = []
        for track in tracks:
            if track.source == "soundcloud":
                want = self.settings.soundcloud_original if original is None else original
                track = replace(track, want_original=bool(want and track.original_available is not False))
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

    def check_originals(self, tracks: Sequence[TrackResult], ok: Any) -> None:
        """1.4.0 (C10.1) : pour chaque son SoundCloud, le fichier d'origine est-il téléchargeable ?
        `ok(tracks)` reçoit les sons mis à jour (original_available renseigné). Réseau, 50 au plus."""
        todo = [x for x in tracks if x.source == "soundcloud" and x.original_available is None][:50]
        if not todo:
            return

        def work() -> List[TrackResult]:
            from ...core.soundcloud import original_available

            return [replace(x, original_available=original_available(x.url)) for x in todo]

        self.dispatcher.submit(work, ok, lambda _e: None, pool="net")

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
            if self.settings.fetch_metadata:          # album, année, genre, label… (Deezer, sans compte)
                from ...core.metadata import enrich

                track = enrich(track)
            result = self.service.download(track, lib.default_download_dir(track.artist, track.album), on_progress=progress)
            job.status, job.percent = "adding", 100.0
            self.dispatcher.post(self._job_changed, job)
            meta = {"year": track.year, "release_date": track.release_date, "genre": track.genre,
                    "label": track.label, "track_no": track.track_no, "isrc": track.isrc}
            added = lib.add_track(
                Path(result.file_path), track.title, track.artist, track.album, track.url, job.playlist_ids,
                meta=meta,
            )
            self.service.refresh_library()
            job.file_path, job.content_id = result.file_path, added.content_id
            job.original = bool(getattr(result, "original", False))
            if track.want_original and not job.original:      # C10.1 : dit pourquoi on a eu le flux
                self.dispatcher.post(self.message, "info", t("sc.original_not_given", title=track.title))
            if job.replace_ids:                       # V1.1.0 : diagnostic, remplacer une mauvaise version
                self._finish_replace(job, lib)
            self._genre_after_change(lib)             # 1.2.2 : playlists par genre tenues à jour
            job.status = "done"
            if lib.last_problems:
                self.dispatcher.post(self.message, "warn", t("msg.added_with_problems", title=track.title,
                                                             detail=" ; ".join(lib.last_problems)[:200]))
            warning = pdb_warning(lib, track.title)
            if warning:
                self.dispatcher.post(self.message, "warn", warning)
        except Exception as exc:  # noqa: BLE001 - affiché dans la ligne du téléchargement
            log.warning("Download %s failed: %s", job.track.video_id, exc)
            from ..controller import is_offline_error

            job.status, job.message = "error", (t("error.offline") if is_offline_error(exc)
                                                else str(exc).replace("ERROR: ", "")[:300])
            self.dispatcher.post(self.engine_failure, job.message)
        self.dispatcher.post(self._job_changed, job)
        if job.status == "done":
            self.dispatcher.post(self._emit, "library")
            self.dispatcher.post(self._analyse_after_download, job)

    def _analyse_after_download(self, job: DownloadJob) -> None:
        """1.3.0-rc.3 (C32) : son téléchargé mis dans la file d'analyse en arrière-plan (le téléchargement
        suivant n'attend pas). Réglage séparé pour la clé et pour la bibliothèque de l'ordinateur ; rien
        si l'utilisateur a changé de bibliothèque entre-temps."""
        if not job.content_id or job.library is None or job.library is not self.library:
            return
        s = self.settings
        if not (s.analyze_after_download_local if self.is_local else s.analyze_after_download_usb):
            return
        self.analyze([job.content_id], quiet=True)

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

    def download_progress(self) -> Tuple[int, int, float]:
        """1.2.1 (C21) : (terminés, total, avancement 0-1) de la série en cours : du plus ancien
        téléchargement pas fini jusqu'au dernier ajouté. (0, 0, 1.0) si rien ne tourne."""
        jobs = list(self.jobs)
        first = next((i for i, j in enumerate(jobs) if not j.is_finished), None)
        if first is None:
            return 0, 0, 1.0
        batch = jobs[first:]
        done = sum(1 for j in batch if j.is_finished)
        return done, len(batch), sum(j.progress for j in batch) / len(batch)

    @property
    def active_jobs(self) -> int:
        return sum(1 for j in self.jobs if not j.is_finished)
