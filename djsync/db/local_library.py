"""Bibliothèque Rekordbox de CET ORDINATEUR (V0.4.0) : master.db de Rekordbox 6/7.

Même interface que `RekordboxUsbLibrary` (clé USB) pour tout ce que l'interface utilise : liste des
sons et des playlists, ajout d'un son téléchargé (analyse, pochette, métadonnées), playlists,
analyse, grille de temps, titre / artiste, doublons, suppression.

Relevé sur une vraie base (Rekordbox 7.2.11, 405 sons, Windows) :
  * master.db : SQLCipher 4, mode WAL, clé connue (pyrekordbox) ; tables « djmd… » ;
  * identifiants = entiers aléatoires en texte (« 83609858 ») + un UUID par ligne ;
  * chaque ligne modifiée reçoit un numéro de séquence (`rb_local_usn`) tiré du compteur
    `agentRegistry.localUpdateCount` : Rekordbox s'en sert pour savoir ce qui a changé ;
  * les playlists sont aussi listées dans masterPlaylists6.xml (à côté de master.db) ;
  * analyse et pochette d'un son rangées d'après son UUID, dans « share » :
      /PIONEER/USBANLZ/<3 premiers caractères>/<reste de l'UUID>/ANLZ0000.DAT (.EXT, .2EX)
      /PIONEER/Artwork/<idem>/artwork.jpg (640 px) + artwork_m.jpg (240) + artwork_s.jpg (80) ;
    chaque fichier a sa ligne dans `contentFile` (empreinte MD5, taille, chemin local) ;
  * PPTH des fichiers ANLZ = « ?/<nom du fichier> » ; Analysed = 105 pour un son analysé ;
  * chemins des sons absolus, en « / » (« D:/telechargements/x.mp3 ») ; FolderPath = chemin complet.

Toutes les règles délicates (compteurs de séquence, masterPlaylists6.xml, identifiants) passent par
pyrekordbox (MasterDatabase) ; DJSync n'écrit que les valeurs relevées sur les sons natifs.

Sécurité :
  * AUCUNE écriture tant que Rekordbox est ouvert (il garde la base en mémoire et l'écraserait) ;
  * copie de master.db (+ -wal, masterPlaylists6.xml) avant chaque modification, dans le dossier de
    sauvegarde de DJSync (Rekordbox garde aussi ses propres master.backup*.db) ;
  * un son ou une analyse que DJSync n'a pas créé n'est jamais réanalysé ni effacé du disque :
    DJSync tient la liste des UUID qu'il a ajoutés (local_library.json, dossier des réglages).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union
from urllib.parse import quote
from uuid import uuid4

from ..core.camelot import to_camelot
from ..models import FOLDER_KIND, PLAYLIST_KIND, SMART_PLAYLIST_KIND, LibraryTrack, PlaylistInfo
from .errors import (
    DatabaseLockedError, DatabaseOpenError, LibraryError, PlaylistNotFoundError, ReadOnlyError, TrackNotFoundError,
)
from .base import KEEP
from .library.common import FILE_TYPES, PdbStatus, _Extras, _safe_name, extract_video_id
from .library.metadata import BeatGrid, PlaylistStats

log = logging.getLogger(__name__)

MASTER_DB = "master.db"
PLAYLIST_XML = "masterPlaylists6.xml"
ANALYSED_FLAG = 105            # valeur de djmdContent.Analysed des sons analysés (396 sur 397)
ART_SIZES = {"artwork.jpg": 640, "artwork_m.jpg": 240, "artwork_s.jpg": 80}
# Valeurs « vides » des sons natifs (chaîne vide / 0 plutôt que NULL), relevées sur une vraie base
NATIVE_EMPTY = {
    "FileNameS": "", "TrackNo": 0, "Commnt": "", "DiscNo": 0, "Subtitle": "", "ReleaseDate": "", "ModifiedByRBM": "",
    "DeliveryComment": "", "Lyricist": "", "ISRC": "", "SamplerTrackInfo": 0, "SamplerPlayOffset": 0,
    "SamplerGain": 0.0, "LyricStatus": 0, "ServiceID": 0, "OrgFolderPath": "", "Reserved1": "",
}
_CAMELOT_NAME = re.compile(r"^\s*(1[0-2]|[1-9])\s*[AB]\s*$", re.I)


# ============================================================================ emplacement
def default_db_dir() -> Optional[Path]:
    """Dossier de master.db de Rekordbox 6/7 sur cet ordinateur (None si absent)."""
    candidates: List[Path] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Pioneer" / "rekordbox")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Pioneer" / "rekordbox")
    for c in candidates:
        if (c / MASTER_DB).is_file():
            return c
    return None


def default_music_dir() -> Path:
    """Dossier des sons téléchargés pour la bibliothèque de l'ordinateur : Musique/DJSync."""
    music = Path.home() / "Music"
    if sys.platform == "win32":
        profile = os.environ.get("USERPROFILE")
        if profile:
            music = Path(profile) / "Music"
    return music / "DJSync"


def _stale_file_error(exc: BaseException) -> bool:
    """Erreur typique d'une connexion restée sur un master.db que Rekordbox a modifié ou remplacé."""
    text = str(exc).lower()
    return any(k in text for k in ("malformed", "file is not a database", "disk i/o error", "no such table"))


# 1.3.0-rc.5 (B26) : seul le programme principal compte. Avant, tout processus dont le nom commençait
# par « rekordbox » (outil de mise à jour, rapport de plantage, serveur de médias…, encore là après la
# fermeture) faisait afficher « Rekordbox ouvert ».
REKORDBOX_PROCESSES = {"rekordbox.exe", "rekordbox"}


def rekordbox_process_name(names) -> str:
    """Nom du processus Rekordbox parmi `names` (ou "")."""
    for name in names:
        if (name or "").strip().lower() in REKORDBOX_PROCESSES:
            return name
    return ""


def rekordbox_running() -> bool:
    """Rekordbox (le programme principal) est-il ouvert ?"""
    try:
        import psutil
    except ImportError:            # pragma: no cover - psutil vient avec pyrekordbox
        return False
    names = []
    for proc in psutil.process_iter(["name", "status"]):
        if proc.info.get("status") == getattr(psutil, "STATUS_ZOMBIE", "zombie"):
            continue
        names.append(proc.info.get("name") or "")
    found = rekordbox_process_name(names)
    if found:
        log.debug("Rekordbox running: %s", found)
    return bool(found)


@dataclass(frozen=True)
class LocalRekordbox:
    """« Cible » de la bibliothèque de l'ordinateur ; même rôle que `UsbDrive` pour une clé."""

    db_dir: Path                     # …/Pioneer/rekordbox (contient master.db)
    music_dir: Path                  # où ranger les sons téléchargés
    label: str = "Rekordbox"
    is_removable: bool = False
    is_local: bool = True

    @property
    def root(self) -> Path:
        """Racine des sons téléchargés (espace libre affiché dans la barre latérale)."""
        return self.music_dir

    @property
    def db_path(self) -> Path:
        return self.db_dir / MASTER_DB

    @property
    def letter(self) -> str:
        return ""

    def __str__(self) -> str:
        return f"{self.label} ({self.db_dir})"


def find_local_rekordbox(db_dir: str = "", music_dir: str = "", label: str = "Rekordbox") -> Optional[LocalRekordbox]:
    """Rekordbox installé ? (`db_dir` imposé dans les Paramètres, sinon emplacement standard)."""
    folder = Path(db_dir) if db_dir else default_db_dir()
    if folder is None or not (folder / MASTER_DB).is_file():
        return None
    return LocalRekordbox(folder, Path(music_dir) if music_dir else default_music_dir(), label)


