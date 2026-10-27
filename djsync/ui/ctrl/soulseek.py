"""Soulseek dans DJSync (1.4.0, C10.2) : connexion, recherche « haute qualité », téléchargements (dans la
file habituelle, onglet Téléchargements) et compteurs P2P. Le protocole est dans `core.soulseek`."""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Callable, List, Optional

from ...i18n import t
from ...models import DownloadJob, TrackResult

log = logging.getLogger(__name__)


def track_of(result: Any) -> TrackResult:
    """Résultat Soulseek -> TrackResult (pour la file de téléchargements). « Artiste - Titre » lu dans le
    nom du fichier ; le résultat d'origine voyage avec (`slsk`)."""
    from ...core.importer import _SPLIT

    stem = result.stem
    stem = re.sub(r"^\d{1,3}[\s.\-_]+", "", stem)          # « 01 - », « 03. »
    parts = _SPLIT.split(stem, maxsplit=1)
    artist, title = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("", stem.strip())
    key = hashlib.sha1(f"{result.username}\0{result.path}".encode("utf-8", "replace")).hexdigest()[:16]
    return TrackResult(video_id=f"slsk:{key}", title=title, artist=artist, album=result.folder or None,
                       duration_seconds=int(result.duration or 0), source="soulseek",
                       source_url=None, result_type="song", slsk=result)


