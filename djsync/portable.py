"""Mode portable : DJSync.exe posé sur la clé USB, utilisable sur n'importe quel PC.

Est « portable » un DJSync qui :
  * a un fichier `portable.flag` à côté de lui, ou la variable DJSYNC_PORTABLE=1, ou
  * se trouve lui-même sur une clé Rekordbox (un de ses dossiers parents contient
    PIONEER/rekordbox/exportLibrary.db).
Dans ce cas : réglages dans `<dossier de l'exe>/DJSync_Data` (rien dans %APPDATA% du PC hôte), la
clé qui porte l'exe est connectée d'office (les lettres de lecteur changent d'un PC à l'autre),
et les outils posés à côté de l'exe (`tools/` : ffmpeg.exe, ffprobe.exe, deno.exe) sont ajoutés au
PATH — rien à installer sur le PC.

Un seul fichier (V1.0.0) : DJSync.exe est un petit lanceur (packaging/launcher) qui porte
l'application zippée. Au premier lancement (ou si le dossier a disparu, ou si la version change) il
l'extrait dans `.djsync/app` à côté de lui, caché ; les réglages vivent dans `.djsync/data` et sont
conservés. Il transmet son dossier à l'application dans DJSYNC_APP_DIR.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DB_RELATIVE = Path("PIONEER") / "rekordbox" / "exportLibrary.db"
TOOL_DIRS = ("tools", "ffmpeg", "bin")
CONTENTS = ".djsync"                      # dossier caché à côté de DJSync.exe (app/ + data/)
LEGACY_DATA = "DJSync_Data"


def app_dir() -> Path:
    """Dossier « visible » de DJSync : celui de DJSync.exe (lanceur un-seul-fichier, qui le transmet
    dans DJSYNC_APP_DIR), sinon de l'exécutable PyInstaller, sinon la racine du projet (développement)."""
    launcher = os.environ.get("DJSYNC_APP_DIR")
    if launcher:
        return Path(launcher)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name == "app" and exe_dir.parent.name == CONTENTS:      # .djsync/app lancé directement
            return exe_dir.parent.parent
        return exe_dir
    return Path(__file__).resolve().parent.parent


def own_drive_root(start: Optional[Path] = None) -> Optional[Path]:
    """Racine de la clé Rekordbox qui contient DJSync, ou None."""
    here = Path(start) if start is not None else app_dir()
    for folder in (here, *here.parents):
        try:
            if (folder / DB_RELATIVE).is_file():
                return folder
        except OSError:
            continue
    return None


def is_portable(start: Optional[Path] = None) -> bool:
    here = Path(start) if start is not None else app_dir()
    return (os.environ.get("DJSYNC_PORTABLE") == "1" or bool(os.environ.get("DJSYNC_APP_DIR"))
            or (here / "portable.flag").exists()
            or (here / CONTENTS / "portable.flag").exists() or own_drive_root(here) is not None)


def portable_data_dir(start: Optional[Path] = None) -> Optional[Path]:
    """Réglages de la version portable : `.djsync/data` (caché), ou l'ancien `DJSync_Data` s'il existe."""
    here = Path(start) if start is not None else app_dir()
    if not is_portable(here):
        return None
    if (here / LEGACY_DATA).is_dir() or not (here / CONTENTS).is_dir():
        return here / LEGACY_DATA
    return here / CONTENTS / "data"


def tool_dirs(start: Optional[Path] = None) -> list:
    here = Path(start) if start is not None else app_dir()
    bases = [here / CONTENTS / "app", here / CONTENTS, here]
    if start is None and getattr(sys, "frozen", False):
        bases.insert(0, Path(sys.executable).resolve().parent)          # outils livrés avec l'application
    seen, out = set(), []
    for base in bases:
        for d in TOOL_DIRS:
            p = base / d
            if p.is_dir() and str(p) not in seen:
                seen.add(str(p))
                out.append(p)
    return out


FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
_INVALID = 0xFFFFFFFF


def hide(path: Path) -> bool:
    """Attributs Windows « caché » + « système » (comme desktop.ini) : l'Explorateur ne montre pas le
    dossier, même avec « Éléments masqués » coché (seul « Masquer les fichiers protégés du système »,
    activé par défaut, le révèlerait). Le point en tête de nom suffit ailleurs. Sans effet si absent."""
    if sys.platform != "win32" or not path.exists():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        k32.GetFileAttributesW.restype = wintypes.DWORD
        k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        k32.SetFileAttributesW.restype = wintypes.BOOL
        wanted = FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
        attrs = k32.GetFileAttributesW(str(path))
        if attrs == _INVALID:
            log.warning("Cannot read the attributes of %s (error %s)", path, ctypes.get_last_error())
            return False
        if attrs & wanted == wanted:
            return True
        if not k32.SetFileAttributesW(str(path), attrs | wanted):
            log.warning("Cannot hide %s (error %s)", path, ctypes.get_last_error())
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - lecteur en lecture seule, etc. : purement cosmétique
        log.warning("Cannot hide %s: %s", path, exc)
        return False


def hide_support_files(start: Optional[Path] = None) -> None:
    """Tout ce qui accompagne l'exe est caché : l'utilisateur ne voit que DJSync.exe."""
    here = Path(start) if start is not None else app_dir()
    for name in (CONTENTS, LEGACY_DATA, "portable.flag", *TOOL_DIRS):
        hide(here / name)


def prepare_environment(start: Optional[Path] = None, hide: bool = True) -> list:
    """Ajoute les dossiers d'outils embarqués au PATH du processus (ffmpeg, deno pour yt-dlp) et
    cache les fichiers d'accompagnement de l'exe."""
    if hide and getattr(sys, "frozen", False) and start is None:
        hide_support_files()
    added = [str(d) for d in tool_dirs(start)]
    if added:
        os.environ["PATH"] = os.pathsep.join(added + [os.environ.get("PATH", "")])
    return added
