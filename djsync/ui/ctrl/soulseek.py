"""Soulseek dans DJSync (1.4.0, C10.2) : connexion, recherche « haute qualité », téléchargements (dans la
file habituelle, onglet Téléchargements) et compteurs P2P. Le protocole est dans `core.soulseek`."""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
                found = self.slsk.search(query, duration=duration, on_partial=on_partial)
                self._slsk_last = list(found)            # 1.4.0-rc.2 (B60) : réserve d'autres pairs
                return found

            def failed(exc: BaseException) -> None:
                log.warning("Soulseek search failed: %s", exc)
                self.message("error", t("slsk.search_failed", detail=str(exc)[:160]))
                ok([])

            self.dispatcher.submit(work, ok, failed, pool="net")

        self.slsk_connect(run)

    def slsk_enqueue(self, results: List[Any], playlist_ids: List[int]) -> List[DownloadJob]:
        from ...core.soulseek import alternatives

        pool = list(getattr(self, "_slsk_last", []) or [])
        alts = self.__dict__.setdefault("_slsk_alts", {})
        jobs = self.enqueue([track_of(r) for r in results], playlist_ids)
        for job in jobs or []:
            if job.track.slsk is not None:               # 1.4.0-rc.2 (B60) : même fichier chez d'autres pairs
                alts.setdefault(job.id, []).extend(self.slsk_order(alternatives(job.track.slsk, pool)))
        return jobs

    # ------------------------------------------------------------------ téléchargement (fil « dl »)
    def _slsk_download_any(self, job: DownloadJob, result: Any, progress: Callable[[float, str], None]) -> Any:
        """1.4.0-rc.2 (B60) : si le pair bloque, refuse ou bannit, on passe tout seul au même fichier chez un
        autre pair. 1.4.0-rc.3 (B72) : un seul transfert à la fois par pair (un pair n'envoie qu'un ou deux
        fichiers à la fois par personne : les autres attendaient dans sa file et étaient coupés à 60 s) ;
        pair injoignable abandonné en 20 s ; en file chez le pair, on attend (moins longtemps s'il y a
        d'autres pairs)."""
        from dataclasses import replace

        from ...core.soulseek import QUEUE_WAIT_S, REACH_S, STALL_S, SoulseekError

        # liste partagée : remplie par slsk_enqueue / improve_apply, même si le travail a déjà démarré
        others = self.__dict__.setdefault("_slsk_alts", {}).setdefault(job.id, [])
        while True:
            result = self._slsk_claim(job, result, others, progress)
            claimed = result.username
            try:
                wait = 60.0 if others else QUEUE_WAIT_S
                return self.slsk.download(result, progress, stall=STALL_S, reach=REACH_S, queue_wait=wait)
            except SoulseekError as exc:
                self._slsk_mute(result.username, str(exc))
                if not others or str(exc) == "cancelled":
                    raise
                log.info("Soulseek: %s from %s (%s); trying another user", result.name, result.username, exc)
                result = others.pop(0)
                job.track = replace(job.track, slsk=result)
                job.message = t("slsk.next_peer", reason=str(exc)[:60])
                self.dispatcher.post(self._job_changed, job)
            finally:
                self._slsk_release(claimed)

    def slsk_order(self, results: List[Any]) -> List[Any]:
        """B72 : pairs restés muets pendant la session en dernier."""
        muted = self.__dict__.get("_slsk_muted", set())
        return sorted(results, key=lambda r: r.username in muted)

    # ---------------------------------------------------------------- B72 : un transfert par pair
    def _slsk_busy(self) -> Dict[str, int]:
        return self.__dict__.setdefault("_slsk_users", {})

    def _slsk_claim(self, job: DownloadJob, result: Any, others: List[Any],
                    progress: Callable[[float, str], None]) -> Any:
        """Réserve le pair de `result` ; s'il est déjà pris par un autre téléchargement, prend un autre pair
        libre qui a le même fichier, sinon attend son tour (« en attente : même pair »)."""
        from dataclasses import replace

        lock = self.__dict__.setdefault("_slsk_lock", threading.Lock())
        waited = False
        while True:
            with lock:
                busy = self._slsk_busy()
                if not busy.get(result.username):
                    busy[result.username] = job.id
                    return result
                free = next((r for r in others if not busy.get(r.username)), None)
                if free is not None:
                    others.remove(free)
                    others.append(result)                    # gardé en secours
                    busy[free.username] = job.id
                    job.track = replace(job.track, slsk=free)
                    return free
            if not waited:
                waited = True
                progress(0.0, "same_user")
            if job.status == "cancelled":
                from ...core.soulseek import SoulseekError

                raise SoulseekError("cancelled")
            time.sleep(1.0)

    def _slsk_release(self, username: str) -> None:
        lock = self.__dict__.setdefault("_slsk_lock", threading.Lock())
        with lock:
            self._slsk_busy().pop(username, None)

    def _slsk_mute(self, username: str, reason: str) -> None:
        """Pairs restés muets pendant la session : mis en bas des choix suivants."""
        if "no answer" in reason or "no data" in reason:
            self.__dict__.setdefault("_slsk_muted", set()).add(username)

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
            if state.startswith("queued_at:"):                       # 1.4.0-rc.3 (B72) : file chez le pair
                job.message = t("slsk.queued_at", n=state.split(":", 1)[1])
            elif state in ("same_user", "queued_remote"):
                job.message = t(f"slsk.{state}")
            else:
                job.message = t(f"slsk.state_{state}") if state in ("queued", "initializing", "downloading") else ""
            self.dispatcher.post(self._job_changed, job)

        try:
            if self.slsk is None or not self.slsk.connected:
                raise SoulseekError(t("slsk.not_connected"))
            path = self._slsk_download_any(job, result, progress)
            result = job.track.slsk or result
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
            from ..controller import known_error

            key = known_error(f"Soulseek: {exc}")
            job.status, job.message = "error", (t(key) if key else t("slsk.download_failed", detail=str(exc)[:200]))
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

