"""Lecture des sons, sondage audio, suppression (fichier + analyse)."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


class TracksMixin:
    # ---------------------------------------------------------------- lecture sons
    @staticmethod
    def _track(row: Tuple[Any, ...]) -> LibraryTrack:
        cid, title, artist, album, length, path, bpmx100, ftype, comment, added, analysis, art = row[:12]
        key = row[12] if len(row) > 12 else None
        return LibraryTrack(
            content_id=cid, title=title or "", artist=artist, album=album,
            duration_seconds=int(length), path=path or "", bpm=bpmx100 / 100.0, file_type=ftype,
            source_url=comment if comment and (extract_video_id(comment) or comment.startswith("http")) else None,
            date_added=added, is_analysed=bool(analysis), artwork_path=art or None,
            sequence=int(row[13]) if len(row) > 13 and row[13] is not None else 0,
            key=key or None, analysis_path=analysis or None,
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
        return [self._track(r) for r in self._read(_track_select(self._has_key) + " ORDER BY c.content_id")]

    def get_track(self, content_id: int) -> LibraryTrack:
        rows = self._read(_track_select(self._has_key) + " WHERE c.content_id = ?", (content_id,))
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        return self._track(rows[0])

    def find_by_source_url(self, url_or_video_id: str) -> Optional[LibraryTrack]:
        """Doublon exact : le son a déjà été téléchargé depuis cette vidéo YouTube (id) ou
        cette URL (SoundCloud…)."""
        vid = extract_video_id(url_or_video_id)
        if vid:
            sql, arg = " WHERE instr(c.djComment, ?) > 0", vid
        else:
            arg = (url_or_video_id or "").strip().split("?")[0].split("#")[0]
            if not arg.startswith("http"):
                return None
            sql = " WHERE c.djComment = ?"
        rows = self._read(_track_select(self._has_key) + sql + " ORDER BY c.content_id LIMIT 1", (arg,))
        return self._track(rows[0]) if rows else None

    def track_count(self) -> int:
        return self._read("SELECT COUNT(*) FROM content")[0][0]

    # ------------------------------------------------------------- ajout / suppression
    @staticmethod
    def _probe_audio(path: Path) -> Dict[str, int]:
        import mutagen

        ftype = FILE_TYPES.get(path.suffix.lower())
        if ftype is None:
            raise UnsupportedFormatError(f"Unsupported format: {path.suffix or '(no extension)'}")
        try:
            audio = mutagen.File(str(path))
        except Exception as exc:  # mutagen lève des erreurs variées sur fichier tronqué
            raise UnsupportedFormatError(f"Unreadable audio file: {exc}") from exc
        if audio is None or audio.info is None:
            raise UnsupportedFormatError("Unreadable audio file (invalid header).")
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

    def delete_track(self, content_id: int, delete_file: bool = True) -> bool:
        """Retire le son de la bibliothèque et de toutes les playlists.

        Renvoie True si le fichier physique a été supprimé. La base est modifiée en premier :
        si la suppression du fichier échoue, la bibliothèque reste cohérente (le son a disparu
        de la base, le fichier est simplement orphelin) et on renvoie False.
        """
        with self._write() as conn:
            row = conn.execute("SELECT path, analysisDataFilePath, masterDbId FROM content WHERE content_id = ?",
                               (content_id,)).fetchone()
            if row is None:
                raise TrackNotFoundError(f"Track not found (id {content_id}).")
            path, anlz_path, master = row
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
            if path and not shared:
                self._stage(lambda db, p=path: db.delete_track(p))

        if not delete_file or shared or not path:
            return False
        if anlz_path and master is None:
            self._delete_analysis(anlz_path, path)
        return self._delete_physical_file(path)

    def _delete_analysis(self, anlz_path: str, track_path: str) -> None:
        """Supprime les fichiers ANLZ d'un son DJSync supprimé (seulement s'ils lui appartiennent :
        balise PPTH = chemin du son) ; la pochette est conservée (elle peut servir à l'album)."""
        from ...analysis.anlz import read_path

        dat = (self.drive.root / anlz_path.lstrip("/")).resolve()
        root = (self.drive.root / "PIONEER" / "USBANLZ").resolve()
        if root not in dat.parents or dat.name.upper() != "ANLZ0000.DAT":
            return
        try:
            if read_path(dat.read_bytes()).casefold() != track_path.casefold():
                return
            for ext in (".DAT", ".EXT", ".2EX"):
                dat.with_suffix(ext).unlink(missing_ok=True)
            folder = dat.parent
            while folder != root and root in folder.parents and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            log.warning("Analysis files not deleted (%s): %s", dat, exc)

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
            log.error("Deletion refused (suspicious path): %s", target)
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
            log.warning("File not deleted (%s): %s", target, exc)
            return False
