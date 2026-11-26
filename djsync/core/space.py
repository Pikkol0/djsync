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
from typing import Any, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

# Postes, dans l'ordre de la barre (« other » et « free » sont calculés)
USB_PARTS = ("music", "analysis", "databases", "backups", "app", "caches", "other", "free")
LOCAL_PARTS = ("music", "analysis", "databases", "backups", "caches", "other", "free")   # C27 ; « other » : C129
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
    music_elsewhere: Dict[str, int] = field(default_factory=dict)   # 1.4.0 (C129) : disque -> musique ailleurs
    disk: str = ""                          # 1.4.4 (C222) : disque de la barre (principal)

    @property
    def library(self) -> int:
        """1.4.0 (C129) : place prise par la bibliothèque (tous les postes sauf « autres » et « libre »)."""
        return sum(v for k, v in self.parts.items() if k not in ("other", "free", "app"))

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
                        log.debug("Ignored error in tree_size", exc_info=True)  # 1.4.3 (A3-4)
                        continue
        except OSError:
            log.debug("Ignored error in tree_size", exc_info=True)  # 1.4.3 (A3-4)
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


def drive_of(path: Any) -> str:
    """1.4.0 (C129) : disque d'un chemin (« C:\\ » sous Windows, point de montage ailleurs)."""
    p = Path(str(path))
    if p.anchor and p.drive:
        return p.anchor
    try:
        q = p if p.exists() else p.parent
        while not os.path.ismount(q) and q.parent != q:
            q = q.parent
        return str(q)
    except OSError:
        return p.anchor or "/"


def local_usage(music_dir: Path, backup_dir: Path, data_dir: Path, track_bytes: Any = None,
                share_dir: Optional[Path] = None, db_dir: Optional[Path] = None) -> Usage:
    """Bibliothèque de l'ordinateur, comme Rekordbox la voit (C27) :
      * Musique : taille des fichiers des sons de la collection (`track_bytes`, lue dans master.db : un
        nombre, ou {disque: octets} quand la musique est sur plusieurs disques) ; à défaut, le dossier de
        téléchargement de DJSync ;
      * Analyses et pochettes, Bases Rekordbox, Sauvegardes DJSync, Caches ;
      * 1.4.0 (C129) : la barre couvre tout le disque principal (celui qui a le plus de musique) : postes de
        la bibliothèque sur ce disque, puis « Autres fichiers » (le reste de l'occupé), puis Libre ; la
        musique rangée sur d'autres disques est donnée à part (`music_elsewhere`)."""
    cache = Path(data_dir) / "cache"
    elsewhere: Dict[str, int] = {}
    if isinstance(track_bytes, dict) and track_bytes:
        main = max(track_bytes, key=lambda d: track_bytes[d])
        music = int(track_bytes[main])
        elsewhere = {d: int(b) for d, b in track_bytes.items() if d != main and b}
        disk_root = Path(main)
    else:
        music = int(track_bytes) if track_bytes is not None else _sizes([Path(music_dir)])
        disk_root = Path(music_dir)
    dbs = sorted(Path(db_dir).glob("master*")) if db_dir is not None and Path(db_dir).is_dir() else []
    parts = {"music": music, "analysis": _sizes([Path(share_dir)]) if share_dir is not None else 0,
             "databases": _sizes(dbs), "backups": _sizes([Path(backup_dir)]), "caches": _sizes([cache])}
    total, free = _disk(disk_root)
    where = {"analysis": share_dir, "databases": db_dir, "backups": backup_dir, "caches": cache}
    main_drive = drive_of(disk_root)
    on_disk = parts["music"] + sum(parts[k] for k, p in where.items() if p is not None and drive_of(p) == main_drive)
    parts["other"] = max(0, (total - free) - on_disk) if total else 0
    parts["free"] = free
    folders = {"music": Path(music_dir), "analysis": Path(share_dir) if share_dir is not None else None,
               "databases": Path(db_dir) if db_dir is not None else None, "backups": Path(backup_dir),
               "caches": cache}
    return Usage(parts, total, free, {k: v for k, v in folders.items() if v is not None and v.exists()}, time.time(),
                 elsewhere, main_drive)


