"""Espace occupé (1.3.1, C27) : ce que DJSync et Rekordbox occupent sur la clé (ou sur l'ordinateur).

Lecture seule, sauf deux actions sans risque :
  * vider les caches de DJSync (formes d'onde, grilles, empreintes : recréés au besoin) ;
  * ne garder que les N derniers points de restauration automatiques (le point d'origine et les
    points créés à la main ne sont jamais supprimés).

Le calcul parcourt les dossiers (quelques secondes sur une grosse clé) : il est lancé en arrière-plan
à l'ouverture de la carte « Espace », jamais au branchement de la clé, et gardé quelques minutes.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

# Postes, dans l'ordre de la barre (« other » et « free » sont calculés)
USB_PARTS = ("music", "analysis", "databases", "backups", "app", "caches", "other", "free")
LOCAL_PARTS = ("music", "backups", "caches", "free")
LOW_FREE = 0.10              # alerte : moins de 10 % libre
BACKUPS_HEAVY = 0.25         # alerte : les sauvegardes dépassent 25 % de l'espace occupé par DJSync et la musique
CACHE_SECONDS = 300


@dataclass
class Usage:
    parts: Dict[str, int]                   # poste -> octets
    total: int = 0
    free: int = 0
    folders: Dict[str, Path] = field(default_factory=dict)   # poste -> dossier à ouvrir
    at: float = 0.0

    @property
    def used(self) -> int:
        return max(0, self.total - self.free)

    def warnings(self) -> List[str]:
        """Codes des alertes : « low_free », « heavy_backups »."""
        out = []
        if self.total and self.free < self.total * LOW_FREE:
            out.append("low_free")
        mine = sum(v for k, v in self.parts.items() if k not in ("other", "free"))
        if mine and self.parts.get("backups", 0) > mine * BACKUPS_HEAVY:
            out.append("heavy_backups")
        return out


def tree_size(path: Path) -> int:
    """Taille d'un fichier ou d'un dossier (liens symboliques ignorés, erreurs de lecture aussi)."""
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    stack = [path]
    while stack:
        folder = stack.pop()
        try:
            with os.scandir(folder) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir():
                            stack.append(Path(e.path))
                        else:
                            total += e.stat().st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _sizes(paths: Iterable[Path], skip: Iterable[Path] = ()) -> int:
    skip_r = {p.resolve() for p in skip if p.exists()}
    total = 0
    for p in paths:
        if not p.exists():
            continue
        if skip_r and p.is_dir():
            inner = [c for c in skip_r if p.resolve() in c.parents]
            if inner:
                total += tree_size(p) - sum(tree_size(c) for c in inner)
                continue
        total += tree_size(p)
    return total


def _disk(root: Path) -> Tuple[int, int]:
    p = root
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        u = shutil.disk_usage(p)
        return u.total, u.free
    except OSError:
        return 0, 0


def usb_usage(root: Path, contents_dir: str = "Contents", data_dir: Optional[Path] = None) -> Usage:
    """Postes de la clé. `data_dir` : dossier des réglages s'il est sur la clé (version portable)."""
    root = Path(root)
    pioneer = root / "PIONEER"
    cache = [data_dir / "cache"] if data_dir is not None and _on(root, data_dir) else []
    app = [root / n for n in ("DJSync.exe", "DJSync.app", "DJSync", ".djsync", "DJSync_Data")]
    analysis = [c for c in (pioneer.iterdir() if pioneer.is_dir() else []) if c.name.lower() != "rekordbox"]
    parts = {
        "music": _sizes([root / contents_dir]),
        "analysis": _sizes(analysis),
        "databases": _sizes([pioneer / "rekordbox"]),
        "backups": _sizes([root / "DJSync_Backups"]),
        "app": _sizes(app, skip=cache),
        "caches": _sizes(cache),
    }
    total, free = _disk(root)
    parts["other"] = max(0, (total - free) - sum(parts.values())) if total else 0
    parts["free"] = free
    folders = {"music": root / contents_dir, "analysis": pioneer, "databases": pioneer / "rekordbox",
               "backups": root / "DJSync_Backups"}
    if cache:
        folders["caches"] = cache[0]
    return Usage(parts, total, free, {k: v for k, v in folders.items() if v.exists()}, time.time())


def local_usage(music_dir: Path, backup_dir: Path, data_dir: Path) -> Usage:
    """Bibliothèque de l'ordinateur : sons téléchargés par DJSync, sauvegardes de master.db, caches."""
    cache = Path(data_dir) / "cache"
    parts = {"music": _sizes([Path(music_dir)]), "backups": _sizes([Path(backup_dir)]), "caches": _sizes([cache])}
    total, free = _disk(Path(music_dir))
    parts["free"] = free
    folders = {"music": Path(music_dir), "backups": Path(backup_dir), "caches": cache}
    return Usage(parts, total, free, {k: v for k, v in folders.items() if v.exists()}, time.time())


def _on(root: Path, p: Path) -> bool:
    try:
        return Path(root).resolve() in Path(p).resolve().parents
    except OSError:
        return False


# --------------------------------------------------------------------------------- actions
def clear_caches(data_dir: Path) -> int:
    """Vide `data_dir/cache` (formes d'onde, grilles, empreintes : recalculés au besoin).
    Renvoie les octets libérés."""
    cache = Path(data_dir) / "cache"
    if not cache.is_dir():
        return 0
    freed = 0
    for child in list(cache.iterdir()):
        size = tree_size(child)
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            freed += size
        except OSError as exc:
            log.warning("Cache not removed (%s): %s", child, exc)
    return freed


def trim_points(backup_dir: Path, keep: int) -> Tuple[int, int]:
    """Ne garde que les `keep` points automatiques (et « avant restauration ») les plus récents.
    L'origine et les points manuels ne sont jamais touchés. Renvoie (points supprimés, octets)."""
    from ..db import backups

    keep = max(1, int(keep))
    points = [p for p in backups.list_points(Path(backup_dir)) if p.kind in ("auto", "restore")]
    points.sort(key=lambda p: p.created, reverse=True)
    removed = freed = 0
    for p in points[keep:]:
        size = tree_size(p.path)
        try:
            backups.delete_point(p)
            removed += 1
            freed += size
        except OSError as exc:
            log.warning("Restore point not removed (%s): %s", p.path, exc)
    return removed, freed


class UsageCache:
    """Résultat gardé quelques minutes par dossier (la carte se rouvre sans tout recompter)."""

    def __init__(self, seconds: int = CACHE_SECONDS) -> None:
        self.seconds = seconds
        self._items: Dict[str, Usage] = {}

    def get(self, key: str) -> Optional[Usage]:
        u = self._items.get(key)
        return u if u is not None and time.time() - u.at < self.seconds else None

    def put(self, key: str, usage: Usage) -> None:
        self._items[key] = usage

    def drop(self, key: Optional[str] = None) -> None:
        if key is None:
            self._items.clear()
        else:
            self._items.pop(key, None)
