"""Gestion de PIONEER/rekordbox/exportLibrary.db (OneLibrary / Device Library Plus).

Points clés, vérifiés sur une vraie base de clé USB :
  * la base est chiffrée en SQLCipher 4 (le module `sqlite3` standard ne peut PAS l'ouvrir) ;
  * elle est en mode WAL ; le -wal est chiffré lui aussi ;
  * les chemins sont stockés relatifs à la racine de la clé, en "/", ex. "/Contents/Artiste/Album/x.mp3" ;
  * playlist.attribute : 0 = playlist, 1 = dossier, 4 = playlist intelligente ;
  * un son ajouté sans analyse laisse NULL : analysisDataFilePath, analysedBits, masterDbId,
    masterContentId, contentLink (même choix que pyrekordbox).

Sécurité des données :
  * sauvegarde chiffrée de la base avant la première écriture de chaque session ;
  * chaque modification = une transaction (BEGIN IMMEDIATE ... COMMIT), annulée si erreur ;
  * après chaque commit, `wal_checkpoint(TRUNCATE)` : le fichier principal contient tout et le
    -wal est vidé, car un lecteur/une platine qui ignore le WAL ne verrait sinon rien de neuf.
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from sqlcipher3 import dbapi2 as sqlcipher

from ._key import get_default_key
from .base import LibraryBackend
from .errors import (
    DatabaseLockedError,
    DatabaseOpenError,
    DuplicatePlaylistError,
    LibraryError,
    PlaylistNotFoundError,
    ReadOnlyError,
    TrackNotFoundError,
    UnsupportedFormatError,
)
from .models import FOLDER_KIND, PLAYLIST_KIND, LibraryTrack, PlaylistInfo
from .usb import UsbDrive, drive_from_letter

log = logging.getLogger(__name__)

# Extension -> content.fileType (codes constatés dans la base + enum pyrekordbox)
FILE_TYPES = {".mp3": 1, ".m4a": 4, ".aac": 4, ".flac": 5, ".wav": 11, ".aiff": 12, ".aif": 12}
REQUIRED_TABLES = {"content", "playlist", "playlist_content", "artist", "album", "property"}
# Tables annexes qui référencent un son : nettoyées à la suppression d'un son
_CONTENT_REFS = ("cue", "history_content", "myTag_content")
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")

_TRACK_SELECT = """
    SELECT c.content_id, c.title, COALESCE(a.name, ''), al.name, COALESCE(c.length, 0), c.path,
           COALESCE(c.bpmx100, 0), COALESCE(c.fileType, 0), c.djComment,
           COALESCE(c.dateAdded, ''), c.analysisDataFilePath, im.path
    FROM content c
    LEFT JOIN artist a  ON a.artist_id  = c.artist_id_artist
    LEFT JOIN album  al ON al.album_id  = c.album_id
    LEFT JOIN image  im ON im.image_id  = c.image_id
"""


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extrait l'identifiant YouTube (11 caractères) d'une URL, ou le renvoie s'il est déjà nu."""
    text = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = _VIDEO_ID.search(text)
    return m.group(1) if m else None


def _safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned[:100] or fallback


