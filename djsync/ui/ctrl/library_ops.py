"""Bibliothèque de la clé : lecture, playlists, suppression, export.pdb, analyse, doublons, grille.

Toutes les écritures passent par `_write` (thread « db ») ; la sauvegarde AVANT modification est
faite par la couche DB elle-même. L'analyse a son propre thread (« analysis ») : la bibliothèque
reste utilisable pendant qu'elle tourne.
"""
from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...db import LibraryError, RekordboxUsbLibrary, UsbDrive
from ...i18n import plural, t
from ...models import LibraryTrack, PlaylistInfo

Callback = Callable[[Any], None]
log = logging.getLogger(__name__)
FP_FAILURES_LOGGED = 5        # 1.3.0-rc.9 : « No fingerprint » détaillés au journal, ensuite comptés


def pdb_warning(lib: Any, title: str = "") -> str:
    """Avertissement à afficher après une écriture si export.pdb n'a pas suivi ("" sinon). Le cas le plus
    fréquent (table pleine, ajout de pages désactivé) a son propre texte, qui dit quoi faire."""
    if lib.pdb_state != "stale" or not lib.pdb_problem:
        return ""
    if "last page full" in lib.pdb_problem and not lib.pdb_allow_growth:
        return t("msg.pdb_full_track", title=title) if title else t("msg.pdb_full")
    if title:
        return t("msg.pdb_not_updated_track", title=title, detail=lib.pdb_problem)
    return t("msg.pdb_not_updated", detail=lib.pdb_problem)


def existing_parent(path: Any) -> Any:
    """Le dossier lui-même s'il existe, sinon son plus proche parent existant (espace libre)."""
    from pathlib import Path

    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    return p


@dataclass
class DriveSummary:
    """Carte d'une clé sur l'Accueil."""

    drive: UsbDrive
    connected: bool
    total: int = 0
    free: int = 0
    tracks: int = -1           # -1 : inconnu (clé non connectée)
    playlists: int = -1
    unanalysed: int = -1
    has_pdb: bool = False
    is_local: bool = False      # V0.4.0 : bibliothèque Rekordbox de cet ordinateur
    busy: bool = False          # Rekordbox ouvert : lecture seule tant qu'il tourne
    filesystem: str = ""        # 1.3.0 (T01) : FAT32, exFAT, NTFS, HFS+…
    pdb_state: str = ""         # 1.3.0 (T01) : état d'export.pdb de la clé ouverte (ok, stale…)
    pdb_problem: str = ""


class TaskHandle:
    """Tâche longue annulable (analyse)."""

    def __init__(self, total: int) -> None:
        self.total, self.done = total, 0
        self.cancelled = False
        self.finished = False

    def cancel(self) -> None:
        self.cancelled = True


class AnalysisQueue(TaskHandle):
    """V0.2.4 : UNE file d'analyse pour toute l'appli, en arrière-plan (thread « analysis »).

    Ajouter des sons pendant qu'elle tourne les met à la suite (sans doublon) ; la progression est
    publiée par l'évènement « analysis » (barre latérale, vue « À analyser »), la bibliothèque est
    rafraîchie après chaque lot de sons. Aucune fenêtre modale : le reste de l'appli reste utilisable."""

    BATCH = 6

    def __init__(self) -> None:
        super().__init__(0)
        self.finished = True
        self._lock = threading.Lock()
        self.pending: List[int] = []
        self.batch: List[int] = []
        self.forced: set = set()
        self.ids: set = set()            # sons en file ou en cours (pour l'affichage)
        self.current = ""
        self.ok = self.skipped = self.failed = 0
        self.problems: List[str] = []
        self.on_done: List[Callable[[Any], None]] = []
        self.on_progress: List[Callable[[int, int, Optional[LibraryTrack], str], None]] = []

    @property
    def running(self) -> bool:
        return not self.finished

    def add(self, ids: Sequence[int], force: bool) -> int:
        with self._lock:
            new = [i for i in dict.fromkeys(ids) if i not in self.ids]
            self.pending += new
            self.ids.update(new)
            if force:
                self.forced.update(new)
            self.total += len(new)
            return len(new)

    def take(self, size: Optional[int] = None) -> List[int]:
        """Lot suivant (`size` : 1 en mode léger, C65)."""
        n = size or self.BATCH
        with self._lock:
            if self.cancelled:
                self.pending.clear()
            batch, self.pending = self.pending[:n], self.pending[n:]
            # 1.2.1 (C21) : ordre de traitement du lot en cours (forcés après les autres, comme `work`)
            self.batch = [i for i in batch if i not in self.forced] + [i for i in batch if i in self.forced]
            return batch

    def reset(self) -> None:
        with self._lock:
            self.total = self.done = self.ok = self.skipped = self.failed = 0
            self.pending, self.ids, self.forced, self.problems = [], set(), set(), []
            self.batch = []
            self.cancelled, self.current = False, ""
            self.on_done, self.on_progress = [], []

    def cancel(self) -> None:
        self.cancelled = True
        with self._lock:
            self.pending.clear()


