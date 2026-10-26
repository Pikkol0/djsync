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
    drive_from_letter, find_unprepared_drives, find_usb_drives,
)
from ..db.errors import (
    DatabaseOpenError, DuplicatePlaylistError, PlaylistNotFoundError, ReadOnlyError, TrackNotFoundError,
    UnsupportedFormatError,
)
from ..db import local_library as _local
from ..db.local_library import LocalRekordbox, LocalRekordboxLibrary, find_local_rekordbox
from ..i18n import get_language, t
from ..models import (
    Candidate, DownloadJob, PlaylistInfo, SearchMode, SpotifyPlaylist, SpotifyTrack, TrackResult, UrlKind,
)
from ..settings import Settings
from .ctrl.downloads import DownloadsMixin
from .ctrl.engine import EngineMixin
from .ctrl.tools import ToolsMixin
from .ctrl.backups import BackupsMixin
from .ctrl.curation import CurationMixin
from .ctrl.diagnostic import DiagnosticMixin
from .ctrl.library_ops import DriveSummary, LibraryOpsMixin, TaskHandle  # noqa: F401 (ré-export)
from .ctrl.playback import PlaybackMixin, QueueItem  # noqa: F401 (ré-export)
from .runner import UiDispatcher

log = logging.getLogger(__name__)

Callback = Callable[[Any], None]
UPDATE_DELAY_MS = 6000       # nouvelle version de DJSync : vérifiée après le démarrage
POLL_MS = 4000


_OFFLINE = ("max retries exceeded", "failed to establish a new connection", "getaddrinfo failed",
            "name or service not known", "temporary failure in name resolution", "nodename nor servname",
            "network is unreachable", "no route to host", "unable to connect to proxy", "connecttimeout",
            "connection refused", "urlopen error", "errno 11001")


def is_offline_error(exc: Any) -> bool:
    """Pas d'Internet (ou serveur injoignable) : message clair plutôt que la trace technique."""
    try:
        import requests

        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
    except ImportError:                 # pragma: no cover
        pass
    text = str(exc).lower()
    return any(k in text for k in _OFFLINE)


def _same_path(a: Any, b: Any) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


def _flush() -> None:
    import os

    if hasattr(os, "sync"):
        os.sync()