# ================================================================== sons créés par DJSync
class OwnedRegistry:
    """UUID des sons ajoutés (ou analysés) par DJSync, par base : les seuls qu'il réanalyse ou efface."""

    def __init__(self, path: Path, db_key: str) -> None:
        self.path, self.key = path, db_key
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, List[str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def all(self) -> set:
        with self._lock:
            return set(self._load().get(self.key, []))

    def add(self, uuid: str) -> None:
        self._update(lambda s: s.add(uuid))

    def remove(self, uuid: str) -> None:
        self._update(lambda s: s.discard(uuid))

    def _update(self, fn: Callable[[set], None]) -> None:
        with self._lock:
            data = self._load()
            items = set(data.get(self.key, []))
            fn(items)
            data[self.key] = sorted(items)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError as exc:
                log.warning("Owned-track list not saved: %s", exc)


# ======================================================================== bibliothèque
_TRACK_SQL = (
    "SELECT c.ID, c.Title, COALESCE(a.Name,''), al.Name, COALESCE(c.Length,0), c.FolderPath, COALESCE(c.BPM,0), "
    "COALESCE(c.FileType,0), c.Commnt, COALESCE(c.StockDate, c.DateCreated, ''), c.AnalysisDataPath, c.ImagePath, "
    "k.ScaleName, c.UUID, g.Name, lb.Name, c.ReleaseYear, c.BitRate, c.SampleRate, c.Rating, c.ColorID, "
    "c.DJPlayCount, c.DateCreated, c.FileSize "
    "FROM djmdContent c LEFT JOIN djmdArtist a ON a.ID = c.ArtistID LEFT JOIN djmdAlbum al ON al.ID = c.AlbumID "
    "LEFT JOIN djmdKey k ON k.ID = c.KeyID LEFT JOIN djmdGenre g ON g.ID = c.GenreID "
    "LEFT JOIN djmdLabel lb ON lb.ID = c.LabelID "
)
_VISIBLE = "COALESCE(c.rb_local_deleted,0) = 0"


def _num(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _extras(x: Sequence[Any], comment: Any) -> Dict[str, Any]:
    """1.3.1 (C37) : métadonnées en colonnes (genre, label, année, débit…) ; master.db stocke
    ColorID en texte et Rating sur 0..5 (Rekordbox 6/7)."""
    x = list(x) + [None] * max(0, 10 - len(x))
    genre, label, year, bitrate, rate, rating, color, plays, created, size = x[:10]
    return dict(genre=genre or "", label=label or "", year=_num(year), bitrate=_num(bitrate), sample_rate=_num(rate),
                rating=max(0, min(5, _num(rating))), color=_num(color), play_count=_num(plays),
                created=str(created or "")[:10], comment=str(comment or ""))


class LocalRekordboxLibrary:
    """Bibliothèque Rekordbox de l'ordinateur. Thread-safe (un verrou protège la session)."""

    supports_pdb = False
    is_local = True

    def __init__(self, target: LocalRekordbox, backup_keep: int = 10, analyze: bool = False, artwork: bool = True,
                 ffmpeg_location: Optional[str] = None, key_notation: str = "auto", read_only: bool = False,
                 backup_root: Optional[Path] = None, owned_path: Optional[Path] = None, **_ignored: Any) -> None:
        from ..settings import settings_dir

        self.drive = target
        self.backup_keep = backup_keep
        self.analyze = analyze
        self.auto_cue = False                  # V0.5.0 : mémoire cue sur le premier temps fort
        self.artwork = artwork
        self.ffmpeg_location = ffmpeg_location or None
        self.key_notation = key_notation
        self.read_only = read_only
        self.contents_dir = ""
        self.last_problems: List[str] = []
        self.journal_mode = "wal"
        # attributs de la clé USB lus par l'interface : sans objet ici
        self.pdb_sync, self.pdb_allow_growth, self.pdb_state, self.pdb_problem = "off", False, "off", ""
        self._backup_root = backup_root or settings_dir() / "Backups" / "rekordbox"
        self.owned = OwnedRegistry(owned_path or settings_dir() / "local_library.json", str(target.db_path))
        self._db: Any = None
        self._lock = threading.RLock()
        self._writing = 0                         # écritures en cours (les lectures n'y referment rien)
        self._file_id: Tuple[int, ...] = ()   # empreinte de master.db (Rekordbox peut le modifier ou le remplacer)
        self._batch_depth = 0
        self._batch_backed_up = False
        self._share: Optional[Path] = None

    # ------------------------------------------------------------------ connexion
    @property
    def db_path(self) -> Path:
        return self.drive.db_path

    @property
    def contents_root(self) -> Path:
        return self.drive.music_dir

    @property
    def share_dir(self) -> Path:
        return self._share or self.drive.db_dir / "share"

    def default_download_dir(self, artist: str, album: Optional[str] = None) -> Path:
        return self.contents_root / _safe_name(artist, "Unknown Artist") / _safe_name(album or "", "UnknownAlbum")

    def connect(self) -> "LocalRekordboxLibrary":
        with self._lock:
            if self._db is not None:
                return self
            if not self.db_path.is_file():
                raise DatabaseOpenError(f"Database not found: {self.db_path}")
            self._open_db()
            try:
                row = self._read("SELECT str_1 FROM agentRegistry WHERE registry_id = 'SyncAnalysisDataRootPath'")
                if row and row[0][0] and Path(row[0][0]).is_dir():
                    self._share = Path(row[0][0])
            except Exception:  # noqa: BLE001 - emplacement par défaut
                pass
            log.info("Computer library opened: %s", self.db_path)
        return self

    def _open_db(self) -> None:
        logging.getLogger("pyrekordbox").setLevel(logging.ERROR)    # « OS non pris en charge »…
        try:
            from pyrekordbox.masterdb import MasterDatabase
        except ImportError as exc:  # pragma: no cover
            raise DatabaseOpenError("The pyrekordbox package is required for the computer library.") from exc
        try:
            self._db = MasterDatabase(path=str(self.db_path), db_dir=str(self.drive.db_dir))
            self._db.session.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM djmdContent")).fetchall()
            self._db.session.rollback()
            self._file_id = self._identity()
        except Exception as exc:  # noqa: BLE001
            self._db = None
            raise DatabaseOpenError(f"Cannot open the Rekordbox database: {exc}") from exc

    def _identity(self) -> Tuple[int, ...]:
        """Empreinte de master.db (+ -wal) : fichier, taille, date. 1.2.0-rc.4 (B03) : la date et la
        taille comptent aussi, pas seulement l'identité du fichier : Rekordbox peut enregistrer SUR
        PLACE ; DJSync rouvre alors la base avant de lire ou d'écrire, au lieu de rester sur ce qu'il
        en savait (sons ajoutés ensuite invisibles une fois Rekordbox rouvert)."""
        out: List[int] = []
        for name in (MASTER_DB, MASTER_DB + "-wal"):
            try:
                st = (self.drive.db_dir / name).stat()
                out += [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]
            except OSError:
                out += [0, 0, 0, 0]
        return tuple(out)

    def refresh(self) -> None:
        """Rouvre master.db : Rekordbox l'a modifiée, voire remplacée par un nouveau fichier (il le fait
        en enregistrant) ; une connexion restée sur l'ancien fichier lirait un mélange des deux
        (« database disk image is malformed ») et ne verrait pas les playlists créées entre-temps."""
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:  # noqa: BLE001
                    pass
                self._db = None
            self._open_db()
            log.info("Computer library reopened: %s", self.db_path)

    def _log_integrity(self, sql: str) -> None:
        """Diagnostic dans djsync.log (retour testeur) : requête en échec, état du fichier, quick_check."""
        try:
            files = {n: (self.drive.db_dir / n).stat().st_size for n in (MASTER_DB, MASTER_DB + "-wal", MASTER_DB + "-shm")
                     if (self.drive.db_dir / n).exists()}
            from sqlalchemy import text

            check = [r[0] for r in self._db.session.execute(text("PRAGMA quick_check(20)")).fetchall()]
            self._db.session.rollback()
            log.warning("Unreadable Rekordbox database. Query: %s | files: %s | Rekordbox running: %s | "
                        "quick_check: %s", " ".join(sql.split())[:300], files, rekordbox_running(), check)
        except Exception as exc:  # noqa: BLE001
            log.warning("Integrity check failed too: %s", exc)

    def _ensure_fresh(self) -> None:
        if self._db is not None and self._writing == 0 and self._identity() != self._file_id:
            self.refresh()

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:  # noqa: BLE001
                    pass
                self._db = None

    def __enter__(self) -> "LocalRekordboxLibrary":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _session_db(self) -> Any:
        if self._db is None:
            raise LibraryError("Library not connected: call connect().")
        return self._db

    def _read(self, sql: str, params: Dict[str, Any] = None) -> List[Tuple[Any, ...]]:
        """Lecture courte : la transaction est refermée aussitôt (sinon DJSync resterait sur une image
        figée de la base, sans les changements faits ensuite dans Rekordbox)."""
        from sqlalchemy import text

        with self._lock:
            self._ensure_fresh()
            for attempt in (0, 1):
                db = self._session_db()
                try:
                    return [tuple(r) for r in db.session.execute(text(sql), params or {}).fetchall()]
                except Exception as exc:  # noqa: BLE001
                    if attempt == 0 and self._writing == 0 and _stale_file_error(exc):
                        log.warning("Rekordbox database changed under DJSync (%s): reopening", exc)
                        self.refresh()
                        continue
                    if _stale_file_error(exc):
                        self._log_integrity(sql)
                    raise
                finally:
                    if self._writing == 0 and self._db is not None:
                        try:
                            self._db.session.rollback()
                        except Exception:  # noqa: BLE001
                            pass
            return []

    # ------------------------------------------------------------- écritures sûres
    @property
    def backup_dir(self) -> Path:
        return self._backup_root

    def _backup(self) -> None:
        """master.db (+ -wal, masterPlaylists6.xml) copiés avant la modification ; rotation."""
        if self._batch_depth > 0 and self._batch_backed_up:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        target = self.backup_dir / f"master-{stamp}"
        try:
            target.mkdir(parents=True, exist_ok=True)
            for name in (MASTER_DB, MASTER_DB + "-wal", PLAYLIST_XML):
                src = self.drive.db_dir / name
                if src.is_file():
                    shutil.copy2(src, target / name)
            olds = sorted(p for p in self.backup_dir.glob("master-*") if p.is_dir())
            for old in olds[: -max(1, self.backup_keep)]:
                shutil.rmtree(old, ignore_errors=True)
        except OSError as exc:
            raise LibraryError(f"Backup failed, write cancelled for safety: {exc}") from exc
        if self._batch_depth > 0:
            self._batch_backed_up = True

    def ensure_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        if rekordbox_running():
            raise DatabaseLockedError("Close Rekordbox first: DJSync cannot change its library while it is open.")

    @contextmanager
    def batch(self) -> Iterator[None]:
        with self._lock:
            self._batch_depth += 1
            try:
                yield
            finally:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._batch_backed_up = False

    @contextmanager
    def _write(self) -> Iterator[Any]:
        with self._lock:
            self._ensure_fresh()
            db = self._session_db()
            self.ensure_writable()
            self._backup()
            self._writing += 1
            try:
                yield db
                db.commit()
            except BaseException:
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                raise
            finally:
                self._writing -= 1
            self._file_id = self._identity()
            log.info("Computer library: change saved to master.db (size %s, -wal %s)", self._file_id[2], self._file_id[6])

    # ---------------------------------------------------------------------- sons
    @staticmethod
    def _track(row: Tuple[Any, ...], sequence: int = 0) -> LibraryTrack:
        cid, title, artist, album, length, path, bpm, ftype, comment, added, anlz, art, key = row[:13]
        return LibraryTrack(
            content_id=int(cid), title=title or "", artist=artist, album=album or None,
            duration_seconds=int(length or 0), path=path or "", bpm=(bpm or 0) / 100.0, file_type=int(ftype or 0),
            source_url=comment if comment and (extract_video_id(comment) or comment.startswith("http")) else None,
            date_added=str(added or "")[:10], is_analysed=bool(anlz), artwork_path=art or None,
            sequence=sequence, key=key or None, analysis_path=anlz or None,
            **_extras(row[14:24], comment),
        )

    def absolute_path(self, track_or_path: Union[LibraryTrack, str]) -> Path:
        """Chemin réel : les fichiers Rekordbox (« /PIONEER/… ») sont dans « share », les sons ont
        un chemin absolu."""
        p = track_or_path.path if isinstance(track_or_path, LibraryTrack) else track_or_path
        if p.startswith("/PIONEER/"):
            return self.share_dir / p.lstrip("/")
        return Path(p)

    def artwork_file(self, track: LibraryTrack) -> Optional[Path]:
        if not track.artwork_path:
            return None
        p = self.absolute_path(track.artwork_path)
        return p if p.is_file() else None

    def iter_tracks(self) -> Iterable[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for title, artist in self._read(
                "SELECT c.Title, COALESCE(a.Name,'') FROM djmdContent c LEFT JOIN djmdArtist a ON a.ID = c.ArtistID "
                f"WHERE {_VISIBLE}"):
            title = title or ""
            out.append((title, artist))
            if " - " in title:
                left, right = title.split(" - ", 1)
                out.append((right, left))
        return out

    def list_tracks(self) -> List[LibraryTrack]:
        rows = self._read(_TRACK_SQL + f"WHERE {_VISIBLE} AND COALESCE(c.SamplerTrackInfo,0) = 0 "
                          "ORDER BY c.created_at")
        return [self._track(r) for r in rows]

    def get_track(self, content_id: int) -> LibraryTrack:
        rows = self._read(_TRACK_SQL + "WHERE c.ID = :id", {"id": str(content_id)})
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        return self._track(rows[0])

    def find_by_source_url(self, url_or_video_id: str) -> Optional[LibraryTrack]:
        vid = extract_video_id(url_or_video_id)
        if not vid:
            return None
        rows = self._read(_TRACK_SQL + "WHERE instr(c.Commnt, :v) > 0 LIMIT 1", {"v": vid})
        return self._track(rows[0]) if rows else None

    def track_count(self) -> int:
        return int(self._read(f"SELECT COUNT(*) FROM djmdContent c WHERE {_VISIBLE} "
                              "AND COALESCE(c.SamplerTrackInfo,0) = 0")[0][0])

    def unanalysed_tracks(self) -> List[LibraryTrack]:
        rows = self._read(_TRACK_SQL + f"WHERE {_VISIBLE} AND COALESCE(c.SamplerTrackInfo,0) = 0 "
                          "AND (c.AnalysisDataPath IS NULL OR c.AnalysisDataPath = '') ORDER BY c.created_at")
        return [self._track(r) for r in rows]

    def _content(self, content_id: int) -> Any:
        from pyrekordbox.masterdb import models

        c = self._session_db().query(models.DjmdContent).filter_by(ID=str(content_id)).one_or_none()
        if c is None:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        return c

    def is_owned(self, content_id: int) -> bool:
        rows = self._read("SELECT UUID FROM djmdContent WHERE ID = :id", {"id": str(content_id)})
        return bool(rows) and rows[0][0] in self.owned.all()

    # ------------------------------------------------------------------ playlists
    @staticmethod
    def _pid(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0                   # « root »

    def list_playlists(self) -> List[PlaylistInfo]:
        counts = dict(self._read(
            "SELECT sp.PlaylistID, COUNT(*) FROM djmdSongPlaylist sp JOIN djmdContent c ON c.ID = sp.ContentID "
            f"WHERE COALESCE(sp.rb_local_deleted,0) = 0 AND {_VISIBLE} GROUP BY sp.PlaylistID"))
        out = []
        for pid, name, attr, parent, seq in self._read(
                "SELECT ID, Name, COALESCE(Attribute,0), ParentID, COALESCE(Seq,0) FROM djmdPlaylist "
                "WHERE COALESCE(rb_local_deleted,0) = 0 ORDER BY Seq"):
            kind = {0: PLAYLIST_KIND, 1: FOLDER_KIND}.get(int(attr), SMART_PLAYLIST_KIND)
            out.append(PlaylistInfo(int(pid), name or "", self._pid(parent), kind, int(seq), int(counts.get(pid, 0))))
        return out

    def get_playlist(self, playlist_id: int) -> PlaylistInfo:
        p = next((x for x in self.list_playlists() if x.playlist_id == int(playlist_id)), None)
        if p is None:
            raise PlaylistNotFoundError(f"Playlist not found (id {playlist_id}).")
        return p

    def get_playlist_tracks(self, playlist_id: int) -> List[LibraryTrack]:
        rows = self._read(
            _TRACK_SQL.replace("SELECT ", "SELECT sp.TrackNo, ", 1)
            + "JOIN djmdSongPlaylist sp ON sp.ContentID = c.ID "
            f"WHERE sp.PlaylistID = :pid AND COALESCE(sp.rb_local_deleted,0) = 0 AND {_VISIBLE} ORDER BY sp.TrackNo",
            {"pid": str(playlist_id)})
        return [self._track(r[1:], sequence=int(r[0] or 0)) for r in rows]

    def playlist_stats(self) -> Dict[int, PlaylistStats]:
        out: Dict[int, PlaylistStats] = {}
        for pid, n, total, last in self._read(
                "SELECT sp.PlaylistID, COUNT(*), COALESCE(SUM(c.Length),0), COALESCE(MAX(c.StockDate),'') "
                "FROM djmdSongPlaylist sp JOIN djmdContent c ON c.ID = sp.ContentID "
                f"WHERE COALESCE(sp.rb_local_deleted,0) = 0 AND {_VISIBLE} GROUP BY sp.PlaylistID"):
            out[int(pid)] = PlaylistStats(int(n), int(total), str(last or "")[:10])
        n, total, last = self._read(
            f"SELECT COUNT(*), COALESCE(SUM(c.Length),0), COALESCE(MAX(c.StockDate),'') FROM djmdContent c "
            f"WHERE {_VISIBLE} AND COALESCE(c.SamplerTrackInfo,0) = 0")[0]
        out[0] = PlaylistStats(int(n), int(total), str(last or "")[:10])
        return out

    def _playlist(self, db: Any, playlist_id: int, editable: bool = False) -> Any:
        from pyrekordbox.masterdb import models

        pl = db.query(models.DjmdPlaylist).filter_by(ID=str(playlist_id)).one_or_none()
        if pl is None:
            raise PlaylistNotFoundError(f"Playlist not found (id {playlist_id}).")
        if editable and int(pl.Attribute or 0) != 0:
            raise LibraryError("This is a folder or an intelligent playlist: tracks cannot be added to it.")
        return pl

    def _info(self, pl: Any) -> PlaylistInfo:
        kind = {0: PLAYLIST_KIND, 1: FOLDER_KIND}.get(int(pl.Attribute or 0), SMART_PLAYLIST_KIND)
        return PlaylistInfo(int(pl.ID), pl.Name or "", self._pid(pl.ParentID), kind, int(pl.Seq or 0), 0)

    def create_playlist(self, name: str, parent_id: int = 0) -> PlaylistInfo:
        return self._create(name, parent_id, folder=False)

    def create_folder(self, name: str, parent_id: int = 0) -> PlaylistInfo:
        return self._create(name, parent_id, folder=True)

    def _create(self, name: str, parent_id: int, folder: bool) -> PlaylistInfo:
        name = (name or "").strip()
        if not name:
            raise LibraryError("The name cannot be empty.")
        with self._write() as db:
            parent = str(parent_id) if parent_id else None
            pl = db.create_playlist_folder(name, parent=parent) if folder else db.create_playlist(name, parent=parent)
            info = self._info(pl)
        return info

    def rename_playlist(self, playlist_id: int, new_name: str) -> None:
        new_name = (new_name or "").strip()
        if not new_name:
            raise LibraryError("The name cannot be empty.")
        with self._write() as db:
            db.rename_playlist(self._playlist(db, playlist_id), new_name)

    def delete_playlist(self, playlist_id: int) -> None:
        with self._write() as db:
            db.delete_playlist(self._playlist(db, playlist_id))

    def _songs(self, db: Any, playlist_id: int) -> List[Any]:
        from pyrekordbox.masterdb import models

        return (db.query(models.DjmdSongPlaylist).filter_by(PlaylistID=str(playlist_id))
                .order_by(models.DjmdSongPlaylist.TrackNo).all())

    @staticmethod
    def _renumber(songs: Sequence[Any]) -> None:
        now = datetime.now()
        for i, song in enumerate(songs, start=1):
            if song.TrackNo != i:
                song.TrackNo = i
                song.updated_at = now

    def add_to_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> int:
        with self._write() as db:
            return self._add_songs(db, playlist_id, content_ids)

    def _add_songs(self, db: Any, playlist_id: int, content_ids: Sequence[int]) -> int:
        pl = self._playlist(db, playlist_id, editable=True)
        present = {s.ContentID for s in self._songs(db, playlist_id)}
        added = 0
        for cid in dict.fromkeys(str(c) for c in content_ids):
            if cid in present:
                continue
            db.add_to_playlist(pl, cid)
            present.add(cid)
            added += 1
        return added

    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        with self._write() as db:
            self._remove_songs(db, playlist_id, content_ids)

    def _remove_songs(self, db: Any, playlist_id: int, content_ids: Sequence[int]) -> None:
        self._playlist(db, playlist_id, editable=True)
        drop = {str(c) for c in content_ids}
        keep = []
        for song in self._songs(db, playlist_id):
            if song.ContentID in drop:
                db.delete(song)
            else:
                keep.append(song)
        db.flush()
        self._renumber(keep)

    def move_tracks(self, content_ids: Sequence[int], from_playlist_id: int, to_playlist_id: int) -> None:
        with self._write() as db:
            self._add_songs(db, to_playlist_id, content_ids)
            self._remove_songs(db, from_playlist_id, content_ids)

    def set_playlist_order(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        with self._write() as db:
            self._playlist(db, playlist_id, editable=True)
            songs = self._songs(db, playlist_id)
            by_id = {s.ContentID: s for s in songs}
            order = [by_id[str(c)] for c in content_ids if str(c) in by_id]
            order += [s for s in songs if s not in order]
            self._renumber(order)

    # ------------------------------------------------------------- références
    def _get_named(self, db: Any, model: Any, name: str, create: Callable[[str], Any]) -> Optional[str]:
        name = (name or "").strip()
        if not name:
            return None
        row = db.query(model).filter(model.Name == name).first()
        if row is None:
            from sqlalchemy import func

            row = db.query(model).filter(func.lower(model.Name) == name.lower()).first()
        return (row or create(name)).ID

    def _artist_id(self, db: Any, name: str) -> Optional[str]:
        from pyrekordbox.masterdb import models

        return self._get_named(db, models.DjmdArtist, name, lambda n: db.add_artist(n))

    def _album_id(self, db: Any, name: Optional[str]) -> Optional[str]:
        from pyrekordbox.masterdb import models

        return self._get_named(db, models.DjmdAlbum, name or "", lambda n: db.add_album(n, compilation=False))

    def _genre_id(self, db: Any, name: Optional[str]) -> Optional[str]:
        from pyrekordbox.masterdb import models

        return self._get_named(db, models.DjmdGenre, name or "", lambda n: db.add_genre(n))

    def _label_id(self, db: Any, name: Optional[str]) -> Optional[str]:
        from pyrekordbox.masterdb import models

        return self._get_named(db, models.DjmdLabel, name or "", lambda n: db.add_label(n))

    def _key_id(self, db: Any, musical: str) -> Optional[str]:
        """Ligne de djmdKey : notation demandée, ou en « auto » celle majoritaire (musicale par défaut,
        comme Rekordbox sur l'ordinateur) ; une ligne équivalente existante est réutilisée."""
        from pyrekordbox.masterdb import models

        code = to_camelot(musical)
        if not code:
            return None
        keys = db.query(models.DjmdKey).all()
        style = self.key_notation
        if style not in ("camelot", "musical"):
            camelot = sum(1 for k in keys if k.ScaleName and _CAMELOT_NAME.match(k.ScaleName))
            style = "camelot" if camelot > len(keys) - camelot else "musical"
        for k in keys:
            name = k.ScaleName or ""
            if to_camelot(name) == code and bool(_CAMELOT_NAME.match(name)) == (style == "camelot"):
                return k.ID
        wanted = code if style == "camelot" else musical
        key = models.DjmdKey.create(ID=str(db.generate_unused_id(models.DjmdKey)), ScaleName=wanted,
                                    Seq=len(keys) + 1, UUID=str(uuid4()))
        db.add(key)
        db.flush()
        return key.ID

    # ---------------------------------------------------------- fichiers « share »
    @staticmethod
    def _uuid_dir(uuid: str) -> str:
        return f"{uuid[:3]}/{uuid[3:]}"

    def _file_row(self, db: Any, content: Any, rel: str) -> None:
        """Ligne contentFile (empreinte MD5, taille, chemin local) d'un fichier de « share »."""
        from pyrekordbox.masterdb import models

        path = self.share_dir / rel.lstrip("/")
        data = path.read_bytes()
        row_id = f"{content.UUID}_{quote(rel, safe='')}"
        row = db.query(models.ContentFile).filter_by(ID=row_id).one_or_none()
        md5 = hashlib.md5(data).hexdigest()
        if row is None:
            db.add(models.ContentFile.create(
                ID=row_id, ContentID=content.ID, Path=rel, Hash=md5, Size=len(data),
                rb_local_path=os.path.normpath(str(path)), UUID=str(uuid4()),
                created_at=datetime.now(), updated_at=datetime.now()))
        elif row.Hash != md5 or row.Size != len(data):
            row.Hash, row.Size, row.updated_at = md5, len(data), datetime.now()

    def _write_artwork(self, uuid: str, image: bytes) -> Tuple[Optional[str], List[Path]]:
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(image))
            img.load()
            img = img.convert("RGB")
        except Exception:  # noqa: BLE001 - pochette illisible : pas de pochette
            return None, []
        w, h = img.size
        s = min(w, h)
        img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
        rel_dir = f"/PIONEER/Artwork/{self._uuid_dir(uuid)}"
        folder = self.share_dir / rel_dir.lstrip("/")
        folder.mkdir(parents=True, exist_ok=True)
        written = []
        for name, size in ART_SIZES.items():
            target = folder / name
            img.resize((size, size), Image.LANCZOS).save(target, "JPEG", quality=90)
            written.append(target)
        return f"{rel_dir}/artwork.jpg", written

    def _prepare(self, file_path: Path, file_type: int, sample_rate: int, uuid: str, analysis: bool,
                 cover: bool) -> _Extras:
        """Analyse + pochette (calcul long, fichiers écrits dans « share » sous l'UUID du son)."""
        ex = _Extras()
        if analysis:
            try:
                from ..analysis import analyze_file, write_anlz

                ex.analysis = analyze_file(file_path, self.ffmpeg_location)
                rel_dir = f"/PIONEER/USBANLZ/{self._uuid_dir(uuid)}"
                ex.anlz_path = write_anlz(self.share_dir, f"?/{file_path.name}", ex.analysis, file_type,
                                          sample_rate or 44100, rel_dir=rel_dir)
                dat = self.share_dir / ex.anlz_path.lstrip("/")
                ex.written += [dat, dat.with_suffix(".EXT"), dat.with_suffix(".2EX")]
            except Exception as exc:  # noqa: BLE001 - son ajouté sans analyse
                log.warning("Analysis failed (%s): %s", file_path.name, exc)
                ex.problems.append(f"analysis: {exc}")
        if cover and self.artwork:
            try:
                from ..audio.covers import extract_embedded_cover

                data = extract_embedded_cover(file_path)
                if data:
                    art, written = self._write_artwork(uuid, data)
                    if art:
                        ex.jpegs = {"path": art}            # type: ignore[assignment]
                        ex.written += written
            except Exception as exc:  # noqa: BLE001
                ex.problems.append(f"artwork: {exc}")
        return ex

    def _apply_extras(self, db: Any, content: Any, ex: _Extras) -> None:
        now = datetime.now()
        if ex.analysis is not None and ex.anlz_path:
            content.BPM = int(round(ex.analysis.bpm * 100))
            key_id = self._key_id(db, ex.analysis.key.name)
            if key_id:
                content.KeyID = key_id
            content.AnalysisDataPath = ex.anlz_path
            content.Analysed = ANALYSED_FLAG
            content.AnalysisUpdated = str(int(content.AnalysisUpdated or 0) + 1)
            if self.auto_cue:
                self._memory_cue(db, content, ex.analysis.first_downbeat_ms)
            for ext in (".DAT", ".EXT", ".2EX"):
                rel = ex.anlz_path[:-4] + ext
                if (self.share_dir / rel.lstrip("/")).is_file():
                    self._file_row(db, content, rel)
        if ex.jpegs and ex.jpegs.get("path"):
            content.ImagePath = ex.jpegs["path"]
            self._file_row(db, content, ex.jpegs["path"])
        content.updated_at = now

    @staticmethod
    def _memory_cue(db: Any, content: Any, ms: Optional[int]) -> None:
        """Mémoire cue (Kind 0) au premier temps fort : djmdCue + contentCue, comme Rekordbox. Seulement
        si le son n'a encore aucun cue (jamais de modification des cues de l'utilisateur)."""
        from pyrekordbox.masterdb import models

        if ms is None or db.query(models.DjmdCue).filter_by(ContentID=content.ID).first() is not None:
            return
        now = datetime.now()
        cue = dict(ID=str(db.generate_unused_id(models.DjmdCue)), ContentID=content.ID, ContentUUID=content.UUID,
                   InMsec=int(ms), InFrame=int(ms) * 150 // 1000, InMpegFrame=0, InMpegAbs=0, OutMsec=-1,
                   OutFrame=0, OutMpegFrame=0, OutMpegAbs=0, Kind=0, Color=-1, UUID=str(uuid4()))
        db.add(models.DjmdCue.create(**cue, ActiveLoop=0, BeatLoopSize=0, CueMicrosec=0,
                                     created_at=now, updated_at=now))
        stamp = now.astimezone().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        entry = dict(cue, created_at=stamp, updated_at=stamp)
        row = db.query(models.ContentCue).filter_by(ContentID=content.ID).one_or_none()
        if row is None:
            db.add(models.ContentCue.create(ID=content.UUID, ContentID=content.ID, Cues=json.dumps([entry]),
                                            rb_cue_count=1, UUID=str(uuid4()), created_at=now, updated_at=now))
        content.CueUpdated = str(int(content.CueUpdated or 0) + 1)

    @staticmethod
    def _discard(paths: Sequence[Path]) -> None:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def _common_content_link(self) -> Optional[int]:
        """ContentLink le plus courant chez les sons de la collection (valeur interne de Rekordbox)."""
        rows = self._read("SELECT ContentLink, COUNT(*) n FROM djmdContent WHERE COALESCE(SamplerTrackInfo,0) = 0 "
                          "AND ContentLink IS NOT NULL GROUP BY ContentLink ORDER BY n DESC LIMIT 1")
        return int(rows[0][0]) if rows else None

    # ----------------------------------------------------------------------- ajout
    def add_track(self, file_path: Path, title: str, artist: str, album: Optional[str] = None,
                  source_url: Optional[str] = None, playlist_ids: Sequence[int] = (),
                  meta: Optional[Dict[str, Any]] = None) -> LibraryTrack:
        """Ajoute un son téléchargé à la collection Rekordbox (+ analyse, pochette, playlists)."""
        from pyrekordbox.masterdb import models

        from .library.tracks import TracksMixin

        file_path = Path(file_path)
        if not file_path.is_file():
            raise LibraryError(f"File not found: {file_path}")
        self.ensure_writable()
        audio = TracksMixin._probe_audio(file_path)
        posix = file_path.resolve().as_posix()
        title = (title or "").strip() or file_path.stem
        meta = meta or {}
        vid = extract_video_id(source_url or "")
        comment = f"https://www.youtube.com/watch?v={vid}" if vid else (source_url or "").split("?")[0]

        existing = self._read("SELECT ID FROM djmdContent WHERE FolderPath = :p", {"p": posix})
        if existing:                                  # déjà dans la collection : seulement les playlists
            cid = int(existing[0][0])
            if playlist_ids:
                with self._write() as db:
                    for pid in playlist_ids:
                        self._add_songs(db, pid, [cid])
            self.last_problems = []
            return self.get_track(cid)

        uuid = str(uuid4())
        ex = self._prepare(file_path, audio["fileType"], audio["samplingRate"], uuid, analysis=self.analyze, cover=True)
        self.last_problems = list(ex.problems)
        try:
            with self._write() as db:
                for pid in playlist_ids:
                    self._playlist(db, pid, editable=True)
                device = db.get_device().first()
                menu = db.get_menu_items(Name="TRACK").first()
                today = date.today().isoformat()
                now = datetime.now()
                cid = str(db.generate_unused_id(models.DjmdContent))
                values: Dict[str, Any] = dict(NATIVE_EMPTY)
                values.update(
                    ID=cid, UUID=uuid, MasterSongID=cid,
                    MasterDBID=device.MasterDBID if device is not None else None,
                    DeviceID=device.ID if device is not None else None,
                    ContentLink=self._common_content_link() or (menu.rb_local_usn if menu is not None else None),
                    FolderPath=posix, FileNameL=file_path.name, Title=title,
                    ArtistID=self._artist_id(db, artist), AlbumID=self._album_id(db, album),
                    GenreID=self._genre_id(db, meta.get("genre")), LabelID=self._label_id(db, meta.get("label")),
                    Length=audio["length"], BitRate=audio["bitrate"], BitDepth=audio["bitDepth"],
                    SampleRate=audio["samplingRate"], FileSize=file_path.stat().st_size, FileType=audio["fileType"],
                    Commnt=comment or None, ReleaseYear=int(meta["year"]) if meta.get("year") else None,
                    ReleaseDate=meta.get("release_date") or None, TrackNo=int(meta["track_no"]) if meta.get("track_no") else None,
                    ISRC=meta.get("isrc") or None, StockDate=today, DateCreated=today, ColorID="0", Rating=0,
                    DJPlayCount=0, HotCueAutoLoad="on", DeliveryControl="on", CueUpdated=None, AnalysisUpdated="0",
                    TrackInfoUpdated="0", VideoAssociate="0", ExtInfo="null", Analysed=0,
                    rb_file_id=str(db.generate_unused_id(models.DjmdContent, id_field_name="rb_file_id")),
                    created_at=now, updated_at=now,
                )
                for k in ("Commnt", "ReleaseDate", "ISRC", "TrackNo"):
                    if values.get(k) is None:
                        values[k] = NATIVE_EMPTY[k]
                content = models.DjmdContent.create(**values)
                db.add(content)
                db.flush()
                self._apply_extras(db, content, ex)
                for pid in playlist_ids:
                    self._add_songs(db, pid, [cid])
        except BaseException:
            self._discard(ex.written)
            raise
        self.owned.add(uuid)
        return self.get_track(int(cid))

    # ---------------------------------------------------------------------- analyse
    def analyze_track(self, content_id: int, force: bool = False) -> LibraryTrack:
        self.analyze_tracks([content_id], force=force)
        return self.get_track(content_id)

    def analyze_tracks(self, content_ids: Sequence[int], force: bool = False,
                       on_progress: Optional[Callable[[int, int, Optional[LibraryTrack], str], None]] = None,
                       should_stop: Optional[Callable[[], bool]] = None, chunk: int = 8) -> Tuple[int, int, int]:
        """Analyse les sons sans analyse ; avec `force`, réanalyse AUSSI ceux que DJSync a créés —
        jamais une analyse de Rekordbox. Renvoie (analysés, ignorés, échecs)."""
        ids = list(dict.fromkeys(int(c) for c in content_ids))
        owned = self.owned.all()
        done = skipped = failed = 0
        for i, cid in enumerate(ids, start=1):
            if should_stop and should_stop():
                break
            problem = ""
            try:
                track = self.get_track(cid)
                rows = self._read("SELECT UUID, COALESCE(SampleRate,44100) FROM djmdContent WHERE ID = :id",
                                  {"id": str(cid)})
                uuid, rate = rows[0]
                if track.is_analysed and not (force and uuid in owned):
                    skipped += 1
                else:
                    path = Path(track.path)
                    if not path.is_file():
                        raise LibraryError(f"File not found: {path}")
                    self.ensure_writable()
                    ex = self._prepare(path, track.file_type, int(rate), uuid, analysis=True,
                                       cover=not track.artwork_path)
                    if ex.analysis is None:
                        failed += 1
                        problem = "; ".join(ex.problems)
                    else:
                        with self._write() as db:
                            self._apply_extras(db, self._content(cid), ex)
                        self.owned.add(uuid)
                        done += 1
                        problem = "; ".join(ex.problems)
            except LibraryError as exc:
                failed += 1
                problem = str(exc)
            if on_progress:
                try:
                    t = self.get_track(cid)
                except LibraryError:
                    t = None
                on_progress(i, len(ids), t, problem)
        return done, skipped, failed

    def import_analysis(self, content_id: int, files: Dict[str, bytes], bpm: float = 0.0,
                        key: Optional[str] = None) -> LibraryTrack:
        """V0.5.0 (copie entre bibliothèques) : reprend une analyse existante au lieu de recalculer."""
        from ..analysis.anlz import _write_atomic, retarget

        self.ensure_writable()
        rows = self._read("SELECT FolderPath, AnalysisDataPath, UUID FROM djmdContent WHERE ID = :id",
                          {"id": str(content_id)})
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        folder_path, anlz, uuid = rows[0]
        if anlz or ".DAT" not in files:
            return self.get_track(content_id)
        rel_dir = f"/PIONEER/USBANLZ/{self._uuid_dir(uuid)}"
        written = []
        try:
            for ext, data in files.items():
                target = self.share_dir / rel_dir.lstrip("/") / f"ANLZ0000{ext}"
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_atomic(target, retarget(data, f"?/{Path(folder_path).name}"))
                written.append(target)
            with self._write() as db:
                c = self._content(content_id)
                if bpm > 0:
                    c.BPM = int(round(bpm * 100))
                key_id = self._key_id(db, key) if key else None
                if key_id:
                    c.KeyID = key_id
                c.AnalysisDataPath = f"{rel_dir}/ANLZ0000.DAT"
                c.Analysed = ANALYSED_FLAG
                c.AnalysisUpdated = str(int(c.AnalysisUpdated or 0) + 1)
                for f in written:
                    self._file_row(db, c, f"{rel_dir}/{f.name}")
                c.updated_at = datetime.now()
        except BaseException:
            self._discard(written)
            raise
        return self.get_track(content_id)

    # ---------------------------------------------------------------- métadonnées
    def complete_metadata(self, content_id: int, meta: Dict[str, Any], album: Optional[str] = None) -> bool:
        """V0.5.0 : complète les champs VIDES seulement (album, année, genre, label, n° de piste, ISRC)."""
        with self._write() as db:
            c = self._content(content_id)
            changed = False
            if meta.get("year") and not c.ReleaseYear:
                c.ReleaseYear, changed = int(meta["year"]), True
            if meta.get("release_date") and not c.ReleaseDate:
                c.ReleaseDate, changed = str(meta["release_date"])[:10], True
            if meta.get("track_no") and not c.TrackNo:
                c.TrackNo, changed = int(meta["track_no"]), True
            if meta.get("isrc") and not c.ISRC:
                c.ISRC, changed = str(meta["isrc"]), True
            if meta.get("genre") and not c.GenreID:
                c.GenreID, changed = self._genre_id(db, meta["genre"]), True
            if meta.get("label") and not c.LabelID:
                c.LabelID, changed = self._label_id(db, meta["label"]), True
            if album and album.strip() and not c.AlbumID:
                c.AlbumID, changed = self._album_id(db, album.strip()), True
            if changed:
                c.TrackInfoUpdated = str(int(c.TrackInfoUpdated or 0) + 1)
                c.updated_at = datetime.now()
        return changed

    # ------------------------------------------------------- 1.2.2 : infos complètes
    def track_details(self, content_id: int) -> Dict[str, Any]:
        rows = self._read(
            "SELECT COALESCE(al.Name,''), COALESCE(c.ReleaseYear,0), COALESCE(g.Name,''), COALESCE(lb.Name,''), "
            "COALESCE(c.ImagePath,'') FROM djmdContent c LEFT JOIN djmdAlbum al ON al.ID = c.AlbumID "
            "LEFT JOIN djmdGenre g ON g.ID = c.GenreID LEFT JOIN djmdLabel lb ON lb.ID = c.LabelID WHERE c.ID = :id",
            {"id": str(content_id)})
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        album, year, genre, label, art = rows[0]
        return {"album": album, "year": int(year or 0), "genre": genre, "label": label, "artwork_path": art or None}

    def track_genres(self) -> Dict[int, str]:
        out: Dict[int, str] = {}
        for cid, name in self._read("SELECT c.ID, g.Name FROM djmdContent c JOIN djmdGenre g ON g.ID = c.GenreID "
                                    f"WHERE g.Name IS NOT NULL AND g.Name <> '' AND {_VISIBLE}"):
            try:
                out[int(cid)] = name
            except (TypeError, ValueError):
                continue
        return out

    def edit_track_metadata(self, content_id: int, title: Optional[str] = None, artist: Optional[str] = None,
                            album: Optional[str] = None, year: Optional[int] = None, genre: Optional[str] = None,
                            artwork: Any = KEEP) -> LibraryTrack:
        """1.2.2 : même contrat que la clé (None = inchangé, "" / 0 = effacé, pochette KEEP / None /
        octets). Le fichier audio n'est ni modifié ni renommé."""
        title = title.strip() if title is not None else None
        if title is not None and not title:
            raise LibraryError("The title cannot be empty.")
        written: List[Path] = []
        try:
            with self._write() as db:
                c = self._content(content_id)
                if title is not None:
                    c.Title = title
                if artist is not None:
                    c.ArtistID = self._artist_id(db, artist.strip()) if artist.strip() else None
                if album is not None:
                    c.AlbumID = self._album_id(db, album.strip()) if album.strip() else None
                if year is not None:
                    c.ReleaseYear = int(year) if year else None
                if genre is not None:
                    c.GenreID = self._genre_id(db, genre.strip()) if genre.strip() else None
                if artwork is None:
                    c.ImagePath = None
                elif artwork is not KEEP:
                    rel, written = self._write_artwork(f"{c.UUID}-{uuid4().hex[:6]}", artwork)
                    if rel is None:
                        raise LibraryError("Unreadable image.")
                    c.ImagePath = rel
                    self._file_row(db, c, rel)
                c.TrackInfoUpdated = str(int(c.TrackInfoUpdated or 0) + 1)
                c.updated_at = datetime.now()
        except BaseException:
            for f in written:
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        return self.get_track(content_id)

    def relink_track(self, content_id: int, new_file: Path) -> LibraryTrack:
        """1.3.1 (C43) : le fichier a été déplacé : le son pointe vers `new_file` (comme « Relocaliser »
        dans Rekordbox ; playlists, grille et cues gardés)."""
        target = Path(new_file)
        if target.suffix.lower() not in FILE_TYPES or not target.is_file():
            raise LibraryError("The file must be an existing audio file.")
        posix = target.resolve().as_posix()
        existing = self._read("SELECT ID FROM djmdContent WHERE FolderPath = :p AND ID != :id "
                              f"AND {_VISIBLE}", {"p": posix, "id": str(content_id)})
        if existing:
            raise LibraryError("Another track of the library already uses this file.")
        with self._write():
            c = self._content(content_id)
            c.FolderPath = posix
            c.FileNameL = target.name
            c.FileSize = target.stat().st_size
            c.updated_at = datetime.now()
        return self.get_track(content_id)

    def update_track_metadata(self, content_id: int, title: Optional[str] = None,
                              artist: Optional[str] = None) -> LibraryTrack:
        title = title.strip() if title is not None else None
        artist = artist.strip() if artist is not None else None
        if title is not None and not title:
            raise LibraryError("The title cannot be empty.")
        with self._write() as db:
            c = self._content(content_id)
            if title is not None:
                c.Title = title
            if artist is not None:
                c.ArtistID = self._artist_id(db, artist) if artist else None
            c.TrackInfoUpdated = str(int(c.TrackInfoUpdated or 0) + 1)
            c.updated_at = datetime.now()
        return self.get_track(content_id)

    # --------------------------------------------------------------- grille de temps
    def analysis_files(self, track: LibraryTrack) -> Tuple[Optional[Path], Optional[Path]]:
        if not track.analysis_path:
            return None, None
        dat = self.absolute_path(track.analysis_path)
        ext = dat.with_suffix(".EXT")
        return (dat if dat.is_file() else None), (ext if ext.is_file() else None)

    def beat_grid(self, content_id: int) -> BeatGrid:
        from ..analysis.anlz import read_beats

        rows = self._read("SELECT AnalysisDataPath, COALESCE(Length,0), UUID FROM djmdContent WHERE ID = :id",
                          {"id": str(content_id)})
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        anlz, length, uuid = rows[0]
        if not anlz:
            raise LibraryError("This track is not analysed yet: run the analysis first.")
        dat = self.absolute_path(anlz)
        try:
            beats = read_beats(dat.read_bytes())
        except (OSError, ValueError) as exc:
            raise LibraryError(f"Unreadable analysis file: {exc}") from exc
        if not beats:
            raise LibraryError("This track has no beat grid.")
        return BeatGrid(content_id, beats, int(length) * 1000, dat, uuid not in self.owned.all())

    def save_beat_grid(self, content_id: int, beats: Sequence[Tuple[int, int, int]]) -> LibraryTrack:
        from ..analysis.anlz import _write_atomic, drop_extended_grid, replace_beats

        self.ensure_writable()
        beats = [(int(n), int(t), int(ms)) for n, t, ms in beats]
        if len(beats) < 2 or any(b[2] >= c[2] for b, c in zip(beats, beats[1:])):
            raise LibraryError("Invalid grid (at least two beats, increasing positions).")
        grid = self.beat_grid(content_id)
        files = [f for f in [grid.dat_path] + [grid.dat_path.with_suffix(s) for s in (".EXT", ".2EX")] if f.is_file()]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.backup_dir / "anlz" / f"{stamp}-{content_id}"
        backup.mkdir(parents=True, exist_ok=True)
        from .library.metadata import ANLZ_BACKUPS_KEEP, prune_folders

        prune_folders(backup.parent, ANLZ_BACKUPS_KEEP)
        originals = {f: f.read_bytes() for f in files}
        for f, data in originals.items():
            (backup / f.name).write_bytes(data)
        new = {grid.dat_path: replace_beats(originals[grid.dat_path], beats)}
        for f in files[1:]:
            changed = drop_extended_grid(originals[f])
            if changed != originals[f]:
                new[f] = changed
        tempos = sorted(b[1] for b in beats)
        try:
            for f, data in new.items():
                _write_atomic(f, data)
            with self._write() as db:
                c = self._content(content_id)
                c.BPM = tempos[len(tempos) // 2]
                c.AnalysisUpdated = str(int(c.AnalysisUpdated or 0) + 1)
                c.updated_at = datetime.now()
                anlz = c.AnalysisDataPath or ""
                for f in new:
                    rel = anlz[:-4] + f.suffix
                    self._file_row(db, c, rel)
        except BaseException:
            for f, data in originals.items():
                try:
                    _write_atomic(f, data)
                except OSError:
                    log.error("Could not restore %s (copy in %s)", f, backup)
            raise
        return self.get_track(content_id)

    # ------------------------------------------------------------ hot cues (1.3.0, C22)
    def track_cues(self, content_id: int) -> List[Any]:
        """Cues du son tels que Rekordbox les montre : table djmdCue (Kind 0 mémoire, 1-3 A-C, 5-9 D-H)."""
        from ..analysis.cues import PALETTE, SLOT_FOR_KIND, Cue

        rows = self._read("SELECT Kind, InMsec, OutMsec, ColorTableIndex, Comment, BeatLoopSize, ActiveLoop "
                          "FROM djmdCue WHERE ContentID = :id AND COALESCE(rb_local_deleted,0) = 0",
                          {"id": str(content_id)})
        out: List[Any] = []
        for kind, in_ms, out_ms, color, comment, loop_size, active in rows:
            slot = SLOT_FOR_KIND.get(int(kind or 0))
            if slot is None or in_ms is None or int(in_ms) < 0:
                continue
            loop = int(out_ms) if out_ms is not None and int(out_ms) > int(in_ms) else None
            code = int(color or 0)
            out.append(Cue(slot, int(in_ms), loop, int(loop_size or 0) if loop else 0, comment or "",
                           code if code in PALETTE else 0, PALETTE.get(code, (0, 0, 0)),
                           active=bool(int(active or 0)) and loop is not None and not slot))
        hot = sorted((c for c in out if c.slot), key=lambda c: c.slot)
        mem = sorted((c for c in out if not c.slot), key=lambda c: c.ms)
        return hot + mem

    def save_track_cues(self, content_id: int, cues: Sequence[Any]) -> LibraryTrack:
        """Remplace les cues du son : djmdCue + contentCue (master.db) et fichiers d'analyse (ANLZ du dossier
        de partage Rekordbox). Rekordbox doit être fermé ; sauvegardes avant écriture."""
        from pyrekordbox.masterdb import models

        from ..analysis.cues import KIND_FOR_SLOT, save_to_files
        from .library.metadata import ANLZ_BACKUPS_KEEP, prune_folders

        self.ensure_writable()
        slots = [c.slot for c in cues if c.slot]
        if len(slots) != len(set(slots)):
            raise LibraryError("Two hot cues on the same pad.")
        track = self.get_track(content_id)
        dat, _ext = self.analysis_files(track)
        if dat is not None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.backup_dir / "anlz" / f"{stamp}-{content_id}-cues"
            backup.mkdir(parents=True, exist_ok=True)
            prune_folders(backup.parent, ANLZ_BACKUPS_KEEP)
            try:
                save_to_files(dat, cues, backup)
            except ValueError as exc:
                raise LibraryError(str(exc)) from exc
        with self._write() as db:
            content = self._content(content_id)
            for row in db.query(models.DjmdCue).filter_by(ContentID=content.ID).all():
                db.delete(row)
            db.flush()
            now = datetime.now()
            stamp_iso = now.astimezone().isoformat(timespec="milliseconds").replace("+00:00", "Z")
            entries = []
            for c in cues:
                loop = c.loop_ms if c.is_loop else None
                cue = dict(ID=str(db.generate_unused_id(models.DjmdCue)), ContentID=content.ID,
                           ContentUUID=content.UUID, InMsec=int(c.ms), InFrame=int(c.ms) * 150 // 1000,
                           InMpegFrame=0, InMpegAbs=0, OutMsec=int(loop) if loop else -1,
                           OutFrame=int(loop) * 150 // 1000 if loop else 0, OutMpegFrame=0, OutMpegAbs=0,
                           Kind=KIND_FOR_SLOT.get(int(c.slot), 0), Color=-1,
                           ColorTableIndex=int(c.color_code) if c.slot else None,
                           ActiveLoop=1 if getattr(c, "is_active_loop", False) else 0,     # 1.3.1-rc.2 (C75)
                           Comment=c.name or None, BeatLoopSize=int(c.loop_beats) if loop else 0, CueMicrosec=0,
                           UUID=str(uuid4()))
                db.add(models.DjmdCue.create(**cue, created_at=now, updated_at=now))
                db.flush()
                entries.append(dict(cue, created_at=stamp_iso, updated_at=stamp_iso))
            row = db.query(models.ContentCue).filter_by(ContentID=content.ID).one_or_none()
            if row is None and entries:
                db.add(models.ContentCue.create(ID=content.UUID, ContentID=content.ID, Cues=json.dumps(entries),
                                                rb_cue_count=len(entries), UUID=str(uuid4()), created_at=now,
                                                updated_at=now))
            elif row is not None:
                row.Cues, row.rb_cue_count, row.updated_at = json.dumps(entries), len(entries), now
            content.CueUpdated = str(int(content.CueUpdated or 0) + 1)
            content.updated_at = now
        return self.get_track(content_id)

    # -------------------------------------------------------------- suppression
    def _delete_content(self, db: Any, content: Any) -> None:
        from pyrekordbox.masterdb import models

        affected = set()
        for model in (models.DjmdSongPlaylist, models.DjmdSongMyTag, models.DjmdSongTagList, models.DjmdCue,
                      models.ContentCue, models.ContentFile, models.DjmdSongRelatedTracks):
            for row in db.query(model).filter_by(ContentID=content.ID).all():
                if model is models.DjmdSongPlaylist:
                    affected.add(row.PlaylistID)
                db.delete(row)
        db.delete(content)
        db.flush()
        for pid in affected:
            self._renumber(self._songs(db, pid))

    def delete_tracks(self, content_ids: Sequence[int], delete_files: bool = True) -> Tuple[int, int]:
        """Retire des sons de la collection. Le fichier audio, l'analyse et la pochette ne sont effacés
        que pour les sons ajoutés par DJSync et rangés dans son dossier de téléchargement."""
        removed = failures = 0
        owned = self.owned.all()
        to_clean: List[Tuple[str, str, Optional[str], Optional[str]]] = []
        with self._write() as db:
            for cid in content_ids:
                try:
                    c = self._content(cid)
                except TrackNotFoundError:
                    continue
                to_clean.append((c.UUID, c.FolderPath or "", c.AnalysisDataPath, c.ImagePath))
                self._delete_content(db, c)
                removed += 1
        for uuid, path, anlz, art in to_clean:
            if uuid not in owned:
                continue
            self.owned.remove(uuid)
            for rel in (anlz, art):
                if rel:
                    folder = self.absolute_path(rel).parent
                    if self._uuid_dir(uuid).split("/")[1] == folder.name:
                        shutil.rmtree(folder, ignore_errors=True)
            if delete_files and path and not self._delete_audio(Path(path)):
                failures += 1
        return removed, failures

    def _delete_audio(self, path: Path) -> bool:
        root = self.contents_root.resolve()
        target = path.resolve()
        if root not in target.parents or target.suffix.lower() not in FILE_TYPES:
            return False                   # hors du dossier DJSync : on ne touche pas au fichier
        try:
            target.unlink(missing_ok=True)
            parent = target.parent
            while parent != root and root in parent.parents and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            return True
        except OSError as exc:
            log.warning("File not deleted (%s): %s", target, exc)
            return False

    def playlists_of(self, content_ids: Sequence[int]) -> Dict[int, List[int]]:
        """1.2.1 (C11) : {son: [playlists qui le contiennent]}, pour l'outil Doublons."""
        ids = [int(i) for i in content_ids]
        out: Dict[int, List[int]] = {i: [] for i in ids}
        if not ids:
            return out
        params = {f"c{k}": str(i) for k, i in enumerate(ids)}
        rows = self._read("SELECT DISTINCT ContentID, PlaylistID FROM djmdSongPlaylist WHERE COALESCE(rb_local_deleted,0) = 0 AND ContentID IN ("
                          + ",".join(f":c{k}" for k in range(len(ids))) + ")", params)
        for cid, pid in rows:
            try:
                out.setdefault(int(cid), []).append(self._pid(pid))
            except (TypeError, ValueError):
                continue
        return out

    def merge_duplicates(self, keep_id: int, remove_ids: Sequence[int], delete_files: bool = True) -> Tuple[int, int]:
        remove = [str(c) for c in dict.fromkeys(remove_ids) if int(c) != int(keep_id)]
        if not remove:
            return 0, 0
        keep = str(keep_id)
        with self.batch():
            with self._write() as db:
                from pyrekordbox.masterdb import models

                self._content(keep_id)
                pids = {r.PlaylistID for r in db.query(models.DjmdSongPlaylist)
                        .filter(models.DjmdSongPlaylist.ContentID.in_(remove)).all()}
                for pid in pids:
                    has_keep, kept = False, []
                    for song in self._songs(db, pid):
                        if song.ContentID == keep and has_keep:
                            db.delete(song)                     # déjà remis à la place d'un doublon
                            continue
                        if song.ContentID == keep:
                            has_keep = True
                        elif song.ContentID in remove and not has_keep:
                            song.ContentID, song.updated_at = keep, datetime.now()     # même position
                            has_keep = True
                        kept.append(song)
                    db.flush()
                    self._renumber(kept)
            return self.delete_tracks([int(r) for r in remove], delete_files=delete_files)

    # ---------------------------------------------------------- spécifique clé USB
    def pdb_status(self) -> PdbStatus:
        return PdbStatus("off")

    def pdb_catch_up(self) -> Any:
        return None

    def legacy_format_present(self) -> bool:
        return False


__all__ = ["LocalRekordbox", "LocalRekordboxLibrary", "find_local_rekordbox", "default_db_dir",
           "default_music_dir", "rekordbox_running"]
