"""Points de restauration de la clé (V1.2.0) : DJSync_Backups/Points/<date>-<type>/.

Un point = l'état COMPLET de la bibliothèque de la clé à un instant : exportLibrary.db (copie
chiffrée cohérente, API de sauvegarde SQLite) + export.pdb s'il existe + point.json (type, date,
nombre de sons et de playlists). On revient à n'importe quel point en un clic (Réglages ▸
Sauvegardes de la clé) ; l'état actuel est d'abord lui-même mis de côté.

Conservation :
  * « origine » : l'état de la clé AVANT la toute première modification par DJSync. Jamais supprimé.
    Sur une clé déjà utilisée avec une version précédente, c'est la plus ancienne sauvegarde trouvée ;
  * « manuel » : créé par l'utilisateur, avec un nom. Supprimé seulement par lui ;
  * « auto » : un point au début de chaque session qui modifie la clé. On garde les 5 derniers, plus
    le premier de l'année, du mois et de la semaine en cours (remplacés quand l'année, le mois ou la
    semaine change) : on peut toujours revenir à l'état d'il y a une semaine, un mois ou un an ;
  * « avant restauration » : l'état remplacé par une restauration (3 derniers), pour l'annuler.

Les sons (Contents/) et les analyses (USBANLZ/) ne sont pas copiés : restaurer ne supprime aucun
fichier audio, il remet seulement la bibliothèque (sons connus, playlists, ordre) dans son état.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from sqlcipher3 import dbapi2 as sqlcipher

from ._key import get_default_key

log = logging.getLogger(__name__)

POINTS_DIR = "Points"
DB_NAME = "exportLibrary.db"
PDB_NAME = "export.pdb"
META = "point.json"
KEEP_RECENT = 5
KEEP_RESTORE = 3
KINDS = ("origin", "manual", "auto", "restore")


class BackupError(Exception):
    pass


@dataclass
class RestorePoint:
    path: Path
    kind: str                       # origin | manual | auto | restore
    created: datetime
    label: str = ""
    tags: List[str] = field(default_factory=list)   # auto : year / month / week
    tracks: Optional[int] = None
    playlists: Optional[int] = None
    version: str = ""
    approx: bool = False            # origine reconstituée depuis une ancienne sauvegarde

    @property
    def has_pdb(self) -> bool:
        return (self.path / PDB_NAME).is_file()

    @property
    def size(self) -> int:
        return sum(p.stat().st_size for p in self.path.iterdir() if p.is_file())

    @property
    def id(self) -> str:
        return self.path.name


def points_dir(backup_dir: Path) -> Path:
    return Path(backup_dir) / POINTS_DIR


def list_points(backup_dir: Path) -> List[RestorePoint]:
    """Points valides, du plus récent au plus ancien."""
    root = points_dir(backup_dir)
    out: List[RestorePoint] = []
    if not root.is_dir():
        return out
    for folder in root.iterdir():
        p = _load(folder)
        if p is not None:
            out.append(p)
    out.sort(key=lambda p: (p.created, p.id), reverse=True)
    return out


def _load(folder: Path) -> Optional[RestorePoint]:
    try:
        if not folder.is_dir() or not (folder / DB_NAME).is_file():
            return None
        meta = json.loads((folder / META).read_text("utf-8"))
        return RestorePoint(folder, str(meta.get("kind", "auto")), datetime.fromisoformat(meta["created"]),
                            str(meta.get("label", "")), list(meta.get("tags", [])), meta.get("tracks"),
                            meta.get("playlists"), str(meta.get("version", "")), bool(meta.get("approx", False)))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Ignored backup folder %s: %s", folder, exc)
        return None


def _counts(conn: Any) -> tuple:
    try:
        tracks = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        playlists = conn.execute("SELECT COUNT(*) FROM playlist WHERE COALESCE(attribute,0) = 0").fetchone()[0]
        return int(tracks), int(playlists)
    except sqlcipher.Error:
        return None, None


def _tags_for(now: datetime, existing: List[RestorePoint]) -> List[str]:
    autos = [p for p in existing if p.kind == "auto"]
    tags = []
    if not any("year" in p.tags and p.created.year == now.year for p in autos):
        tags.append("year")
    if not any("month" in p.tags and (p.created.year, p.created.month) == (now.year, now.month) for p in autos):
        tags.append("month")
    week = now.isocalendar()[:2]
    if not any("week" in p.tags and p.created.isocalendar()[:2] == week for p in autos):
        tags.append("week")
    return tags


def _new_folder(backup_dir: Path, kind: str, now: datetime) -> Path:
    root = points_dir(backup_dir)
    root.mkdir(parents=True, exist_ok=True)
    base = f"{now:%Y%m%d-%H%M%S}-{kind}"
    folder, n = root / base, 1
    while folder.exists():
        n += 1
        folder = root / f"{base}-{n}"
    folder.mkdir()
    return folder


def _write_meta(folder: Path, kind: str, now: datetime, label: str, tags: List[str], counts: tuple,
                approx: bool = False) -> None:
    from .. import __version__

    meta = {"kind": kind, "created": now.isoformat(timespec="microseconds"), "label": label, "tags": tags,
            "tracks": counts[0], "playlists": counts[1], "version": __version__, "approx": approx}
    (folder / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")


def _backup_db(conn: Any, key: str, target: Path) -> None:
    dest = sqlcipher.connect(str(target))
    try:
        dest.execute("PRAGMA key = '%s'" % key.replace("'", "''"))
        conn.backup(dest)
    finally:
        dest.close()


def snapshot(rekordbox_dir: Path, backup_dir: Path, kind: str, label: str = "", conn: Any = None,
             key: Optional[str] = None, now: Optional[datetime] = None) -> RestorePoint:
    """Crée un point de l'état actuel. `conn` : connexion ouverte sur exportLibrary.db (sinon on en
    ouvre une le temps de la copie). Lève BackupError ; rien n'est laissé à moitié."""
    if kind not in KINDS:
        raise ValueError(kind)
    now = now or datetime.now()
    key = key or get_default_key()
    db = Path(rekordbox_dir) / DB_NAME
    pdb = Path(rekordbox_dir) / PDB_NAME
    existing = list_points(backup_dir)
    tags = _tags_for(now, existing) if kind == "auto" else []
    folder: Optional[Path] = None
    own = None
    try:
        folder = _new_folder(backup_dir, kind, now)
        if conn is None:
            own = conn = sqlcipher.connect(str(db))
            conn.execute("PRAGMA key = '%s'" % key.replace("'", "''"))
        counts = _counts(conn)
        _backup_db(conn, key, folder / DB_NAME)
        if pdb.is_file():
            shutil.copy2(pdb, folder / PDB_NAME)
            if (folder / PDB_NAME).stat().st_size != pdb.stat().st_size:
                raise OSError("incomplete copy of export.pdb")
        _write_meta(folder, kind, now, label, tags, counts)
    except (OSError, sqlcipher.Error) as exc:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        raise BackupError(f"Backup failed: {exc}") from exc
    finally:
        if own is not None:
            own.close()
    log.info("Restore point created: %s", folder.name)
    point = _load(folder)
    assert point is not None
    prune(backup_dir)
    return point


