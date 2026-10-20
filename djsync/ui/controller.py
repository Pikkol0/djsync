"""Contrôleur : toute la logique de l'application, SANS widget.

Les vues appellent ces méthodes ; les opérations lentes (réseau, base, FFmpeg, analyse) tournent
dans des threads (UiDispatcher) et rappellent la vue dans le thread UI. Les vues écoutent des
évènements : "drive", "drives", "library", "downloads", "download_update", "message",
"navigate", "player", "queue", "zoom", "rebuild_ui".

V0.2.0 : découpé par sujet (ce fichier : évènements, clé USB, recherche, import, réglages) :
  * ctrl/library_ops.py : bibliothèque, playlists, export.pdb, analyse, doublons, grille ;
  * ctrl/downloads.py   : file de téléchargements ;
  * ctrl/playback.py    : lecture, file d'écoute (précédent / suivant), formes d'onde.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from .. import portable
from ..audio.player import AudioPlayer
from ..core.service import MusicService
from ..core.spotify import SpotifyError, parse_text_list
from ..core.urlimport import UrlImportError
from ..db import (
    DatabaseLockedError, DriveNotFoundError, LibraryError, RekordboxUsbLibrary, UsbDrive,
    drive_from_letter, find_usb_drives,
)
from ..db.errors import (
    DatabaseOpenError, DuplicatePlaylistError, PlaylistNotFoundError, ReadOnlyError, TrackNotFoundError,
    UnsupportedFormatError,
)
from ..i18n import get_language, t
from ..models import (
    Candidate, DownloadJob, PlaylistInfo, SearchMode, SpotifyPlaylist, SpotifyTrack, TrackResult, UrlKind,
)
from ..settings import Settings
from .ctrl.downloads import DownloadsMixin
from .ctrl.library_ops import DriveSummary, LibraryOpsMixin, TaskHandle  # noqa: F401 (ré-export)
from .ctrl.playback import PlaybackMixin, QueueItem  # noqa: F401 (ré-export)
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


class AppController(LibraryOpsMixin, DownloadsMixin, PlaybackMixin):
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
            post=dispatcher.post, on_event=lambda k, p: self._player_event(k, p),
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
        self._init_playback()

    # ------------------------------------------------------------------ évènements
    def on(self, event: str, fn: Callable[..., None]) -> None:
        self._listeners[event].append(fn)

    def listener_mark(self) -> Dict[str, int]:
        """Instantané du nombre d'écouteurs par évènement (voir reset_listeners)."""
        return {k: len(v) for k, v in self._listeners.items()}

    def reset_listeners(self, mark: Dict[str, int]) -> None:
        """Oublie les écouteurs ajoutés depuis `mark` (vues détruites par une reconstruction de l'UI)."""
        for event in list(self._listeners):
            del self._listeners[event][mark.get(event, 0):]

    def _emit(self, event: str, *args: Any) -> None:
        for fn in list(self._listeners[event]):
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - une vue en erreur ne doit pas casser les autres
                log.exception("Listener %s", event)

    def message(self, kind: str, text: str) -> None:
        """kind : info | ok | warn | error — affiché dans la barre d'état."""
        self._emit("message", kind, text)

    # erreurs fréquentes : message traduit ; les autres gardent le détail technique
    _ERROR_KEYS = (
        (DatabaseLockedError, "error.db_locked"), (ReadOnlyError, "error.read_only"),
        (DuplicatePlaylistError, "error.duplicate_playlist"), (PlaylistNotFoundError, "error.playlist_not_found"),
        (TrackNotFoundError, "error.track_not_found"), (UnsupportedFormatError, "error.unsupported_format"),
        (DriveNotFoundError, "error.drive_not_found"), (DatabaseOpenError, "error.db_open"),
    )

    def error_text(self, exc: BaseException) -> str:
        """Messages d'exception écrits en anglais (V0.2.1) ; les plus fréquents sont traduits dans
        les autres langues, les autres restent en anglais."""
        if get_language() != "en":
            for cls, key in self._ERROR_KEYS:
                if isinstance(exc, cls):
                    return t(key, detail=str(exc))
        if isinstance(exc, (LibraryError, SpotifyError, UrlImportError)):
            return str(exc)
        return f"{type(exc).__name__}: {exc}"

    def _on_error(self, exc: BaseException) -> None:
        self.message("error", self.error_text(exc))

    @property
    def has_library(self) -> bool:
        return self.library is not None

    @property
    def drive_label(self) -> str:
        return str(self.drive) if self.drive else t("nav.no_drive")

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
            self.message("warn", t("msg.several_drives", n=len(candidates)))
            self._emit("navigate", "home")

    def connect(self, drive: Union[UsbDrive, str], remember: bool = True) -> None:
        """Ouvre la bibliothèque d'une clé (lettre forcée « E », chemin, ou UsbDrive détecté)."""
        if self._connecting:
            return
        self._connecting = True
        self._user_disconnected = False
        old = self.library
        if old is not None and self.analysis.running:
            self.analysis.cancel()

        def work() -> Any:
            target = drive if isinstance(drive, UsbDrive) else drive_from_letter(str(drive))
            lib = RekordboxUsbLibrary(
                target, contents_dir=self.settings.contents_dir, backup_keep=self.settings.backup_keep,
                pdb_sync=self.settings.pdb_sync, pdb_allow_growth=self.settings.pdb_allow_growth,
                analyze=self.settings.analyze_on_add, artwork=True,
                ffmpeg_location=self.settings.ffmpeg_location or None, key_notation=self.settings.key_notation,
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
            self.message("ok", t("msg.drive_connected", drive=str(self.drive)))
            self._emit("drive")

        def err(exc: BaseException) -> None:
            self._connecting = False
            failed = str(drive.root if isinstance(drive, UsbDrive) else drive)
            self._connect_failed.add(failed)
            self._on_error(exc)

        self.dispatcher.submit(work, ok, err, pool="db")

    def disconnect(self, by_user: bool = True) -> None:
        lib = self.library
        if self.analysis.running:            # V0.2.3 : la file d'analyse ne survit pas à la clé
            self.analysis.cancel()
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
                self.message("warn", t("msg.drive_unplugged", drive=str(active)))
                self.disconnect(by_user=False)
            elif self.library is None and changed:
                self._auto_connect()
            root.after(POLL_MS, self._poll)

        def err(_exc: BaseException) -> None:
            self._polling = False
            root.after(POLL_MS, self._poll)

        self.dispatcher.submit(probe, ok, err, pool="net")

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
            (err or self._on_error)(UrlImportError(t("error.url_unknown")))
            return
        self.dispatcher.submit(work, lambda r: ok(*r), err or self._on_error, pool="net")

    def is_url(self, text: str) -> bool:
        """Omnibar : lien à importer (Spotify, YouTube, SoundCloud) ou texte à chercher ?"""
        text = (text or "").strip()
        if not text or " " in text:
            return False
        return self.service.classify_url(text) != UrlKind.UNKNOWN or text.lower().startswith(("http://", "https://"))

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
            self.library.analyze = s.analyze_on_add
            self.library.artwork = True
            self.library.ffmpeg_location = s.ffmpeg_location or None
            self.library.key_notation = s.key_notation
        s.save()

    @staticmethod
    def ffmpeg_status(location: str) -> Tuple[bool, str]:
        """(trouvé ?, texte d'état) pour l'onglet Paramètres."""
        if location:
            for name in ("ffmpeg.exe", "ffmpeg"):
                if (Path(location) / name).is_file():
                    return True, t("settings.ffmpeg_found", path=str(Path(location) / name))
            return False, t("settings.ffmpeg_not_in_folder")
        found = shutil.which("ffmpeg")
        return (True, t("settings.ffmpeg_in_path", path=found)) if found else (False, t("settings.ffmpeg_missing"))

    # ------------------------------------------------------------------- fermeture
    def shutdown(self) -> None:
        self.analysis.cancel()
        self.settings.volume = self.player.volume
        self.settings.save()
        self.player.close()
        lib, self.library = self.library, None
        if lib is not None:
            try:
                lib.close()
            except Exception:  # noqa: BLE001
                log.exception("Closing the database")
        if self._preview_dir is not None:
            shutil.rmtree(self._preview_dir, ignore_errors=True)
        self.dispatcher.shutdown()