class RekordboxUsbLibrary(LibraryBackend):
    """Bibliothèque d'une clé USB Rekordbox. Thread-safe (un verrou protège la connexion)."""

    def __init__(
        self,
        drive: Union[UsbDrive, str, Path],
        key: Optional[str] = None,
        read_only: bool = False,
        contents_dir: str = "Contents",
        backup_keep: int = 10,
        backup_session_keep: int = 5,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self.drive = drive if isinstance(drive, UsbDrive) else drive_from_letter(str(drive))
        self.read_only = read_only
        self.contents_dir = contents_dir.strip("/\\") or "Contents"
        self._key = key or get_default_key()
        self.backup_keep = backup_keep                  # sauvegardes « avant modification » conservées
        self.backup_session_keep = backup_session_keep  # sauvegardes « début de session » conservées
        self._busy_timeout_ms = busy_timeout_ms
        self._conn: Optional[Any] = None
        self._lock = threading.RLock()
        self._session_backed_up = False
        self._batch_depth = 0
        self._batch_backed_up = False
        self._ref_tables: List[str] = []
        self.journal_mode = ""

    # ------------------------------------------------------------------ connexion
    @property
    def db_path(self) -> Path:
        return self.drive.db_path

    @property
    def contents_root(self) -> Path:
        """Dossier de destination des sons (modifiable via `contents_dir`)."""
        return self.drive.root / self.contents_dir

    def default_download_dir(self, artist: str, album: Optional[str] = None) -> Path:
        """Convention Rekordbox : <clé>/Contents/<Artiste>/<Album ou UnknownAlbum>/."""
        return (
            self.contents_root
            / _safe_name(artist, "Unknown Artist")
            / _safe_name(album or "", "UnknownAlbum")
        )

    def connect(self) -> "RekordboxUsbLibrary":
        with self._lock:
            if self._conn is not None:
                return self
            if not self.db_path.is_file():
                raise DatabaseOpenError(f"Base introuvable : {self.db_path}")

            conn = sqlcipher.connect(
                str(self.db_path),
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,        # transactions gérées explicitement (BEGIN/COMMIT)
                check_same_thread=False,     # l'UI Tk utilisera des threads de travail
            )
            try:
                conn.execute("PRAGMA key = '%s'" % self._key.replace("'", "''"))
                conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlcipher.OperationalError as exc:
                conn.close()
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise DatabaseLockedError(
                        "La base est utilisée par un autre programme (Rekordbox est-il ouvert ?)."
                    ) from exc
                raise DatabaseOpenError(str(exc)) from exc
            except sqlcipher.DatabaseError as exc:
                conn.close()
                raise DatabaseOpenError(
                    "Impossible de déchiffrer la base (mauvaise clé, fichier corrompu "
                    "ou ce n'est pas une base OneLibrary)."
                ) from exc

            missing = REQUIRED_TABLES - tables
            if missing:
                conn.close()
                raise DatabaseOpenError(f"Base inattendue, tables manquantes : {sorted(missing)}")

            conn.execute("PRAGMA synchronous = FULL")  # support amovible : durabilité avant vitesse
            if self.read_only:
                conn.execute("PRAGMA query_only = ON")
            self.journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if self.journal_mode.lower() != "wal":
                log.warning("Mode journal inattendu : %s (attendu : wal)", self.journal_mode)

            self._ref_tables = [
                t for t in _CONTENT_REFS
                if t in tables and any(c[1] == "content_id" for c in conn.execute(f'PRAGMA table_info("{t}")'))
            ]
            self._conn = conn
            log.info("Bibliothèque ouverte : %s (journal=%s)", self.db_path, self.journal_mode)
            return self

    def close(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            if not self.read_only:
                self._checkpoint()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "RekordboxUsbLibrary":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _db(self) -> Any:
        if self._conn is None:
            raise LibraryError("Bibliothèque non connectée : appelez connect().")
        return self._conn

    # ------------------------------------------------------------ WAL / transactions
    def _checkpoint(self) -> None:
        """Fusionne le -wal dans le fichier principal et le vide."""
        try:
            busy, _, _ = self._db().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy:
                log.warning("Checkpoint WAL incomplet : un autre processus lit la base.")
        except sqlcipher.Error as exc:
            log.warning("Checkpoint WAL impossible : %s", exc)

    @property
    def backup_dir(self) -> Path:
        return self.drive.root / "DJSync_Backups"

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Regroupe plusieurs écritures sous UNE seule sauvegarde (suppression de 40 sons, etc.)."""
        with self._lock:
            self._batch_depth += 1
            try:
                yield
            finally:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._batch_backed_up = False

    def _backup_before_write(self) -> None:
        """Copie chiffrée de la base AVANT chaque modification.

        Deux séries, à rotation séparée : « session » (1re modification de la session : l'état
        dans lequel vous avez trouvé la clé, jamais écrasé par les suivantes) et « auto »
        (état juste avant chaque modification, dernières `backup_keep` conservées).
        Si la sauvegarde échoue (clé pleine…), l'écriture est annulée par prudence.
        """
        if self._batch_depth > 0 and self._batch_backed_up:
            return
        tag = "auto" if self._session_backed_up else "session"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        target = self.backup_dir / f"exportLibrary-{stamp}-{tag}.db"
        try:
            self.backup_dir.mkdir(exist_ok=True)
            self._checkpoint()
            try:  # API de sauvegarde SQLite : cohérente même si le WAL n'est pas vide
                dest = sqlcipher.connect(str(target))
                dest.execute("PRAGMA key = '%s'" % self._key.replace("'", "''"))
                self._db().backup(dest)
                dest.close()
            except (sqlcipher.Error, AttributeError):
                target.unlink(missing_ok=True)
                shutil.copy2(self.db_path, target)  # WAL vidé juste avant : le fichier est complet
            for pattern, keep in (("*-auto.db", self.backup_keep), ("*-session.db", self.backup_session_keep)):
                for old in sorted(self.backup_dir.glob(f"exportLibrary-{pattern}"))[: -keep or None]:
                    old.unlink(missing_ok=True)
            log.info("Sauvegarde : %s", target.name)
        except OSError as exc:
            raise LibraryError(f"Sauvegarde impossible, écriture annulée par prudence : {exc}") from exc
        self._session_backed_up = True
        if self._batch_depth > 0:
            self._batch_backed_up = True

    @contextmanager
    def _write(self) -> Iterator[Any]:
        """Transaction d'écriture atomique + checkpoint WAL. Tout ou rien."""
        with self._lock:
            conn = self._db()
            if self.read_only:
                raise ReadOnlyError("Bibliothèque ouverte en lecture seule.")
            self._backup_before_write()
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlcipher.OperationalError as exc:
                raise DatabaseLockedError(
                    "Impossible d'écrire : base verrouillée (Rekordbox ouvert ?)."
                ) from exc
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlcipher.Error:
                    pass
                raise
            self._checkpoint()

    def _read(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
        with self._lock:
            return self._db().execute(sql, params).fetchall()

    # ---------------------------------------------------------------- lecture sons
    @staticmethod
    def _track(row: Tuple[Any, ...]) -> LibraryTrack:
        cid, title, artist, album, length, path, bpmx100, ftype, comment, added, analysis, art = row[:12]
        return LibraryTrack(
            content_id=cid, title=title or "", artist=artist, album=album,
            duration_seconds=int(length), path=path or "", bpm=bpmx100 / 100.0, file_type=ftype,
            source_url=comment if comment and extract_video_id(comment) else None,
            date_added=added, is_analysed=bool(analysis), artwork_path=art or None,
            sequence=int(row[12]) if len(row) > 12 and row[12] is not None else 0,
        )

    def absolute_path(self, track_or_path: Union[LibraryTrack, str]) -> Path:
        """Chemin réel sur la clé d'un son (ou d'un chemin de la base, ex. "/Contents/…")."""
        rel = track_or_path.path if isinstance(track_or_path, LibraryTrack) else track_or_path
        return self.drive.root / rel.lstrip("/\\")

    def artwork_file(self, track: LibraryTrack) -> Optional[Path]:
        """Pochette Rekordbox du son si elle existe sur la clé."""
        if not track.artwork_path:
            return None
        p = self.absolute_path(track.artwork_path)
        return p if p.is_file() else None

    def iter_tracks(self) -> Iterable[Tuple[str, str]]:
        """Contrat LibraryProvider : couples (titre, artiste) pour la détection de doublons.

        Beaucoup de titres existants sont de la forme "Artiste - Titre" (82 sur 213 dans la base
        analysée) et l'artiste en base peut différer ("Vald - Désaccordé" / artiste "V5LD").
        On fournit donc aussi l'interprétation découpée, en plus de la brute.
        """
        out: List[Tuple[str, str]] = []
        for title, artist in self._read(
            "SELECT c.title, COALESCE(a.name,'') FROM content c "
            "LEFT JOIN artist a ON a.artist_id = c.artist_id_artist"
        ):
            title = title or ""
            out.append((title, artist))
            if " - " in title:
                left, right = title.split(" - ", 1)
                out.append((right, left))
        return out

    def list_tracks(self) -> List[LibraryTrack]:
        return [self._track(r) for r in self._read(_TRACK_SELECT + " ORDER BY c.content_id")]

    def get_track(self, content_id: int) -> LibraryTrack:
        rows = self._read(_TRACK_SELECT + " WHERE c.content_id = ?", (content_id,))
        if not rows:
            raise TrackNotFoundError(f"Son introuvable (id {content_id}).")
        return self._track(rows[0])

    def find_by_source_url(self, url_or_video_id: str) -> Optional[LibraryTrack]:
        """Doublon exact : le son a déjà été téléchargé depuis cette vidéo YouTube."""
        vid = extract_video_id(url_or_video_id)
        if not vid:
            return None
        rows = self._read(
            _TRACK_SELECT + " WHERE instr(c.djComment, ?) > 0 ORDER BY c.content_id LIMIT 1", (vid,)
        )
        return self._track(rows[0]) if rows else None

    def track_count(self) -> int:
        return self._read("SELECT COUNT(*) FROM content")[0][0]

    # ------------------------------------------------------------------- playlists
    _PLAYLIST_SELECT = """
        SELECT p.playlist_id, p.name, COALESCE(p.playlist_id_parent, 0), COALESCE(p.attribute, 0),
               COALESCE(p.sequenceNo, 0),
               (SELECT COUNT(*) FROM playlist_content pc WHERE pc.playlist_id = p.playlist_id)
        FROM playlist p
    """

    def list_playlists(self) -> List[PlaylistInfo]:
        rows = self._read(self._PLAYLIST_SELECT + " ORDER BY 3, 5, 1")
        return [PlaylistInfo(*r) for r in rows]

    def get_playlist(self, playlist_id: int) -> PlaylistInfo:
        rows = self._read(self._PLAYLIST_SELECT + " WHERE p.playlist_id = ?", (playlist_id,))
        if not rows:
            raise PlaylistNotFoundError(f"Playlist introuvable (id {playlist_id}).")
        return PlaylistInfo(*rows[0])

    def get_playlist_tracks(self, playlist_id: int) -> List[LibraryTrack]:
        self.get_playlist(playlist_id)
        rows = self._read(
            _TRACK_SELECT.replace("im.path", "im.path, pc.sequenceNo", 1)
            + " JOIN playlist_content pc ON pc.content_id = c.content_id"
            + " WHERE pc.playlist_id = ? ORDER BY pc.sequenceNo, pc.rowid",
            (playlist_id,),
        )
        return [self._track(r) for r in rows]

    @staticmethod
    def _clean_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise LibraryError("Le nom de la playlist ne peut pas être vide.")
        return name

    @staticmethod
    def _require_playlist(conn: Any, playlist_id: int, editable: bool = False) -> Tuple[Any, ...]:
        row = conn.execute(
            "SELECT playlist_id, COALESCE(attribute,0), name FROM playlist WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        if row is None:
            raise PlaylistNotFoundError(f"Playlist introuvable (id {playlist_id}).")
        if editable and row[1] != PLAYLIST_KIND:
            raise LibraryError(f"« {row[2]} » n'est pas une playlist classique : contenu non modifiable.")
        return row

    @staticmethod
    def _name_taken(conn: Any, name: str, parent_id: int, exclude_id: int = -1) -> bool:
        return conn.execute(
            "SELECT 1 FROM playlist WHERE name = ? COLLATE NOCASE AND COALESCE(playlist_id_parent,0) = ? "
            "AND playlist_id != ?",
            (name, parent_id, exclude_id),
        ).fetchone() is not None

    def create_playlist(self, name: str, parent_id: int = 0) -> PlaylistInfo:
        name = self._clean_name(name)
        with self._write() as conn:
            if parent_id != 0 and self._require_playlist(conn, parent_id)[1] != FOLDER_KIND:
                raise LibraryError("Le parent doit être un dossier de playlists.")
            if self._name_taken(conn, name, parent_id):
                raise DuplicatePlaylistError(f"Une playlist « {name} » existe déjà ici.")
            seq = conn.execute(
                "SELECT COALESCE(MAX(sequenceNo), 0) + 1 FROM playlist "
                "WHERE COALESCE(playlist_id_parent,0) = ?", (parent_id,),
            ).fetchone()[0]
            new_id = conn.execute(
                "INSERT INTO playlist (sequenceNo, name, image_id, attribute, playlist_id_parent) "
                "VALUES (?, ?, NULL, ?, ?)",
                (seq, name, PLAYLIST_KIND, parent_id),
            ).lastrowid
        return self.get_playlist(new_id)

    def rename_playlist(self, playlist_id: int, new_name: str) -> None:
        new_name = self._clean_name(new_name)
        with self._write() as conn:
            self._require_playlist(conn, playlist_id)
            parent = conn.execute(
                "SELECT COALESCE(playlist_id_parent,0) FROM playlist WHERE playlist_id = ?", (playlist_id,)
            ).fetchone()[0]
            if self._name_taken(conn, new_name, parent, exclude_id=playlist_id):
                raise DuplicatePlaylistError(f"Une playlist « {new_name} » existe déjà ici.")
            conn.execute("UPDATE playlist SET name = ? WHERE playlist_id = ?", (new_name, playlist_id))

    def delete_playlist(self, playlist_id: int) -> None:
        """Supprime la playlist (et, pour un dossier, tout son contenu). Les SONS sont conservés."""
        with self._write() as conn:
            self._require_playlist(conn, playlist_id)
            doomed, frontier = [playlist_id], [playlist_id]
            while frontier:
                marks = ",".join("?" * len(frontier))
                frontier = [r[0] for r in conn.execute(
                    f"SELECT playlist_id FROM playlist WHERE playlist_id_parent IN ({marks})", frontier)]
                doomed += frontier
            marks = ",".join("?" * len(doomed))
            conn.execute(f"DELETE FROM playlist_content WHERE playlist_id IN ({marks})", doomed)
            conn.execute(f"DELETE FROM playlist WHERE playlist_id IN ({marks})", doomed)

    # ------------------------------------------------- contenu des playlists (internes)
    @staticmethod
    def _resequence(conn: Any, playlist_id: int) -> None:
        ids = [r[0] for r in conn.execute(
            "SELECT content_id FROM playlist_content WHERE playlist_id = ? ORDER BY sequenceNo, rowid",
            (playlist_id,))]
        conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (playlist_id,))
        conn.executemany(
            "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
            [(playlist_id, cid, i) for i, cid in enumerate(ids, start=1)],
        )

    @staticmethod
    def _append(conn: Any, playlist_id: int, content_ids: Sequence[int]) -> int:
        present = {r[0] for r in conn.execute(
            "SELECT content_id FROM playlist_content WHERE playlist_id = ?", (playlist_id,))}
        seq = conn.execute(
            "SELECT COALESCE(MAX(sequenceNo), 0) FROM playlist_content WHERE playlist_id = ?",
            (playlist_id,)).fetchone()[0]
        added = 0
        for cid in dict.fromkeys(content_ids):  # dédoublonne en gardant l'ordre
            if cid in present:
                continue
            if conn.execute("SELECT 1 FROM content WHERE content_id = ?", (cid,)).fetchone() is None:
                raise TrackNotFoundError(f"Son introuvable (id {cid}).")
            seq += 1
            added += 1
            conn.execute(
                "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                (playlist_id, cid, seq))
        return added

    # --------------------------------------------- contenu des playlists (publiques)
    def add_to_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> int:
        """Ajoute en fin de playlist (les sons déjà présents sont ignorés). Renvoie le nombre ajouté."""
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            return self._append(conn, playlist_id, content_ids)

    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        """Retire de la playlist SANS supprimer le son de la bibliothèque."""
        if not content_ids:
            return
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            marks = ",".join("?" * len(content_ids))
            conn.execute(
                f"DELETE FROM playlist_content WHERE playlist_id = ? AND content_id IN ({marks})",
                [playlist_id, *content_ids])
            self._resequence(conn, playlist_id)

    def move_tracks(self, content_ids: Sequence[int], from_playlist_id: int, to_playlist_id: int) -> None:
        """Déplace des sons d'une playlist à une autre, de façon atomique."""
        if from_playlist_id == to_playlist_id or not content_ids:
            return
        with self._write() as conn:
            self._require_playlist(conn, from_playlist_id, editable=True)
            self._require_playlist(conn, to_playlist_id, editable=True)
            marks = ",".join("?" * len(content_ids))
            found = {r[0] for r in conn.execute(
                f"SELECT content_id FROM playlist_content WHERE playlist_id = ? AND content_id IN ({marks})",
                [from_playlist_id, *content_ids])}
            missing = [c for c in content_ids if c not in found]
            if missing:
                raise TrackNotFoundError(f"Sons absents de la playlist source : {missing}")
            ordered = [c for c in content_ids if c in found]
            self._append(conn, to_playlist_id, ordered)
            conn.execute(
                f"DELETE FROM playlist_content WHERE playlist_id = ? AND content_id IN ({marks})",
                [from_playlist_id, *content_ids])
            self._resequence(conn, from_playlist_id)

    def reorder_track(self, playlist_id: int, content_id: int, new_position: int) -> None:
        """Place un son à la position `new_position` (1 = premier) dans sa playlist."""
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            ids = [r[0] for r in conn.execute(
                "SELECT content_id FROM playlist_content WHERE playlist_id = ? ORDER BY sequenceNo, rowid",
                (playlist_id,))]
            if content_id not in ids:
                raise TrackNotFoundError("Ce son n'est pas dans la playlist.")
            ids.remove(content_id)
            ids.insert(max(0, min(new_position - 1, len(ids))), content_id)
            conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (playlist_id,))
            conn.executemany(
                "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                [(playlist_id, cid, i) for i, cid in enumerate(ids, start=1)])

    def set_playlist_order(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        """Enregistre l'ordre (champ sequenceNo) d'une playlist : `content_ids` doit contenir
        EXACTEMENT les sons actuels de la playlist, dans le nouvel ordre."""
        wanted = list(content_ids)
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            current = {r[0] for r in conn.execute(
                "SELECT content_id FROM playlist_content WHERE playlist_id = ?", (playlist_id,))}
            if set(wanted) != current or len(wanted) != len(current):
                raise LibraryError("La playlist a changé entre-temps : rechargez-la avant d'enregistrer l'ordre.")
            conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (playlist_id,))
            conn.executemany(
                "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                [(playlist_id, cid, i) for i, cid in enumerate(wanted, start=1)])

    # ------------------------------------------------------------- ajout / suppression
    @staticmethod
    def _probe_audio(path: Path) -> Dict[str, int]:
        import mutagen

        ftype = FILE_TYPES.get(path.suffix.lower())
        if ftype is None:
            raise UnsupportedFormatError(f"Format non géré : {path.suffix or '(sans extension)'}")
        try:
            audio = mutagen.File(str(path))
        except Exception as exc:  # mutagen lève des erreurs variées sur fichier tronqué
            raise UnsupportedFormatError(f"Fichier audio illisible : {exc}") from exc
        if audio is None or audio.info is None:
            raise UnsupportedFormatError("Fichier audio illisible (en-tête invalide).")
        info = audio.info
        return {
            "fileType": ftype,
            "length": int(round(getattr(info, "length", 0) or 0)),
            "bitrate": int((getattr(info, "bitrate", 0) or 0) / 1000),
            "bitDepth": int(getattr(info, "bits_per_sample", 0) or 16),
            "samplingRate": int(getattr(info, "sample_rate", 0) or 0),
        }

    @staticmethod
    def _get_or_create(conn: Any, table: str, id_col: str, name: str, extra_match: str = "",
                       extra_params: Tuple[Any, ...] = (), insert_sql: str = "",
                       insert_params: Tuple[Any, ...] = ()) -> int:
        row = conn.execute(
            f"SELECT {id_col} FROM {table} WHERE name = ? COLLATE NOCASE {extra_match} LIMIT 1",
            (name, *extra_params)).fetchone()
        return row[0] if row else conn.execute(insert_sql, insert_params).lastrowid

    def add_track(
        self,
        file_path: Path,
        title: str,
        artist: str,
        album: Optional[str] = None,
        source_url: Optional[str] = None,
        playlist_ids: Sequence[int] = (),
    ) -> LibraryTrack:
        """Insère une entrée « minimale » (titre, artiste, chemin) et l'ajoute aux playlists.

        Pas de BPM, de tonalité ni de waveform : l'analyse se fera dans Rekordbox.
        Idempotent : si le fichier est déjà référencé, on réutilise l'entrée et on
        l'ajoute simplement aux playlists demandées.
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise LibraryError(f"Fichier introuvable : {file_path}")
        try:
            rel = file_path.resolve().relative_to(self.drive.root.resolve())
        except ValueError as exc:
            raise LibraryError(f"Le fichier doit se trouver sur la clé ({self.drive.root}).") from exc
        db_path = "/" + rel.as_posix()

        title = (title or "").strip() or file_path.stem
        artist = (artist or "").strip()
        album = (album or "").strip() or None
        vid = extract_video_id(source_url or "")
        comment = f"https://www.youtube.com/watch?v={vid}" if vid else (source_url or "")
        audio = self._probe_audio(file_path)
        today = date.today().isoformat()

        with self._write() as conn:
            for pid in playlist_ids:
                self._require_playlist(conn, pid, editable=True)

            existing = conn.execute(
                "SELECT content_id FROM content WHERE path = ? COLLATE NOCASE", (db_path,)).fetchone()
            if existing:
                content_id = existing[0]
            else:
                artist_id = None
                if artist:
                    artist_id = self._get_or_create(
                        conn, "artist", "artist_id", artist,
                        insert_sql="INSERT INTO artist (name, nameForSearch) VALUES (?, NULL)",
                        insert_params=(artist,))
                album_id = None
                if album:
                    album_id = self._get_or_create(
                        conn, "album", "album_id", album,
                        extra_match="AND (artist_id IS ? OR artist_id IS NULL)", extra_params=(artist_id,),
                        insert_sql="INSERT INTO album (name, artist_id, image_id, isComplation, nameForSearch) "
                                   "VALUES (?, ?, NULL, 0, NULL)",
                        insert_params=(album, artist_id))

                cols: Dict[str, Any] = {
                    "title": title, "subtitle": "", "bpmx100": 0, "length": audio["length"],
                    "trackNo": 0, "discNo": 0, "artist_id_artist": artist_id, "artist_id_lyricist": 0,
                    "album_id": album_id, "color_id": 0, "djComment": comment, "rating": 0,
                    "releaseYear": 0, "releaseDate": "", "dateCreated": today, "dateAdded": today,
                    "path": db_path, "fileName": file_path.name, "fileSize": file_path.stat().st_size,
                    "fileType": audio["fileType"], "bitrate": audio["bitrate"],
                    "bitDepth": audio["bitDepth"], "samplingRate": audio["samplingRate"],
                    "isrc": "", "djPlayCount": 0, "isHotCueAutoLoadOn": 1, "isKuvoDeliverStatusOn": 1,
                    "kuvoDeliveryComment": "", "hasModified": 0, "cueUpdateCount": 0,
                    "analysisDataUpdateCount": 0, "informationUpdateCount": 0,
                    # NULL volontaires (son non analysé, absent de la base PC) :
                    # analysisDataFilePath, analysedBits, masterDbId, masterContentId, contentLink
                }
                content_id = conn.execute(
                    f"INSERT INTO content ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    tuple(cols.values())).lastrowid
                conn.execute("UPDATE property SET numberOfContents = (SELECT COUNT(*) FROM content)")

            for pid in playlist_ids:
                self._append(conn, pid, [content_id])
        return self.get_track(content_id)

    def delete_track(self, content_id: int, delete_file: bool = True) -> bool:
        """Retire le son de la bibliothèque et de toutes les playlists.

        Renvoie True si le fichier physique a été supprimé. La base est modifiée en premier :
        si la suppression du fichier échoue, la bibliothèque reste cohérente (le son a disparu
        de la base, le fichier est simplement orphelin) et on renvoie False.
        """
        with self._write() as conn:
            row = conn.execute("SELECT path FROM content WHERE content_id = ?", (content_id,)).fetchone()
            if row is None:
                raise TrackNotFoundError(f"Son introuvable (id {content_id}).")
            path = row[0]
            affected = [r[0] for r in conn.execute(
                "SELECT DISTINCT playlist_id FROM playlist_content WHERE content_id = ?", (content_id,))]
            conn.execute("DELETE FROM playlist_content WHERE content_id = ?", (content_id,))
            for table in self._ref_tables:
                conn.execute(f'DELETE FROM "{table}" WHERE content_id = ?', (content_id,))
            conn.execute("DELETE FROM content WHERE content_id = ?", (content_id,))
            for pid in affected:
                self._resequence(conn, pid)
            conn.execute("UPDATE property SET numberOfContents = (SELECT COUNT(*) FROM content)")
            shared = conn.execute(
                "SELECT 1 FROM content WHERE path = ? COLLATE NOCASE", (path,)).fetchone() is not None

        if not delete_file or shared or not path:
            return False
        return self._delete_physical_file(path)

    def delete_tracks(self, content_ids: Sequence[int], delete_files: bool = True) -> Tuple[int, int]:
        """Supprime plusieurs sons sous une seule sauvegarde.
        Renvoie (sons retirés de la base, fichiers qui n'ont pas pu être effacés)."""
        removed = file_failures = 0
        with self.batch():
            for cid in content_ids:
                try:
                    file_deleted = self.delete_track(cid, delete_file=delete_files)
                except TrackNotFoundError:
                    continue
                removed += 1
                if delete_files and not file_deleted:
                    file_failures += 1
        return removed, file_failures

    def _delete_physical_file(self, db_path: str) -> bool:
        root = self.drive.root.resolve()
        target = (root / db_path.lstrip("/")).resolve()
        # Garde-fou : jamais hors de la clé, jamais autre chose qu'un fichier audio connu.
        if root not in target.parents or target.suffix.lower() not in FILE_TYPES:
            log.error("Suppression refusée (chemin suspect) : %s", target)
            return False
        try:
            target.unlink(missing_ok=True)
            stop = self.contents_root.resolve()
            parent = target.parent
            while parent != stop and stop in parent.parents and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            return True
        except OSError as exc:
            log.warning("Fichier non supprimé (%s) : %s", target, exc)
            return False
