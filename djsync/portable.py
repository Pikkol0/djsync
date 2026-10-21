"""Mode portable : DJSync.exe posé sur la clé USB, utilisable sur n'importe quel PC.

Est « portable » un DJSync qui :
  * a un fichier `portable.flag` à côté de lui, ou la variable DJSYNC_PORTABLE=1, ou
  * se trouve lui-même sur une clé Rekordbox (un de ses dossiers parents contient
    PIONEER/rekordbox/exportLibrary.db).
Dans ce cas : réglages dans `<dossier de l'exe>/DJSync_Data` (rien dans %APPDATA% du PC hôte), la
clé qui porte l'exe est connectée d'office (les lettres de lecteur changent d'un PC à l'autre),
et les outils posés à côté de l'exe (`tools/` : ffmpeg.exe, ffprobe.exe, deno.exe) sont ajoutés au
PATH — rien à installer sur le PC.

Un seul fichier visible (V0.5.0) : l'exe Windows est construit en mode « dossier » (démarrage
rapide, rien à décompresser à chaque lancement depuis une clé lente) mais tout ce qui l'accompagne
— bibliothèques, outils, réglages — vit dans le dossier `.djsync` à côté de lui, marqué « caché »
au premier lancement. L'utilisateur ne voit que DJSync.exe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

DB_RELATIVE = Path("PIONEER") / "rekordbox" / "exportLibrary.db"
TOOL_DIRS = ("tools", "ffmpeg", "bin")
CONTENTS = ".djsync"                      # dossier caché de l'exe (PyInstaller contents_directory)
LEGACY_DATA = "DJSync_Data"


def app_dir() -> Path:
    """Dossier de l'exécutable (PyInstaller) ou de la racine du projet (développement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
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
    return (os.environ.get("DJSYNC_PORTABLE") == "1" or (here / "portable.flag").exists()
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
    return [base / d for base in (here / CONTENTS, here) for d in TOOL_DIRS if (base / d).is_dir()]


def hide(path: Path) -> bool:
    """Attribut Windows « caché » (le point en tête de nom suffit ailleurs). Sans effet si absent."""
    if sys.platform != "win32" or not path.exists():
        return False
    try:
        import ctypes

        FILE_ATTRIBUTE_HIDDEN = 0x2
        get = ctypes.windll.kernel32.GetFileAttributesW
        attrs = get(str(path))
        if attrs == -1 or attrs == 0xFFFFFFFF:
            return False
        if attrs & FILE_ATTRIBUTE_HIDDEN:
            return True
        return bool(ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN))
    except Exception:  # noqa: BLE001 - lecteur en lecture seule, etc. : purement cosmétique
        return False


def hide_support_files(start: Optional[Path] = None) -> None:
    """Tout ce qui accompagne l'exe est caché : l'utilisateur ne voit que DJSync.exe."""
    here = Path(start) if start is not None else app_dir()
    for name in (CONTENTS, LEGACY_DATA, "portable.flag", *TOOL_DIRS):
        hide(here / name)


def prepare_environment(start: Optional[Path] = None) -> list:
    """Ajoute les dossiers d'outils embarqués au PATH du processus (ffmpeg, deno pour yt-dlp) et
    cache les fichiers d'accompagnement de l'exe."""
    if getattr(sys, "frozen", False) and start is None:
        hide_support_files()
    added = [str(d) for d in tool_dirs(start)]
    if added:
        os.environ["PATH"] = os.pathsep.join(added + [os.environ.get("PATH", "")])
    return added
