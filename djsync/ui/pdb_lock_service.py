"""1.4.4 (B134) : clé ouverte dans Rekordbox (export.pdb gardé ouvert) : prévenir avant d'écrire.

Service à part (A3-10) tenu par le contrôleur (`ctrl.pdb_lock`). La réécriture automatique d'export.pdb
dès qu'il est libre est dans la bibliothèque (`pdb_late`, `db/library/pdb_mirror.py`)."""
from __future__ import annotations

import logging
from typing import Any

from ..i18n import t

log = logging.getLogger(__name__)


class PdbLockService:
    def __init__(self, ctrl: Any) -> None:
        self.ctrl = ctrl

    def ask(self, lib: Any) -> None:
        """Rekordbox vu ouvert avec une clé active : si export.pdb est gardé ouvert, question « Continuer /
        Annuler » ; sinon, l'avertissement d'avant (msg.rekordbox_open_usb)."""
        from ..db.pdb.lock import pdb_locked

        ctrl = self.ctrl

        def work() -> bool:
            db_path = getattr(lib, "db_path", None)
            return db_path is not None and pdb_locked(db_path.parent / "export.pdb")

        def done(locked: bool) -> None:
            if lib is not ctrl.library:
                return
            if locked and not getattr(lib, "read_only", False):
                ctrl._emit("pdb_locked_ask", lib)
            else:
                ctrl.message("warn", t("msg.rekordbox_open_usb"))

        ctrl.dispatcher.submit(work, done, lambda _e: ctrl.message("warn", t("msg.rekordbox_open_usb")),
                               pool="tools")

    def answer(self, lib: Any, go_on: bool) -> None:
        """« Continuer » : écritures permises (export.pdb en retard, rattrapé seul) ; « Annuler » : la clé reste
        en lecture seule jusqu'à sa réouverture."""
        ctrl = self.ctrl
        if lib is not ctrl.library:
            return
        if go_on:
            ctrl.message("info", t("pdb_lock.continued"))
            return
        lib.read_only = True
        log.info("Drive kept read-only while Rekordbox has it open (B134)")
        ctrl.message("warn", t("pdb_lock.cancelled"))
        ctrl._emit("drive")
