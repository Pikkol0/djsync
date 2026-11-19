"""1.4.3 (A6-1) : reprise d'un remplacement interrompu sur la clé (clé retirée au mauvais moment).

Sur FAT32 / exFAT, remplacer un fichier n'est pas atomique : DJSync écrit `nom.djsync-tmp`, puis le renomme
par-dessus l'original. Un retrait entre l'effacement de l'ancienne entrée et le renommage laisse le temporaire,
complet, et plus de fichier. Ce module, appelé à la détection et à l'ouverture d'une clé :

- fichier absent + temporaire présent : le temporaire est contrôlé (export.pdb : chargement strict ; base :
  ouverture SQLCipher et `PRAGMA quick_check`) ; valide → remis en place ; sinon rien n'est effacé et l'état
  « damaged » est signalé (la restauration d'un point est proposée) ;
- fichier présent + temporaire présent (arrêt avant le renommage) : le fichier en place fait foi ; le
  temporaire est déplacé (pas effacé) dans DJSync_Backups.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

TMP = ".djsync-tmp"
DB_NAME = "exportLibrary.db"
PDB_NAME = "export.pdb"
BACKUP_DIR = "DJSync_Backups"


@dataclass
class Recovery:
    restored: List[str] = field(default_factory=list)     # fichiers remis en place depuis leur temporaire
    damaged: List[str] = field(default_factory=list)      # absents, temporaire illisible : restauration à proposer
    moved: List[str] = field(default_factory=list)        # temporaires mis de côté (le fichier était là)

    @property
    def empty(self) -> bool:
        return not (self.restored or self.damaged or self.moved)


def _valid_pdb(path: Path) -> bool:
    try:
        from .pdb.database import PdbDatabase

        PdbDatabase(path.read_bytes())
        return True
    except Exception as exc:  # noqa: BLE001 - n'importe quelle erreur de lecture = pas valide
        log.info("Leftover %s is not a valid export.pdb: %s", path.name, exc)
        return False


def _valid_db(path: Path, key: Optional[str]) -> bool:
    from sqlcipher3 import dbapi2 as sqlcipher

    from ._key import get_default_key

    try:
        conn = sqlcipher.connect(str(path))
        try:
            conn.execute("PRAGMA key = '%s'" % (key or get_default_key()).replace("'", "''"))
            ok = conn.execute("PRAGMA quick_check").fetchone()[0]
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        return ok == "ok" and "content" in tables
    except Exception as exc:  # noqa: BLE001
        log.info("Leftover %s is not a valid library: %s", path.name, exc)
        return False


def _drive_root(rekordbox_dir: Path) -> Path:
    return rekordbox_dir.parent.parent            # <clé>/PIONEER/rekordbox


def recover(rekordbox_dir: Path, key: Optional[str] = None, read_only: bool = False) -> Recovery:
    """Reprend les remplacements interrompus dans `rekordbox_dir` (voir le module). `read_only` : rien n'est
    changé, l'état est seulement signalé."""
    rekordbox_dir = Path(rekordbox_dir)
    out = Recovery()
    for name in (DB_NAME, PDB_NAME):
        target = rekordbox_dir / name
        tmp = rekordbox_dir / (name + TMP)
        try:
            if not tmp.is_file():
                continue
            if target.is_file():
                if read_only:
                    continue
                keep = _drive_root(rekordbox_dir) / BACKUP_DIR
                keep.mkdir(exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                dest = keep / f"{name}-leftover-{stamp}{TMP}"
                shutil.move(str(tmp), str(dest))
                out.moved.append(name)
                log.warning("Leftover %s%s moved to %s (the file in place is kept)", name, TMP, dest)
                continue
            valid = _valid_db(tmp, key) if name == DB_NAME else _valid_pdb(tmp)
            if not valid:
                out.damaged.append(name)
                log.warning("%s is missing and its leftover copy is unreadable: nothing changed, "
                            "a backup can be restored", name)
                continue
            if read_only:
                continue
            os.replace(tmp, target)
            out.restored.append(name)
            log.warning("%s was missing (drive removed while it was being replaced): put back from %s%s",
                        name, name, TMP)
        except OSError as exc:
            log.warning("Leftover %s%s not handled: %s", name, TMP, exc)
    return out


def damaged_library(root: Path) -> bool:
    """La clé `root` a perdu exportLibrary.db pendant un remplacement (temporaire présent mais illisible)."""
    rb = Path(root) / "PIONEER" / "rekordbox"
    return not (rb / DB_NAME).is_file() and (rb / (DB_NAME + TMP)).is_file()


def restore_latest(root: Path) -> str:
    """Remet la base (et export.pdb) du point de restauration le plus récent sur une clé dont exportLibrary.db
    est perdue. Le temporaire illisible est gardé (déplacé dans DJSync_Backups). Renvoie l'identifiant du point."""
    from . import backups

    root = Path(root)
    rb = root / "PIONEER" / "rekordbox"
    points = backups.list_points(root / BACKUP_DIR)
    if not points:
        raise backups.BackupError("No restore point on this drive.")
    point = points[0]
    for name in (DB_NAME, PDB_NAME):
        tmp = rb / (name + TMP)
        if tmp.is_file():
            keep = root / BACKUP_DIR
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.move(str(tmp), str(keep / f"{name}-leftover-{stamp}{TMP}"))
    for extra in ("-wal", "-shm"):
        Path(str(rb / DB_NAME) + extra).unlink(missing_ok=True)
    backups._replace(point.path / DB_NAME, rb / DB_NAME)  # noqa: SLF001 - même écriture sûre que Restaurer
    if point.has_pdb and not (rb / PDB_NAME).is_file():
        backups._replace(point.path / PDB_NAME, rb / PDB_NAME)  # noqa: SLF001
    log.warning("Library put back from restore point %s", point.id)
    return point.id
