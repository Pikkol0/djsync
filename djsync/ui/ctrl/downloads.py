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
        if created and self._auto_analysis():          # 1.4.0-rc.5 (C161) : l'analyse compte tout le lot d'emblée
            self.analyze([], quiet=True, expect=[j.id for j in created])
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
            from ...core.soundcloud import track_info

            out = []
            for x in todo:
                info = track_info(x.url)
                out.append(replace(x, original_available=info["original"], free_download_url=info["free_url"]))
            return out

        self.dispatcher.submit(work, ok, lambda _e: None, pool="net")

    def _job_changed(self, job: DownloadJob) -> None:
        if job.status == "error" and self.analysis.drop(job.id):    # 1.4.0-rc.5 (C161) : retiré du total
            self._emit("analysis")
        self._emit("download_update", job)

    def _auto_analysis(self) -> bool:
        s = self.settings
        return bool(s.analyze_after_download_local if self.is_local else s.analyze_after_download_usb)

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

        if getattr(self, "_youtube_paused", False) and job.track.source in ("youtube", "ytmusic"):   # B66 : pause
            job.status, job.message, job.reason = "error", t("error.youtube_bot"), "error.youtube_bot"
            self.dispatcher.post(self._job_changed, job)
            return
        if job.track.source == "soulseek":              # 1.4.0 (C10.2)
            self._run_slsk_job(job)
            return
        job.status = "downloading"
        self.dispatcher.post(self._job_changed, job)
        try:
            lib = job.library
            track = job.track
            check = getattr(lib, "ensure_writable", None)
            if check is not None:                     # 1.3.2 (B54) : Rekordbox ouvert -> refus AVANT le téléchargement
                check()
            if self.settings.fetch_metadata:          # album, année, genre, label… (Deezer, sans compte)
                from ...core.metadata import enrich

                track = enrich(track)
            result = self.service.download(track, lib.default_download_dir(track.artist, track.album), on_progress=progress)
            fmt = "" if getattr(lib, "is_local", False) else (self.settings.player_format or "")
            from ...core import players

            if players.needs(Path(result.file_path), fmt):     # C26 sens C : FLAC d'origine pour les platines
                job.status = "converting"
                self.dispatcher.post(self._job_changed, job)
                flac = Path(result.file_path)
                out = players.convert(flac, players.target_path(flac, fmt), fmt, self.settings.ffmpeg_location or None)
                flac.unlink(missing_ok=True)
                result = replace(result, file_path=str(out))
            job.status, job.percent = "adding", 100.0
            self.dispatcher.post(self._job_changed, job)
            meta = {"year": track.year, "release_date": track.release_date, "genre": track.genre,
                    "label": track.label, "track_no": track.track_no, "isrc": track.isrc}
            try:
                added = lib.add_track(
                    Path(result.file_path), track.title, track.artist, track.album, track.url, job.playlist_ids,
                    meta=meta,
                )
            except Exception:
                # 1.3.2 (B54) : pas de fichier orphelin ; une relance retéléchargeait sous un autre nom (« [id] »)
                try:
                    Path(result.file_path).unlink()
                    log.info("Download %s not added to the library: file removed (%s)", track.video_id,
                             Path(result.file_path).name)
                except OSError:
                    pass
                raise
            self.service.refresh_library()
            job.file_path, job.content_id = result.file_path, added.content_id
            job.original = bool(getattr(result, "original", False))
            if track.want_original and not job.original:      # C10.1 : dit pourquoi on a eu le flux
                self.dispatcher.post(self.message, "info", t("sc.original_not_given", title=track.title))
            if job.replace_ids:                       # V1.1.0 : diagnostic, remplacer une mauvaise version
                self._finish_replace(job, lib)
            self._genre_after_change(lib)             # 1.2.2 : playlists par genre tenues à jour
            job.status = "done"
            self._bot_streak = 0                      # 1.4.0-rc.2 (B66) : YouTube répond de nouveau
            if lib.last_problems:
                self.dispatcher.post(self.message, "warn", t("msg.added_with_problems", title=track.title,
                                                             detail=" ; ".join(lib.last_problems)[:200]))
            warning = pdb_warning(lib, track.title)
            if warning:
                self.dispatcher.post(self.message, "warn", warning)
        except Exception as exc:  # noqa: BLE001 - affiché dans la ligne du téléchargement
            log.warning("Download %s failed: %s", job.track.video_id, exc)
            from ..controller import is_offline_error, known_error

            key = "error.offline" if is_offline_error(exc) else known_error(exc)
            job.status, job.message = "error", (t(key) if key else str(exc).replace("ERROR: ", "")[:300])
            job.reason = key                                       # 1.4.0-rc.2 (B66)
            if key == "error.youtube_bot":
                self.dispatcher.post(self._youtube_bot, job)
            else:
                self.dispatcher.post(self.engine_failure, job.message)
        self.dispatcher.post(self._job_changed, job)
        if job.status == "done":
            self.dispatcher.post(self._emit, "library")
            self.dispatcher.post(self._analyse_after_download, job)

    def _analyse_after_download(self, job: DownloadJob) -> None:
        """1.3.0-rc.3 (C32) : son téléchargé mis dans la file d'analyse en arrière-plan (le téléchargement
        suivant n'attend pas). Réglage séparé pour la clé et pour la bibliothèque de l'ordinateur ; rien
        si l'utilisateur a changé de bibliothèque entre-temps."""
        q = self.analysis
        if job.id in q.stopped:                  # 1.4.0-rc.5 (C161) : analyse arrêtée : pas de relance
            return
        if not job.content_id or job.library is None or job.library is not self.library or not self._auto_analysis():
            if q.drop(job.id):
                self._emit("analysis")
            return
        if q.running and q.fulfil(job.id, job.content_id):         # attendu : déjà compté dans le total
            self._emit("analysis")
            return
        q.drop(job.id)
        self.analyze([job.content_id], quiet=True)

    # ---------------------------------------------------------------- 1.4.0-rc.2 (B66) : YouTube « robot »
    BOT_PAUSE_AFTER = 3

    def _youtube_bot(self, job: DownloadJob) -> None:
        """YouTube demande de prouver qu'on n'est pas un robot (souvent un VPN) : message clair, bouton vers
        le réglage du navigateur ; après plusieurs échecs d'affilée, les sons YouTube en attente sont mis de
        côté (en erreur, même raison) pour ne pas aggraver le blocage."""
        self._bot_streak = getattr(self, "_bot_streak", 0) + 1
        if self._bot_streak == 1 or self._bot_streak == self.BOT_PAUSE_AFTER:
            self.message("error", t("error.youtube_bot"))
            self._emit("message_action", t("error.youtube_bot_action"),
                       lambda: self._emit("open_settings_section", "download"))
        if self._bot_streak >= self.BOT_PAUSE_AFTER:
            self._youtube_paused = True

    def youtube_paused(self, job: DownloadJob) -> bool:
        return bool(getattr(self, "_youtube_paused", False)) and job.track.source in ("youtube", "ytmusic")

    def retry_bot_failures(self) -> None:
        """Navigateur choisi : on relance les sons refusés pour cette raison."""
        self._bot_streak, self._youtube_paused = 0, False
        for job in list(self.jobs):
            if job.status == "error" and getattr(job, "reason", "") == "error.youtube_bot":
                self.retry(job)

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
            self._batch_from = None
            return 0, 0, 1.0
        # 1.4.0 (B55) : la série commence au premier téléchargement lancé alors que rien ne tournait, et garde ce
        # début tant qu'elle n'est pas finie (avant, chaque son terminé en sortait : la barre retombait à 0)
        start = getattr(self, "_batch_from", None)
        if start is None or start > first or start >= len(jobs):
            start = self._batch_from = first
        batch = jobs[start:]
        done = sum(1 for j in batch if j.is_finished)
        return done, len(batch), sum(j.progress for j in batch) / len(batch)

    @property
    def active_jobs(self) -> int:
        return sum(1 for j in self.jobs if not j.is_finished)
