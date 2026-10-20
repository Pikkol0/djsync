"""Métadonnées, doublons, statistiques de playlists et grille de temps (V0.2.0).

Toutes les modifications passent par `_write()` (sauvegarde + transaction) puis sont répercutées
dans export.pdb par le miroir (même id de piste : les playlists des platines restent valides).
"""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


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
                    self._stage(lambda db, p=path, t=title, a=artist: db.update_track(p, title=t, artist=a))
        return self.get_track(content_id)

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
                    self._stage(lambda db, p=row[0], b=bpmx100: db.update_track(p, bpmx100=b))
        except BaseException:
            for f, data in originals.items():          # retour à l'état d'origine
                try:
                    _write_atomic(f, data)
                except OSError:
                    log.error("Could not restore %s (copy in %s)", f, backup)
            raise
        return self.get_track(content_id)
