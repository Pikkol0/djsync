"""Ajout de fichiers de l'ordinateur (1.4.0, C26 sens A) : bouton « Ajouter des fichiers… », glisser-
déposer, et (C10.3) dossier surveillé. Le travail lourd est dans `core.importer`."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from ...i18n import plural, t

log = logging.getLogger(__name__)


class ImportsMixin:
    def import_files(self, paths: Sequence[Any], playlist_ids: Sequence[int] = (),
                     ok: Optional[Callable[[Any], None]] = None, quiet: bool = False) -> bool:
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
            report = importer.import_files(lib, files, pids, progress)
            self.service.refresh_library()
            return report

        def done(report: Any) -> None:
            self._emit("library")
            self._emit("import_progress", 0, 0)
            self._import_done(report, lib, quiet)
            if ok:
                ok(report)

        def failed(exc: BaseException) -> None:
            self._emit("import_progress", 0, 0)
            self._on_error(exc)

        self.dispatcher.submit(work, done, failed, pool="db")
        return True

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