def eject_volume(root: Any) -> bool:
    """Éjection système (Windows : comme « Éjecter » dans l'Explorateur). True si réussie."""
    import subprocess
    import sys

    root = str(root)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if sys.platform == "win32":
            letter = root.rstrip("\\/")[:2]
            script = (f"$d=(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{letter}');"
                      "if($d){$d.InvokeVerb('Eject')}; Start-Sleep -Milliseconds 1500;"
                      f"if(Test-Path '{letter}\\'){{exit 1}}")
            proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                  capture_output=True, timeout=30, creationflags=flags)
            return proc.returncode == 0
        if sys.platform == "darwin":
            return subprocess.run(["diskutil", "eject", root], capture_output=True, timeout=30).returncode == 0
        return subprocess.run(["gio", "mount", "-e", root], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _unprepared() -> List[Any]:
    """Clés sans bibliothèque (T02) ; jamais bloquant."""
    try:
        return find_unprepared_drives()
    except Exception as exc:  # noqa: BLE001 - information seulement
        log.debug("Unprepared drives: %s", exc)
        return []


class MatchHandle:
    """Permet d'interrompre une série de correspondances Spotify."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class AppController(LibraryOpsMixin, DownloadsMixin, PlaybackMixin, EngineMixin, ToolsMixin,
                    DiagnosticMixin, BackupsMixin, CurationMixin):
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
        self._apply_output()

        self.drive: Optional[UsbDrive] = None
        self.library: Optional[RekordboxUsbLibrary] = None
        self.drives: List[UsbDrive] = []
        self.unprepared: List[Any] = []            # 1.2.4 (T02) : clés sans bibliothèque
        self.duplicate_matches: Dict[int, Any] = {}   # 1.3.0 (B02) : verdicts audio de l'outil Doublons
        self.local: Optional[LocalRekordbox] = None    # V0.4.0 : Rekordbox installé sur cet ordinateur
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
        self._local_offered = False
        self._rekordbox_warned = False
        self._init_playback()
        self.error_reporter = self._make_error_reporter()       # 1.2.3

    def _make_error_reporter(self) -> Any:
        """1.2.3 : rapports d'erreur à l'auteur (demande à l'utilisateur, sauf réglage contraire)."""
        from .. import full_version
        from ..core.error_reports import ErrorReporter
        from ..settings import settings_dir

        def context() -> Dict[str, Any]:
            lib = t("local.name") if self.is_local else ("USB" if self.has_library else "")
            root = None if (self.drive is None or self.is_local) else getattr(self.drive, "root", None)
            return {"version": full_version(), "library": lib, "drive_root": root,
                    "client": self.feedback_client_id(), "log_dir": settings_dir()}

        def ask(summary: str, answer: Callable[[bool], None]) -> None:
            self.dispatcher.post(lambda: self._emit("error_report_ask", summary, answer))

        return ErrorReporter(settings_dir() / "error_reports.json", lambda: self.settings.error_reports, context,
                             ask=ask)

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
        if is_offline_error(exc):
            return t("error.offline")
        low = str(exc).lower()
        if self.is_local and ("malformed" in low or "file is not a database" in low):
            return t("error.local_db_unreadable")        # V1.2.0 : retour testeur macOS
        if get_language() != "en":
            for cls, key in self._ERROR_KEYS:
                if isinstance(exc, cls):
                    return t(key, detail=str(exc))
        if isinstance(exc, (LibraryError, SpotifyError, UrlImportError)):
            return str(exc)
        return f"{type(exc).__name__}: {exc}"

    def _on_error(self, exc: BaseException) -> None:
        log.warning("Error shown to the user: %s", exc, exc_info=exc)     # trace complète dans djsync.log
        self.message("error", self.error_text(exc))
        reporter = getattr(self, "error_reporter", None)
        if reporter is not None:
            reporter.report(exc, "shown to the user")

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
        self.dispatcher.call_later(POLL_MS, self._poll)
        self.dispatcher.call_later(UPDATE_DELAY_MS, self.app_update_check)
        from ..core import selfupdate                 # 1.2.0-rc.4 : restes d'une mise à jour précédente

        self.dispatcher.submit(selfupdate.cleanup, None, lambda exc: log.info("Update cleanup: %s", exc), pool="db")
        if portable.translocated():               # macOS : app encore en « quarantaine », copie temporaire
            self.message("warn", t("mac.translocated"))

    def find_local(self) -> Optional[LocalRekordbox]:
        """Rekordbox de cet ordinateur (dossier imposé dans les Paramètres, sinon emplacement standard)."""
        s = self.settings
        try:
            return find_local_rekordbox(s.local_db_dir, s.local_music_dir, t("local.name"))
        except OSError:
            return None

    def refresh_drives(self, then: Optional[Callable[[], None]] = None) -> None:
        def ok(result: Any) -> None:
            drives, local, unprepared = result
            if [str(d.root) for d in drives] != [str(d.root) for d in self.drives]:
                self._connect_failed.clear()
            self.drives, self.local, self.unprepared = drives, local, unprepared
            self._emit("drives")
            if then:
                then()

        self.dispatcher.submit(lambda: (find_usb_drives(), self.find_local(), _unprepared()), ok, self._on_error,
                               pool="net")

    @property
    def is_local(self) -> bool:
        """La bibliothèque active est-elle celle de l'ordinateur ?"""
        return isinstance(self.drive, LocalRekordbox)

    @staticmethod
    def host_name() -> str:
        import socket

        try:
            return socket.gethostname() or "?"
        except OSError:
            return "?"

    def local_allowed(self) -> bool:
        """Version portable (sur une clé, de PC en PC) : la bibliothèque Rekordbox du PC hôte n'est
        ouverte d'office que si l'utilisateur l'a acceptée une fois sur CE PC."""
        return not portable.is_portable() or self.host_name() in self.settings.local_hosts

    def allow_local(self) -> None:
        host = self.host_name()
        if host not in self.settings.local_hosts:
            self.settings.local_hosts.append(host)
            self.settings.save()

    def connect_local(self) -> None:
        """Choix explicite de l'utilisateur : vaut accord pour ce PC."""
        if self.local is not None:
            self.allow_local()
            self.connect(self.local)

    def _offer_local(self) -> bool:
        """Ouvre la bibliothèque de l'ordinateur, ou la propose (version portable sur un PC inconnu)."""
        if self.local is None or str(self.local.root) in self._connect_failed:
            return False
        if self.local_allowed():
            self.connect(self.local)
        elif not self._local_offered:
            self._local_offered = True
            self._emit("local_offer", self.local, self.host_name())
        return True

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
        if self.settings.active_drive == "local" and self.local is not None:
            if self._offer_local():
                return
        candidates = [d for d in self.drives if str(d.root) not in self._connect_failed]
        preferred = self.settings.active_drive.strip().rstrip(":\\/").upper()
        pick = next((d for d in candidates if preferred and (d.letter == preferred or str(d.root) == self.settings.active_drive)), None)
        if pick is None and len(candidates) == 1:
            pick = candidates[0]
        if pick is not None:
            self.connect(pick)
        elif not candidates and self.local is not None:
            self._offer_local()                     # aucune clé : la bibliothèque de l'ordinateur
        elif len(candidates) > 1:
            self.message("warn", t("msg.several_drives", n=len(candidates)))
            self._emit("navigate", "home")

    def connect(self, drive: Union[UsbDrive, LocalRekordbox, str], remember: bool = True) -> None:
        """Ouvre la bibliothèque d'une clé (lettre forcée « E », chemin, ou UsbDrive détecté)."""
        if self._connecting:
            return
        self._connecting = True
        self._user_disconnected = False
        old = self.library
        if old is not None and self.analysis.running:
            self.analysis.cancel()

        def work() -> Any:
            if isinstance(drive, LocalRekordbox):
                lib: Any = LocalRekordboxLibrary(
                    drive, backup_keep=self.settings.backup_keep, analyze=self.settings.analyze_on_add, artwork=True,
                    ffmpeg_location=self.settings.ffmpeg_location or None, key_notation=self.settings.key_notation,
                ).connect()
                lib.auto_cue = self.settings.auto_cue
                self.service.set_library(lib)
                if old is not None:
                    old.close()
                return drive, lib
            target = drive if isinstance(drive, UsbDrive) else drive_from_letter(str(drive))
            lib = RekordboxUsbLibrary(
                target, contents_dir=self.settings.contents_dir, backup_keep=self.settings.backup_keep,
                pdb_sync=self.settings.pdb_sync, pdb_allow_growth=self.settings.pdb_allow_growth,
                analyze=self.settings.analyze_on_add, artwork=True,
                ffmpeg_location=self.settings.ffmpeg_location or None, key_notation=self.settings.key_notation,
            ).connect()
            lib.auto_cue = self.settings.auto_cue
            try:                                      # 1.3.0 (T01) : utile pour les retours « platine »
                from ..db.usb import drive_filesystem

                pdb = target.db_path.parent / "export.pdb"
                log.info("Drive %s: file system %s, export.pdb %s", target, drive_filesystem(target.root) or "?",
                         f"present ({pdb.stat().st_size} bytes)" if pdb.is_file() else "absent")
            except OSError:
                pass
            self.service.set_library(lib)
            if old is not None:
                old.close()
            return target, lib

        def ok(result: Any) -> None:
            self._connecting = False
            self.drive, self.library = result
            if remember:
                self.settings.active_drive = ("local" if isinstance(self.drive, LocalRekordbox)
                                              else self.drive.letter or str(self.drive.root))
                self.settings.save()
            self.message("ok", t("msg.drive_connected", drive=self.drive.label or str(self.drive.root)))
            self._emit("drive")
            self._rekordbox_warned = False
            self._repair_pdb(self.library)

        def err(exc: BaseException) -> None:
            self._connecting = False
            failed = str(drive.root if isinstance(drive, (UsbDrive, LocalRekordbox)) else drive)
            self._connect_failed.add(failed)
            self._on_error(exc)

        self.dispatcher.submit(work, ok, err, pool="db")

    def disconnect(self, by_user: bool = True) -> None:
        lib = self.library
        if self.analysis.running:            # V0.2.4 : la file d'analyse ne survit pas à la clé
            self.analysis.cancel()
        self.library, self.drive = None, None
        self._user_disconnected = by_user
        self.playlists = []
        self.service.set_library(None)
        if lib is not None:
            self.dispatcher.submit(lib.close, pool="db")
        self._emit("drive")

    # ------------------------------------------- clé USB : export.pdb et Rekordbox (V1.0.0)
    def _repair_pdb(self, lib: Any) -> None:
        """À l'ouverture d'une clé : si export.pdb (Device Library, anciennes platines) a perdu des
        sons ou des playlists de exportLibrary.db — typiquement réécrit par Rekordbox ouvert en même
        temps —, rattrapage ADDITIF automatique (rien n'est supprimé ni réordonné)."""
        if lib is None or not getattr(lib, "supports_pdb", True) or getattr(lib, "read_only", False):
            return

        def work() -> Any:
            if lib.pdb_status().state != "stale":
                return None
            return lib.pdb_catch_up()

        def done(summary: Any) -> None:
            if summary is not None and (summary.tracks_added or summary.playlists_added or summary.entries_added):
                self.message("info", t("msg.pdb_repaired", tracks=summary.tracks_added,
                                       playlists=summary.playlists_added))

        self.dispatcher.submit(work, done, lambda exc: log.warning("export.pdb check: %s", exc), pool="db")

    def _warn_rekordbox(self, running: bool) -> None:
        """Rekordbox ouvert pendant que DJSync modifie la clé : il garde en mémoire une Device Library
        périmée et peut réécrire export.pdb par-dessus (sons ajoutés par DJSync perdus).
        V1.2.0 : quand Rekordbox se ferme, la bibliothèque de l'ordinateur est relue (playlists créées
        dans Rekordbox entre-temps, fichier master.db éventuellement remplacé)."""
        was = getattr(self, "_rekordbox_was_running", False)
        self._rekordbox_was_running = running
        if was and not running and self.is_local and self.library is not None:
            lib = self.library
            self.dispatcher.submit(lib.refresh, lambda _r: self._emit("library"),
                                   lambda exc: log.warning("Reopening the computer library: %s", exc), pool="db")
        if not running:
            self._rekordbox_warned = False
        elif self.library is not None and not self.is_local and not self._rekordbox_warned:
            self._rekordbox_warned = True
            self.message("warn", t("msg.rekordbox_open_usb"))

    # ---------------------------------------------------------------- éjection (V0.5.0)
    def eject(self) -> None:
        """Ferme proprement la clé (base fermée, journal WAL vidé, lecture arrêtée) puis l'éjecte.
        Si DJSync tourne depuis cette clé, Windows ne peut pas l'éjecter : on propose de quitter."""
        drive = self.drive
        if drive is None or self.is_local:
            return
        own = portable.own_drive_root()
        same = own is not None and _same_path(own, drive.root)
        lib = self.library
        if self.analysis.running:
            self.analysis.cancel()
        self.player.stop()
        self.library, self.drive = None, None
        self._user_disconnected = True
        self.playlists = []
        self.service.set_library(None)
        self._emit("drive")
        self.message("info", t("eject.working"))

        def work() -> bool:
            if lib is not None:
                lib.close()
            _flush()
            return True if same else eject_volume(drive.root)

        def ok(ejected: bool) -> None:
            if same:
                self._emit("eject_own", drive)
            elif ejected:
                self.message("ok", t("eject.done", drive=drive.label or str(drive.root)))
            else:
                self.message("warn", t("eject.closed_only", drive=drive.label or str(drive.root)))
            self.refresh_drives()

        self.dispatcher.submit(work, ok, self._on_error, pool="db")

    def _poll(self) -> None:
        """Surveille le branchement/débranchement des clés (toutes les 4 s, hors thread UI)."""
        if self._polling:
            self.dispatcher.call_later(POLL_MS, self._poll)
            return
        self._polling = True
        active = self.drive

        def probe() -> Any:
            return (find_usb_drives(), (active is None or active.db_path.is_file()), _local.rekordbox_running(),
                    _unprepared())

        def ok(result: Any) -> None:
            self._polling = False
            drives, still_there, rb_open, unprepared = result
            self._warn_rekordbox(rb_open)
            changed = [str(d.root) for d in drives] != [str(d.root) for d in self.drives]
            blank_changed = [(str(u.drive.root), u.kind) for u in unprepared] != \
                [(str(u.drive.root), u.kind) for u in self.unprepared]
            self.unprepared = unprepared
            if changed:
                self.drives = drives
                self._connect_failed.clear()
            if changed or blank_changed:
                self._emit("drives")
            if self.drive is not None and self.drive is active and not still_there:
                self.message("warn", t("msg.drive_unplugged", drive=active.label or str(active.root)))
                self.disconnect(by_user=False)
            elif self.library is None and changed:
                self._auto_connect()
            self.dispatcher.call_later(POLL_MS, self._poll)

        def err(_exc: BaseException) -> None:
            self._polling = False
            self.dispatcher.call_later(POLL_MS, self._poll)

        self.dispatcher.submit(probe, ok, err, pool="net")

    # ---------------------------------------------------------------- recherche
    def search(self, query: str, ok: Callback, err: Optional[Callback] = None) -> None:
        try:
            mode = SearchMode(self.settings.search_mode)
        except ValueError:
            mode = SearchMode.ALL
        exclude = self.settings.exclude_words
        extra: Dict[str, Any] = {}                 # 1.2.1 (C08) : champ et durée maximale
        if self.settings.search_field != "all":
            extra["field"] = self.settings.search_field
        if self.settings.search_max_minutes:
            extra["max_seconds"] = self.settings.search_max_minutes * 60
        self.dispatcher.submit(
            lambda: self.service.search(query, limit=20, mode=mode, exclude=exclude, **extra),
            ok, err or self._on_error, pool="net",
        )

    def feedback_client_id(self) -> str:
        """1.2.1 (C18) : identifiant aléatoire de cet ordinateur pour les limites d'envoi des retours
        (pas de nom, pas d'adresse : seulement de quoi compter les envois)."""
        if not self.settings.feedback_id:
            import uuid

            self.settings.feedback_id = uuid.uuid4().hex
            try:
                self.settings.save()
            except OSError:
                pass
        return self.settings.feedback_id

    def album_tracks(self, browse_id: str, ok: Callback, err: Optional[Callback] = None) -> None:
        self.dispatcher.submit(lambda: self.service.album_tracks(browse_id), ok, err or self._on_error, pool="net")

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
        def failed(exc: BaseException) -> None:
            (err or self._on_error)(exc)
            self.engine_failure(str(exc))

        self.dispatcher.submit(work, lambda r: ok(*r), failed, pool="net")

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
        self._apply_output()
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
            self.library.auto_cue = s.auto_cue
            if s.pdb_sync != "off" and not self.is_local:
                self._repair_pdb(self.library)      # option d'agrandissement activée : rattrapage aussitôt
        s.save()

    def _apply_output(self) -> None:
        if hasattr(self.service, "set_output"):
            self.service.set_output(self.settings.audio_format, self.settings.normalize_volume)

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
