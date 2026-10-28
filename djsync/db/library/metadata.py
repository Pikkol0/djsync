"""Métadonnées, doublons, statistiques de playlists et grille de temps (V0.2.0).

Toutes les modifications passent par `_write()` (sauvegarde + transaction) puis sont répercutées
dans export.pdb par le miroir (même id de piste : les playlists des platines restent valides).
"""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


ANLZ_BACKUPS_KEEP = 30           # grilles d'origine conservées (les plus récentes)


def prune_folders(folder: Path, keep: int) -> None:
    """Ne garde que les `keep` sous-dossiers les plus récents (noms horodatés)."""
    import shutil

    olds = sorted(p for p in folder.iterdir() if p.is_dir())[:-keep or None]
    for old in olds:
        shutil.rmtree(old, ignore_errors=True)


@dataclass(frozen=True)
class PlaylistStats:
    """Nombre de sons, durée totale et date du dernier ajout (« modifiée le ») d'une playlist."""

    track_count: int
    total_seconds: int
    last_added: str            # AAAA-MM-JJ ('' si inconnue)


@dataclass
class BeatGrid:
    """Grille de temps d'un son (balise PQTZ de son .DAT)."""

    content_id: int
    beats: List[Tuple[int, int, int]]      # (n° dans la mesure 1-4, tempo x100, position ms)
    duration_ms: int
    dat_path: Path
    native: bool                           # son analysé par Rekordbox (exporté depuis le PC)

    @property
    def bpm(self) -> float:
        return self.beats[0][1] / 100.0 if self.beats else 0.0

    @property
    def is_constant(self) -> bool:
        return len({b[1] for b in self.beats}) <= 1


