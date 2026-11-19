"""Connexion à exportLibrary.db (SQLCipher, WAL), transactions atomiques, sauvegardes."""
from __future__ import annotations

import sys
import time

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


def _sqlite_code(exc: BaseException) -> str:
    """1.4.3 (B105) : erreur SQLite avec son code étendu (pour le journal)."""
    return (f"{exc} (code {getattr(exc, 'sqlite_errorcode', '?')} "
            f"{getattr(exc, 'sqlite_errorname', '') or type(exc).__name__})")


class LibraryBase:
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
        pdb_sync: str = "auto",
        pdb_allow_growth: bool = True,          # 1.3.0-rc.2 : comme l'app (défaut depuis la 1.0.0)
        analyze: bool = True,
        artwork: bool = True,
        ffmpeg_location: Optional[str] = None,
        key_notation: str = "auto",
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
        # 1.4.3 (A3-6) : 2e connexion, en lecture seule, pour les lectures faites hors d'une écriture : la base
        # est en WAL, une lecture voit la dernière version validée sans attendre le verrou des écritures
        # (sauvegarde, export.pdb). Comme `_read_fast` pour master.db (B52).
        self._reader: Optional[Any] = None
        self._reader_lock = threading.Lock()
        self._reader_off = False                    # désactivée après un échec (lecture normale ensuite)
        self._closing = False                       # 1.4.3-rc.2 : plus de 2e connexion pendant la fermeture
        self._session_backed_up = False
        self._batch_depth = 0
        self._batch_backed_up = False
        self._session_point_id = ""                 # 1.4.2 (A6-6) : point de session de cette session
        self._no_copy_point = ""                    # 1.4.2 (A6-6) : suppression sans copie permise (point de retour)
        self._ref_tables: List[str] = []
        self._tables: set = set()
        self._content_cols: set = set()
        self._has_key = False
        self.journal_mode = ""
        # ---- miroir export.pdb (V1.1-A3)
        self.pdb_sync = pdb_sync                    # "auto" | "off"
        self.pdb_allow_growth = pdb_allow_growth    # autorise l'ajout de pages (non validé sur platine)
        self.pdb_state = "unknown"                  # unknown | off | absent | unsupported | stale | ok
        self.pdb_problem = ""                       # dernier message d'échec (vide si tout va bien)
        self.pdb_last_summary: Optional[PdbSummary] = None
        self._pdb_queue: List[PdbOp] = []           # opérations validées en base, pas encore écrites dans export.pdb
        self._txn_ops: List[PdbOp] = []             # opérations de la transaction en cours
        # 1.3.0-rc.2 : export.pdb est réconcilié avec exportLibrary.db (db/pdb/sync.py) ; les
        # suppressions / renommages / infos modifiées sont notés dans un journal sur la clé.
        self._txn_marks: List[Any] = []
        self._pdb_dirty = False
        # 1.4.3 (A1-2) : hors lot, export.pdb est réécrit `pdb_delay` s après la dernière écriture (une seule fois
        # pour une rafale de téléchargements ou d'analyses), et toujours avant fermeture, éjection, « Prêt pour le
        # set » ou toute lecture de son état (`pdb_status`). 0 = tout de suite (défaut ; l'application met 3 s).
        self.pdb_delay = 0.0
        self.pdb_delay_max = 30.0                   # rafale sans fin : réécrit quand même toutes les 30 s
        self._pdb_timer: Optional[threading.Timer] = None
        self.recovery: Any = None                   # 1.4.3 (A6-1) : reprise faite à l'ouverture (recover.Recovery)
        self._pdb_pending_since = 0.0
        # ---- analyse / pochettes (V1.1-A4)
        self.analyze = analyze                      # BPM, tonalité, ANLZ à l'ajout
        self.auto_cue = False                       # V0.5.0 : mémoire cue sur le premier temps fort
        self.native_parts: Tuple[str, ...] = ()     # 1.4.1 (C131) : ce qu'une réanalyse refait sur un son de Rekordbox
        self.artwork = artwork                      # pochette intégrée -> PIONEER/Artwork
        self.ffmpeg_location = ffmpeg_location or None
        self.key_notation = key_notation            # auto | camelot | musical
        self.last_problems: List[str] = []          # ce qui n'a pas pu être fait au dernier ajout
        self._has_image = False
        self._date_sample: Optional[str] = None     # date d'un son natif (sert de modèle de format)
        self._date_probed = False

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
            self._closing = False
            from ..recover import recover

            # 1.4.3 (A6-1) : remplacement interrompu (clé retirée) : copie temporaire valide remise en place
            self.recovery = recover(self.db_path.parent, self._key, read_only=self.read_only)
            if not self.db_path.is_file():
                raise DatabaseOpenError(f"Database not found: {self.db_path}")

            try:
                conn, tables = self._open_conn()
            except sqlcipher.OperationalError as exc:
                if not self._shm_fault(exc):
                    raise self._open_error(exc) from exc
                self._repair_shm(exc)                # 1.4.3 (B105) : comme Rekordbox, puis ouverture normale
                try:
                    conn, tables = self._open_conn()
                except sqlcipher.Error as again:
                    log.warning("Drive database still unreadable after the exclusive repair: %s",
                                _sqlite_code(again))
                    raise ShmRepairError(self._drive_name(), "still") from again
            except sqlcipher.DatabaseError as exc:
                raise DatabaseOpenError(
                    "Cannot decrypt the database (wrong key, corrupted file "
                    "or not a OneLibrary database)."
                ) from exc

            missing = REQUIRED_TABLES - tables
            if missing:
                conn.close()
                raise DatabaseOpenError(f"Unexpected database, missing tables: {sorted(missing)}")

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
            self._tables = set(tables)
            self._content_cols = {c[1] for c in conn.execute('PRAGMA table_info("content")')}
            self._has_key = "key" in tables and any(
                c[1] == "key_id" for c in conn.execute('PRAGMA table_info("key")'))
            self._has_image = "image" in tables and any(
                c[1] == "path" for c in conn.execute('PRAGMA table_info("image")'))
            self._conn = conn
            log.info("Library opened: %s (journal=%s)", self.db_path, self.journal_mode)
        try:                      # état de export.pdb (lecture seule) : n'empêche jamais la connexion
            self.pdb_status()
        except Exception:  # noqa: BLE001
            log.exception("export.pdb state unknown")
        return self

    def _open_conn(self, exclusive: bool = False) -> Tuple[Any, set]:
        """Ouvre exportLibrary.db (clé SQLCipher, délai) et lit la liste des tables (premier accès : c'est là
        qu'une erreur de -wal / -shm apparaît). `exclusive` (B105) : `locking_mode = EXCLUSIVE` avant le premier
        accès : SQLite garde l'index du journal en mémoire et n'ouvre pas le -shm (comme Rekordbox)."""
        conn = sqlcipher.connect(
            str(self.db_path),
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,        # transactions gérées explicitement (BEGIN/COMMIT)
            check_same_thread=False,     # l'UI Tk utilisera des threads de travail
        )
        try:
            conn.execute("PRAGMA key = '%s'" % self._key.replace("'", "''"))
            conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
            if exclusive:
                conn.execute("PRAGMA locking_mode = EXCLUSIVE")
            if sys.platform == "darwin":          # 1.4.3 (A7-4) : vidage complet (SQLite se replie sur exFAT)
                conn.execute("PRAGMA fullfsync = ON")
                conn.execute("PRAGMA checkpoint_fullfsync = ON")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except BaseException:
            conn.close()
            raise
        return conn, tables

    @staticmethod
    def _open_error(exc: BaseException) -> LibraryError:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return DatabaseLockedError("The database is used by another program (is Rekordbox open?).")
        return DatabaseOpenError(str(exc))

    def _drive_name(self) -> str:
        try:
            return str(self.drive)
        except Exception:  # noqa: BLE001
            return str(self.db_path.parent.parent.parent)

    @property
    def _shm_path(self) -> Path:
        return Path(str(self.db_path) + "-shm")

    def _shm_fault(self, exc: BaseException) -> bool:
        """1.4.3 (B105) : erreur d'E/S (ou fichier impossible à ouvrir) à l'ouverture, avec un -shm présent."""
        log.warning("Drive database open failed: %s", _sqlite_code(exc))
        code = getattr(exc, "sqlite_errorcode", None)
        text = str(exc).lower()
        io = "disk i/o" in text or (isinstance(code, int) and code & 0xFF == 10)            # SQLITE_IOERR
        cant = "unable to open" in text or (isinstance(code, int) and code & 0xFF == 14)    # SQLITE_CANTOPEN
        try:
            return (io or cant) and self._shm_path.exists() and self.db_path.is_file()
        except OSError:
            return False

    def _repair_shm(self, cause: BaseException) -> None:
        """1.4.3 (B105) : comme Rekordbox, réouverture une fois en mode exclusif (le -shm est ignoré, le -wal
        repris), checkpoint, fermeture. Aucun fichier supprimé ; le mode exclusif n'est jamais gardé (une
        session, le mode live C15, a besoin du mode partagé). Lève ShmRepairError si c'est impossible."""
        name = self._drive_name()
        if self.read_only:
            log.warning("Drive %s: -shm unreadable, library opened read-only: not repaired", name)
            raise ShmRepairError(name, "read_only") from cause
        log.warning("Drive %s: -shm present and unreadable, reopening once in exclusive mode (like Rekordbox)",
                    name)
        try:
            conn, _ = self._open_conn(exclusive=True)
        except sqlcipher.Error as exc:
            log.warning("Exclusive open failed: %s", _sqlite_code(exc))
            raise ShmRepairError(name, "exclusive") from exc
        try:
            wal = Path(str(self.db_path) + "-wal")
            size = wal.stat().st_size if wal.exists() else 0
            busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy:
                raise sqlcipher.OperationalError("database is locked (checkpoint busy)")
            log.warning("Drive %s repaired in exclusive mode (journal of %s bytes merged), reopening normally",
                        name, size)
        except sqlcipher.Error as exc:
            log.warning("Exclusive checkpoint failed: %s", _sqlite_code(exc))
            raise ShmRepairError(name, "exclusive") from exc
        finally:
            conn.close()

    def close(self) -> None:
        # 1.4.3-rc.2 : une lecture d'un autre fil ne rouvre plus la 2e connexion pendant la fermeture (blocage
        # vu en test : connexion de lecture ouverte par le fil « db » pendant la fermeture de la principale)
        self._closing = True
        self._close_reader()
        self._pdb_cancel_timer()
        with self._lock:
            if self._conn is None:
                return
            if not self.read_only:
                if self._pdb_dirty:                # 1.4.3 (A1-2) : réécriture en attente faite avant de fermer
                    self._pdb_flush()
                self._checkpoint()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "RekordboxUsbLibrary":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _db(self) -> Any:
        if self._conn is None:
            raise LibraryError("Library not connected: call connect().")
        return self._conn

    def alive(self) -> Optional[bool]:
        """1.3.0-rc.7 (B28) : la connexion à la base répond-elle encore ? None si la bibliothèque est
        occupée (on ne bloque jamais la surveillance des clés), False si la base ne se lit plus (clé
        retirée, même si elle a été rebranchée depuis : l'ancienne connexion ne sert plus à rien)."""
        if self._conn is None or not self._lock.acquire(blocking=False):
            return None
        try:
            self._conn.execute("PRAGMA schema_version").fetchone()
            return True
        except sqlcipher.Error as exc:
            text = str(exc).lower()
            return False if any(k in text for k in ("disk i/o", "unable to open", "not a database", "malformed")) \
                else None
        finally:
            self._lock.release()

    # ------------------------------------------------------------ WAL / transactions
    def _checkpoint(self) -> None:
        """Fusionne le -wal dans le fichier principal et le vide."""
        if not Path(self.db_path).exists():         # 1.3.0-rc.3 (B22) : clé retirée, rien à faire
            log.info("WAL checkpoint skipped: %s is gone (drive removed?)", self.db_path)
            return
        try:
            with self._reader_lock:      # 1.4.3 (A3-6) : pas de lecture en cours pendant le checkpoint (TRUNCATE)
                busy, _, _ = self._db().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy:
                log.warning("Incomplete WAL checkpoint: another process is reading the database.")
        except sqlcipher.Error as exc:
            log.warning("WAL checkpoint failed: %s", exc)

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
                    self._pdb_flush()          # UNE seule réécriture d'export.pdb pour tout le lot

    @contextmanager
    def long_batch(self) -> Iterator[None]:
        """1.4.2 (C23) : comme batch() (une seule sauvegarde, UNE seule réécriture d'export.pdb à la fin), mais
        le verrou n'est pas gardé entre deux écritures : pendant un long transfert (copie de centaines de
        fichiers), les lectures de l'interface passent. Une écriture venue d'ailleurs pendant ce temps rejoint
        le lot (export.pdb mis à jour à la fin)."""
        with self._lock:
            self._batch_depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._batch_backed_up = False
                    self._pdb_flush()

    def session_point(self) -> None:
        """V1.2.0 : point de restauration complet (exportLibrary.db + export.pdb) avant la première
        modification de la session ; la toute première fois sur cette clé, c'est l'« origine »."""
        from .. import backups

        folder = self.db_path.parent
        try:
            fresh_origin = backups.ensure_origin(folder, self.backup_dir, conn=self._db(), key=self._key)
            if not fresh_origin:
                point = backups.snapshot(folder, self.backup_dir, "auto", conn=self._db(), key=self._key)
            else:
                point = next(iter(backups.list_points(self.backup_dir)), None)
        except backups.BackupError as exc:
            raise LibraryError(f"Backup failed, write cancelled for safety: {exc}") from exc
        self._session_point_id = getattr(point, "id", "") or ""
        self._session_backed_up = True

    # ------------------------------------------------------------ 1.4.2 (A6-6) : clé pleine
    def full_state(self) -> Tuple[bool, int, int]:
        """(pleine ?, place libre, seuil) ; seuil = base + export.pdb + 10 Mo."""
        from .. import key_space

        return key_space.state(self.db_path.parent)

    def full_error(self, exc: BaseException) -> Optional[KeyFullError]:
        """KeyFullError si `exc` est une erreur « disque plein » ET que la place libre est sous le seuil."""
        from .. import key_space

        if isinstance(exc, KeyFullError):
            return exc
        if not key_space.is_space_error(exc):
            return None
        full, free, need = self.full_state()
        if not full:
            return None
        name = getattr(self.drive, "label", "") or str(self.drive.root)
        return KeyFullError(free, need, name)

    def full_return_point(self) -> Any:
        """Point de retour pour une suppression sans copie (règle 3 b), ou None."""
        from .. import key_space

        return key_space.return_point(self.backup_dir, self._key, self._session_point_id)

    def create_backup(self, label: str = "") -> Any:
        """Sauvegarde manuelle (Réglages ▸ Sauvegardes de la clé)."""
        from .. import backups

        with self._lock:
            self._checkpoint()
            try:
                return backups.snapshot(self.db_path.parent, self.backup_dir, "manual", label=label.strip(),
                                        conn=self._db(), key=self._key)
            except backups.BackupError as exc:
                raise LibraryError(str(exc)) from exc

    def _backup_before_write(self) -> None:
        """Copie chiffrée de la base AVANT chaque modification.

        V1.2.0 : la 1re modification de la session crée d'abord un point de restauration complet
        (DJSync_Backups/Points, voir db/backups.py) ; puis chaque modification laisse une copie
        « auto » (état juste avant, dernières `backup_keep` conservées).
        Si la sauvegarde échoue (clé pleine…), l'écriture est annulée par prudence.
        """
        if self._batch_depth > 0 and self._batch_backed_up:
            return
        try:
            self._backup_copy()
        except LibraryError as exc:
            full = self.full_error(exc)
            if full is None:
                raise
            if not self._no_copy_point:                 # A6-6 règle 3 : seulement la suppression confirmée
                raise full from exc
            log.warning("Write without backup copy (drive full), way back: %s", self._no_copy_point)
            if self._batch_depth > 0:
                self._batch_backed_up = True

    def _backup_copy(self) -> None:
        if not self._session_backed_up:
            self.session_point()
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
            try:
                target.unlink(missing_ok=True)           # A6-6 : pas de copie à moitié écrite sur une clé pleine
            except OSError:
                log.debug("Ignored error in _backup_copy", exc_info=True)  # 1.4.3 (A3-4)
            raise LibraryError(f"Backup failed, write cancelled for safety: {exc}") from exc
        self._session_backed_up = True
        if self._batch_depth > 0:
            self._batch_backed_up = True

    @contextmanager
    def _write(self) -> Iterator[Any]:
        """Transaction d'écriture atomique + checkpoint WAL. Tout ou rien."""
        with self._lock:
            conn = self._db()
            if self.read_only:
                raise ReadOnlyError("Library opened read-only.")
            self._backup_before_write()
            self._txn_ops = []
            self._txn_marks = []
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlcipher.OperationalError as exc:
                raise DatabaseLockedError(
                    "Cannot write: database locked (Rekordbox open?)."
                ) from exc
            try:
                yield conn
                if self._txn_marks:
                    # 1.4.3 (A6-9) : marques (son supprimé, playlist renommée…) dans le journal de la clé AVANT
                    # le COMMIT : une coupure entre les deux ne peut plus les perdre. Si la transaction est
                    # annulée, la marque n'a plus d'objet et la réconciliation suivante la retire.
                    self._pdb_journal().add(self._txn_marks)
                conn.execute("COMMIT")
            except BaseException as exc:
                self._txn_ops = []             # transaction annulée : rien à répercuter dans export.pdb
                self._txn_marks = []
                try:
                    conn.execute("ROLLBACK")
                except sqlcipher.Error:
                    log.debug("Ignored error in _write", exc_info=True)  # 1.4.3 (A3-4)
                full = self.full_error(exc) if isinstance(exc, Exception) else None
                if full is not None and full is not exc:
                    raise full from exc        # A6-6 : « clé pleine » au lieu de « disk I/O error »
                raise
            self._checkpoint()
            if self._txn_ops or self._txn_marks:
                self._pdb_dirty = True
            self._txn_ops, self._txn_marks = [], []
            if self._batch_depth == 0:
                self._pdb_flush_later()

    # ------------------------------------------------- 1.4.3 (A1-2) : export.pdb après la rafale
    @property
    def pdb_pending(self) -> bool:
        """Une réécriture d'export.pdb attend la fin de la rafale d'écritures."""
        return self._pdb_timer is not None

    def _pdb_flush_later(self) -> None:
        if self.pdb_delay <= 0 or not self._pdb_dirty:
            self._pdb_flush()
            return
        now = time.monotonic()
        if self._pdb_timer is None:
            self._pdb_pending_since = now
        elif now - self._pdb_pending_since >= self.pdb_delay_max:
            self._pdb_cancel_timer()
            self._pdb_flush()
            return
        self._pdb_cancel_timer()
        timer = threading.Timer(self.pdb_delay, self._pdb_timer_fired)
        timer.daemon = True
        timer.name = "djsync-pdb-later"
        self._pdb_timer = timer
        timer.start()

    def _pdb_cancel_timer(self) -> None:
        timer, self._pdb_timer = self._pdb_timer, None
        if timer is not None:
            timer.cancel()

    def _pdb_timer_fired(self) -> None:
        with self._lock:
            if self._pdb_timer is None or self._pdb_timer is not threading.current_thread():
                return                              # remplacé ou annulé entre-temps
            self._pdb_timer = None
            if self._conn is None or self._batch_depth > 0:
                return                              # fermée (déjà faite) ou lot en cours (fait à la fin du lot)
            self._pdb_flush()

    def pdb_flush_now(self) -> None:
        """Fait tout de suite la réécriture d'export.pdb en attente (éjection, « Prêt pour le set »…)."""
        if self._pdb_timer is None:
            return
        self._pdb_cancel_timer()
        with self._lock:
            if self._conn is not None and self._batch_depth == 0:
                self._pdb_flush()

    def library_identity(self) -> str:
        """1.4.3 (A3-3) : identifiant stable de cette clé (date de création et nom de l'appareil de la table
        `property`), pour les réglages par bibliothèque. "" si illisible (noté au journal)."""
        try:
            rows = self._read("SELECT COALESCE(createdDate,''), COALESCE(deviceName,'') FROM property LIMIT 1")
        except Exception as exc:  # noqa: BLE001 - réglages de confort : pas d'erreur à l'écran
            log.info("Key identity not read (settings per library fall back to the label): %s", exc)
            return ""
        return "|".join(str(x) for x in rows[0]) if rows else ""

    def _read(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
        """Lecture. 1.4.3 (A3-6) : hors d'une écriture du même fil, par la connexion de lecture (sans attendre
        le verrou des écritures) ; dans une écriture (ou si la connexion de lecture manque), par la connexion
        principale, qui voit aussi ce que la transaction en cours a écrit."""
        if not self._owns_lock():
            rows = self._read_side(sql, params)
            if rows is not None:
                return rows
        with self._lock:
            return self._db().execute(sql, params).fetchall()

    def _owns_lock(self) -> bool:
        owned = getattr(self._lock, "_is_owned", None)
        return bool(owned()) if owned is not None else True

    def _read_side(self, sql: str, params: Sequence[Any]) -> Optional[List[Tuple[Any, ...]]]:
        """1.4.3 (A3-6) : lecture par la 2e connexion ; None = passer par la connexion principale."""
        if self._reader_off or self._closing or self._conn is None or self.journal_mode.lower() != "wal":
            return None
        with self._reader_lock:
            if self._closing:
                return None
            try:
                if self._reader is None:
                    self._reader = self._open_reader()
                return self._reader.execute(sql, params).fetchall()
            except sqlcipher.Error as exc:
                log.info("Separate read connection unavailable (%s): normal read", exc)
                self._drop_reader()
                if not Path(self.db_path).exists():
                    return None
                self._reader_off = True
                return None

    def _open_reader(self) -> Any:
        conn = sqlcipher.connect(str(self.db_path), timeout=self._busy_timeout_ms / 1000, isolation_level=None,
                                 check_same_thread=False)
        try:
            conn.execute("PRAGMA key = '%s'" % self._key.replace("'", "''"))
            conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
            conn.execute("PRAGMA query_only = ON")
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        except BaseException:
            conn.close()
            raise
        return conn

    def _drop_reader(self) -> None:
        reader, self._reader = self._reader, None
        if reader is not None:
            try:
                reader.close()
            except sqlcipher.Error:
                log.debug("Ignored error in _drop_reader", exc_info=True)  # 1.4.3 (A3-4)

    def _close_reader(self) -> None:
        with self._reader_lock:
            self._drop_reader()
            self._reader_off = False

    # ------------------------------------------------- compatibilité / réparation
    @property
    def legacy_format_present(self) -> bool:
        """True si la clé contient aussi l'ancien format (export.pdb), que DJSync ne met PAS à jour."""
        folder = self.db_path.parent
        return any((folder / name).is_file() for name in LEGACY_DB_NAMES)

