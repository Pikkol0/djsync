"""1.4.2 (A6-6) : clé pleine. Spec : claude/spec-a6-6.md (validée le 18/11/2026).

- Clé pleine = place libre < seuil, seuil = taille d'exportLibrary.db + taille d'export.pdb (s'il existe) + 10 Mo.
- Reconnue sur une erreur d'écriture « disque plein » (ENOSPC, « database or disk is full », « disk I/O error »),
  toujours avec une place libre sous le seuil.
- « Libérer de la place » (clé qui ne s'ouvre plus) : supprime les copies automatiques de la base
  (DJSync_Backups/exportLibrary-*-auto.db et *-session.db) en gardant les 2 plus récentes de chaque sorte ; ne touche
  jamais aux points de restauration (DJSync_Backups/Points), donc jamais à l'origine.
"""
from __future__ import annotations

import errno
import logging
import shutil
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

MARGIN = 10 * 1024 * 1024
KEEP_COPIES = 2
COPY_PATTERNS = ("exportLibrary-*-auto.db", "*-session.db")
_SPACE_WORDS = ("database or disk is full", "disk i/o error", "no space left", "not enough space", "disk full",
                "winerror 112", "errno 28")


def free_bytes(path: Path) -> int:
    for folder in (Path(path), *Path(path).parents):
        try:
            if folder.exists():
                return int(shutil.disk_usage(folder).free)
        except OSError:
            log.debug("Ignored error in free_bytes", exc_info=True)  # 1.4.3 (A3-4)
            continue
    return 1 << 62


def _size(p: Path) -> int:
    try:
        return p.stat().st_size if p.is_file() else 0
    except OSError:
        return 0


def threshold(rekordbox_dir: Path) -> int:
    """Base + export.pdb (s'il existe) + 10 Mo (décision Q1 du 18/11)."""
    folder = Path(rekordbox_dir)
    return _size(folder / "exportLibrary.db") + _size(folder / "export.pdb") + MARGIN


def state(rekordbox_dir: Path) -> Tuple[bool, int, int]:
    """(pleine ?, place libre, seuil)."""
    free, need = free_bytes(rekordbox_dir), threshold(rekordbox_dir)
    return free < need, free, need


def is_space_error(exc: Optional[BaseException]) -> bool:
    """L'erreur (ou l'une de ses causes) ressemble-t-elle à « disque plein » ?"""
    seen = 0
    while exc is not None and seen < 8:
        if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            return True
        text = f"{type(exc).__name__} {exc}".lower()
        if any(k in text for k in _SPACE_WORDS):
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False


def copies(backup_dir: Path) -> List[List[Path]]:
    """Copies automatiques de la base, une liste par sorte, de la plus ancienne à la plus récente."""
    folder = Path(backup_dir)
    if not folder.is_dir():
        return [[] for _ in COPY_PATTERNS]
    return [sorted(p for p in folder.glob(pattern) if p.is_file()) for pattern in COPY_PATTERNS]


def purge_copies(backup_dir: Path, keep: int = KEEP_COPIES) -> int:
    """Supprime les copies automatiques en gardant les `keep` plus récentes de chaque sorte. Renvoie les octets
    rendus. Les points (sous-dossier Points) ne sont jamais touchés : le motif ne regarde que le dossier lui-même."""
    from . import backups

    gained = 0
    protect = set()
    if not any(p.kind == "origin" for p in backups.list_points(backup_dir)):
        oldest = sorted(Path(backup_dir).glob("exportLibrary-*.db"))     # servira à reconstituer l'origine
        protect = {oldest[0]} if oldest else set()
    for kind in copies(backup_dir):
        for old in kind[: -keep or None] if keep else kind:
            if old in protect:
                continue
            for p in (old, old.with_name(old.name + "-wal"), old.with_name(old.name + "-shm")):
                size = _size(p)
                try:
                    p.unlink(missing_ok=True)
                    gained += size
                except OSError as exc:
                    log.warning("Backup copy not deleted (%s): %s", p, exc)
    log.info("Drive full: %d bytes freed in %s", gained, backup_dir)
    return gained


def _opens(db: Path, key: Optional[str]) -> bool:
    """Le point a une base qui s'ouvre (en lecture seule)."""
    try:
        from sqlcipher3 import dbapi2 as sqlcipher

        from ._key import get_default_key

        uri = Path(db).resolve().as_uri() + "?mode=ro"
        conn = sqlcipher.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA key = '%s'" % (key or get_default_key()).replace("'", "''"))
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - point illisible : pas un retour possible
        log.info("Restore point %s not readable: %s", db, exc)
        return False


def return_point(backup_dir: Path, key: Optional[str] = None, session_id: str = "") -> Any:
    """Point de retour pour une suppression sans copie (règle 3 b) : le point de session de cette session
    (`session_id`), sinon le plus récent point « session » (auto) ou « origine » dont la base s'ouvre ; None sinon."""
    from . import backups

    points = backups.list_points(backup_dir)
    ordered: Iterable[Any] = sorted(points, key=lambda p: p.id != session_id) if session_id else points
    for p in ordered:
        if (p.id == session_id or p.kind in ("auto", "origin")) and _opens(p.path / backups.DB_NAME, key):
            return p
    return None
