"""Ajout de fichiers de l'ordinateur (1.4.0, C26 sens A) : bouton « Ajouter des fichiers… », glisser-
déposer, et (C10.3) dossier surveillé. Le travail lourd est dans `core.importer`."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from ...i18n import plural, t

log = logging.getLogger(__name__)

# 1.4.0-rc.5 (C160) : anciens noms de la playlist du dossier surveillé, repris et renommés
OLD_WATCH_PLAYLISTS = ("Importés", "Imported")


class ImportsMixin:
    def import_files(self, paths: Sequence[Any], playlist_ids: Sequence[int] = (),
                     ok: Optional[Callable[[Any], None]] = None, quiet: bool = False,
                     playlist_name: str = "", watched_from: str = "") -> bool:
        """Ajoute les fichiers (ou dossiers) à la bibliothèque ouverte, dans le fil « db ». Les sons
        ajoutés sont analysés ensuite si le réglage « analyser après téléchargement » est coché."""
        from ...core import importer

        lib = self.library
        if lib is None:
            self.message("error", t("msg.no_drive"))
            return False
        files = importer.collect(paths)
        if not files:
            if not quiet:
                self.message("info", t("import_files.none"))
            return False
        pids = list(playlist_ids)
        if not quiet:
            self.message("info", plural("import_files.start_one", "import_files.start_many", len(files)))

        def progress(i: int, n: int) -> None:
            self.dispatcher.post(self._emit, "import_progress", i, n)

        def work() -> Any:
            if playlist_name:                                 # dossier surveillé : sa playlist
                pids.append(self._watch_playlist(lib, playlist_name))
            fmt = "" if self.is_local else (self.settings.player_format or "")
            report = importer.import_files(lib, files, pids, progress, player_format=fmt,
                                           ffmpeg=self.settings.ffmpeg_location or None)
            self.service.refresh_library()
            return report

        def done(report: Any) -> None:
            self._importing = False
            if watched_from:                                  # 1.4.0-rc.5 (C160)
                self._watched_done(report, lib, watched_from)
            self._emit("library")
            self._emit("import_progress", 0, 0)
            self._import_done(report, lib, quiet)
            if ok:
                ok(report)

        def failed(exc: BaseException) -> None:
            self._importing = False
            self._emit("import_progress", 0, 0)
            self._on_error(exc)

        self._importing = True
        self.dispatcher.submit(work, done, failed, pool="db")
        return True

    # ------------------------------------------------------------- 1.4.0 (C10.3) : dossier surveillé
    def watch_tick(self) -> None:
        """Appelé toutes les quelques secondes par la fenêtre : importe les fichiers prêts du dossier
        surveillé dans la bibliothèque ouverte (rien si aucune n'est ouverte ou si un import tourne)."""
        from ...core.watcher import FolderWatch, same_folder

        folder = (getattr(self.settings, "watch_folder", "") or "").strip()
        skip = ("" if not folder else "no library open" if self.library is None
                else "import running" if getattr(self, "_importing", False)
                else "busy" if getattr(self, "_watch_busy", False) else "")
        if not folder or skip:
            if skip and skip != getattr(self, "_watch_skip", ""):      # 1.4.0-rc.4 (B77) : raison notée
                log.info("Watched folder skipped: %s", skip)
            self._watch_skip = skip
            return
        self._watch_skip = ""
        w = getattr(self, "_watch", None)
        # 1.4.0-rc.4 (B77) : sous Windows, le réglage garde « C:/… » et Path donne « C:\… » : la
        # comparaison en texte recréait le surveillant à chaque passage, qui oubliait tout.
        if w is None or not same_folder(w.folder, folder):
            w = self._watch = FolderWatch(Path(folder))
            log.info("Watching folder %s", w.folder)
        self._watch_busy = True

        def work() -> List[Path]:
            moved = []
            for p in w.stable_files():
                try:
                    moved.append(w.take(p))
                except OSError as exc:
                    log.warning("Watched file not taken (%s): %s", p, exc)
            return moved

        def done(moved: List[Path]) -> None:
            self._watch_busy = False
            seen = (len(w.last_seen), len(moved))
            if seen != getattr(self, "_watch_counts", None):
                self._watch_counts = seen
                log.info("Watched folder: %d file(s) seen, %d taken", *seen)
            if moved:
                name = t("watch.playlist") if self.settings.watch_playlist else ""
                self.message("info", plural("watch.found_one", "watch.found_many", len(moved)))
                self.import_files([str(p) for p in moved], quiet=True, playlist_name=name, watched_from=str(w.folder))

        def failed(exc: BaseException) -> None:
            self._watch_busy = False
            log.warning("Watched folder: %s", exc)

        self.dispatcher.submit(work, done, failed, pool="watch")   # 1.4.0-rc.4 (B77) : jamais derrière les outils

    # ------------------------------------------------------------- 1.4.0-rc.5 (C160)
    @staticmethod
    def _watch_playlist(lib: Any, name: str) -> int:
        """Playlist du dossier surveillé (fil « db ») : la reprend, ou renomme l'ancienne « Importés »,
        ou la crée."""
        playlists = [p for p in lib.list_playlists() if p.is_editable]
        found = next((p for p in playlists if p.name == name), None)
        if found is None:
            old = next((p for p in playlists if p.name in OLD_WATCH_PLAYLISTS and p.name != name), None)
            if old is not None:
                lib.rename_playlist(old.playlist_id, name)
                log.info("Watched folder playlist renamed: %r -> %r", old.name, name)
                return old.playlist_id
            return lib.create_playlist(name).playlist_id
        return found.playlist_id

    def _watched_done(self, report: Any, lib: Any, folder: str) -> None:
        """Retient les sons arrivés par le dossier surveillé (colonne Source) ; au tout premier, un message
        avec un lien vers la playlist."""
        from datetime import date

        from ...core import watched

        files = []
        for x in report.added:
            name = str(getattr(x, "path", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
            size = int(getattr(x, "file_size", 0) or 0)
            if not size:
                try:
                    size = lib.absolute_path(x).stat().st_size
                except (OSError, AttributeError, TypeError):
                    size = 0
            files.append((name, size))
        watched.record(files, folder, date.today().isoformat())
        if report.added and not self.settings.watch_first_done:
            self.settings.watch_first_done = True
            self.save_settings_quiet()
            self.message("ok", plural("watch.first_one", "watch.first_many", len(report.added)))
            if self.settings.watch_playlist:
                self._emit("message_action", t("watch.open_playlist"),
                           lambda: self._emit("open_playlist_named", t("watch.playlist")))

    def _import_done(self, report: Any, lib: Any, quiet: bool) -> None:
        added = len(report.added)
        parts: List[str] = []
        if added:
            parts.append(plural("import_files.added_one", "import_files.added_many", added))
        if report.already:
            parts.append(plural("import_files.already_one", "import_files.already_many", len(report.already)))
        if report.failed:
            parts.append(plural("import_files.failed_one", "import_files.failed_many", len(report.failed))
                         + " " + t("import_files.failed_detail", name=report.failed[0][0].name, why=report.failed[0][1]))
        if parts and not (quiet and not added and not report.failed):
            self.message("warn" if report.failed else "ok", " · ".join(parts))
        if report.duplicates:
            self._emit("message_action", t("import_files.see_duplicates", n=len(report.duplicates)),
                       lambda: self._emit("open_diagnostic", "dup"))
        if added and lib is self.library:
            s = self.settings
            if s.analyze_after_download_local if self.is_local else s.analyze_after_download_usb:
                self.analyze([x.content_id for x in report.added], quiet=True)
