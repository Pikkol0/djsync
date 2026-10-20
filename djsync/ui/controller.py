"""Contrôleur : toute la logique de l'application, SANS widget.

Les vues appellent ces méthodes ; les opérations lentes (réseau, base, FFmpeg) tournent dans
des threads (UiDispatcher) et rappellent la vue dans le thread UI. Les vues écoutent des
évènements : "drive", "drives", "library", "downloads", "download_update", "message",
"navigate", "player".
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Union

from .. import portable
from ..audio.player import AudioPlayer, NowPlaying
from ..core.service import MusicService
from ..core.spotify import SpotifyError, parse_text_list
from ..core.urlimport import UrlImportError
from ..db import (
    AmbiguousDriveError, DatabaseLockedError, DriveNotFoundError, LibraryError, RekordboxUsbLibrary, UsbDrive,
    drive_from_letter, find_usb_drives,
)
from ..models import (
    Candidate, DownloadJob, LibraryTrack, PlaylistInfo, SearchMode, SpotifyPlaylist, SpotifyTrack, TrackResult,
    UrlKind,
)
from ..settings import Settings
from .runner import UiDispatcher

log = logging.getLogger(__name__)

Callback = Callable[[Any], None]
POLL_MS = 4000


class MatchHandle:
    """Permet d'interrompre une série de correspondances Spotify."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class AppController:
    def __init__(
        self,
        settings: Settings,
        dispatcher: UiDispatcher,
        service: Optional[MusicService] = None,
        player: Optional[AudioPlayer] = None,
    ) -> None:
        self.settings = settings
        self.dispatcher = dispatcher
        self.service = service or MusicService(ffmpeg_location=settings.ffmpeg_location or None)
        self.player = player or AudioPlayer(
            post=dispatcher.post, on_event=lambda k, p: self._emit("player", k, p),
            ffmpeg_location=settings.ffmpeg_location or None,
        )
        self.player.set_volume(settings.volume)

        self.drive: Optional[UsbDrive] = None
        self.library: Optional[RekordboxUsbLibrary] = None
        self.drives: List[UsbDrive] = []
        self.playlists: List[PlaylistInfo] = []
        self.jobs: List[DownloadJob] = []
        self.last_playlist_ids: List[int] = []   # pré-cochés dans le popup de téléchargement

        self._listeners: Dict[str, List[Callable[..., None]]] = defaultdict(list)
        self._job_seq = 0
        self._connecting = False
        self._connect_failed: Set[str] = set()
        self._user_disconnected = False
        self._preview_dir: Optional[Path] = None
        self._preview_files: Dict[str, str] = {}
        self._polling = False
        self._views_inflight: Set[str] = set()

    # ------------------------------------------------------------------ évènements
    def on(self, event: str, fn: Callable[..., None]) -> None:
        self._listeners[event].append(fn)

    def _emit(self, event: str, *args: Any) -> None:
        for fn in list(self._listeners[event]):
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - une vue en erreur ne doit pas casser les autres
                log.exception("Écouteur %s", event)

    def message(self, kind: str, text: str) -> None:
        """kind : info | ok | warn | error — affiché dans la barre d'état."""
        self._emit("message", kind, text)

    def _on_error(self, exc: BaseException) -> None:
        known = (LibraryError, SpotifyError, UrlImportError)
        self.message("error", str(exc) if isinstance(exc, known) else f"{type(exc).__name__} : {exc}")

    @property
    def has_library(self) -> bool:
        return self.library is not None

    @property
    def drive_label(self) -> str:
        return str(self.drive) if self.drive else "Aucune clé"

    @property
    def preview_dir(self) -> Path:
        if self._preview_dir is None:
            self._preview_dir = Path(tempfile.mkdtemp(prefix="djsync_preview_"))
        return self._preview_dir

    # ------------------------------------------------------------------- clé USB
    def startup(self) -> None:
        self.refresh_drives(then=self._auto_connect)
        self.dispatcher._root.after(POLL_MS, self._poll)

    def refresh_drives(self, then: Optional[Callable[[], None]] = None) -> None:
        def ok(drives: List[UsbDrive]) -> None:
            if [str(d.root) for d in drives] != [str(d.root) for d in self.drives]:
                self._connect_failed.clear()
            self.drives = drives
            self._emit("drives")
            if then:
                then()

        self.dispatcher.submit(find_usb_drives, ok, self._on_error, pool="net")

    def _auto_connect(self) -> None:
        if self.library or self._connecting or self._user_disconnected:
            return
        forced = self.settings.forced_drive.strip()
        if forced:
            self.connect(forced, remember=False)
            return
        own = portable.own_drive_root()            # DJSync lancé depuis la clé : c'est elle, d'office
        if own is not None:
            self.connect(str(own), remember=False)
            return
        candidates = [d for d in self.drives if str(d.root) not in self._connect_failed]
        preferred = self.settings.active_drive.strip().rstrip(":\\/").upper()
        pick = next((d for d in candidates if preferred and (d.letter == preferred or str(d.root) == self.settings.active_drive)), None)
        if pick is None and len(candidates) == 1:
            pick = candidates[0]
        if pick is not None:
            self.connect(pick)
        elif len(candidates) > 1:
            self.message("warn", str(AmbiguousDriveError(candidates)))
            self._emit("navigate", "settings")

    def connect(self, drive: Union[UsbDrive, str], remember: bool = True) -> None:
        """Ouvre la bibliothèque d'une clé (lettre forcée « E », chemin, ou UsbDrive détecté)."""
        if self._connecting:
            return
        self._connecting = True
        self._user_disconnected = False
        old = self.library

        def work() -> Any:
            target = drive if isinstance(drive, UsbDrive) else drive_from_letter(str(drive))
            lib = RekordboxUsbLibrary(
                target, contents_dir=self.settings.contents_dir, backup_keep=self.settings.backup_keep,
                pdb_sync=self.settings.pdb_sync, pdb_allow_growth=self.settings.pdb_allow_growth,
            ).connect()
            self.service.set_library(lib)
            if old is not None:
                old.close()
            return target, lib

        def ok(result: Any) -> None:
            self._connecting = False
            self.drive, self.library = result
            if remember:
                self.settings.active_drive = self.drive.letter or str(self.drive.root)
                self.settings.save()
            self.message("ok", f"Clé {self.drive} connectée.")
            self._emit("drive")

        def err(exc: BaseException) -> None:
            self._connecting = False
            failed = str(drive.root if isinstance(drive, UsbDrive) else drive)
            self._connect_failed.add(failed)
            if isinstance(exc, DatabaseLockedError):
                self.message("error", f"{exc} Fermez Rekordbox puis réessayez.")
            else:
                self._on_error(exc)

        self.dispatcher.submit(work, ok, err, pool="db")

    def disconnect(self, by_user: bool = True) -> None:
        lib = self.library
        self.library, self.drive = None, None
        self._user_disconnected = by_user
        self.playlists = []
        self.service.set_library(None)
        if lib is not None:
            self.dispatcher.submit(lib.close, pool="db")
        self._emit("drive")

    def _poll(self) -> None:
        """Surveille le branchement/débranchement des clés (toutes les 4 s, hors thread UI)."""
        root = self.dispatcher._root
        if self._polling:
            root.after(POLL_MS, self._poll)
            return
        self._polling = True
        active = self.drive

        def probe() -> Any:
            return find_usb_drives(), (active is None or active.db_path.is_file())

        def ok(result: Any) -> None:
            self._polling = False
            drives, still_there = result
            changed = [str(d.root) for d in drives] != [str(d.root) for d in self.drives]
            if changed:
                self.drives = drives
                self._connect_failed.clear()
                self._emit("drives")
            if self.drive is not None and self.drive is active and not still_there:
                self.message("warn", f"Clé {active} débranchée.")
                self.disconnect(by_user=False)
            elif self.library is None and changed:
                self._auto_connect()
            root.after(POLL_MS, self._poll)

        def err(_exc: BaseException) -> None:
            self._polling = False
            root.after(POLL_MS, self._poll)

        self.dispatcher.submit(probe, ok, err, pool="net")

    # ------------------------------------------------------- bibliothèque (lecture)
    def load_library(self, ok: Callback, err: Optional[Callback] = None) -> None:
        """ok({"playlists": [...], "tracks": [...]})."""
        lib = self.library
        if lib is None:
            ok({"playlists": [], "tracks": []})
            return

        def work() -> Dict[str, Any]:
            return {"playlists": lib.list_playlists(), "tracks": lib.list_tracks()}

        def done(data: Dict[str, Any]) -> None:
            if lib is self.library:
                self.playlists = data["playlists"]
                ok(data)

        self.dispatcher.submit(work, done, err or self._on_error, pool="db")

    def fetch_playlists(self, ok: Callback) -> None:
        lib = self.library
        if lib is None:
            ok([])
            return

        def done(playlists: List[PlaylistInfo]) -> None:
            self.playlists = playlists
            ok(playlists)

        self.dispatcher.submit(lib.list_playlists, done, self._on_error, pool="db")

    def playlist_tracks(self, playlist_id: int, ok: Callback) -> None:
        lib = self.library
        if lib is not None:
            self.dispatcher.submit(lambda: lib.get_playlist_tracks(playlist_id), ok, self._on_error, pool="db")

    # -------------------------------------------------------- bibliothèque (écriture)
    def _write(self, fn: Callable[[RekordboxUsbLibrary], Any], ok: Optional[Callback] = None,
               success: str = "", err: Optional[Callback] = None) -> None:
        """Exécute une écriture dans le thread DB. La sauvegarde (backup) AVANT modification
        est faite par la classe DB elle-même ; ici on rafraîchit les vues et les doublons."""
        lib = self.library
        if lib is None:
            self.message("error", "Aucune clé connectée.")
            return

        def work() -> Any:
            result = fn(lib)
            self.service.refresh_library()
            return result

        def done(result: Any) -> None:
            if lib.pdb_state == "stale" and lib.pdb_problem:
                self.message("warn", f"Modifié dans exportLibrary.db, mais pas dans export.pdb : {lib.pdb_problem}")
            elif success:
                self.message("ok", success)
            self._emit("library")
            if ok:
                ok(result)

        self.dispatcher.submit(work, done, err or self._on_error, pool="db")

    def create_playlist(self, name: str, parent_id: int = 0, ok: Optional[Callback] = None,
                        err: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.create_playlist(name, parent_id), ok, f"Playlist « {name.strip()} » créée.", err)

    def rename_playlist(self, playlist_id: int, name: str, ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.rename_playlist(playlist_id, name), ok, "Playlist renommée.")

    def delete_playlist(self, playlist_id: int, ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.delete_playlist(playlist_id), ok, "Playlist supprimée (les sons sont conservés).")

    def add_to_playlists(self, content_ids: Sequence[int], playlist_ids: Sequence[int]) -> None:
        def run(lib: RekordboxUsbLibrary) -> int:
            with lib.batch():
                return sum(lib.add_to_playlist(pid, content_ids) for pid in playlist_ids)
        self._write(run, lambda n: None, "Sons ajoutés aux playlists.")

    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        self._write(lambda lib: lib.remove_from_playlist(playlist_id, content_ids), None, "Retiré de la playlist.")

    def move_tracks(self, content_ids: Sequence[int], from_id: int, to_id: int) -> None:
        self._write(lambda lib: lib.move_tracks(content_ids, from_id, to_id), None, "Sons déplacés.")

    def save_order(self, playlist_id: int, content_ids: Sequence[int], ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.set_playlist_order(playlist_id, content_ids), ok, "Ordre enregistré.")

    def delete_tracks(self, content_ids: Sequence[int], delete_files: bool = True) -> None:
        def done(result: Any) -> None:
            removed, failures = result
            text = f"{removed} son(s) supprimé(s)."
            if failures:
                text += f" {failures} fichier(s) n'ont pas pu être effacés de la clé."
            self.message("warn" if failures else "ok", text)

        self._write(lambda lib: lib.delete_tracks(content_ids, delete_files), done)

    # ------------------------------------------------------------ export.pdb (anciennes platines)
    def pdb_status(self, ok: Callback) -> None:
        lib = self.library
        if lib is not None:
            self.dispatcher.submit(lib.pdb_status, ok, self._on_error, pool="db")

    def pdb_sync_now(self, ok: Optional[Callback] = None) -> None:
        def done(summary: Any) -> None:
            self.message("ok", f"export.pdb synchronisé : {summary.tracks_added} son(s), "
                               f"{summary.playlists_added} playlist(s) ajouté(s).")
            self._emit("library")
            if ok:
                ok(summary)
        lib = self.library
        if lib is None:
            self.message("error", "Aucune clé connectée.")
            return
        self.dispatcher.submit(lib.pdb_catch_up, done, self._on_error, pool="db")

    # ---------------------------------------------------------------- recherche
    def search(self, query: str, ok: Callback, err: Optional[Callback] = None) -> None:
        try:
            mode = SearchMode(self.settings.search_mode)
        except ValueError:
            mode = SearchMode.ALL
        exclude = self.settings.exclude_words
        self.dispatcher.submit(
            lambda: self.service.search(query, limit=20, mode=mode, exclude=exclude),
            ok, err or self._on_error, pool="net",
        )

    def enrich_views(self, tracks: Sequence[TrackResult], on_views: Callable[[str, int], None], max_items: int = 30) -> None:
        """Charge en arrière-plan les vues des Titres (absentes de la recherche)."""
        if not self.settings.fetch_views:
            return
        for track in [t for t in tracks if t.views is None][:max_items]:
            if track.video_id in self._views_inflight or track.source != "ytmusic":
                continue
            self._views_inflight.add(track.video_id)

            def done(views: Optional[int], vid: str = track.video_id) -> None:
                self._views_inflight.discard(vid)
                if views is not None:
                    on_views(vid, views)

            self.dispatcher.submit(
                lambda vid=track.video_id: self.service.fetch_views(vid), done,
                lambda _e, vid=track.video_id: self._views_inflight.discard(vid), pool="net",
            )

    def reannotate(self, tracks: Sequence[TrackResult], ok: Callback) -> None:
        """Re-marque les doublons (après un téléchargement ou un changement de clé)."""
        self.dispatcher.submit(lambda: self.service.annotate(tracks), ok, None, pool="net")

    # ------------------------------------------------------------ import par URL
    def import_url(self, url: str, ok: Callable[[str, Any], None], err: Optional[Callback] = None) -> None:
        """ok("spotify", SpotifyPlaylist) ou ok("direct", ResolvedUrl)."""
        kind = self.service.classify_url(url)
        if kind == UrlKind.SPOTIFY:
            work: Callable[[], Any] = lambda: ("spotify", self.service.fetch_spotify(url))  # noqa: E731
        elif kind in (UrlKind.YOUTUBE, UrlKind.SOUNDCLOUD):
            work = lambda: ("direct", self.service.resolve_direct(url))  # noqa: E731
        else:
            (err or self._on_error)(UrlImportError("URL non reconnue : collez un lien Spotify, YouTube ou SoundCloud."))
            return
        self.dispatcher.submit(work, lambda r: ok(*r), err or self._on_error, pool="net")

    @staticmethod
    def parse_pasted_list(text: str) -> SpotifyPlaylist:
        return parse_text_list(text)

    def match_spotify(self, sources: Sequence[SpotifyTrack], on_item: Callable[[int, List[Candidate]], None],
                      on_done: Callable[[], None]) -> MatchHandle:
        """Cherche (en parallèle, 3 à la fois) les candidats Titre ET Vidéo de chaque morceau."""
        handle = MatchHandle(len(sources))
        if not sources:
            on_done()
            return handle

        def finish(i: int, cands: List[Candidate]) -> None:
            if handle.cancelled:
                return
            handle.done += 1
            on_item(i, cands)
            if handle.done >= handle.total:
                on_done()

        for i, src in enumerate(sources):
            self.dispatcher.submit(
                lambda src=src: None if handle.cancelled else self.service.match_spotify(src),
                lambda cands, i=i: finish(i, cands or []),
                lambda exc, i=i: finish(i, []),
                pool="match",
            )
        return handle

    # ------------------------------------------------------------ téléchargements
    def enqueue(self, tracks: Sequence[TrackResult], playlist_ids: Sequence[int]) -> List[DownloadJob]:
        lib = self.library
        if lib is None:
            self.message("error", "Aucune clé connectée : branchez-la ou choisissez-la dans Paramètres.")
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
        where = f" → {', '.join(names.get(p, '?') for p in playlist_ids)}" if playlist_ids else " (bibliothèque seule)"
        self.message("info", f"{len(created)} téléchargement(s) ajouté(s){where}.")
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
            lib: RekordboxUsbLibrary = job.library
            track = job.track
            result = self.service.download(track, lib.default_download_dir(track.artist, track.album), on_progress=progress)
            job.status, job.percent = "adding", 100.0
            self.dispatcher.post(self._job_changed, job)
            added = lib.add_track(
                Path(result.file_path), track.title, track.artist, track.album, track.url, job.playlist_ids
            )
            self.service.refresh_library()
            job.file_path, job.content_id, job.status = result.file_path, added.content_id, "done"
            if lib.pdb_state == "stale" and lib.pdb_problem:
                self.dispatcher.post(self.message, "warn",
                                     f"« {track.title} » est dans exportLibrary.db mais pas dans export.pdb : {lib.pdb_problem}")
        except Exception as exc:  # noqa: BLE001 - affiché dans la ligne du téléchargement
            log.warning("Téléchargement %s en échec : %s", job.track.video_id, exc)
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

    # --------------------------------------------------------------------- lecture
    def preview(self, track: TrackResult) -> None:
        """Préécoute AVANT téléchargement sur la clé : fichier temporaire, lu dans le lecteur."""
        self.message("info", f"Préécoute : récupération de « {track.title} »…")
        cached = self._preview_files.get(track.video_id)

        def work() -> str:
            if cached and Path(cached).is_file():
                return cached
            return self.service.download(track, self.preview_dir, tag=False).file_path

        def ok(path: str) -> None:
            self._preview_files[track.video_id] = path
            self.player.play(path, NowPlaying(track.title, track.artist, path, cover_url=track.thumbnail_url))

        self.dispatcher.submit(work, ok, self._on_error, pool="net")

    def play_library_track(self, track: LibraryTrack) -> None:
        lib = self.library
        if lib is None:
            return
        path = lib.absolute_path(track)
        art = lib.artwork_file(track)
        self.player.play(path, NowPlaying(track.title, track.artist, str(path), cover_path=str(art) if art else None))

    def play_job(self, job: DownloadJob) -> None:
        if job.status == "done" and job.file_path:
            t = job.track
            self.player.play(job.file_path, NowPlaying(t.title, t.artist, job.file_path, cover_url=t.thumbnail_url))

    # -------------------------------------------------------------------- réglages
    def apply_settings(self) -> None:
        """Applique les réglages modifiés (FFmpeg, dossier de destination, sauvegardes) et les enregistre."""
        s = self.settings
        self.service.set_ffmpeg_location(s.ffmpeg_location or None)
        self.player.ffmpeg_location = s.ffmpeg_location or None
        if self.library is not None:
            self.library.contents_dir = s.contents_dir.strip("/\\") or "Contents"
            self.library.backup_keep = s.backup_keep
            self.library.pdb_sync = s.pdb_sync
            self.library.pdb_allow_growth = s.pdb_allow_growth
        s.save()

    @staticmethod
    def ffmpeg_status(location: str) -> str:
        """Texte d'état pour l'onglet Paramètres."""
        if location:
            for name in ("ffmpeg.exe", "ffmpeg"):
                if (Path(location) / name).is_file():
                    return f"FFmpeg trouvé : {Path(location) / name}"
            return "FFmpeg introuvable dans ce dossier."
        found = shutil.which("ffmpeg")
        return f"FFmpeg trouvé dans le PATH : {found}" if found else "FFmpeg introuvable : requis (téléchargement, lecture m4a)."

    # ------------------------------------------------------------------- fermeture
    def shutdown(self) -> None:
        self.settings.volume = self.player.volume
        self.settings.save()
        self.player.close()
        lib, self.library = self.library, None
        if lib is not None:
            try:
                lib.close()
            except Exception:  # noqa: BLE001
                log.exception("Fermeture de la base")
        if self._preview_dir is not None:
            shutil.rmtree(self._preview_dir, ignore_errors=True)
        self.dispatcher.shutdown()
