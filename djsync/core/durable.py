"""1.4.3 (A7-4) : écriture sûre d'un fichier sur une clé, sur tous les systèmes de fichiers d'une clé de DJ.

Repris de Sleeve (https://github.com/alii/sleeve, GPL-2.0-or-later, crates/rbl-core/src/durable.rs), avec ses
constats :
  * sous macOS, `os.fsync` ne vide pas le cache du disque : il faut `fcntl(F_FULLFSYNC)`. Apple ne le prend
    en charge que sur HFS, FAT, UDF et APFS : sur une clé exFAT il répond ENOTSUP (erreur 45). On fait alors
    comme SQLite : un `fsync` ordinaire (les données arrivent sur la clé ; seule la barrière du cache manque) ;
  * après un renommage, le dossier est vidé lui aussi (Unix) ; macOS refuse ce vidage sur exFAT (ENOTSUP) :
    ce n'est pas une raison de dire qu'une écriture terminée a échoué.
"""
from __future__ import annotations

import errno
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# macOS : ENOTSUP 45, EOPNOTSUPP 102 ; Linux : EOPNOTSUPP / ENOTSUP 95 ; ENOSYS partout
_UNSUPPORTED = {45, 102, 95, getattr(errno, "ENOTSUP", 95), getattr(errno, "EOPNOTSUPP", 95),
                getattr(errno, "ENOSYS", 38), getattr(errno, "EINVAL", 22)}


def unsupported(exc: BaseException) -> bool:
    """Le système de fichiers ne sait pas faire l'opération (par opposition à un échec)."""
    return isinstance(exc, OSError) and (exc.errno in _UNSUPPORTED or isinstance(exc, NotImplementedError))


def flush_fd(fd: int, full: Optional[Callable[[int], Any]] = None) -> None:
    """Vide les données et métadonnées du fichier jusqu'au disque. macOS : F_FULLFSYNC, puis `fsync` si le
    système de fichiers ne le prend pas en charge (exFAT). Toute autre erreur remonte."""
    if full is None and sys.platform == "darwin":
        import fcntl

        flag = getattr(fcntl, "F_FULLFSYNC", 51)
        full = lambda f: fcntl.fcntl(f, flag)            # noqa: E731
    if full is None:
        os.fsync(fd)
        return
    try:
        full(fd)
    except OSError as exc:
        if not unsupported(exc):
            raise
        log.debug("Full flush not supported here (%s): plain fsync", exc)
        os.fsync(fd)


def flush(fh: Any) -> None:
    """`fh.flush()` puis `flush_fd` : à la place de `os.fsync(fh.fileno())` avant un remplacement atomique."""
    fh.flush()
    flush_fd(fh.fileno())


def sync_dir(path: Any) -> None:
    """Vide les entrées d'un dossier (après un renommage), sous Unix. Un refus « non pris en charge » (exFAT sous
    macOS) est ignoré ; les autres erreurs sont notées au journal sans faire échouer une écriture terminée."""
    if os.name == "nt":
        return
    try:
        fd = os.open(str(Path(path)), os.O_RDONLY)
    except OSError as exc:
        log.debug("Folder not opened for flush %s: %s", path, exc)
        return
    try:
        flush_fd(fd)
    except OSError as exc:
        if unsupported(exc):
            log.debug("Folder flush not supported on %s: %s", path, exc)
        else:
            log.info("Folder not flushed %s: %s", path, exc)
    finally:
        os.close(fd)


def replace(tmp: Any, target: Any) -> None:
    """`os.replace` puis vidage du dossier."""
    os.replace(tmp, target)
    sync_dir(Path(target).parent)
