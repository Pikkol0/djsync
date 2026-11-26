"""1.4.4 (B134) : export.pdb gardé ouvert par Rekordbox (clé montée dans son panneau).

Sous Windows, Rekordbox ouvre export.pdb sans autoriser son remplacement : le renommage du fichier
temporaire par-dessus échoue (« Accès refusé »). On le voit sans rien changer : on demande un accès
« suppression » au fichier en partageant tout ; si un autre programme l'a ouvert sans le permettre, Windows
refuse (violation de partage). Ailleurs (macOS, Linux), pas de verrou imposé : toujours libre.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DELETE = 0x00010000
_SHARE_ALL = 0x1 | 0x2 | 0x4                 # lecture, écriture, suppression
_OPEN_EXISTING = 3
_ERROR_SHARING_VIOLATION = 32
_ERROR_ACCESS_DENIED = 5
_ERROR_LOCK_VIOLATION = 33


def pdb_locked(path: Any) -> bool:
    """True si `path` existe et ne peut pas être remplacé maintenant (gardé ouvert par un autre programme)."""
    p = Path(path)
    if sys.platform != "win32" or not p.is_file():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                           wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(p), _DELETE, _SHARE_ALL, None, _OPEN_EXISTING, 0, None)
        invalid = wintypes.HANDLE(-1).value
        if handle in (None, 0, invalid):
            code = ctypes.get_last_error()
            return code in (_ERROR_SHARING_VIOLATION, _ERROR_ACCESS_DENIED, _ERROR_LOCK_VIOLATION)
        kernel32.CloseHandle(handle)
        return False
    except Exception:  # noqa: BLE001 - sonde de confort : en cas de doute, on essaie d'écrire
        log.debug("export.pdb lock probe failed", exc_info=True)
        return False


def is_lock_error(exc: BaseException) -> bool:
    """L'échec d'écriture vient-il d'un fichier gardé ouvert (à refaire plus tard) ?"""
    seen = 0
    while exc is not None and seen < 5:
        if isinstance(exc, PermissionError):
            return True
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (5, 32, 33):
            return True
        text = str(exc).lower()
        if "access is denied" in text or "accès refusé" in text or "being used by another process" in text:
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False


__all__ = ["pdb_locked", "is_lock_error"]