class MetadataMixin:
    # ------------------------------------------------------------------ statistiques
    def playlist_stats(self) -> Dict[int, PlaylistStats]:
        """{playlist_id: PlaylistStats} en une requête ; clé 0 = toute la bibliothèque."""
        out: Dict[int, PlaylistStats] = {}
        for pid, n, total, last in self._read(
                "SELECT pc.playlist_id, COUNT(*), COALESCE(SUM(c.length),0), COALESCE(MAX(c.dateAdded),'') "
                "FROM playlist_content pc JOIN content c ON c.content_id = pc.content_id GROUP BY pc.playlist_id"):
            out[pid] = PlaylistStats(int(n), int(total), (last or "")[:10])
        n, total, last = self._read("SELECT COUNT(*), COALESCE(SUM(length),0), COALESCE(MAX(dateAdded),'') FROM content")[0]
        out[0] = PlaylistStats(int(n), int(total), (last or "")[:10])
        return out

    # ------------------------------------------------------------------ métadonnées
    def complete_metadata(self, content_id: int, meta: Dict[str, Any], album: Optional[str] = None) -> bool:
        """V0.5.0 : complète les champs VIDES (album, année, date, genre, label, n° de piste, ISRC) ;
        rien de ce qui est déjà renseigné n'est remplacé. True si quelque chose a changé."""
        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        with self._write() as conn:
            row = conn.execute(
                "SELECT releaseYear, releaseDate, trackNo, isrc, genre_id, label_id, album_id, artist_id_artist, "
                "COALESCE(informationUpdateCount,0) FROM content WHERE content_id = ?", (content_id,)).fetchone()
            if row is None:
                raise TrackNotFoundError(f"Track not found (id {content_id}).")
            year, date, track_no, isrc, genre_id, label_id, album_id, artist_id, count = row
            wanted = {k: v for k, v in meta.items() if v}
            for key, current in (("year", year), ("release_date", date), ("track_no", track_no), ("isrc", isrc),
                                 ("genre", genre_id), ("label", label_id)):
                if current:
                    wanted.pop(key, None)
            cols = self._meta_columns(conn, wanted)
            album = (album or "").strip()
            if album and not album_id:
                cols["album_id"] = self._get_or_create(
                    conn, "album", "album_id", album,
                    extra_match="AND (artist_id IS ? OR artist_id IS NULL)", extra_params=(artist_id,),
                    insert_sql="INSERT INTO album (name, artist_id, image_id, isComplation, nameForSearch) "
                               "VALUES (?, ?, NULL, 0, ?)",
                    insert_params=(album, artist_id, album))
            if not cols:
                return False
            cols["informationUpdateCount"] = int(count) + 1
            conn.execute(f"UPDATE content SET {', '.join(f'{k} = ?' for k in cols)} WHERE content_id = ?",
                         (*cols.values(), content_id))
        return True

    def update_track_metadata(self, content_id: int, title: Optional[str] = None,
                              artist: Optional[str] = None) -> LibraryTrack:
        """Change le titre et/ou l'artiste d'un son (base + export.pdb). Le fichier n'est pas renommé."""
        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        title = title.strip() if title is not None else None
        artist = artist.strip() if artist is not None else None
        if title is not None and not title:
            raise LibraryError("The title cannot be empty.")
        with self._write() as conn:
            row = conn.execute("SELECT path, COALESCE(informationUpdateCount,0) FROM content WHERE content_id = ?",
                               (content_id,)).fetchone()
            if row is None:
                raise TrackNotFoundError(f"Track not found (id {content_id}).")
            cols: Dict[str, Any] = {}
            if title is not None:
                cols.update(title=title, titleForSearch=title)
            if artist is not None:
                cols["artist_id_artist"] = self._get_or_create(
                    conn, "artist", "artist_id", artist,
                    insert_sql="INSERT INTO artist (name, nameForSearch) VALUES (?, ?)",
                    insert_params=(artist, artist)) if artist else None
            if cols:
                cols["informationUpdateCount"] = int(row[1]) + 1
                conn.execute(f"UPDATE content SET {', '.join(f'{k} = ?' for k in cols)} WHERE content_id = ?",
                             (*cols.values(), content_id))
                path = row[0]
                if path:
                    self._pdb_mark(TRACK_FIELDS, path)
        return self.get_track(content_id)

    # ------------------------------------------------------- 1.2.2 : infos complètes
    def track_details(self, content_id: int) -> Dict[str, Any]:
        """{album, year, genre, label, artwork_path} d'un son (éditeur d'infos, Uniformiser)."""
        has_genre = self._has_table("genre")
        has_label = self._has_table("label")
        rows = self._read(
            "SELECT COALESCE(al.name,''), COALESCE(c.releaseYear,0), "
            + ("COALESCE(g.name,'')" if has_genre else "''") + ", "
            + ("COALESCE(lb.name,'')" if has_label else "''") + ", COALESCE(im.path,'') FROM content c "
            "LEFT JOIN album al ON al.album_id = c.album_id LEFT JOIN image im ON im.image_id = c.image_id "
            + ("LEFT JOIN genre g ON g.genre_id = c.genre_id " if has_genre else "")
            + ("LEFT JOIN label lb ON lb.label_id = c.label_id " if has_label else "")
            + "WHERE c.content_id = ?", (content_id,))
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        album, year, genre, label, art = rows[0]
        return {"album": album, "year": int(year or 0), "genre": genre, "label": label, "artwork_path": art or None}

    def track_genres(self) -> Dict[int, str]:
        """{son: genre} des sons qui en ont un (playlists par genre)."""
        if not self._has_table("genre"):
            return {}
        return {int(cid): name for cid, name in self._read(
            "SELECT c.content_id, g.name FROM content c JOIN genre g ON g.genre_id = c.genre_id "
            "WHERE g.name IS NOT NULL AND g.name <> ''")}

    def _has_table(self, table: str) -> bool:
        cols = {r[1] for r in self._read(f'PRAGMA table_info("{table}")')}
        return {f"{table}_id", "name"} <= cols

    def edit_track_metadata(self, content_id: int, title: Optional[str] = None, artist: Optional[str] = None,
                            album: Optional[str] = None, year: Optional[int] = None, genre: Optional[str] = None,
                            artwork: Any = KEEP) -> LibraryTrack:
        """1.2.2 : modifie les infos d'un son (None = inchangé ; "" ou 0 = effacé). `artwork` : KEEP,
        None (retirer la pochette) ou les octets d'une image. Titre / artiste vont aussi dans
        export.pdb ; genre aussi (1.3.1, C38) ; album, année et pochette dans exportLibrary.db seulement. Le fichier
        audio n'est ni modifié ni renommé."""
        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        with self.batch():
            if title is not None or artist is not None:
                self.update_track_metadata(content_id, title, artist)
            if album is None and year is None and genre is None and artwork is KEEP:
                return self.get_track(content_id)
            jpegs = None
            if artwork is not KEEP and artwork is not None:
                jpegs = _art.make_jpegs(artwork)
                if not jpegs:
                    raise LibraryError("Unreadable image.")
            written: List[Path] = []
            try:
                with self._write() as conn:
                    row = conn.execute("SELECT artist_id_artist, COALESCE(informationUpdateCount,0) FROM content "
                                       "WHERE content_id = ?", (content_id,)).fetchone()
                    if row is None:
                        raise TrackNotFoundError(f"Track not found (id {content_id}).")
                    artist_id, count = row
                    cols: Dict[str, Any] = {}
                    if album is not None:
                        name = album.strip()
                        cols["album_id"] = self._get_or_create(
                            conn, "album", "album_id", name,
                            extra_match="AND (artist_id IS ? OR artist_id IS NULL)", extra_params=(artist_id,),
                            insert_sql="INSERT INTO album (name, artist_id, image_id, isComplation, nameForSearch) "
                                       "VALUES (?, ?, NULL, 0, ?)",
                            insert_params=(name, artist_id, name)) if name else None
                    if year is not None:
                        cols["releaseYear"] = int(year) if year else None
                    if genre is not None:
                        if genre.strip():
                            cols.update(self._meta_columns(conn, {"genre": genre.strip()}))
                        elif self._has_table("genre"):
                            cols["genre_id"] = None
                    if artwork is None:
                        cols["image_id"] = None
                    elif jpegs:
                        number = _art.next_number(self.drive.root, self._known_artwork_paths(conn))
                        written = _art.write(self.drive.root, number, jpegs)
                        cols["image_id"] = conn.execute("INSERT INTO image (path) VALUES (?)",
                                                        (_art.rel_path(number),)).lastrowid
                    if cols:
                        cols["informationUpdateCount"] = int(count) + 1
                        conn.execute(f"UPDATE content SET {', '.join(f'{k} = ?' for k in cols)} WHERE content_id = ?",
                                     (*cols.values(), content_id))
                    if "genre_id" in cols or "label_id" in cols:    # 1.3.1 (C38) : genre recopié dans export.pdb
                        path = conn.execute("SELECT path FROM content WHERE content_id = ?", (content_id,)).fetchone()
                        if path and path[0]:
                            self._pdb_mark(TRACK_FIELDS, path[0])
            except BaseException:
                self._discard(written)
                raise
        return self.get_track(content_id)

    def playlists_of(self, content_ids: Sequence[int]) -> Dict[int, List[int]]:
        """1.2.1 (C11) : {son: [playlists qui le contiennent]}, pour l'outil Doublons."""
        ids = [int(i) for i in content_ids]
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        out: Dict[int, List[int]] = {i: [] for i in ids}
        for cid, pid in self._read(f"SELECT DISTINCT content_id, playlist_id FROM playlist_content WHERE content_id IN ({q})", ids):
            out.setdefault(int(cid), []).append(int(pid))
        return out

    def merge_duplicates(self, keep_id: int, remove_ids: Sequence[int], delete_files: bool = True) -> Tuple[int, int]:
        """Garde `keep_id` et supprime `remove_ids` : dans chaque playlist, le son gardé PREND LA
        PLACE du doublon (même position ; s'il y était déjà, le doublon est simplement retiré).
        Renvoie (sons supprimés, fichiers non effacés)."""
        remove = [c for c in dict.fromkeys(remove_ids) if c != keep_id]
        if not remove:
            return 0, 0
        with self.batch():
            with self._write() as conn:
                if conn.execute("SELECT 1 FROM content WHERE content_id = ?", (keep_id,)).fetchone() is None:
                    raise TrackNotFoundError(f"Track not found (id {keep_id}).")
                q = ",".join("?" * len(remove))
                affected = [r[0] for r in conn.execute(
                    f"SELECT DISTINCT playlist_id FROM playlist_content WHERE content_id IN ({q})", remove)]
                for pid in affected:
                    order = [r[0] for r in conn.execute(
                        "SELECT content_id FROM playlist_content WHERE playlist_id = ? ORDER BY sequenceNo, rowid",
                        (pid,))]
                    new: List[int] = []
                    for cid in order:
                        cid = keep_id if cid in remove else cid
                        if cid not in new:
                            new.append(cid)
                    conn.execute("DELETE FROM playlist_content WHERE playlist_id = ?", (pid,))
                    conn.executemany(
                        "INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (?, ?, ?)",
                        [(pid, cid, i) for i, cid in enumerate(new, start=1)])
                    self._stage_order(conn, pid)
            return self.delete_tracks(remove, delete_files=delete_files)

    # ---------------------------------------------------------------- 1.3.0 (C22) : hot cues
    def track_cues(self, content_id: int) -> List[Any]:
        """Hot cues, boucles et mémoires du son (fichiers d'analyse, comme Rekordbox)."""
        from ...analysis.cues import read_cues

        dat = self.beat_grid(content_id).dat_path
        ext = dat.with_suffix(".EXT")
        try:
            return read_cues(dat.read_bytes(), ext.read_bytes() if ext.is_file() else None)
        except (OSError, ValueError) as exc:
            raise LibraryError(f"Unreadable analysis file: {exc}") from exc

    def save_track_cues(self, content_id: int, cues: Sequence[Any]) -> LibraryTrack:
        """Écrit les cues dans le .DAT / .EXT (Rekordbox ne les met pas dans exportLibrary.db) ;
        fichiers d'origine copiés dans DJSync_Backups/anlz/ avant écriture."""
        from ...analysis.cues import save_to_files

        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        dat = self.beat_grid(content_id).dat_path
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.backup_dir / "anlz" / f"{stamp}-{content_id}-cues"
        backup.mkdir(parents=True, exist_ok=True)
        prune_folders(backup.parent, ANLZ_BACKUPS_KEEP)
        try:
            save_to_files(dat, cues, backup)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        return self.get_track(content_id)

    # ---------------------------------------------------------------- grille de temps
    def analysis_files(self, track: LibraryTrack) -> Tuple[Optional[Path], Optional[Path]]:
        """(.DAT, .EXT) existants du son (None si absents)."""
        if not track.analysis_path:
            return None, None
        dat = self.absolute_path(track.analysis_path)
        ext = dat.with_suffix(".EXT")
        return (dat if dat.is_file() else None), (ext if ext.is_file() else None)

    def beat_grid(self, content_id: int) -> BeatGrid:
        from ...analysis.anlz import read_beats

        rows = self._read("SELECT analysisDataFilePath, COALESCE(length,0), masterDbId FROM content WHERE content_id = ?",
                          (content_id,))
        if not rows:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        anlz, length, master = rows[0]
        if not anlz:
            raise LibraryError("This track is not analysed yet: run the analysis first.")
        dat = self.absolute_path(anlz)
        try:
            beats = read_beats(dat.read_bytes())
        except (OSError, ValueError) as exc:
            raise LibraryError(f"Unreadable analysis file: {exc}") from exc
        if not beats:
            raise LibraryError("This track has no beat grid.")
        return BeatGrid(content_id, beats, int(length) * 1000, dat, master is not None)

    def save_beat_grid(self, content_id: int, beats: Sequence[Tuple[int, int, int]]) -> LibraryTrack:
        """Enregistre une grille corrigée : .DAT réécrit (PQTZ), grille étendue PQT2 retirée des
        .EXT/.2EX, BPM mis à jour dans la base et export.pdb. Les fichiers d'origine sont copiés dans
        DJSync_Backups/anlz/<date>/ avant toute écriture."""
        from ...analysis.anlz import _write_atomic, drop_extended_grid, replace_beats

        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")
        beats = [(int(n), int(t), int(ms)) for n, t, ms in beats]
        if len(beats) < 2 or any(b[2] >= c[2] for b, c in zip(beats, beats[1:])):
            raise LibraryError("Invalid grid (at least two beats, increasing positions).")
        grid = self.beat_grid(content_id)
        files = [grid.dat_path] + [grid.dat_path.with_suffix(s) for s in (".EXT", ".2EX")]
        files = [f for f in files if f.is_file()]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.backup_dir / "anlz" / f"{stamp}-{content_id}"
        backup.mkdir(parents=True, exist_ok=True)
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
        bpmx100 = tempos[len(tempos) // 2]
        try:
            for f, data in new.items():
                _write_atomic(f, data)
            with self._write() as conn:
                row = conn.execute("SELECT path, COALESCE(analysisDataUpdateCount,0) FROM content WHERE content_id = ?",
                                   (content_id,)).fetchone()
                conn.execute("UPDATE content SET bpmx100 = ?, analysisDataUpdateCount = ? WHERE content_id = ?",
                             (bpmx100, int(row[1]) + 1, content_id))
                if row[0]:
                    self._pdb_mark(TRACK_FIELDS, row[0])
        except BaseException:
            for f, data in originals.items():          # retour à l'état d'origine
                try:
                    _write_atomic(f, data)
                except OSError:
                    log.error("Could not restore %s (copy in %s)", f, backup)
            raise
        return self.get_track(content_id)
