"""Mode portable : DJSync.exe posé sur la clé USB, utilisable sur n'importe quel PC.

Est « portable » un DJSync qui :
  * a un fichier `portable.flag` à côté de lui, ou la variable DJSYNC_PORTABLE=1, ou
  * se trouve lui-même sur une clé Rekordbox (un de ses dossiers parents contient
    PIONEER/rekordbox/exportLibrary.db).
Dans ce cas : réglages dans `<dossier de l'exe>/DJSync_Data` (rien dans %APPDATA% du PC hôte), la
clé qui porte l'exe est connectée d'office (les lettres de lecteur changent d'un PC à l'autre),
et les outils posés à côté de l'exe (`tools/` : ffmpeg.exe, ffprobe.exe, deno.exe) sont ajoutés au
PATH — rien à installer sur le PC.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

DB_RELATIVE = Path("PIONEER") / "rekordbox" / "exportLibrary.db"
TOOL_DIRS = ("tools", "ffmpeg", "bin")


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
            or own_drive_root(here) is not None)


def portable_data_dir(start: Optional[Path] = None) -> Optional[Path]:
    here = Path(start) if start is not None else app_dir()
    return here / "DJSync_Data" if is_portable(here) else None


def tool_dirs(start: Optional[Path] = None) -> list:
    here = Path(start) if start is not None else app_dir()
    return [here / d for d in TOOL_DIRS if (here / d).is_dir()]


def prepare_environment(start: Optional[Path] = None) -> list:
    """Ajoute les dossiers d'outils embarqués au PATH du processus (ffmpeg, deno pour yt-dlp)."""
    added = [str(d) for d in tool_dirs(start)]
    if added:
        os.environ["PATH"] = os.pathsep.join(added + [os.environ.get("PATH", "")])
    return added
