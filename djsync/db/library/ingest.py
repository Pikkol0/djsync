"""Ajout de sons (V1.1-A4) : date au format natif, pochette, analyse BPM/tonalité/ANLZ."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)


class IngestMixin:
    # ------------------------------------------------- analyse, pochette, date (V1.1-A4)
    def _probe_date_style(self, conn: Any) -> None:
        """Modèle de date : un son NATIF (exporté par Rekordbox : masterDbId renseigné, ce que DJSync ne
        fait jamais) ; à défaut n'importe quel son déjà présent ; sinon format complet OneLibrary."""
        if self._date_probed:
            return
        self._date_probed = True
        for where in ("masterDbId IS NOT NULL AND", ""):
            row = conn.execute(
                f"SELECT dateAdded FROM content WHERE {where} dateAdded IS NOT NULL AND dateAdded != '' "
                "ORDER BY content_id DESC LIMIT 1").fetchone()
            if row:
                self._date_sample = str(row[0])
                return

    def now_date(self, conn: Any = None) -> str:
        """« Maintenant » au format des dates d'ajout de CETTE clé."""
        self._probe_date_style(conn if conn is not None else self._db())
        return format_date_like(self._date_sample)

    @staticmethod
    def _native_analysed_bits(conn: Any) -> Optional[int]:
        """Valeur la plus courante de analysedBits chez les sons analysés par Rekordbox (NULL s'il n'y
        en a pas) : on s'aligne sur les sons natifs plutôt que d'inventer une valeur."""
        rows = [r[0] for r in conn.execute(
            "SELECT analysedBits FROM content WHERE masterDbId IS NOT NULL AND analysisDataFilePath IS NOT NULL "
            "AND analysedBits IS NOT NULL LIMIT 500")]
        return Counter(rows).most_common(1)[0][0] if rows else None

    def _prepare_extras(self, file_path: Path, db_path: str, audio: Dict[str, int],
                        analysis: bool = True, cover: bool = True, explicit: bool = False) -> _Extras:
        """Analyse (BPM, grille, tonalité, ANLZ) + pochette, HORS transaction (plusieurs secondes).
        Ne lève jamais : un échec est noté dans `problems` et le son est ajouté sans ce détail."""
        ex = _Extras()
        if (self.analyze or explicit) and analysis:      # explicit : menu Analyse (V0.2.0)
            try:
                from ...analysis import analyze_file, write_anlz   # import tardif : numpy

                ex.analysis = analyze_file(file_path, self.ffmpeg_location)
                if not self.read_only:
                    ex.anlz_path = write_anlz(self.drive.root, db_path, ex.analysis, audio["fileType"],
                                              audio["samplingRate"] or 44100)
                    folder = self.drive.root / ex.anlz_path.lstrip("/")
                    ex.written += [folder, folder.with_suffix(".EXT")]
                log.info("Analyse %s : %.2f BPM, %s (%s), %.1f s", file_path.name, ex.analysis.bpm,
                         ex.analysis.key.name, ex.analysis.key.camelot, ex.analysis.seconds)
            except Exception as exc:  # noqa: BLE001 - FFmpeg absent, fichier exotique… : son ajouté quand même
                log.warning("Analysis failed (%s): %s", file_path.name, exc)
                ex.problems.append(f"analysis: {exc}")
        if self.artwork and cover and self._has_image:
            try:
                from ...audio.covers import extract_embedded_cover

                data = extract_embedded_cover(file_path)
                ex.jpegs = _art.make_jpegs(data) if data else None
            except Exception as exc:  # noqa: BLE001
                log.warning("Unreadable artwork (%s): %s", file_path.name, exc)
                ex.problems.append(f"artwork: {exc}")
        return ex

    @staticmethod
    def _key_style(name: str) -> str:
        return "camelot" if _CAMELOT_NAME.match(name.strip()) else "musical"

    def _key_id_for(self, conn: Any, musical: str) -> Optional[int]:
        """Ligne de la table `key` pour une tonalité détectée (« Am »). Notation : celle demandée, ou en
        « auto » celle déjà majoritaire sur la clé (Camelot si la table est vide) ; une ligne équivalente
        existante dans cette notation est toujours réutilisée (« Am » ≡ « 8A »)."""
        if not self._has_key:
            return None
        code = to_camelot(musical)
        if not code:
            return None
        rows = conn.execute("SELECT key_id, name FROM key WHERE name IS NOT NULL").fetchall()
        style = self.key_notation
        if style not in ("camelot", "musical"):
            styles = Counter(self._key_style(n) for _k, n in rows if to_camelot(n))
            style = styles.most_common(1)[0][0] if styles else "camelot"
        for kid, name in rows:
            if to_camelot(name) == code and self._key_style(name) == style:
                return kid
        wanted = code if style == "camelot" else musical
        for kid, name in rows:                       # même nom, casse différente (colonne UNIQUE)
            if name.strip().casefold() == wanted.casefold():
                return kid
        return conn.execute("INSERT INTO key (name) VALUES (?)", (wanted,)).lastrowid

    def _known_artwork_paths(self, conn: Any) -> List[str]:
        paths = [r[0] for r in conn.execute("SELECT path FROM image WHERE path IS NOT NULL")]
        if self._pdb_enabled():
            try:
                paths += self._pdb_store().load().artwork_paths()
            except PdbError:
                pass
        return paths

    def _store_artwork(self, conn: Any, ex: _Extras, album_id: Optional[int]) -> Optional[int]:
        """Écrit la pochette et sa ligne `image` ; réutilise celle de l'album si elle existe déjà."""
        if not ex.jpegs or not self._has_image:
            return None
        if album_id:
            row = conn.execute(
                "SELECT c.image_id, im.path FROM content c JOIN image im ON im.image_id = c.image_id "
                "WHERE c.album_id = ? AND c.image_id IS NOT NULL LIMIT 1", (album_id,)).fetchone()
            if row and row[1] and self.absolute_path(row[1]).is_file():
                return row[0]
        number = _art.next_number(self.drive.root, self._known_artwork_paths(conn))
        ex.written += _art.write(self.drive.root, number, ex.jpegs)
        return conn.execute("INSERT INTO image (path) VALUES (?)", (_art.rel_path(number),)).lastrowid

    def _extra_columns(self, conn: Any, ex: _Extras, album_id: Optional[int]) -> Dict[str, Any]:
        cols: Dict[str, Any] = {}
        if ex.analysis is not None:
            if ex.analysis.bpm > 0:
                cols["bpmx100"] = ex.analysis.bpmx100
            if ex.analysis.key.name:
                kid = self._key_id_for(conn, ex.analysis.key.name)
                if kid is not None:
                    cols["key_id"] = kid
        if ex.anlz_path:
            cols["analysisDataFilePath"] = ex.anlz_path
            cols["analysedBits"] = self._native_analysed_bits(conn)
        image_id = self._store_artwork(conn, ex, album_id)
        if image_id is not None:
            cols["image_id"] = image_id
        return cols

    @staticmethod
    def _discard(paths: Sequence[Path]) -> None:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------- ajout / analyse
    def add_track(
        self,
        file_path: Path,
        title: str,
        artist: str,
        album: Optional[str] = None,
        source_url: Optional[str] = None,
        playlist_ids: Sequence[int] = (),
    ) -> LibraryTrack:
        """Insère le son (titre, artiste, chemin, date d'ajout) et l'ajoute aux playlists.

        V1.1-A4 : le son est analysé avant insertion (BPM, grille, tonalité, formes d'onde ANLZ) et sa
        pochette intégrée est copiée dans PIONEER/Artwork : il est prêt pour les platines sans passer
        par Rekordbox. `last_problems` liste ce qui n'a pas pu être fait (le son est ajouté quand même).
        Idempotent : si le fichier est déjà référencé, on réutilise l'entrée (complétée si elle n'était
        pas analysée) et on l'ajoute simplement aux playlists demandées.
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise LibraryError(f"File not found: {file_path}")
        try:
            rel = file_path.resolve().relative_to(self.drive.root.resolve())
        except ValueError as exc:
            raise LibraryError(f"The file must be on the drive ({self.drive.root}).") from exc
        db_path = "/" + rel.as_posix()

        title = (title or "").strip() or file_path.stem
        artist = (artist or "").strip()
        album = (album or "").strip() or None
        vid = extract_video_id(source_url or "")
        comment = (f"https://www.youtube.com/watch?v={vid}" if vid
                   else (source_url or "").split("?")[0].split("#")[0])
        audio = self._probe_audio(file_path)
        if self.read_only:
            raise ReadOnlyError("Library opened read-only.")

        with self._lock:
            existing = self._db().execute(
                "SELECT content_id, analysisDataFilePath, image_id FROM content WHERE path = ? COLLATE NOCASE",
                (db_path,)).fetchone()
        # son déjà présent ET déjà analysé (Rekordbox ou DJSync) : on ne réanalyse rien
        ex = self._prepare_extras(file_path, db_path, audio,
                                  analysis=existing is None or not existing[1],
                                  cover=existing is None or existing[2] is None)
        self.last_problems = list(ex.problems)

        try:
            with self._write() as conn:
                for pid in playlist_ids:
                    self._require_playlist(conn, pid, editable=True)

                row = conn.execute(
                    "SELECT content_id, album_id, image_id FROM content WHERE path = ? COLLATE NOCASE",
                    (db_path,)).fetchone()
                if row:
                    content_id = row[0]
                    extra = self._extra_columns(conn, ex, row[1]) if (ex.analysis or ex.jpegs) else {}
                    if row[2] is not None:
                        extra.pop("image_id", None)
                    if extra:
                        conn.execute(
                            f"UPDATE content SET {', '.join(f'{k} = ?' for k in extra)} WHERE content_id = ?",
                            (*extra.values(), content_id))
                else:
                    artist_id = None
                    if artist:
                        artist_id = self._get_or_create(
                            conn, "artist", "artist_id", artist,
                            insert_sql="INSERT INTO artist (name, nameForSearch) VALUES (?, ?)",
                            insert_params=(artist, artist))
                    album_id = None
                    if album:
                        album_id = self._get_or_create(
                            conn, "album", "album_id", album,
                            extra_match="AND (artist_id IS ? OR artist_id IS NULL)", extra_params=(artist_id,),
                            insert_sql="INSERT INTO album (name, artist_id, image_id, isComplation, nameForSearch) "
                                       "VALUES (?, ?, NULL, 0, ?)",
                            insert_params=(album, artist_id, album))
                    added = self.now_date(conn)
                    cols: Dict[str, Any] = {
                        "title": title, "titleForSearch": title, "subtitle": "", "bpmx100": 0,
                        "length": audio["length"], "trackNo": 0, "discNo": 0, "artist_id_artist": artist_id,
                        "artist_id_lyricist": 0, "album_id": album_id, "color_id": 0, "djComment": comment, "rating": 0,
                        "releaseYear": 0, "releaseDate": "", "dateCreated": added, "dateAdded": added,
                        "path": db_path, "fileName": file_path.name, "fileSize": file_path.stat().st_size,
                        "fileType": audio["fileType"], "bitrate": audio["bitrate"],
                        "bitDepth": audio["bitDepth"], "samplingRate": audio["samplingRate"],
                        "isrc": "", "djPlayCount": 0, "isHotCueAutoLoadOn": 1, "isKuvoDeliverStatusOn": 1,
                        "kuvoDeliveryComment": "", "hasModified": 0, "cueUpdateCount": 0,
                        "analysisDataUpdateCount": 0, "informationUpdateCount": 0,
                        # NULL volontaires : masterDbId, masterContentId, contentLink (son absent de la base
                        # PC) et clés étrangères optionnelles (remixer, genre, label). Sans analyse/pochette,
                        # key_id, image_id, analysisDataFilePath, analysedBits restent NULL comme avant.
                        # color_id / artist_id_lyricist = 0 : convention des sons natifs (voir en-tête).
                    }
                    cols.update(self._extra_columns(conn, ex, album_id))
                    content_id = conn.execute(
                        f"INSERT INTO content ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        tuple(cols.values())).lastrowid
                    conn.execute("UPDATE property SET numberOfContents = (SELECT COUNT(*) FROM content)")

                for pid in playlist_ids:
                    self._append(conn, pid, [content_id])
                paths = self._stage_tracks(conn, [content_id])
                for pid in playlist_ids:
                    pl_path = self._pl_path(conn, pid)
                    self._stage(lambda db, p=pl_path, t=paths: db.playlist_add(p, t))
        except BaseException:
            self._discard(ex.written)            # rien en base : pas de fichiers orphelins
            raise
        return self.get_track(content_id)

    def _analysis_job(self, content_id: int, force: bool = False) -> Optional[Tuple[int, _Extras, Any]]:
        """Phase longue (HORS verrou) : analyse + pochette. None si rien à faire."""
        row = self._read("SELECT path, analysisDataFilePath, image_id, masterDbId, album_id, fileType, samplingRate "
                         "FROM content WHERE content_id = ?", (content_id,))
        if not row:
            raise TrackNotFoundError(f"Track not found (id {content_id}).")
        db_path, anlz, image_id, master, album_id, ftype, rate = row[0]
        if master is not None or (anlz and not force):
            self.last_problems = []
            return None
        file_path = self.absolute_path(db_path)
        if not file_path.is_file():
            raise LibraryError(f"File not found: {file_path}")
        ex = self._prepare_extras(file_path, db_path, {"fileType": int(ftype or 0), "samplingRate": int(rate or 44100)},
                                  analysis=force or not anlz, cover=image_id is None, explicit=True)
        self.last_problems = list(ex.problems)
        if ex.analysis is None and not ex.jpegs:
            return None
        return content_id, ex, album_id

    def _apply_analysis(self, job: Tuple[int, _Extras, Any]) -> None:
        """Phase courte (transaction) : colonnes de la base + miroir export.pdb."""
        content_id, ex, album_id = job
        try:
            with self._write() as conn:
                extra = self._extra_columns(conn, ex, album_id)
                if ex.anlz_path:
                    extra["analysisDataUpdateCount"] = (conn.execute(
                        "SELECT COALESCE(analysisDataUpdateCount,0) FROM content WHERE content_id = ?",
                        (content_id,)).fetchone()[0] or 0) + 1
                if extra:
                    conn.execute(f"UPDATE content SET {', '.join(f'{k} = ?' for k in extra)} WHERE content_id = ?",
                                 (*extra.values(), content_id))
                self._stage_tracks(conn, [content_id])
        except BaseException:
            self._discard([p for p in ex.written if "Artwork" in p.as_posix()])
            raise

    def analyze_track(self, content_id: int, force: bool = False) -> LibraryTrack:
        """Analyse (ou réanalyse avec force=True) un son déjà présent : BPM, tonalité, ANLZ, pochette.

        Sans `force`, un son déjà analysé (par Rekordbox ou DJSync) n'est pas modifié. Avec `force`,
        seuls les sons ajoutés par DJSync (masterDbId vide) sont réanalysés : jamais un son natif.
        Toujours exécutée, même si l'analyse à l'ajout est désactivée (demande explicite)."""
        job = self._analysis_job(content_id, force)
        if job is not None:
            self._apply_analysis(job)
        return self.get_track(content_id)

    def analyze_tracks(self, content_ids: Sequence[int], force: bool = False,
                       on_progress: Optional[Callable[[int, int, Optional[LibraryTrack], str], None]] = None,
                       should_stop: Optional[Callable[[], bool]] = None, chunk: int = 8) -> Tuple[int, int, int]:
        """Menu Analyse (V0.2.0) : analyse une liste de sons. Le calcul se fait hors verrou (la
        bibliothèque reste utilisable) ; les écritures sont regroupées par lots de `chunk` sons (une
        sauvegarde et une réécriture d'export.pdb par lot). Renvoie (analysés, ignorés, échecs).
        on_progress(i, total, son, problème) ; should_stop() -> True : arrêt propre après le son en cours."""
        ids = list(dict.fromkeys(content_ids))
        done = skipped = failed = 0
        pending: List[Tuple[int, _Extras, Any]] = []

        def flush() -> None:
            nonlocal done, failed
            if not pending:
                return
            with self.batch():
                for job in pending:
                    try:
                        self._apply_analysis(job)
                        done += 1
                    except LibraryError as exc:
                        log.warning("Analysis not saved (id %s): %s", job[0], exc)
                        failed += 1
            pending.clear()

        for i, cid in enumerate(ids, start=1):
            if should_stop and should_stop():
                break
            problem = ""
            try:
                job = self._analysis_job(cid, force)
                if job is None:
                    skipped += 1
                elif job[1].analysis is None:
                    failed += 1
                    problem = "; ".join(job[1].problems)
                    pending.append(job)            # la pochette est quand même enregistrée
                    done -= 1
                else:
                    pending.append(job)
                    problem = "; ".join(job[1].problems)
            except LibraryError as exc:
                failed += 1
                problem = str(exc)
            if len(pending) >= chunk:
                flush()
            if on_progress:
                try:
                    track = self.get_track(cid)
                except LibraryError:
                    track = None
                on_progress(i, len(ids), track, problem)
        flush()
        return done, skipped, failed

    def unanalysed_tracks(self) -> List[LibraryTrack]:
        """Sons ajoutés par DJSync (avant la V1.1-A4) sans analyse : candidats à `analyze_missing`."""
        return [self._track(r) for r in self._read(
            _track_select(self._has_key) + " WHERE c.analysisDataFilePath IS NULL AND c.masterDbId IS NULL "
            "ORDER BY c.content_id")]

    def analyze_missing(self, on_progress: Optional[Callable[[int, int, LibraryTrack], None]] = None) -> Tuple[int, int]:
        """Analyse tous les sons DJSync non analysés (une sauvegarde, une réécriture d'export.pdb).
        Renvoie (sons analysés, échecs)."""
        todo = self.unanalysed_tracks()
        done = failed = 0
        with self.batch():
            for i, track in enumerate(todo, start=1):
                try:
                    t = self.analyze_track(track.content_id)
                    done += 1 if t.is_analysed else 0
                    failed += 0 if t.is_analysed else 1
                except LibraryError as exc:
                    log.warning("Analysis of \"%s\" failed: %s", track.title, exc)
                    failed += 1
                if on_progress:
                    on_progress(i, len(todo), track)
        return done, failed

