"""Miroir export.pdb (V1.1-A3) : les écritures validées dans exportLibrary.db y sont répercutées."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


class PdbMirrorMixin:
    # ------------------------------------------------------- miroir export.pdb (V1.1-A3)
    def _pdb_store(self) -> PdbStore:
        return PdbStore(self.db_path.parent, self.backup_dir, keep=self.backup_keep,
                        session_keep=self.backup_session_keep, allow_growth=self.pdb_allow_growth)

    def _pdb_enabled(self) -> bool:
        return self.pdb_sync != "off" and (self.db_path.parent / "export.pdb").is_file()

    def _stage(self, op: PdbOp) -> None:
        """Met une opération en file ; elle ne part vers export.pdb qu'APRÈS le commit de la base."""
        if self._pdb_enabled():
            self._txn_ops.append(op)

    def _pdb_flush(self) -> None:
        """Applique la file à export.pdb. Ne lève jamais : la base OneLibrary est déjà validée."""
        ops, self._pdb_queue = self._pdb_queue, []
        if not ops:
            return
        try:
            self.pdb_last_summary = self._pdb_store().apply(ops)
            if self.pdb_state != "stale":
                self.pdb_state = "ok"
            self.pdb_problem = ""
        except PdbError as exc:
            self.pdb_state, self.pdb_problem = "stale", str(exc)
            log.warning("export.pdb non mis à jour (exportLibrary.db l'est) : %s", exc)
        except Exception as exc:  # noqa: BLE001 - jamais d'exception vers l'appelant
            self.pdb_state, self.pdb_problem = "stale", f"{type(exc).__name__} : {exc}"
            log.exception("export.pdb non mis à jour")

    @staticmethod
    def _pl_path(conn: Any, playlist_id: int) -> PdbPath:
        names: List[str] = []
        seen = set()
        while playlist_id and playlist_id not in seen:
            seen.add(playlist_id)
            row = conn.execute(
                "SELECT name, COALESCE(playlist_id_parent,0) FROM playlist WHERE playlist_id = ?", (playlist_id,)).fetchone()
            if row is None:
                break
            names.append(row[0])
            playlist_id = row[1]
        return tuple(reversed(names))

    @staticmethod
    def _meta(row: Tuple[Any, ...]) -> TrackMeta:
        added = (row[11] or "")[:10]
        return TrackMeta(
            path=row[16] or "", title=row[1], artist=row[2], album=row[3], length=int(row[4]), bpmx100=int(row[5]),
            file_size=int(row[6]), bitrate=int(row[7]), bit_depth=int(row[8]), sample_rate=int(row[9]),
            file_type=int(row[10]), date_added=added, comment=row[12], track_no=int(row[13]),
            disc_no=int(row[14]), year=int(row[15]), key=row[17] or "", artwork_path=_art.pdb_path(row[18] or ""),
            analyze_path=row[19] or "", analyze_date=added if row[19] else "")

    def _meta_sql(self) -> str:
        return _meta_select(self._has_key, self._has_image)

    def _metas(self, conn: Any, content_ids: Sequence[int]) -> List[TrackMeta]:
        out: List[TrackMeta] = []
        for cid in dict.fromkeys(content_ids):
            row = conn.execute(self._meta_sql() + " WHERE c.content_id = ?", (cid,)).fetchone()
            if row is not None and row[16]:
                out.append(self._meta(row))
        return out

    def _stage_tracks(self, conn: Any, content_ids: Sequence[int]) -> List[str]:
        """Met en file l'ajout (idempotent) des sons concernés ; renvoie leurs chemins."""
        if not self._pdb_enabled():
            return []
        metas = self._metas(conn, content_ids)
        for meta in metas:
            self._stage(lambda db, m=meta: db.add_track(m))
        return [m.path for m in metas]

    def _ordered_paths(self, conn: Any, playlist_id: int) -> List[str]:
        return [r[0] for r in conn.execute(
            "SELECT c.path FROM playlist_content pc JOIN content c ON c.content_id = pc.content_id "
            "WHERE pc.playlist_id = ? ORDER BY pc.sequenceNo, pc.rowid", (playlist_id,))]

    def _ol_snapshot(self) -> Tuple[List[TrackMeta], List[Tuple[PdbPath, bool, List[str]]]]:
        """Sons et playlists (chemin, dossier ?, chemins des sons dans l'ordre) de exportLibrary.db."""
        with self._lock:
            conn = self._db()
            metas = [self._meta(r) for r in conn.execute(self._meta_sql() + " ORDER BY c.content_id") if r[16]]
            nodes = {r[0]: r for r in conn.execute(
                "SELECT playlist_id, name, COALESCE(playlist_id_parent,0), COALESCE(attribute,0), COALESCE(sequenceNo,0) FROM playlist")}
            members: Dict[int, List[str]] = {}
            for pid, path in conn.execute(
                    "SELECT pc.playlist_id, c.path FROM playlist_content pc JOIN content c ON c.content_id = pc.content_id "
                    "ORDER BY pc.playlist_id, pc.sequenceNo, pc.rowid"):
                members.setdefault(pid, []).append(path)
        def path_of(pid: int) -> PdbPath:
            names, seen = [], set()
            while pid and pid in nodes and pid not in seen:
                seen.add(pid)
                names.append(nodes[pid][1])
                pid = nodes[pid][2]
            return tuple(reversed(names))
        ordered = sorted(nodes.values(), key=lambda r: (len(path_of(r[0])), r[2], r[4], r[0]))
        playlists = [(path_of(r[0]), r[3] == FOLDER_KIND, members.get(r[0], [])) for r in ordered]
        return metas, playlists

    def pdb_status(self) -> PdbStatus:
        """Compare export.pdb à exportLibrary.db (lecture seule)."""
        if self.pdb_sync == "off":
            self.pdb_state = "off"
            return PdbStatus("off")
        store = self._pdb_store()
        if not store.exists():
            self.pdb_state = "absent"
            return PdbStatus("absent")
        try:
            pdb = store.load()
        except PdbError as exc:
            self.pdb_state = "unsupported"
            return PdbStatus("unsupported", str(exc))
        metas, playlists = self._ol_snapshot()
        missing = sum(1 for m in metas if not pdb.has_track(m.path))
        missing_pl = sum(1 for path, _f, _t in playlists if pdb.find_playlist(path) is None)
        state = "stale" if (missing or missing_pl) else "ok"
        self.pdb_state = state
        return PdbStatus(state, self.pdb_problem, pdb.track_count, len(metas), missing, missing_pl)

    def pdb_catch_up(self) -> PdbSummary:
        """Rattrapage ADDITIF : ajoute à export.pdb les sons et playlists de exportLibrary.db qui y
        manquent (ex. sons ajoutés par DJSync avant la V1.1-A3). Ne supprime et ne réordonne rien."""
        if self.read_only:
            raise ReadOnlyError("Bibliothèque ouverte en lecture seule.")
        if self.pdb_sync == "off":
            raise LibraryError("La synchronisation de export.pdb est désactivée dans les Paramètres.")
        store = self._pdb_store()
        if not store.exists():
            raise LibraryError("Cette clé ne contient pas de export.pdb : rien à synchroniser.")
        metas, playlists = self._ol_snapshot()
        ops: List[PdbOp] = [lambda db, m=m: db.add_track(m) for m in metas]
        for path, is_folder, tracks in playlists:
            ops.append(lambda db, p=path, f=is_folder: db.ensure_playlist(p, f))
            if not is_folder and tracks:
                ops.append(lambda db, p=path, t=tracks: db.playlist_add(p, t))
        with self._lock:
            try:
                summary = store.apply(ops)
            except PdbError as exc:
                self.pdb_state, self.pdb_problem = "stale", str(exc)
                raise LibraryError(f"export.pdb non synchronisé (la clé n'a pas été modifiée) : {exc}") from exc
        self.pdb_state, self.pdb_problem, self.pdb_last_summary = "ok", "", summary
        return summary

    def inspect_conventions(self) -> Dict[str, Dict[str, int]]:
        """Comment Rekordbox renseigne lui-même les colonnes optionnelles : pour chaque clé étrangère
        de `content`, nombre de lignes à NULL / à 0 / valides / pendantes ; plus les colonnes de
        recherche vides. Lecture seule : sert à ALIGNER DJSync sur les sons natifs, jamais à réécrire."""
        out: Dict[str, Dict[str, int]] = {}
        with self._lock:
            conn = self._db()
            cols = {c[1] for c in conn.execute('PRAGMA table_info("content")')}
            for col, table, id_col in _CONTENT_FKS:
                if col not in cols:
                    continue
                valid = (f'SELECT COUNT(*) FROM content WHERE {col} IN (SELECT {id_col} FROM "{table}")'
                         if table in self._tables else "SELECT 0")
                out[col] = {
                    "NULL": conn.execute(f"SELECT COUNT(*) FROM content WHERE {col} IS NULL").fetchone()[0],
                    "zero": conn.execute(f"SELECT COUNT(*) FROM content WHERE {col} = 0").fetchone()[0],
                    "valid": conn.execute(valid).fetchone()[0],
                    "other": conn.execute(
                        f"SELECT COUNT(*) FROM content WHERE {col} IS NOT NULL AND {col} != 0").fetchone()[0],
                }
            for table, col in (("content", "titleForSearch"), ("artist", "nameForSearch"), ("album", "nameForSearch")):
                if table in self._tables:
                    out[f"{table}.{col}"] = {
                        "NULL": conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL").fetchone()[0],
                        "empty": conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ''").fetchone()[0],
                        "filled": conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} != ''").fetchone()[0],
                    }
        return out