def ensure_origin(rekordbox_dir: Path, backup_dir: Path, conn: Any = None, key: Optional[str] = None) -> bool:
    """Avant la première modification : point « origine » s'il n'existe pas encore. Sur une clé déjà
    modifiée par une version précédente (anciennes sauvegardes présentes), l'origine est reconstituée
    depuis la plus ancienne sauvegarde de exportLibrary.db et de export.pdb.
    True si l'origine vient d'être prise sur l'état ACTUEL de la clé."""
    points = list_points(backup_dir)
    if any(p.kind == "origin" for p in points):
        return False
    backup_dir = Path(backup_dir)
    old_dbs = sorted(backup_dir.glob("exportLibrary-*.db"))
    if not old_dbs and not points:
        snapshot(rekordbox_dir, backup_dir, "origin", conn=conn, key=key)
        return True
    if not old_dbs:
        return False                             # des points mais pas d'origine (supprimée à la main) : rien
    oldest = old_dbs[0]
    old_pdbs = sorted(backup_dir.glob("export-*.pdb"))
    try:
        stamp = datetime.strptime(oldest.name.split("-")[1] + oldest.name.split("-")[2], "%Y%m%d%H%M%S")
    except (ValueError, IndexError):
        stamp = datetime.fromtimestamp(oldest.stat().st_mtime)
    folder = None
    try:
        folder = _new_folder(backup_dir, "origin", stamp)
        shutil.copy2(oldest, folder / DB_NAME)
        if old_pdbs:
            shutil.copy2(old_pdbs[0], folder / PDB_NAME)
        elif (Path(rekordbox_dir) / PDB_NAME).is_file():
            shutil.copy2(Path(rekordbox_dir) / PDB_NAME, folder / PDB_NAME)
        counts: tuple = (None, None)
        try:
            c = sqlcipher.connect(str(folder / DB_NAME))
            c.execute("PRAGMA key = '%s'" % (key or get_default_key()).replace("'", "''"))
            counts = _counts(c)
            c.close()
        except sqlcipher.Error:
            pass
        _write_meta(folder, "origin", stamp, "", [], counts, approx=True)
        log.info("Origin rebuilt from the oldest backup: %s", oldest.name)
    except OSError as exc:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        log.warning("Cannot rebuild the origin backup: %s", exc)
    return False


