"""Bibliothèque de la clé : lecture, playlists, suppression, export.pdb, analyse, doublons, grille.

Toutes les écritures passent par `_write` (thread « db ») ; la sauvegarde AVANT modification est
faite par la couche DB elle-même. L'analyse a son propre thread (« analysis ») : la bibliothèque
reste utilisable pendant qu'elle tourne.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...db import LibraryError, RekordboxUsbLibrary, UsbDrive
from ...i18n import plural, t
from ...models import LibraryTrack, PlaylistInfo

Callback = Callable[[Any], None]


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


class TaskHandle:
    """Tâche longue annulable (analyse)."""

    def __init__(self, total: int) -> None:
        self.total, self.done = total, 0
        self.cancelled = False
        self.finished = False

    def cancel(self) -> None:
        self.cancelled = True


class LibraryOpsMixin:
    # ------------------------------------------------------------------ lecture
    def load_library(self, ok: Callback, err: Optional[Callback] = None) -> None:
        """ok({"playlists": [...], "tracks": [...], "stats": {playlist_id: PlaylistStats}})."""
        lib = self.library
        if lib is None:
            ok({"playlists": [], "tracks": [], "stats": {}})
            return

        def work() -> Dict[str, Any]:
            return {"playlists": lib.list_playlists(), "tracks": lib.list_tracks(), "stats": lib.playlist_stats()}

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
        drives = list(self.drives)
        if self.drive is not None and all(str(d.root) != str(self.drive.root) for d in drives):
            drives.insert(0, self.drive)
        lib, active = self.library, self.drive

        def work() -> List[DriveSummary]:
            out = []
            for d in drives:
                connected = active is not None and str(d.root) == str(active.root) and lib is not None
                s = DriveSummary(d, connected, has_pdb=(d.db_path.parent / "export.pdb").is_file())
                try:
                    usage = shutil.disk_usage(d.root)
                    s.total, s.free = usage.total, usage.free
                except OSError:
                    pass
                if connected:
                    try:
                        s.tracks = lib.track_count()
                        s.playlists = sum(1 for p in lib.list_playlists() if not p.is_folder)
                        s.unanalysed = len(lib.unanalysed_tracks())
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
            if lib.pdb_state == "stale" and lib.pdb_problem:
                self.message("warn", t("msg.pdb_not_updated", detail=lib.pdb_problem))
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

    def pdb_sync_now(self, ok: Optional[Callback] = None) -> None:
        def done(summary: Any) -> None:
            self.message("ok", t("msg.pdb_synced", tracks=summary.tracks_added, playlists=summary.playlists_added))
            self._emit("library")
            if ok:
                ok(summary)
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return
        self.dispatcher.submit(lib.pdb_catch_up, done, self._on_error, pool="db")

    # ------------------------------------------------------------------ analyse (V0.2.0)
    def unanalysed(self, ok: Callable[[List[LibraryTrack]], None]) -> None:
        lib = self.library
        if lib is None:
            ok([])
            return
        self.dispatcher.submit(lib.unanalysed_tracks, ok, self._on_error, pool="db")

    def analyze(self, content_ids: Sequence[int], force: bool = False,
                on_progress: Optional[Callable[[int, int, Optional[LibraryTrack], str], None]] = None,
                on_done: Optional[Callable[[Any], None]] = None) -> Optional[TaskHandle]:
        """Analyse BPM / grille / tonalité / formes d'onde des sons donnés (thread « analysis »)."""
        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return None
        ids = list(content_ids)
        handle = TaskHandle(len(ids))

        def progress(i: int, total: int, track: Optional[LibraryTrack], problem: str) -> None:
            handle.done = i
            if on_progress:
                self.dispatcher.post(on_progress, i, total, track, problem)

        def work() -> Any:
            return lib.analyze_tracks(ids, force=force, on_progress=progress, should_stop=lambda: handle.cancelled)

        def done(result: Any) -> None:
            handle.finished = True
            ok_n, skipped, failed = result
            text = t("msg.analysis_done", done=ok_n, skipped=skipped, failed=failed)
            self.message("warn" if failed else "ok", text)
            self.service.refresh_library()
            self._emit("library")
            if on_done:
                on_done(result)

        def fail(exc: BaseException) -> None:
            handle.finished = True
            self._on_error(exc)
            if on_done:
                on_done(None)

        self.dispatcher.submit(work, done, fail, pool="analysis")
        return handle

    def analyze_missing(self, ok: Optional[Callback] = None) -> None:
        """Compatibilité V1.1-A4 : analyse tous les sons DJSync non analysés."""
        self.unanalysed(lambda tracks: self.analyze([x.content_id for x in tracks], on_done=ok))

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
            return {"grid": grid, "detail": detail}

        self.dispatcher.submit(work, ok, err or self._on_error, pool="db")

    def save_grid(self, content_id: int, beats: Sequence[Any], ok: Optional[Callback] = None,
                  err: Optional[Callback] = None) -> None:
        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            if err:
                err(exc)

        self._write(lambda lib: lib.save_beat_grid(content_id, beats), ok, t("msg.grid_saved"), fail)

    # -------------------------------------------------------------- doublons, métadonnées
    def find_duplicates(self, ok: Callable[[List[List[LibraryTrack]]], None]) -> None:
        lib = self.library
        if lib is None:
            ok([])
            return

        def work() -> List[List[LibraryTrack]]:
            from ...core.duplicates import find_duplicate_groups

            return find_duplicate_groups(lib.list_tracks())

        self.dispatcher.submit(work, ok, self._on_error, pool="db")

    def update_metadata(self, content_id: int, title: Optional[str], artist: Optional[str],
                        ok: Optional[Callback] = None) -> None:
        self._write(lambda lib: lib.update_track_metadata(content_id, title, artist), ok, t("msg.metadata_saved"))

    def resolve_duplicates(self, keep_id: int, remove_ids: Sequence[int], title: Optional[str] = None,
                           artist: Optional[str] = None, ok: Optional[Callback] = None,
                           err: Optional[Callback] = None) -> None:
        """Garde un son (titre/artiste éventuellement corrigés), supprime les autres de la clé."""
        def run(lib: RekordboxUsbLibrary) -> Any:
            with lib.batch():
                if title is not None or artist is not None:
                    lib.update_track_metadata(keep_id, title, artist)
                return lib.merge_duplicates(keep_id, remove_ids, delete_files=True)

        def done(result: Any) -> None:
            removed, failures = result
            self.message("warn" if failures else "ok", plural("msg.duplicates_merged_one", "msg.duplicates_merged_many",
                                                              removed))
            if ok:
                ok(result)

        def fail(exc: BaseException) -> None:
            self._on_error(exc)
            if err:
                err(exc)

        self._write(run, done, err=fail)