class SoulseekMixin:
    slsk: Any = None                # core.soulseek.SoulseekClient une fois connecté

    # ------------------------------------------------------------------ état
    @property
    def slsk_ready(self) -> bool:
        s = self.settings
        return bool(s.soulseek_enabled and s.soulseek_accepted and s.soulseek_user and s.soulseek_password)

    def slsk_client_factory(self) -> Any:      # remplacée par les tests
        from ...core.soulseek import SoulseekClient
        from ...settings import settings_dir

        s = self.settings
        share = None
        if s.soulseek_share:
            lib = self.library
            share = getattr(lib, "contents_root", None) or (s.local_music_dir or None)
        return SoulseekClient(s.soulseek_user, s.soulseek_password, settings_dir() / "soulseek" / "incoming",
                              share_dir=Path(share) if share else None, port=int(s.soulseek_port or 0))

    def slsk_connect(self, ok: Optional[Callable[[], None]] = None) -> None:
        """Connexion (fil « net ») ; ne fait rien si déjà connecté."""
        if not self.slsk_ready:
            self.message("warn", t("slsk.not_ready"))
            return
        if self.slsk is not None and self.slsk.connected:
            if ok:
                ok()
            return

        def work() -> Any:
            client = self.slsk_client_factory()
            client.start()
            return client

        def done(client: Any) -> None:
            self.slsk = client
            self._emit("slsk")
            self.message("ok", t("slsk.connected", user=self.settings.soulseek_user))
            if ok:
                ok()

        def failed(exc: BaseException) -> None:
            log.warning("Soulseek connection failed: %s", exc)
            self.message("error", t("slsk.connect_failed", detail=str(exc)[:160]))
            self._emit("slsk")

        self.dispatcher.submit(work, done, failed, pool="net")

    def slsk_disconnect(self) -> None:
        client, self.slsk = self.slsk, None
        if client is not None:
            self.dispatcher.submit(client.stop, pool="net")
        self._emit("slsk")

    # ------------------------------------------------------------------ recherche
    def slsk_search(self, query: str, ok: Callable[[List[Any]], None], partial: Optional[Callable[[List[Any]], None]] = None,
                    duration: int = 0) -> None:
        def run() -> None:
            def work() -> List[Any]:
                on_partial = (lambda rs: self.dispatcher.post(partial, rs)) if partial else None
                return self.slsk.search(query, duration=duration, on_partial=on_partial)

            def failed(exc: BaseException) -> None:
                log.warning("Soulseek search failed: %s", exc)
                self.message("error", t("slsk.search_failed", detail=str(exc)[:160]))
                ok([])

            self.dispatcher.submit(work, ok, failed, pool="net")

        self.slsk_connect(run)

    def slsk_enqueue(self, results: List[Any], playlist_ids: List[int]) -> List[DownloadJob]:
        return self.enqueue([track_of(r) for r in results], playlist_ids)

    # ------------------------------------------------------------------ téléchargement (fil « dl »)
    def _run_slsk_job(self, job: DownloadJob) -> None:
        """Téléchargement Soulseek -> fichier temporaire -> import (copie / conversion pour les platines,
        tags, doublons) -> vraie qualité vérifiée (C46) ; un faux sans perte est signalé."""
        from ...core import importer
        from ...core.soulseek import SoulseekError

        lib, track = job.library, job.track
        result = track.slsk

        def progress(pct: float, state: str) -> None:
            job.status = "downloading"
            job.percent = pct
            job.message = t(f"slsk.state_{state}") if state in ("queued", "initializing", "downloading") else ""
            self.dispatcher.post(self._job_changed, job)

        try:
            if self.slsk is None or not self.slsk.connected:
                raise SoulseekError(t("slsk.not_connected"))
            path = self.slsk.download(result, progress)
            job.status, job.percent = "adding", 100.0
            self.dispatcher.post(self._job_changed, job)
            src = Path(path)
            if getattr(lib, "is_local", False):                 # ordinateur : rangé dans le dossier de musique
                folder = Path(lib.default_download_dir(track.artist or "Unknown Artist", track.album))
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / src.name
                k = 2
                while dest.exists():
                    dest = folder / f"{src.stem} ({k}){src.suffix}"
                    k += 1
                shutil.move(str(src), str(dest))
                src = dest
            fmt = "" if getattr(lib, "is_local", False) else (self.settings.player_format or "")
            report = importer.import_files(lib, [src], job.playlist_ids, player_format=fmt,
                                           ffmpeg=self.settings.ffmpeg_location or None)
            if report.failed:
                raise SoulseekError(report.failed[0][1])
            added = (report.added or report.already)[0]
            if not getattr(lib, "is_local", False):
                src.unlink(missing_ok=True)                     # la copie est sur la clé
            self.service.refresh_library()
            job.file_path, job.content_id = str(lib.absolute_path(added)), added.content_id
            job.original = result.lossless
            if job.replace_ids:                                  # C47 : remplace une version faible
                self._finish_replace(job, lib)
            job.status = "done"
            self._slsk_check_quality(job, result)
        except Exception as exc:  # noqa: BLE001 - affiché dans la ligne du téléchargement
            log.warning("Soulseek download failed (%s): %s", getattr(result, "path", "?"), exc)
            job.status, job.message = "error", t("slsk.download_failed", detail=str(exc)[:200])
        self.dispatcher.post(self._job_changed, job)
        if job.status == "done":
            self.dispatcher.post(self._emit, "library")
            self.dispatcher.post(self._analyse_after_download, job)

    def _slsk_check_quality(self, job: DownloadJob, result: Any) -> None:
        """C46 : spectre mesuré tout de suite ; « FLAC » qui n'en est pas un -> avertissement + autre source."""
        try:
            from ...analysis.spectrum import measure_and_remember
            from ...core.quality import probe

            measure_and_remember(job.file_path, self.settings.ffmpeg_location or None)
            info = probe(Path(job.file_path))
        except Exception as exc:  # noqa: BLE001
            log.info("Quality check skipped: %s", exc)
            return
        if info.fake:
            text = t("slsk.fake", title=job.track.title, claimed=result.quality_label(), real=info.real_label)
            query = f"{job.track.artist} {job.track.title}".strip()
            self.dispatcher.post(self._emit, "message_action", text, lambda q=query: self._emit("slsk_search", q))

    def slsk_metrics(self) -> Any:
        return self.slsk.metrics if self.slsk is not None else None

