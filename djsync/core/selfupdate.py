"""Mise à jour de DJSync depuis l'application (1.2.0-rc.4, C20).

Réglages ▸ « Mettre à jour vers X » : DJSync télécharge le fichier de la release pour ce système,
vérifie son empreinte SHA-256 (fichier `.sha256` publié à côté), le prépare À CÔTÉ de la version en
cours, puis, après « Redémarrer », un petit script attend la fermeture de DJSync, échange les deux
versions et relance la nouvelle. La version précédente est gardée jusqu'au lancement suivant
(`cleanup`) : en cas d'échec de l'échange, le script la remet en place.

  * Windows : DJSync.exe (lanceur un seul fichier, chemin dans DJSYNC_LAUNCHER). Le lanceur voit
    une nouvelle version embarquée et réextrait `.djsync/app` ; `.djsync/data` est conservé.
  * macOS : DJSync.app (image .dmg montée sans fenêtre, app copiée à côté). Un fichier téléchargé
    par DJSync lui-même n'est pas mis en quarantaine. Les données sont à côté de l'app.
  * Linux : dossier DJSync (archive .tar.gz) ; ses réglages (`DJSync/.djsync`) passent dans le
    nouveau dossier.
Depuis les sources (développement), rien n'est remplacé : la page de la release s'ouvre.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .updates import Update

log = logging.getLogger("djsync.update")

NEW_TAG = ".update-new"           # suffixe de la version préparée (à côté de l'actuelle)
OLD_TAG = ".update-old"           # suffixe de la version remplacée (effacée au lancement suivant)
CHUNK = 256 * 1024


class UpdateError(Exception):
    """Téléchargement, vérification ou préparation impossible (message pour l'utilisateur)."""


@dataclass(frozen=True)
class Plan:
    kind: str                     # "windows" | "mac" | "linux"
    target: Path                  # DJSync.exe | DJSync.app | dossier DJSync


def plan(frozen: Optional[bool] = None, executable: Optional[str] = None,
         platform: Optional[str] = None, launcher: Optional[str] = None) -> Optional[Plan]:
    """Ce qu'il faut remplacer pour cette installation, ou None (depuis les sources : impossible)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return None
    platform = platform or sys.platform
    exe_dir = Path(executable or sys.executable).resolve().parent
    if platform == "win32":
        path = launcher if launcher is not None else os.environ.get("DJSYNC_LAUNCHER")
        return Plan("windows", Path(path)) if path and Path(path).is_file() else None
    if platform == "darwin":
        if exe_dir.name == "MacOS" and exe_dir.parent.name == "Contents" and exe_dir.parent.parent.suffix == ".app":
            return Plan("mac", exe_dir.parent.parent)
        return None
    if (exe_dir / "_internal").is_dir():
        return Plan("linux", exe_dir)
    return None


def staged_path(p: Plan) -> Path:
    return p.target.with_name(p.target.name + NEW_TAG)


def old_path(p: Plan) -> Path:
    return p.target.with_name(p.target.name + OLD_TAG)


# ---------------------------------------------------------------------------------- download
def _session_get(url: str, stream: bool = False):
    import requests

    resp = requests.get(url, timeout=30, stream=stream, headers={"User-Agent": "DJSync"})
    resp.raise_for_status()
    return resp


def expected_sha256(update: Update, get: Optional[Callable[[str], bytes]] = None) -> str:
    if not update.checksum:
        raise UpdateError("no_checksum")
    text = (get(update.checksum) if get else _session_get(update.checksum).content).decode("ascii", "replace")
    digest = text.strip().split()[0].lower() if text.strip() else ""
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise UpdateError("no_checksum")
    return digest


def download(update: Update, dest_dir: Path, progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None,
             opener: Optional[Callable[[str], object]] = None,
             get: Optional[Callable[[str], bytes]] = None) -> Path:
    """Télécharge le fichier de la release dans `dest_dir` et vérifie son SHA-256. Hors thread UI."""
    if not update.asset:
        raise UpdateError("no_asset")
    want = expected_sha256(update, get)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = update.asset.rsplit("/", 1)[-1] or "DJSync-update"
    part = dest_dir / (name + ".part")
    resp = (opener or (lambda u: _session_get(u, stream=True)))(update.asset)
    total = int(getattr(resp, "headers", {}).get("content-length") or 0)
    h = hashlib.sha256()
    done = 0
    try:
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(CHUNK):
                if cancelled is not None and cancelled():
                    raise UpdateError("cancelled")
                if not chunk:
                    continue
                fh.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if h.hexdigest() != want:
        part.unlink(missing_ok=True)
        log.warning("Update %s: SHA-256 mismatch (got %s, expected %s)", update.version, h.hexdigest(), want)
        raise UpdateError("bad_checksum")
    out = dest_dir / name
    os.replace(part, out)
    log.info("Update %s downloaded and verified: %s (%d bytes)", update.version, out, done)
    return out


# ---------------------------------------------------------------------------------- staging
def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass


def prepare(p: Plan, downloaded: Path) -> Path:
    """Installe la nouvelle version À CÔTÉ de l'actuelle (même disque : l'échange est un simple
    renommage). Renvoie son chemin."""
    staged = staged_path(p)
    _remove(staged)
    if p.kind == "windows":
        shutil.copy2(downloaded, staged)
    elif p.kind == "mac":
        _prepare_mac(downloaded, staged)
    else:
        _prepare_linux(downloaded, staged)
    if not staged.exists():
        raise UpdateError("prepare_failed")
    return staged


def _prepare_mac(dmg: Path, staged: Path) -> None:
    mnt = Path(tempfile.mkdtemp(prefix="djsync-dmg-"))
    try:
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mnt), str(dmg)],
                       check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("prepare_failed") from exc
    try:
        app = next((c for c in mnt.iterdir() if c.suffix == ".app"), None)
        if app is None:
            raise UpdateError("prepare_failed")
        subprocess.run(["ditto", str(app), str(staged)], check=True, capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("prepare_failed") from exc
    finally:
        subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"], capture_output=True, timeout=60)
        shutil.rmtree(mnt, ignore_errors=True)


def _prepare_linux(archive: Path, staged: Path) -> None:
    tmp = staged.with_name(staged.name + ".x")
    _remove(tmp)
    tmp.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar.getmembers():          # pas de chemin absolu ni de « .. »
                if m.name.startswith("/") or ".." in Path(m.name).parts:
                    raise UpdateError("prepare_failed")
            try:
                tar.extractall(tmp, filter="tar")
            except TypeError:                   # Python < 3.12 sans filtre
                tar.extractall(tmp)
        inner = tmp / "DJSync"
        if not (inner / "DJSync").exists():
            raise UpdateError("prepare_failed")
        os.replace(inner, staged)
    except (OSError, tarfile.TarError) as exc:
        raise UpdateError("prepare_failed") from exc
    finally:
        _remove(tmp)


# ---------------------------------------------------------------------------------- swap
def _q(path: Path) -> str:
    return "'" + str(path).replace("'", "'\\''") + "'"


def _bat(p: Plan, staged: Path, pids: Sequence[int]) -> str:
    target, old = p.target, old_path(p)
    lines = ["@echo off", "chcp 65001 >nul", "set n=0", ":wait"]
    for pid in pids:
        lines.append(f'tasklist /FI "PID eq {pid}" /NH | find "{pid}" >nul && goto busy')
    lines += ["goto go", ":busy", "set /a n+=1", "if %n% geq 120 goto go", "ping -n 2 127.0.0.1 >nul", "goto wait",
              ":go", "ping -n 2 127.0.0.1 >nul",
              f'if exist "{old}" del /f /q "{old}"',
              f'move /y "{target}" "{old}" >nul || goto fail',
              f'move /y "{staged}" "{target}" >nul || (move /y "{old}" "{target}" >nul & goto fail)',
              f'start "" "{target}"',
              'del /f /q "%~f0"', "exit /b 0",
              ":fail", f'start "" "{target}"', 'del /f /q "%~f0"']
    return "\r\n".join(lines) + "\r\n"


def _sh(p: Plan, staged: Path, pids: Sequence[int]) -> str:
    target, old = p.target, old_path(p)
    alive = " || ".join(f"kill -0 {pid} 2>/dev/null" for pid in pids) or "false"
    if p.kind == "mac":
        launch = f"open {_q(target)}"
        carry = ""
    else:
        launch = f"(cd {_q(target)} && nohup ./DJSync >/dev/null 2>&1 &)"
        # réglages de la version portable Linux : DJSync/.djsync et l'ancien DJSync/DJSync_Data
        carry = "".join(f"[ -e {_q(target / n)} ] && [ ! -e {_q(staged / n)} ] && mv {_q(target / n)} {_q(staged / n)}\n"
                        for n in (".djsync", "DJSync_Data", "portable.flag"))
    return ("#!/bin/sh\n"
            f"i=0\nwhile ( {alive} ) && [ $i -lt 120 ]; do sleep 1; i=$((i+1)); done\nsleep 1\n"
            f"rm -rf {_q(old)}\n"
            f"{carry}"
            f"if mv {_q(target)} {_q(old)}; then\n"
            f"  if ! mv {_q(staged)} {_q(target)}; then mv {_q(old)} {_q(target)}; fi\n"
            "fi\n"
            f"{launch}\n"
            'rm -f -- "$0"\n')


def schedule_swap(p: Plan, staged: Path, pids: Optional[List[int]] = None, run: bool = True) -> Path:
    """Écrit et lance le script qui échange les versions une fois DJSync fermé. Renvoie le script."""
    pids = pids or [os.getpid()]
    tmp = Path(tempfile.gettempdir())
    if p.kind == "windows":
        script = tmp / f"djsync-update-{os.getpid()}.bat"
        script.write_text(_bat(p, staged, pids), encoding="utf-8")
        if run:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=str(tmp), creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        script = tmp / f"djsync-update-{os.getpid()}.sh"
        script.write_text(_sh(p, staged, pids), encoding="utf-8")
        if run:
            subprocess.Popen(["/bin/sh", str(script)], cwd=str(tmp), start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Update scheduled after exit: %s -> %s", staged, p.target)
    return script


def cleanup(p: Optional[Plan] = None) -> None:
    """Au lancement : efface la version remplacée et une préparation abandonnée."""
    p = p if p is not None else plan()
    if p is None:
        return
    for path in (old_path(p), staged_path(p), staged_path(p).with_name(staged_path(p).name + ".x")):
        if path.exists():
            _remove(path)
            log.info("Removed leftover from an update: %s", path)


def download_dir() -> Path:
    from ..settings import settings_dir

    return settings_dir() / "update"