def prune(backup_dir: Path) -> List[str]:
    """Applique la politique de conservation. Renvoie les points supprimés."""
    points = list_points(backup_dir)          # du plus récent au plus ancien
    keep = set()
    autos = [p for p in points if p.kind == "auto"]
    keep.update(p.id for p in autos[:KEEP_RECENT])
    for tag in ("year", "month", "week"):
        newest = next((p for p in autos if tag in p.tags), None)
        if newest is not None:
            keep.add(newest.id)
    keep.update(p.id for p in [p for p in points if p.kind == "restore"][:KEEP_RESTORE])
    keep.update(p.id for p in points if p.kind in ("origin", "manual"))
    removed = []
    for p in points:
        if p.id not in keep:
            shutil.rmtree(p.path, ignore_errors=True)
            removed.append(p.id)
    return removed


def delete_point(point: RestorePoint) -> None:
    if point.kind == "origin":
        raise BackupError("The origin backup cannot be deleted.")
    shutil.rmtree(point.path)


def _replace(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".djsync-tmp")
    shutil.copyfile(src, tmp)
    with open(tmp, "rb+") as fh:
        os.fsync(fh.fileno())
    os.replace(tmp, dst)


def restore(rekordbox_dir: Path, backup_dir: Path, point: RestorePoint, key: Optional[str] = None) -> RestorePoint:
    """Remet la bibliothèque de la clé dans l'état du point. La bibliothèque doit être FERMÉE.
    L'état actuel est d'abord mis de côté (point « avant restauration »), renvoyé."""
    rekordbox_dir = Path(rekordbox_dir)
    key = key or get_default_key()
    try:
        c = sqlcipher.connect(str(point.path / DB_NAME))
        c.execute("PRAGMA key = '%s'" % key.replace("'", "''"))
        c.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        c.close()
    except sqlcipher.Error as exc:
        raise BackupError(f"This backup is unreadable: {exc}") from exc
    before = snapshot(rekordbox_dir, backup_dir, "restore", key=key)
    try:
        db = rekordbox_dir / DB_NAME
        for extra in ("-wal", "-shm"):
            Path(str(db) + extra).unlink(missing_ok=True)
        _replace(point.path / DB_NAME, db)
        if point.has_pdb:
            _replace(point.path / PDB_NAME, rekordbox_dir / PDB_NAME)
    except OSError as exc:
        raise BackupError(f"Restore failed (the previous state is in {before.id}): {exc}") from exc
    log.info("Restored %s (previous state kept in %s)", point.id, before.id)
    return before