# ------------------------------------------------- 1.4.3 (A7-5, repris de Sleeve) : place sur la clé
DEFAULT_BLOCK = 4096
ANLZ_BLOCKS = 4                # .DAT, .EXT, .2EX et la pochette d'un son : environ un bloc chacun


def cluster_size(path: Any) -> int:
    """Taille d'un bloc (unité d'allocation) du disque de `path` : un fichier occupe toujours un nombre entier
    de blocs (32 Ko sur une clé exFAT de 64 Go, par exemple). DEFAULT_BLOCK si inconnue."""
    p = Path(str(path))
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        if os.name == "nt":
            import ctypes

            spc, bps, _f, _t = (ctypes.c_ulong() for _ in range(4))
            root = str(p.resolve().anchor)
            if ctypes.windll.kernel32.GetDiskFreeSpaceW(root, ctypes.byref(spc), ctypes.byref(bps),  # type: ignore[attr-defined]
                                                        ctypes.byref(_f), ctypes.byref(_t)):
                return max(512, int(spc.value) * int(bps.value))
            return DEFAULT_BLOCK
        st = os.statvfs(p)
        return max(512, int(st.f_frsize or st.f_bsize or DEFAULT_BLOCK))
    except (OSError, AttributeError, ValueError):
        return DEFAULT_BLOCK


