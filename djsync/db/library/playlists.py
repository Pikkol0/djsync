"""Playlists : création, renommage, suppression, contenu et ordre."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


class PlaylistsMixin:
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
            raise PlaylistNotFoundError(f"Playlist not found (id {playlist_id}).")
        return PlaylistInfo(*rows[0])

    def get_playlist_tracks(self, playlist_id: int) -> List[LibraryTrack]:
        self.get_playlist(playlist_id)
        rows = self._read(
            _track_select(self._has_key, with_sequence=True)
            + " JOIN playlist_content pc ON pc.content_id = c.content_id"
            + " WHERE pc.playlist_id = ? ORDER BY pc.sequenceNo, pc.rowid",
            (playlist_id,),
        )
        return [self._track(r) for r in rows]

    @staticmethod
    def _clean_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise LibraryError("The playlist name cannot be empty.")
        return name

    @staticmethod
    def _require_playlist(conn: Any, playlist_id: int, editable: bool = False) -> Tuple[Any, ...]:
        row = conn.execute(
            "SELECT playlist_id, COALESCE(attribute,0), name FROM playlist WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        if row is None:
            raise PlaylistNotFoundError(f"Playlist not found (id {playlist_id}).")
        if editable and row[1] != PLAYLIST_KIND:
            raise LibraryError(f"\"{row[2]}\" is not a regular playlist: its content cannot be changed.")
        return row

    @staticmethod
    def _name_taken(conn: Any, name: str, parent_id: int, exclude_id: int = -1) -> bool:
        return conn.execute(
            "SELECT 1 FROM playlist WHERE name = ? COLLATE NOCASE AND COALESCE(playlist_id_parent,0) = ? "
            "AND playlist_id != ?",
            (name, parent_id, exclude_id),
        ).fetchone() is not None

    def create_playlist(self, name: str, parent_id: int = 0) -> PlaylistInfo:
        return self._create_node(name, parent_id, PLAYLIST_KIND)

    def create_folder(self, name: str, parent_id: int = 0) -> PlaylistInfo:
        """Dossier de playlists (V0.2.0)."""
        return self._create_node(name, parent_id, FOLDER_KIND)

    def _create_node(self, name: str, parent_id: int, kind: int) -> PlaylistInfo:
        name = self._clean_name(name)
        with self._write() as conn:
            if parent_id != 0 and self._require_playlist(conn, parent_id)[1] != FOLDER_KIND:
                raise LibraryError("The parent must be a playlist folder.")
            if self._name_taken(conn, name, parent_id):
                raise DuplicatePlaylistError(f"A playlist \"{name}\" already exists here.")
            seq = conn.execute(
                "SELECT COALESCE(MAX(sequenceNo), 0) + 1 FROM playlist "
                "WHERE COALESCE(playlist_id_parent,0) = ?", (parent_id,),
            ).fetchone()[0]
            new_id = conn.execute(
                "INSERT INTO playlist (sequenceNo, name, image_id, attribute, playlist_id_parent) "
                "VALUES (?, ?, NULL, ?, ?)",
                (seq, name, kind, parent_id),
            ).lastrowid
            new_path = self._pl_path(conn, new_id)
            self._stage(lambda db, p=new_path, f=kind == FOLDER_KIND: db.ensure_playlist(p, f))
        return self.get_playlist(new_id)

    def rename_playlist(self, playlist_id: int, new_name: str) -> None:
        new_name = self._clean_name(new_name)
        with self._write() as conn:
            self._require_playlist(conn, playlist_id)
            parent = conn.execute(
                "SELECT COALESCE(playlist_id_parent,0) FROM playlist WHERE playlist_id = ?", (playlist_id,)
            ).fetchone()[0]
            if self._name_taken(conn, new_name, parent, exclude_id=playlist_id):
                raise DuplicatePlaylistError(f"A playlist \"{new_name}\" already exists here.")
            old_path = self._pl_path(conn, playlist_id)
            conn.execute("UPDATE playlist SET name = ? WHERE playlist_id = ?", (new_name, playlist_id))
            self._stage(lambda db, p=old_path, n=new_name: db.rename_playlist(p, n))

    def delete_playlist(self, playlist_id: int) -> None:
        """Supprime la playlist (et, pour un dossier, tout son contenu). Les SONS sont conservés."""
        with self._write() as conn:
            self._require_playlist(conn, playlist_id)
            gone_path = self._pl_path(conn, playlist_id)
            self._stage(lambda db, p=gone_path: db.delete_playlist(p))
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
                raise TrackNotFoundError(f"Track not found (id {cid}).")
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
            added = self._append(conn, playlist_id, content_ids)
            paths = self._stage_tracks(conn, content_ids)
            pl_path = self._pl_path(conn, playlist_id)
            self._stage(lambda db, p=pl_path, t=paths: db.playlist_add(p, t))
            return added

    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        """Retire de la playlist SANS supprimer le son de la bibliothèque."""
        if not content_ids:
            return
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            marks = ",".join("?" * len(content_ids))
            paths = [r[0] for r in conn.execute(
                f"SELECT path FROM content WHERE content_id IN ({marks})", list(content_ids))]
            pl_path = self._pl_path(conn, playlist_id)
            conn.execute(
                f"DELETE FROM playlist_content WHERE playlist_id = ? AND content_id IN ({marks})",
                [playlist_id, *content_ids])
            self._resequence(conn, playlist_id)
            self._stage(lambda db, p=pl_path, t=paths: db.playlist_remove(p, t))

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
                raise TrackNotFoundError(f"Tracks missing from the source playlist: {missing}")
            ordered = [c for c in content_ids if c in found]
            self._append(conn, to_playlist_id, ordered)
            conn.execute(
                f"DELETE FROM playlist_content WHERE playlist_id = ? AND content_id IN ({marks})",
                [from_playlist_id, *content_ids])
            self._resequence(conn, from_playlist_id)
            paths = self._stage_tracks(conn, ordered)
            src, dst = self._pl_path(conn, from_playlist_id), self._pl_path(conn, to_playlist_id)
            self._stage(lambda db, p=dst, t=paths: db.playlist_add(p, t))
            self._stage(lambda db, p=src, t=paths: db.playlist_remove(p, t))

    def reorder_track(self, playlist_id: int, content_id: int, new_position: int) -> None:
        """Place un son à la position `new_position` (1 = premier) dans sa playlist."""
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            ids = [r[0] for r in conn.execute(
                "SELECT content_id FROM playlist_content WHERE playlist_id = ? ORDER BY sequenceNo, rowid",
                (playlist_id,))]
            if content_id not in ids:
                raise TrackNotFoundError("This track is not in the playlist.")
            ids.remove(content_id)
            ids.insert(max(0, min(new_position - 1, len(ids))), content_id)
            conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (playlist_id,))
            conn.executemany(
                "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                [(playlist_id, cid, i) for i, cid in enumerate(ids, start=1)])
            self._stage_order(conn, playlist_id)

    def set_playlist_order(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        """Enregistre l'ordre (champ sequenceNo) d'une playlist : `content_ids` doit contenir
        EXACTEMENT les sons actuels de la playlist, dans le nouvel ordre."""
        wanted = list(content_ids)
        with self._write() as conn:
            self._require_playlist(conn, playlist_id, editable=True)
            current = {r[0] for r in conn.execute(
                "SELECT content_id FROM playlist_content WHERE playlist_id = ?", (playlist_id,))}
            if set(wanted) != current or len(wanted) != len(current):
                raise LibraryError("The playlist changed in the meantime: reload it before saving the order.")
            conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (playlist_id,))
            conn.executemany(
                "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                [(playlist_id, cid, i) for i, cid in enumerate(wanted, start=1)])
            self._stage_order(conn, playlist_id)

    def _stage_order(self, conn: Any, playlist_id: int) -> None:
        if self._pdb_enabled():
            self._stage_tracks(conn, [r[0] for r in conn.execute(
                "SELECT content_id FROM playlist_content WHERE playlist_id = ?", (playlist_id,))])
            pl_path, paths = self._pl_path(conn, playlist_id), self._ordered_paths(conn, playlist_id)
            self._stage(lambda db, p=pl_path, t=paths: db.playlist_set(p, t))

