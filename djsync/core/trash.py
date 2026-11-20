"""1.4.3 (A07, C156) : envoi d'un fichier à la corbeille du système (récupérable), sans dépendance de plus.

- Windows : SHFileOperationW avec FOF_ALLOWUNDO (corbeille du disque du fichier) ;
- macOS : NSFileManager.trashItemAtURL (pyobjc, livré avec l'app), sinon ~/.Trash (même disque) ou
  <volume>/.Trashes/<uid> ;
- Linux et autres : spécification freedesktop.org (corbeille de l'utilisateur si même disque, sinon
  <point de montage>/.Trash-<uid>), avec le fichier .trashinfo qui permet « Restaurer » dans le gestionnaire de fichiers.

`move_to_trash` lève OSError si le fichier n'a pas pu y aller : il n'est alors jamais effacé autrement.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Sequence
from urllib.parse import quote

log = logging.getLogger(__name__)


def move_to_trash(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    _backend(path)
    if path.exists():
        raise OSError(f"Still there after moving to the trash: {path}")
    log.info("Moved to the trash: %s", path)


def move_many_to_trash(paths: Sequence[Path]) -> List[Path]:
    """1.4.3-rc.2 (B120) : plusieurs fichiers à la corbeille ; sous Windows en un seul appel au système (un appel
    par fichier coûtait une à plusieurs dixièmes de seconde chacun). Renvoie les fichiers restés en place."""
    paths = [Path(p) for p in paths]
    if sys.platform == "win32" and _backend is _system and len(paths) > 1:
        try:
            _windows_many(paths)
        except OSError as exc:
            log.info("Recycle Bin refused a batch (%s): files moved one by one", exc)
        left = [p for p in paths if p.exists()]
        for p in paths:
            if not p.exists():
                log.info("Moved to the trash: %s", p)
        paths = left
    refused: List[Path] = []
    for p in paths:
        try:
            move_to_trash(p)
        except OSError as exc:
            log.info("Not moved to the trash (%s): %s", p, exc)
            refused.append(p)
    return refused


def _system(path: Path) -> None:
    if sys.platform == "win32":
        _windows(path)
    elif sys.platform == "darwin":
        _macos(path)
    else:
        _freedesktop(path)


_backend = _system                   # remplacé dans les tests (corbeille simulée : rien dans la vraie corbeille)


# ------------------------------------------------------------------------------------------------ Windows
def _windows(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    fo_delete, allow_undo, no_confirm, silent, no_ui = 3, 0x40, 0x10, 0x04, 0x400
    op = SHFILEOPSTRUCTW(None, fo_delete, str(path.resolve()) + "\0", None,
                         allow_undo | no_confirm | silent | no_ui, False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted:
        raise OSError(f"Recycle Bin refused {path} (code {code})")


def _windows_many(paths: Sequence[Path]) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    fo_delete, allow_undo, no_confirm, silent, no_ui = 3, 0x40, 0x10, 0x04, 0x400
    names = "".join(str(Path(p).resolve()) + "\0" for p in paths)
    op = SHFILEOPSTRUCTW(None, fo_delete, names, None, allow_undo | no_confirm | silent | no_ui, False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted:
        raise OSError(f"Recycle Bin refused {len(paths)} files (code {code})")


# -------------------------------------------------------------------------------------------------- macOS
def _macos(path: Path) -> None:
    try:
        from Foundation import NSURL, NSFileManager  # type: ignore[import-not-found]

        ok, _url, err = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
            NSURL.fileURLWithPath_(str(path.resolve())), None, None)
        if ok:
            return
        log.info("Finder trash refused %s (%s): trying the trash folder", path, err)
    except ImportError:
        log.debug("pyobjc Foundation missing: trash folder used directly")
    home = Path.home() / ".Trash"
    target = home if _same_device(path, home) else _mount_point(path) / ".Trashes" / str(os.getuid())
    target.mkdir(parents=True, exist_ok=True)
    os.rename(path, _free_name(target, path.name))


# ------------------------------------------------------------------------------------- Linux (freedesktop)
def _xdg_trash() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Trash"


def _freedesktop(path: Path) -> None:
    home = _xdg_trash()
    home.mkdir(parents=True, exist_ok=True)
    if _same_device(path, home):
        trash, relative_to = home, None
    else:
        top = _mount_point(path)
        shared = top / ".Trash"
        uid = str(os.getuid()) if hasattr(os, "getuid") else "0"
        if shared.is_dir() and not shared.is_symlink() and os.stat(shared).st_mode & 0o1000:
            trash = shared / uid
        else:
            trash = top / f".Trash-{uid}"
        relative_to = top
    files, info = trash / "files", trash / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    dest = _free_name(files, path.name, info)
    original = path.resolve()
    shown = original.relative_to(relative_to) if relative_to is not None else original
    note = info / (dest.name + ".trashinfo")
    note.write_text("[Trash Info]\nPath=%s\nDeletionDate=%s\n"
                    % (quote(str(shown)), datetime.now().strftime("%Y-%m-%dT%H:%M:%S")), encoding="utf-8")
    try:
        os.rename(original, dest)
    except OSError:
        note.unlink(missing_ok=True)
        raise


# ------------------------------------------------------------------------------------------------- outils
def _same_device(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def _mount_point(path: Path) -> Path:
    p = Path(path).resolve()
    while not os.path.ismount(p) and p.parent != p:
        p = p.parent
    return p


def _free_name(folder: Path, name: str, info: "Path | None" = None) -> Path:
    stem, suffix = os.path.splitext(name)
    candidate, n = folder / name, 1
    while candidate.exists() or (info is not None and (info / (candidate.name + ".trashinfo")).exists()):
        n += 1
        candidate = folder / f"{stem} {n}{suffix}"
    return candidate
