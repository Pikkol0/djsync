"""« Retirer DJSync de cette clé » (V1.2.0) : désinstallation depuis l'application elle-même.

Ce qui est retiré, et RIEN d'autre : le programme (DJSync.exe, DJSync.app ou le dossier DJSync de
Linux), le dossier caché .djsync (application extraite, réglages, journal) et l'ancien DJSync_Data.
La musique (Contents), la bibliothèque Rekordbox (PIONEER) et, sauf demande, les sauvegardes
(DJSync_Backups) restent sur la clé. Option : remettre d'abord la bibliothèque d'origine.

Un programme ne peut pas effacer ses propres fichiers pendant qu'il tourne (Windows) : un petit
script, lancé à part, attend que DJSync soit fermé puis les supprime, et se supprime lui-même.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from . import portable

log = logging.getLogger(__name__)

PROTECTED = ("PIONEER", "Contents", "DJSync_Backups")


def targets(app_dir: Optional[Path] = None, frozen: Optional[bool] = None) -> List[Path]:
    """Fichiers et dossiers de DJSync à supprimer (ceux qui existent)."""
    here = Path(app_dir) if app_dir is not None else portable.app_dir()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    out: List[Path] = []
    if frozen:
        exe_dir = Path(sys.executable).resolve().parent
        launcher = os.environ.get("DJSYNC_LAUNCHER")
        bundle = portable.mac_bundle(exe_dir)
        if launcher:                                        # Windows : DJSync.exe (lanceur un-seul-fichier)
            out.append(Path(launcher))
        elif bundle is not None:                            # macOS : DJSync.app
            out.append(bundle)
        elif sys.platform.startswith("linux") and (exe_dir / "_internal").is_dir():
            out.append(exe_dir)                             # Linux : le dossier DJSync extrait du .tar.gz
    for name in (portable.CONTENTS, portable.LEGACY_DATA):
        out.append(here / name)
    safe: List[Path] = []
    for p in out:
        if not p.exists() or p in safe:
            continue
        if p.is_dir() and any((p / name).exists() for name in PROTECTED):
            log.warning("Not removed (contains music or the library): %s", p)
            continue
        safe.append(p)
    return safe


def keep_computer_backups(data_dir: Optional[Path], backup_dir: Path) -> None:
    """Sauvegardes de la bibliothèque de l'ordinateur (master.db), rangées dans .djsync/data :
    déplacées dans DJSync_Backups/Ordinateur pour ne pas disparaître avec DJSync."""
    src = Path(data_dir) / "Backups" if data_dir is not None else None
    if src is None or not src.is_dir() or not any(src.iterdir()):
        return
    dest = Path(backup_dir) / "Ordinateur"
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if not target.exists():
            shutil.move(str(item), str(target))


def _bat(pid: int, paths: Sequence[Path]) -> str:
    lines = ["@echo off", "chcp 65001 >nul", "set n=0", ":wait",
             f'tasklist /FI "PID eq {pid}" /NH | find "{pid}" >nul || goto go',
             "set /a n+=1", "if %n% geq 90 goto go", "ping -n 2 127.0.0.1 >nul", "goto wait", ":go",
             "ping -n 2 127.0.0.1 >nul"]
    for _ in range(3):                                      # fichier encore verrouillé : on réessaie
        for p in paths:
            if p.is_dir():
                lines += [f'attrib -h -s -r "{p}" /s /d >nul 2>&1', f'rmdir /s /q "{p}" 2>nul']
            else:
                lines.append(f'del /f /q "{p}" 2>nul')
        lines.append("ping -n 2 127.0.0.1 >nul")
    lines.append('del /f /q "%~f0"')
    return "\r\n".join(lines) + "\r\n"


def _sh(pid: int, paths: Sequence[Path]) -> str:
    quoted = " ".join("'" + str(p).replace("'", "'\\''") + "'" for p in paths)
    return (f"#!/bin/sh\ni=0\nwhile kill -0 {pid} 2>/dev/null && [ $i -lt 90 ]; do sleep 1; i=$((i+1)); done\n"
            f"sleep 1\nrm -rf -- {quoted}\nrm -f -- \"$0\"\n")


def schedule_removal(paths: Sequence[Path], pid: Optional[int] = None, run: bool = True) -> Path:
    """Écrit et lance le script qui supprime `paths` une fois DJSync fermé. Renvoie le script."""
    pid = pid or os.getpid()
    tmp = Path(tempfile.gettempdir())
    if sys.platform == "win32":
        script = tmp / f"djsync-uninstall-{pid}.bat"
        script.write_text(_bat(pid, paths), encoding="utf-8")
        if run:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=str(tmp), creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        script = tmp / f"djsync-uninstall-{pid}.sh"
        script.write_text(_sh(pid, paths), encoding="utf-8")
        if run:
            subprocess.Popen(["/bin/sh", str(script)], cwd=str(tmp), start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Uninstall scheduled after exit: %s", ", ".join(str(p) for p in paths))
    return script
