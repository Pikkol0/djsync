"""Sauvegardes de la clé (V1.2.0) : liste, sauvegarde manuelle, restauration en un clic, suppression ;
« Retirer DJSync de cette clé » ; dossier du journal."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, List

from ... import portable
from ...db import backups
from ...i18n import t

log = logging.getLogger(__name__)


class BackupsMixin:
    # ------------------------------------------------------------------ état
    @property
    def backups_available(self) -> bool:
        """Une clé USB est ouverte (pas la bibliothèque de l'ordinateur)."""
        return self.library is not None and not self.is_local and hasattr(self.library, "create_backup")

    def backups_busy(self) -> bool:
        """Téléchargements en cours ou en attente, outil ou analyse : on ne remplace pas la base."""
        return (any(not j.is_finished for j in self.jobs) or self.tool_busy
                or bool(getattr(self.analysis, "running", False)))

    @staticmethod
    def log_folder() -> Path:
        from ...settings import settings_dir

        return settings_dir()

    @staticmethod
    def can_uninstall() -> bool:
        """DJSync (programme compilé) tourne depuis une clé Rekordbox."""
        return bool(getattr(sys, "frozen", False)) and portable.own_drive_root() is not None

    @staticmethod
    def uninstall_mode() -> str:
        """1.3.1 (C88) : « drive », « computer » ou « source » (voir djsync.uninstall.mode)."""
        from ... import uninstall

        return uninstall.mode()

    @staticmethod
    def computer_uninstall_plan(keep_backups: bool = True) -> Any:
        """1.3.1 (C88) : (fichiers et dossiers qui partiront, sauvegardes de master.db présentes ?)."""
        from ... import uninstall
        from ...settings import settings_dir

        data = settings_dir()
        has_backups = (data / "Backups").is_dir() and any((data / "Backups").iterdir())
        return uninstall.computer_targets(data, keep_backups), has_backups

    def uninstall_computer(self, delete_backups: bool) -> None:
        """1.3.1 (C88) : désinstaller DJSync de l'ordinateur, puis quitter. La musique et les
        bibliothèques Rekordbox ne sont jamais touchées ; les sauvegardes de master.db restent
        (dans le dossier des réglages, ou mises à l'abri dans ~/DJSync_Backups) sauf demande."""
        from ... import uninstall
        from ...settings import settings_dir

        if self.backups_busy():
            self.message("warn", t("backups.busy"))
            return
        lib = self.library
        self.player.stop()
        self.library, self.drive = None, None
        self.playlists = []
        self.service.set_library(None)
        self._emit("drive")
        data = settings_dir()

        def work() -> Any:
            if lib is not None:
                lib.close()
            paths = uninstall.computer_targets(data, keep_backups=not delete_backups)
            if not delete_backups and any(p == data or p in data.parents for p in paths):
                uninstall.keep_computer_backups(data, uninstall.computer_backups_home())
            uninstall.schedule_removal(paths)
            return paths

        self.dispatcher.submit(work, lambda _p: self._emit("quit"), self._on_error, pool="db")

    # ------------------------------------------------------------------ points
    def backup_points(self, ok: Callable[[List[Any]], None]) -> None:
        lib = self.library
        if not self.backups_available:
            ok([])
            return
        self.dispatcher.submit(lambda: backups.list_points(lib.backup_dir), ok, self._on_error, pool="db")

    def create_backup(self, label: str, ok: Callable[[Any], None]) -> None:
        lib = self.library
        if not self.backups_available:
            return

        def done(point: Any) -> None:
            self.message("ok", t("backups.created"))
            ok(point)

        self.dispatcher.submit(lambda: lib.create_backup(label), done, self._on_error, pool="db")

    def delete_backup(self, point: Any, ok: Callable[[], None]) -> None:
        self.dispatcher.submit(lambda: backups.delete_point(point), lambda _r: ok(), self._on_error, pool="db")

    def restore_backup(self, point: Any, ok: Callable[[], None]) -> None:
        """Ferme la clé, remet la bibliothèque dans l'état du point, rouvre la clé."""
        if not self.backups_available:
            return
        if self.backups_busy():
            self.message("warn", t("backups.busy"))
            return
        drive, lib = self.drive, self.library
        self.player.stop()
        self.library, self.drive = None, None
        self.playlists = []
        self.service.set_library(None)
        self._emit("drive")
        self.message("info", t("backups.restoring"))

        def work() -> Any:
            lib.close()
            return backups.restore(lib.db_path.parent, lib.backup_dir, point, key=getattr(lib, "_key", None))

        def reopen() -> None:
            self._user_disconnected = False
            self._connect_failed.discard(str(drive.root))
            self.connect(drive, remember=False)

        def done(_before: Any) -> None:
            reopen()
            self.message("ok", t("backups.restored", date=point.created.strftime("%d/%m/%Y %H:%M")))
            ok()

        def failed(exc: BaseException) -> None:
            reopen()
            self._on_error(exc)

        self.dispatcher.submit(work, done, failed, pool="db")

    # ------------------------------------------------------------ désinstallation
    def uninstall(self, restore_origin: bool, delete_backups: bool) -> None:
        """Retire DJSync de la clé qui le porte, puis quitte (les fichiers partent après la fermeture)."""
        from ... import uninstall
        from ...settings import settings_dir

        root = portable.own_drive_root()
        if root is None:
            return
        if self.backups_busy():
            self.message("warn", t("backups.busy"))
            return
        lib = self.library
        self.player.stop()
        self.library, self.drive = None, None
        self.playlists = []
        self.service.set_library(None)
        self._emit("drive")
        backup_dir = root / "DJSync_Backups"
        rekordbox = root / "PIONEER" / "rekordbox"

        def work() -> Any:
            if lib is not None:
                lib.close()
            if restore_origin:
                origin = next((p for p in backups.list_points(backup_dir) if p.kind == "origin"), None)
                if origin is None:
                    raise backups.BackupError(t("uninstall.no_origin"))
                backups.restore(rekordbox, backup_dir, origin)
            if delete_backups:
                import shutil

                shutil.rmtree(backup_dir, ignore_errors=True)
            else:
                uninstall.keep_computer_backups(settings_dir(), backup_dir)
            paths = uninstall.targets()
            uninstall.schedule_removal(paths)
            return paths

        def done(_paths: Any) -> None:
            self._emit("quit")

        self.dispatcher.submit(work, done, self._on_error, pool="db")
