"""Connexion à exportLibrary.db (SQLCipher, WAL), transactions atomiques, sauvegardes."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


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
        pdb_allow_growth: bool = False,
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
        self._session_backed_up = False
        self._batch_depth = 0
        self._batch_backed_up = False
        self._ref_tables: List[str] = []
        self._tables: set = set()
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
        # ---- analyse / pochettes (V1.1-A4)
        self.analyze = analyze                      # BPM, tonalité, ANLZ à l'ajout
        self.auto_cue = False                       # V0.5.0 : mémoire cue sur le premier temps fort
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
            if not self.db_path.is_file():
                raise DatabaseOpenError(f"Database not found: {self.db_path}")

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
                        "The database is used by another program (is Rekordbox open?)."
                    ) from exc
                raise DatabaseOpenError(str(exc)) from exc
            except sqlcipher.DatabaseError as exc:
                conn.close()
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
            raise LibraryError("Library not connected: call connect().")
        return self._conn

    # ------------------------------------------------------------ WAL / transactions
    def _checkpoint(self) -> None:
        """Fusionne le -wal dans le fichier principal et le vide."""
        try:
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

    def session_point(self) -> None:
        """V1.2.0 : point de restauration complet (exportLibrary.db + export.pdb) avant la première
        modification de la session ; la toute première fois sur cette clé, c'est l'« origine »."""
        from .. import backups

        folder = self.db_path.parent
        try:
            fresh_origin = backups.ensure_origin(folder, self.backup_dir, conn=self._db(), key=self._key)
            if not fresh_origin:
                backups.snapshot(folder, self.backup_dir, "auto", conn=self._db(), key=self._key)
        except backups.BackupError as exc:
            raise LibraryError(f"Backup failed, write cancelled for safety: {exc}") from exc
        self._session_backed_up = True

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
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlcipher.OperationalError as exc:
                raise DatabaseLockedError(
                    "Cannot write: database locked (Rekordbox open?)."
                ) from exc
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                self._txn_ops = []             # transaction annulée : rien à répercuter dans export.pdb
                try:
                    conn.execute("ROLLBACK")
                except sqlcipher.Error:
                    pass
                raise
            self._checkpoint()
            self._pdb_queue.extend(self._txn_ops)
            self._txn_ops = []
            if self._batch_depth == 0:
                self._pdb_flush()

    def _read(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
        with self._lock:
            return self._db().execute(sql, params).fetchall()

    # ------------------------------------------------- compatibilité / réparation
    @property
    def legacy_format_present(self) -> bool:
        """True si la clé contient aussi l'ancien format (export.pdb), que DJSync ne met PAS à jour."""
        folder = self.db_path.parent
        return any((folder / name).is_file() for name in LEGACY_DB_NAMES)