def on_disk(size: int, block: int) -> int:
    """Place réellement prise par un fichier de `size` octets (arrondi au bloc supérieur)."""
    block = max(1, int(block or DEFAULT_BLOCK))
    return -(-max(0, int(size)) // block) * block


def estimate_copy(sizes: Iterable[int], block: int) -> int:
    """Place nécessaire pour copier ces sons : chaque fichier arrondi au bloc, plus leurs fichiers d'analyse
    et pochette (ANLZ_BLOCKS blocs par son). Rien n'est écrit."""
    sizes = list(sizes)
    return sum(on_disk(s, block) for s in sizes) + len(sizes) * ANLZ_BLOCKS * max(1, int(block or DEFAULT_BLOCK))


# ------------------------------------------------------------- 1.4.3 (C200) : DJSync sur cet ordinateur
# 1.4.3-rc.2 (C228) : les sons téléchargés (« music ») sont comptés à part, plus dans le total de DJSync
FOOTPRINT_PARTS = ("app", "caches", "backups", "settings")


def app_size() -> int:
    """Taille de DJSync installé : l'exécutable (ou son paquet .app / son dossier), sinon le dossier du code."""
    import sys

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        for parent in exe.parents:
            if parent.suffix == ".app":
                return tree_size(parent)
        if (exe.parent / "_internal").is_dir():
            return tree_size(exe.parent)
        try:
            return exe.stat().st_size
        except OSError:
            return 0
    return tree_size(Path(__file__).resolve().parent.parent)


def djsync_footprint(data_dir: Path, music_dir: Optional[Path] = None) -> Dict[str, int]:
    """Place prise par DJSync sur cet ordinateur : application, caches, sauvegardes (master.db), réglages et
    journaux ; « total » = leur somme. « music » : sons téléchargés sur l'ordinateur, à part (1.4.3-rc.2, C228)."""
    data_dir = Path(data_dir)
    cache, backups = data_dir / "cache", data_dir / "Backups"
    out = {"app": app_size(), "caches": _sizes([cache]), "backups": _sizes([backups]),
           "settings": _sizes([data_dir], skip=[cache, backups]),
           "music": _sizes([Path(music_dir)]) if music_dir is not None else 0}
    out["total"] = sum(out[k] for k in FOOTPRINT_PARTS)
    return out


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


def _trimmable(backup_dir: Path, keep: int) -> list:
    from ..db import backups

    keep = max(1, int(keep))
    points = [p for p in backups.list_points(Path(backup_dir)) if p.kind in ("auto", "restore")]
    points.sort(key=lambda p: p.created, reverse=True)
    return points[keep:]


def trim_preview(backup_dir: Path, keep: int) -> Tuple[int, int]:
    """1.4.2 (A2-13) : ce que `trim_points` supprimerait (nombre de points, octets), sans rien toucher."""
    points = _trimmable(backup_dir, keep)
    return len(points), sum(tree_size(p.path) for p in points)


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


# ------------------------------------------------- 1.4.4 (C222) : une barre par disque concerné
@dataclass
class DiskBar:
    """Un disque (de l'ordinateur ou une clé) qui contient quelque chose de DJSync : titre et usage."""
    title: str
    kind: str                     # "computer" | "usb"
    usage: Usage
    absent: bool = False          # 1.4.4 (C240) : disque de la collection débranché ou introuvable
    tracks: int = 0               # 1.4.4 (C240) : sons de la collection sur ce disque


def _bar_usage(parts: Dict[str, int], root: Path) -> Usage:
    total, free = _disk(Path(root))
    parts = {k: int(v) for k, v in parts.items() if v}
    parts["other"] = max(0, (total - free) - sum(parts.values())) if total else 0
    parts["free"] = free
    return Usage(parts, total, free, {}, time.time())


def computer_disks(where: Dict[str, Any], music_by_disk: Optional[Dict[str, int]] = None,
                   skip: Iterable[str] = (), sizes: Optional[Dict[str, int]] = None,
                   tracks_by_disk: Optional[Dict[str, int]] = None) -> List[DiskBar]:
    """Disques de l'ordinateur qui contiennent musique, données ou sauvegardes de DJSync (sauf `skip`, déjà
    montré par la barre principale). `where` : poste -> dossier ; `sizes` : tailles déjà mesurées par poste
    (sinon mesurées ici) ; `music_by_disk` : musique de la collection par disque."""
    per: Dict[str, Dict[str, int]] = {}
    for d, n in (music_by_disk or {}).items():
        if n:
            per.setdefault(d, {})["music"] = per.get(d, {}).get("music", 0) + int(n)
    for key, folder in where.items():
        if folder is None or not Path(folder).exists():
            continue
        d = drive_of(folder)
        size = (sizes or {}).get(key)
        if size is None:
            size = _sizes([Path(folder)])
        if size:
            per.setdefault(d, {})[key] = per.get(d, {}).get(key, 0) + int(size)
    skip = set(skip)
    out = []
    for d, parts in sorted(per.items()):
        if d in skip:
            continue
        n = int((tracks_by_disk or {}).get(d, 0))
        if not _present(d):            # 1.4.4 (C240) : pas de barre pleine pour un disque absent
            out.append(DiskBar(d, "computer", Usage(dict(parts), 0, 0), absent=True, tracks=n))
            continue
        out.append(DiskBar(d, "computer", _bar_usage(parts, Path(d)), tracks=n))
    return out


def _present(disk: str) -> bool:
    """1.4.4 (C240) : disque branché et lisible (taille non nulle ; un disque absent donne 0 / 0)."""
    return _disk(Path(disk))[0] > 0


def usb_disks(drives: Iterable[Any], contents_dir: str = "Contents", skip: Iterable[str] = ()) -> List[DiskBar]:
    """Une barre par clé branchée (sauf celles de `skip`, chemins de racine)."""
    skip = {str(s) for s in skip}
    out = []
    for d in drives:
        root = Path(getattr(d, "root", d))
        if str(root) in skip:
            continue
        try:
            usage = usb_usage(root, contents_dir)
        except OSError:
            continue
        out.append(DiskBar(getattr(d, "label", "") or str(root), "usb", usage))
    return out
