"""1.3.2 (C70) : lancer DJSync depuis la recherche de Windows, Spotlight (macOS) ou le menu des
applications (Linux), sans rien installer.

DJSync est portable (un seul fichier, souvent sur la clé) : rien n'est inscrit dans le système, donc la
recherche ne le trouve pas. Sur demande (Paramètres ▸ DJSync, ou l'accueil du premier lancement), on pose
un simple raccourci vers l'exécutable en cours :
  * Windows : DJSync.lnk dans le menu Démarrer de l'utilisateur (trouvé par la recherche Windows même
    sans indexation des fichiers) ;
  * macOS   : alias de DJSync.app dans ~/Applications (Spotlight, Launchpad) ;
  * Linux   : djsync.desktop dans ~/.local/share/applications (menus et recherche de GNOME / KDE).
Pas de droits administrateur. Le raccourci est remis à jour à chaque lancement (la lettre de la clé peut
changer) et retiré quand on décoche l'option. Clé absente : le système dit que la cible est introuvable.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)
NAME = "DJSync"


def target() -> Optional[Path]:
    """Ce que le raccourci doit lancer ; None depuis les sources (pas d'exécutable à pointer)."""
    launcher = os.environ.get("DJSYNC_LAUNCHER")          # Windows : DJSync.exe (lanceur un seul fichier)
    if launcher and Path(launcher).is_file():
        return Path(launcher)
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable)
    if sys.platform == "darwin":
        app = next((p for p in exe.parents if p.suffix == ".app"), None)
        return app
    return exe


def location(platform: str = sys.platform, home: Optional[Path] = None) -> Path:
    home = home or Path.home()
    if platform == "win32":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{NAME}.lnk"
    if platform == "darwin":
        return home / "Applications" / f"{NAME}.app"
    return home / ".local" / "share" / "applications" / "djsync.desktop"


def _no_window() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def create(dest: Optional[Path] = None, exe: Optional[Path] = None, icon: Optional[Path] = None,
           platform: str = sys.platform) -> Path:
    """Pose (ou remet à jour) le raccourci. Lève OSError si impossible."""
    exe = exe or target()
    if exe is None:
        raise OSError("DJSync runs from its source code: no program to point the shortcut to.")
    dest = dest or location(platform)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if platform == "win32":
        script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(dest))});"
                  f"$s.TargetPath={_ps_quote(str(exe))};$s.WorkingDirectory={_ps_quote(str(exe.parent))};"
                  f"$s.IconLocation={_ps_quote(str(exe) + ',0')};$s.Description='DJSync';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                       timeout=30, creationflags=_no_window(), capture_output=True)
    elif platform == "darwin":
        if dest.is_dir() and not dest.is_symlink():
            raise OSError(f"{dest} is a real application: left untouched.")
        remove(dest, platform)
        try:                                               # vrai alias Finder (trouvé par Spotlight)
            subprocess.run(["osascript", "-e", f'tell application "Finder" to make alias file to POSIX file '
                            f'"{exe}" at POSIX file "{dest.parent}"'], check=True, timeout=30, capture_output=True)
            made = dest.parent / exe.name
            if made != dest and made.exists():
                made.rename(dest)
        except (OSError, subprocess.SubprocessError):
            os.symlink(exe, dest)                          # repli : lien symbolique
    else:
        lines = ["[Desktop Entry]", "Type=Application", f"Name={NAME}",
                 "Comment=Music for Rekordbox USB drives, without Rekordbox",
                 f'Exec="{exe}"', f"Path={exe.parent}", "Terminal=false", "Categories=AudioVideo;Audio;"]
        if icon is not None and icon.is_file():
            lines.append(f"Icon={icon}")
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        dest.chmod(0o755)
    log.info("Shortcut %s -> %s", dest, exe)
    return dest


def remove(dest: Optional[Path] = None, platform: str = sys.platform) -> bool:
    dest = dest or location(platform)
    try:
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
            return True
        if dest.is_dir() and platform == "darwin":       # alias Finder vu comme dossier : jamais un vrai .app
            return False
    except OSError as exc:
        log.info("Shortcut not removed (%s): %s", dest, exc)
    return False


def exists(platform: str = sys.platform) -> bool:
    dest = location(platform)
    return dest.exists() or dest.is_symlink()