class LibraryOpsMixin:
    # ------------------------------------------------------------------ 1.4.0 (C65) : mode léger
    def _light(self) -> bool:
        from ...core.machine import light_active

        return light_active(self.settings)

    def _wait_while_playing(self, q: Any, step: float = 0.5) -> None:
        """Mode léger : l'analyse en arrière-plan attend la fin de la lecture (le son reste fluide)."""
        import time

        from ...audio.player import PLAYING

        while not q.cancelled and getattr(getattr(self, "player", None), "state", None) == PLAYING:
            time.sleep(step)

    # ------------------------------------------------------------------ lecture
    def load_library(self, ok: Callback, err: Optional[Callback] = None) -> None:
        """ok({"playlists": [...], "tracks": [...], "stats": {playlist_id: PlaylistStats}})."""
        lib = self.library
        if lib is None:
            ok({"playlists": [], "tracks": [], "stats": {}})
            return

        def work() -> Dict[str, Any]:
            data = {"playlists": lib.list_playlists(), "tracks": lib.list_tracks(), "stats": {}}
            try:                                        # statistiques : jamais bloquantes
                data["stats"] = lib.playlist_stats()
            except Exception as exc:  # noqa: BLE001
                log.warning("Playlist statistics unavailable: %s", exc, exc_info=exc)
            return data

        def done(data: Dict[str, Any]) -> None:
            if lib is self.library:
                self.playlists = data["playlists"]
                ok(data)

        self.dispatcher.submit(work, done, err or self._on_error, pool="db")

    def fetch_playlists(self, ok: Callback) -> None:
        lib = self.library
        if lib is None:
            ok([])
            return

        def done(playlists: List[PlaylistInfo]) -> None:
            self.playlists = playlists
            ok(playlists)

        self.dispatcher.submit(lib.list_playlists, done, self._on_error, pool="db")

    def playlist_tracks(self, playlist_id: int, ok: Callback) -> None:
        lib = self.library
        if lib is not None:
            self.dispatcher.submit(lambda: lib.get_playlist_tracks(playlist_id), ok, self._on_error, pool="db")

    def drive_summaries(self, ok: Callable[[List[DriveSummary]], None]) -> None:
        """Clés détectées pour l'Accueil : espace libre, contenu (si connectée), export.pdb."""
        drives: List[Any] = list(self.drives)
        if self.local is not None:
            drives.append(self.local)
        if self.drive is not None and all(str(d.db_path) != str(self.drive.db_path) for d in drives):
            drives.insert(0, self.drive)
        lib, active = self.library, self.drive

        rb_open = bool(getattr(self, "_rekordbox_was_running", False))   # rc.5 (B26) : état stable de la veille

        def work() -> List[DriveSummary]:
            out = []
            for d in drives:
                local = bool(getattr(d, "is_local", False))
                connected = active is not None and str(d.db_path) == str(active.db_path) and lib is not None
                s = DriveSummary(d, connected, has_pdb=not local and (d.db_path.parent / "export.pdb").is_file(),
                                 is_local=local, busy=local and rb_open)
                if not local:
                    from ...db.usb import drive_filesystem

                    s.filesystem = drive_filesystem(d.root)
                try:
                    usage = shutil.disk_usage(existing_parent(d.root))
                    s.total, s.free = usage.total, usage.free
                except OSError:
                    pass
                if connected:
                    try:
                        s.tracks = lib.track_count()
                        s.playlists = sum(1 for p in lib.list_playlists() if not p.is_folder)
                        s.unanalysed = len(lib.unanalysed_tracks())
                        s.pdb_state = str(getattr(lib, "pdb_state", "") or "")
                        s.pdb_problem = str(getattr(lib, "pdb_problem", "") or "")
                    except LibraryError:
                        pass
                out.append(s)
            return out

        self.dispatcher.submit(work, ok, self._on_error, pool="db")

    # -------------------------------------------------------- bibliothèque (écriture)
    def _write(self, fn: Callable[[RekordboxUsbLibrary], Any], ok: Optional[Callback] = None,
               success: str = "", err: Optional[Callback] = None) -> None:
        """Exécute une écriture dans le thread DB puis rafraîchit les vues et les doublons."""
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return

        def work() -> Any:
            result = fn(lib)
            self.service.refresh_library()
            return result

        def done(result: Any) -> None:
            warning = pdb_warning(lib)
            if warning:
                self.message("warn", warning)
            elif success:
                self.message("ok", success)
            self._emit("library")
            if ok:
                ok(result)

        self.dispatcher.submit(work, done, err or self._on_error, pool="db")

    def create_playlist(self, name: str, parent_id: int = 0, ok: Optional[Callback] = None,
                        err: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.create_playlist(name, parent_id), ok, t("msg.playlist_created", name=name.strip()), err)

    def create_folder(self, name: str, parent_id: int = 0, ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.create_folder(name, parent_id), ok, t("msg.folder_created", name=name.strip()))

    def rename_playlist(self, playlist_id: int, name: str, ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.rename_playlist(playlist_id, name), ok, t("msg.playlist_renamed"))

    def delete_playlist(self, playlist_id: int, ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.delete_playlist(playlist_id), ok, t("msg.playlist_deleted"))

    def add_to_playlists(self, content_ids: Sequence[int], playlist_ids: Sequence[int]) -> None:
        def run(lib: RekordboxUsbLibrary) -> int:
            with lib.batch():
                return sum(lib.add_to_playlist(pid, content_ids) for pid in playlist_ids)
        self._write(run, lambda n: None, plural("msg.added_to_playlists_one", "msg.added_to_playlists_many",
                                                len(content_ids)))

    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        self._write(lambda lib: lib.remove_from_playlist(playlist_id, content_ids), None, t("msg.removed_from_playlist"))

    def move_tracks(self, content_ids: Sequence[int], from_id: int, to_id: int) -> None:
        self._write(lambda lib: lib.move_tracks(content_ids, from_id, to_id), None, t("msg.tracks_moved"))

    def save_order(self, playlist_id: int, content_ids: Sequence[int], ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.set_playlist_order(playlist_id, content_ids), ok, t("msg.order_saved"))

    def delete_tracks(self, content_ids: Sequence[int], delete_files: bool = True) -> None:
        def done(result: Any) -> None:
            removed, failures = result
            text = plural("msg.deleted_one", "msg.deleted_many", removed)
            if failures:
                text += " " + t("msg.files_not_deleted", n=failures)
            self.message("warn" if failures else "ok", text)

        self._write(lambda lib: lib.delete_tracks(content_ids, delete_files), done)

    # ------------------------------------------------------------ export.pdb (anciennes platines)
    def pdb_status(self, ok: Callback) -> None:
        lib = self.library
        if lib is not None:
            self.dispatcher.submit(lib.pdb_status, ok, self._on_error, pool="db")

    def pdb_sync_now(self, ok: Optional[Callback] = None, failed: Optional[Callback] = None) -> None:
        """Paramètres ▸ Synchroniser maintenant, et 1.3.0-rc.3 (C36) bouton de l'Accueil : réconciliation
        complète d'export.pdb. L'Accueil est redessiné dans tous les cas (réussite, écart restant, échec)."""
        lib = self.library

        def done(summary: Any) -> None:
            if getattr(lib, "pdb_state", "ok") == "stale":
                self.message("warn", t("msg.pdb_left", detail=getattr(lib, "pdb_problem", "") or "?"))
            else:
                self.message("ok", t("msg.pdb_up_to_date"))
            self._emit("library")
            if ok:
                ok(summary)

        def error(exc: BaseException) -> None:
            text = str(exc)
            if "another program" in text or "Permission denied" in text:
                self.message("warn", t("msg.pdb_locked"))
            else:
                self._on_error(exc)
            self._emit("library")
            if failed:
                failed(exc)

        if lib is None:
            self.message("error", t("msg.no_drive"))
            return
        self.dispatcher.submit(lib.pdb_catch_up, done, error, pool="db")

    # ------------------------------------------------------------------ analyse (V0.2.0)
    def orphan_ids(self, content_ids: Sequence[int], ok: Callable[[set], None]) -> None:
        """1.3.2 (C56) : sons qui ne sont dans aucune playlist (les playlists intelligentes ne comptent pas)."""
        ids = [int(i) for i in content_ids]
        self.playlist_membership(ids, lambda found: ok({cid for cid in ids if not found.get(cid)}))

    def playlist_membership(self, content_ids: Sequence[int], ok: Callable[[Dict[int, List[int]]], None]) -> None:
        """1.4.0 (C103) : playlists (identifiants) de chaque son, par lots de 800, hors du fil de l'interface."""
        lib = self.library
        ids = [int(i) for i in content_ids]
        if lib is None or not ids or not hasattr(lib, "playlists_of"):
            ok({})
            return

        def work() -> Dict[int, List[int]]:
            out: Dict[int, List[int]] = {}
            for k in range(0, len(ids), 800):
                found = lib.playlists_of(ids[k:k + 800])
                out.update({int(cid): list(v) for cid, v in found.items() if v})
            return out

        self.dispatcher.submit(work, ok, lambda exc: log.info("Playlist membership not read: %s", exc), pool="db")

    def unanalysed(self, ok: Callable[[List[LibraryTrack]], None]) -> None:
        lib = self.library
        if lib is None:
            ok([])
            return
        self.dispatcher.submit(lib.unanalysed_tracks, ok, self._on_error, pool="db")

    @property
    def analysis(self) -> AnalysisQueue:
        if "_analysis" not in self.__dict__:
            self._analysis = AnalysisQueue()
        return self._analysis

    @property
    def analysis_results(self) -> Dict[int, str]:
        """content_id -> « ok » / « failed » : sons analysés pendant cette session."""
        if "_analysis_results" not in self.__dict__:
            self._analysis_results: Dict[int, str] = {}
        return self._analysis_results

    def analyze(self, content_ids: Sequence[int], force: bool = False,
                on_progress: Optional[Callable[[int, int, Optional[LibraryTrack], str], None]] = None,
                on_done: Optional[Callable[[Any], None]] = None, quiet: bool = False) -> Optional[TaskHandle]:
        """Met des sons dans la file d'analyse (BPM / grille / tonalité / formes d'onde) et la lance si
        elle ne tourne pas. Renvoie la file (annulable). Les sons analysés par Rekordbox sont ignorés."""
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return None
        q = self.analysis
        if not q.running:
            q.reset()
        if on_done:
            q.on_done.append(on_done)
        if on_progress:
            q.on_progress.append(on_progress)
        added = q.add(content_ids, force)
        if q.running:
            if added and not quiet:       # quiet : analyse après téléchargement (C32), pas de message par son
                self.message("info", plural("msg.analysis_queued_one", "msg.analysis_queued_many", added))
            self._emit("analysis")
            return q
        q.finished = False
        self._emit("analysis")

        def progress(_i: int, _total: int, track: Optional[LibraryTrack], problem: str) -> None:
            q.done += 1
            if track is not None:
                q.current = track.display_name
            if problem:
                q.problems.append(f"{track.display_name if track else '?'}: {problem}"[:160])
            self.dispatcher.post(self._analysis_progress, q.done, q.total, track, problem)

        def work() -> Any:
            while True:
                light = self._light()
                if light:                    # 1.4.0 (C65) : mode léger, pas d'analyse pendant la lecture
                    self._wait_while_playing(q)
                batch = q.take(1 if light else None)
                if not batch or q.cancelled:
                    break
                normal = [i for i in batch if i not in q.forced]
                forced = [i for i in batch if i in q.forced]
                for ids, force_it in ((normal, False), (forced, True)):
                    if ids and not q.cancelled:
                        a, sk, fl = lib.analyze_tracks(ids, force=force_it, on_progress=progress,
                                                       should_stop=lambda: q.cancelled)
                        q.ok, q.skipped, q.failed = q.ok + a, q.skipped + sk, q.failed + fl
                self.dispatcher.post(self._analysis_batch_saved, lib)
            return q.ok, q.skipped, q.failed

        def finish(result: Any) -> None:
            q.finished, q.current = True, ""
            if self.library is lib:
                self.service.refresh_library()
            if result is not None:
                ok_n, skipped, failed = result
                text = t("msg.analysis_done", done=ok_n, skipped=skipped, failed=failed)
                if q.cancelled:
                    text = t("msg.analysis_stopped") + "  " + text
                warning = pdb_warning(lib)
                self.message("warn" if (failed or warning) else "ok", warning or text)
            self._emit("library")
            self._emit("analysis")
            for cb in list(q.on_done):
                try:
                    cb(result)
                except Exception:  # noqa: BLE001
                    log.exception("analysis callback")

        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            finish(None)

        self.dispatcher.submit(work, finish, fail, pool="analysis")
        return q

    def _analysis_progress(self, i: int, total: int, track: Optional[LibraryTrack], problem: str) -> None:
        if track is not None:          # état par son pour Téléchargements & analyse (toute la session)
            self.analysis_results[track.content_id] = "failed" if problem else "ok"
        for cb in list(self.analysis.on_progress):
            try:
                cb(i, total, track, problem)
            except Exception:  # noqa: BLE001 - fenêtre fermée…
                log.debug("analysis progress callback", exc_info=True)
        self._emit("analysis")

    def _analysis_batch_saved(self, lib: Any) -> None:
        """Un lot vient d'être enregistré : la bibliothèque affichée suit (pastilles, BPM, « À analyser »)."""
        if self.library is lib and self.analysis.running:
            self.service.refresh_library()
            self._emit("library")

    def stop_analysis(self) -> None:
        if self.analysis.running:
            self.analysis.cancel()
            self.message("info", t("analysis.stopping"))
            self._emit("analysis")

    def analyze_missing(self, ok: Optional[Callback] = None) -> None:
        """Compatibilité V1.1-A4 : analyse tous les sons DJSync non analysés."""
        self.unanalysed(lambda tracks: self.analyze([x.content_id for x in tracks], on_done=ok))

    # -------------------------------------------------------- son en cours (lecteur, V0.2.4)
    def current_library_id(self) -> Optional[int]:
        """content_id du son en cours de lecture s'il est sur la clé (son de la bibliothèque, ou
        téléchargement terminé et ajouté), sinon None."""
        item = self.current_item
        if item is None or self.library is None:
            return None
        if item.kind == "library":
            return item.item.content_id
        if item.kind == "job":
            return getattr(item.item, "content_id", None)
        return None

    def fresh_track(self, content_id: int, ok: Callable[[LibraryTrack], None]) -> None:
        """Relit un son dans la base (état d'analyse, BPM et tonalité à jour)."""
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return
        self.dispatcher.submit(lambda: lib.get_track(content_id), ok, self._on_error, pool="db")

    # -------------------------------------------------------------- grille de temps
    def load_grid(self, content_id: int, ok: Callback, err: Optional[Callback] = None) -> None:
        """ok({"grid": BeatGrid, "detail": [(hauteur, couleur)] à 150 colonnes/s})."""
        lib = self.library
        if lib is None:
            return

        def work() -> Dict[str, Any]:
            from ...analysis.anlz import read_detail

            grid = lib.beat_grid(content_id)
            ext = grid.dat_path.with_suffix(".EXT")
            try:
                detail = read_detail(ext.read_bytes()) if ext.is_file() else []
            except (OSError, ValueError):
                detail = []
            band = None                                # 1.3.0-rc.3 (B21) : 3 bandes de Rekordbox (.2EX)
            two = grid.dat_path.with_suffix(".2EX")
            try:
                if two.is_file():
                    from ...analysis.anlz import read_band_detail

                    band = read_band_detail(two.read_bytes())
            except (OSError, ValueError):
                band = None
            try:                                       # 1.3.0 (C22) : hot cues, boucles et mémoires
                cues = list(lib.track_cues(content_id))
            except Exception as exc:  # noqa: BLE001 - la grille reste éditable sans les cues
                log.info("Cues not read for %s: %s", content_id, exc)
                cues = []
            return {"grid": grid, "detail": detail, "cues": cues, "band": band}

        self.dispatcher.submit(work, ok, err or self._on_error, pool="db")

    def load_grid_wave(self, track: LibraryTrack, ok: Callback) -> None:
        """Forme d'onde 3 bandes fine de l'éditeur de grille, calculée depuis le fichier audio (≈ 1 à
        2 s la première fois, puis lue dans le cache des réglages). ok(None) si impossible : l'éditeur
        affiche alors la forme d'onde des fichiers d'analyse."""
        lib = self.library
        if lib is None:
            return

        def work() -> Any:
            from ...analysis.waveform import cached_band_wave
            from ...settings import settings_dir

            return cached_band_wave(lib.absolute_path(track), self.settings.ffmpeg_location or None,
                                    settings_dir() / "cache" / "grid")

        def failed(exc: BaseException) -> None:
            log.info("Grid waveform not computed: %s", exc)
            ok(None)

        self.dispatcher.submit(work, ok, failed, pool="match")

    def save_grid(self, content_id: int, beats: Sequence[Any], ok: Optional[Callback] = None,
                  err: Optional[Callback] = None) -> None:
        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            if err:
                err(exc)

        self._write(lambda lib: lib.save_beat_grid(content_id, beats), ok, t("msg.grid_saved"), fail)

    def save_grid_and_cues(self, content_id: int, beats: Optional[Sequence[Any]], cues: Optional[Sequence[Any]],
                           ok: Optional[Callback] = None, err: Optional[Callback] = None) -> None:
        """1.3.0 (C22) : enregistre la grille et / ou les cues de la page « Grille et cues » (None = inchangé)."""
        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            if err:
                err(exc)

        def work(lib: Any) -> Any:
            out = None
            if beats is not None:
                out = lib.save_beat_grid(content_id, beats)
            if cues is not None:
                out = lib.save_track_cues(content_id, cues)
            return out

        msg = t("msg.cues_saved") if beats is None else t("msg.grid_saved")
        self._write(work, ok, msg, fail)

    def _carry_cues(self, lib: Any, src_id: int, dst_id: int) -> Any:
        """1.3.0 (C13) : cues de `src_id` recalés sur `dst_id` (voir core.duplicates.carry_cues)."""
        from ...core.duplicates import carry_cues

        return carry_cues(lib, src_id, dst_id, lambda x: self._fingerprint(lib, x))

    # -------------------------------------------------------------- doublons, métadonnées
    @property
    def duplicate_ignores(self) -> Any:
        """1.3.0-rc.5 (C62) : mémoire des « pas un doublon »."""
        if getattr(self, "_dup_ignores", None) is None:
            from ...core.dup_ignore import DuplicateIgnores

            self._dup_ignores = DuplicateIgnores()
        return self._dup_ignores

    def find_duplicates(self, ok: Callable[[List[List[LibraryTrack]]], None],
                        progress: Optional[Callable[[int, int], None]] = None, full: bool = False) -> None:
        """Groupes par le titre, tout de suite (1.3.0-rc.5, C63 : avant, l'empreinte audio de TOUS les sons
        était calculée avant d'afficher quoi que ce soit). Le son de chaque groupe est vérifié ensuite,
        groupe par groupe (`refine_duplicate_group`). Les sons déclarés « pas un doublon » ne sont plus
        regroupés, sauf pour une détection complète (`full`)."""
        lib = self.library
        if lib is None:
            ok([])
            return
        ignored = set() if full else self.duplicate_ignores.pairs()

        def work() -> List[List[LibraryTrack]]:
            from ...core.duplicates import find_duplicate_groups

            self.duplicate_matches = {}
            tracks = lib.list_tracks()
            if progress is not None:                           # 1.3.2 (C84) : nombre de sons comparés
                self.dispatcher.post(progress, 0, len(tracks))
            return find_duplicate_groups(tracks, ignored=ignored)

        self.dispatcher.submit(work, ok, self._on_error, pool="match")

    def refine_duplicate_group(self, group: List[LibraryTrack], ok: Callable[[List[List[LibraryTrack]]], None]) -> None:
        """1.3.0 (B02) : le titre propose, le son décide, pour UN groupe : renvoie ses sous-groupes
        (souvent le groupe lui-même ; [] si aucun son n'est le même). Empreintes en cache disque."""
        lib = self.library
        if lib is None or not getattr(self.settings, "audio_duplicates", True):
            ok([group])
            return

        def work() -> List[List[LibraryTrack]]:
            from ...core.duplicates import refine_by_audio

            groups, matches = refine_by_audio([group], lambda x: self._fingerprint(lib, x))
            if not isinstance(getattr(self, "duplicate_matches", None), dict):
                self.duplicate_matches = {}
            self.duplicate_matches.update(matches)
            return groups

        self.dispatcher.submit(work, ok, lambda exc: (log.info("Audio check: %s", exc), ok([group])), pool="match")

    def _fingerprint(self, lib: Any, track: LibraryTrack) -> Any:
        from ...analysis.fingerprint import file_fingerprint
        from ...settings import settings_dir

        try:
            return file_fingerprint(lib.absolute_path(track), self.settings.ffmpeg_location or None,
                                    settings_dir() / "cache" / "fp")
        except Exception as exc:  # noqa: BLE001 - illisible : le son reste dans son groupe, sans verdict
            # 1.3.0-rc.9 : les 5 premiers au journal, puis un compte tous les 100. Avant, une ligne par son
            # (sons Apple Music, clé absente) : des centaines de lignes qui noyaient la fin du journal envoyé.
            n = self.__dict__["_fp_failures"] = self.__dict__.get("_fp_failures", 0) + 1
            if n <= FP_FAILURES_LOGGED:
                log.info("No fingerprint for %s: %s", track.title, exc)
                if n == FP_FAILURES_LOGGED:
                    log.info("No fingerprint: further failures are only counted")
            elif n % 100 == 0:
                log.info("No fingerprint for %d sounds so far (latest: %s: %s)", n, track.title, exc)
            return None

    def load_group_cues(self, tracks: Sequence[LibraryTrack], ok: Callback) -> None:
        """1.3.0 (C13) : {content_id: [cues]} des versions d'un groupe de doublons ([] si non analysé)."""
        lib = self.library
        if lib is None:
            return

        def work() -> Dict[int, List[Any]]:
            out: Dict[int, List[Any]] = {}
            for x in tracks:
                try:
                    out[x.content_id] = list(lib.track_cues(x.content_id))
                except Exception:  # noqa: BLE001 - pas analysé
                    out[x.content_id] = []
            return out

        self.dispatcher.submit(work, ok, lambda exc: ok({}), pool="db")

    def analysis_current_id(self) -> Optional[int]:
        """1.2.1 (C21) : son en cours d'analyse (le premier du lot pas encore traité), ou None."""
        q = self.analysis
        if not q.running:
            return None
        return next((i for i in list(q.batch) if i not in self.analysis_results), None)

    def track_playlists(self, content_ids: Sequence[int], ok: Callable[[Dict[int, List[str]]], None]) -> None:
        """1.2.1 (C11) : {son: [noms des playlists qui le contiennent]} (outil Doublons)."""
        lib = self.library
        if lib is None or not hasattr(lib, "playlists_of"):
            ok({})
            return
        names = {p.playlist_id: p.name for p in self.playlists}

        def work() -> Dict[int, List[str]]:
            found = lib.playlists_of(content_ids)
            return {cid: sorted({names.get(pid, "?") for pid in pids}, key=str.lower) for cid, pids in found.items()}

        self.dispatcher.submit(work, ok, lambda exc: log.info("Playlists of tracks: %s", exc), pool="db")

    def update_metadata(self, content_id: int, title: Optional[str], artist: Optional[str],
                        ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.update_track_metadata(content_id, title, artist), ok, t("msg.metadata_saved"))

    # ------------------------------------------------------------ 1.3.2 (C82) : fusion différée, « Annuler »
    def schedule_duplicates_merge(self, keep_id: int, remove_ids: Sequence[int], title: Optional[str] = None,
                                  artist: Optional[str] = None, cues_from: Optional[int] = None,
                                  delay_s: float = 10.0, ok: Optional[Callback] = None,
                                  err: Optional[Callback] = None) -> int:
        """La fusion ne s'écrit qu'après `delay_s` secondes : jusque-là rien ne change sur la clé et
        `cancel_merge` l'annule. Fermeture, changement de clé, éjection : appliquée tout de suite."""
        from PySide6.QtCore import QTimer

        pending = self.__dict__.setdefault("pending_merges", {})
        self._merge_seq = getattr(self, "_merge_seq", 0) + 1
        token = self._merge_seq
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._run_pending_merge(token))
        pending[token] = {"timer": timer, "lib": self.library,
                          "args": (keep_id, list(remove_ids), title, artist, ok, err, cues_from)}
        timer.start(int(max(0.0, delay_s) * 1000))
        return token

    def cancel_merge(self, token: int) -> bool:
        job = self.__dict__.get("pending_merges", {}).pop(token, None)
        if job is None:
            return False
        job["timer"].stop()
        return True

    def _run_pending_merge(self, token: int) -> None:
        job = self.__dict__.get("pending_merges", {}).pop(token, None)
        if job is None:
            return
        job["timer"].stop()
        if job["lib"] is not self.library:                 # clé changée entre-temps : déjà appliquée ou perdue
            return
        self.resolve_duplicates(*job["args"][:4], ok=job["args"][4], err=job["args"][5], cues_from=job["args"][6])

    def flush_merges(self) -> int:
        """Applique tout de suite, dans ce fil, les fusions en attente (fermeture, changement de clé)."""
        pending = self.__dict__.get("pending_merges", {})
        n = 0
        for token in list(pending):
            job = pending.pop(token)
            job["timer"].stop()
            lib = job["lib"]
            if lib is None or lib is not self.library:
                log.warning("Pending duplicate merge dropped: the library changed")
                continue
            keep_id, remove_ids, title, artist, _ok, _err, cues_from = job["args"]
            try:
                self._merge_job(keep_id, remove_ids, title, artist, cues_from, {})(lib)
                n += 1
            except Exception as exc:  # noqa: BLE001 - on ferme quand même
                log.warning("Pending duplicate merge failed: %s", exc)
        if n:
            try:
                self.service.refresh_library()
            except Exception:  # noqa: BLE001
                pass
        return n

    def _merge_job(self, keep_id: int, remove_ids: Sequence[int], title: Optional[str], artist: Optional[str],
                   cues_from: Optional[int], carried: Dict[str, int]) -> Callable[[Any], Any]:
        def run(lib: RekordboxUsbLibrary) -> Any:
            moved = None
            if cues_from is not None and int(cues_from) != int(keep_id):
                moved = self._carry_cues(lib, int(cues_from), int(keep_id))       # avant la suppression
            with lib.batch():
                if title is not None or artist is not None:
                    lib.update_track_metadata(keep_id, title, artist)
                result = lib.merge_duplicates(keep_id, remove_ids, delete_files=True)
            if moved is not None:
                cues, lost = moved
                lib.save_track_cues(keep_id, cues)
                carried.update(n=len(cues), lost=lost)
            return result
        return run

    def resolve_duplicates(self, keep_id: int, remove_ids: Sequence[int], title: Optional[str] = None,
                           artist: Optional[str] = None, ok: Optional[Callback] = None,
                           err: Optional[Callback] = None, cues_from: Optional[int] = None) -> None:
        """Garde un son (titre/artiste éventuellement corrigés), supprime les autres de la clé."""
        carried: Dict[str, int] = {}
        run = self._merge_job(keep_id, remove_ids, title, artist, cues_from, carried)

        def done(result: Any) -> None:
            removed, failures = result
            text = plural("msg.duplicates_merged_one", "msg.duplicates_merged_many", removed)
            if carried:
                text += " " + (t("msg.cues_carried_lost", n=carried["n"], lost=carried["lost"]) if carried["lost"]
                               else t("msg.cues_carried", n=carried["n"]))
            self.message("warn" if failures or carried.get("lost") else "ok", text)
            if ok:
                ok(result)

        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            if err:
                err(exc)

        self._write(run, done, err=fail)
