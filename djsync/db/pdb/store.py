"""Fichier export.pdb sur la clé : lecture, sauvegarde, écriture atomique, vérification.

Séquence d'une écriture (rien n'est modifié sur la clé avant l'étape 4) :
  1. lecture du fichier et chargement strict (PdbFormatError si le modèle ne correspond pas) ;
  2. application des opérations EN MÉMOIRE ;
  3. contrôle du résultat : fichier valide, seules les pages touchées ont changé ;
  4. copie de sauvegarde de l'original (DJSync_Backups/export-<date>-<session|auto>.pdb) ;
  5. écriture dans un fichier temporaire du même dossier, fsync, puis remplacement atomique ;
  6. relecture et comparaison avec ce qui devait être écrit.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .database import PdbDatabase, Summary
from .format import PdbError

log = logging.getLogger(__name__)
Op = Callable[[PdbDatabase], None]


class PdbStore:
    NAME = "export.pdb"

    def __init__(self, folder: Path, backup_dir: Path, keep: int = 10, session_keep: int = 5,
                 allow_growth: bool = False) -> None:
        self.path = Path(folder) / self.NAME
        self.backup_dir = Path(backup_dir)
        self.keep, self.session_keep = keep, session_keep
        self.allow_growth = allow_growth
        self._session_backed_up = False

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> PdbDatabase:
        try:
            return PdbDatabase(self.path.read_bytes(), allow_growth=self.allow_growth)
        except OSError as exc:
            raise PdbError(f"unreadable export.pdb: {exc}") from exc

    def apply(self, ops: Sequence[Op]) -> Summary:
        """Applique les opérations ; n'écrit sur la clé que si tout s'est bien passé."""
        try:
            original = self.path.read_bytes()
        except OSError as exc:
            raise PdbError(f"unreadable export.pdb: {exc}") from exc
        db = PdbDatabase(original, allow_growth=self.allow_growth)
        for op in ops:
            op(db)
        new = db.to_bytes()
        if new == original:
            return db.summary
        self._backup(original)
        self._write_atomic(new)
        return db.summary

    # ------------------------------------------------------------------ interne
    def _backup(self, original: bytes) -> None:
        tag = "auto" if self._session_backed_up else "session"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        try:
            self.backup_dir.mkdir(exist_ok=True)
            target = self.backup_dir / f"export-{stamp}-{tag}.pdb"
            target.write_bytes(original)
            if target.stat().st_size != len(original):
                raise OSError("incomplete backup")
            for pattern, keep in (("export-*-auto.pdb", self.keep), ("export-*-session.pdb", self.session_keep)):
                for old in sorted(self.backup_dir.glob(pattern))[: -keep or None]:
                    old.unlink(missing_ok=True)
        except OSError as exc:
            raise PdbError(f"export.pdb backup failed, write cancelled: {exc}") from exc
        self._session_backed_up = True
        log.info("Sauvegarde : %s", target.name)

    def _write_atomic(self, data: bytes) -> None:
        tmp = self.path.with_name(self.NAME + ".djsync-tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            if self.path.read_bytes() != data:
                raise OSError("read-back does not match what was written")
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise PdbError(f"cannot write export.pdb (file used by another program?): {exc}") from exc
