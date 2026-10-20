"""Détection des clés USB contenant une bibliothèque Rekordbox (OneLibrary).

Automatique : on parcourt les lecteurs et on garde ceux qui contiennent
`PIONEER\\rekordbox\\exportLibrary.db`. Manuel : `drive_from_letter("E")` force un lecteur.
On ne filtre PAS sur "amovible" : un SSD externe est vu comme disque fixe par Windows.
"""
from __future__ import annotations

import logging
import os
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

from .errors import AmbiguousDriveError, DriveNotFoundError

log = logging.getLogger(__name__)

DB_RELATIVE_PATH = Path("PIONEER") / "rekordbox" / "exportLibrary.db"

# GetDriveTypeW
_DRIVE_REMOVABLE, _DRIVE_FIXED = 2, 3
_SEM_FAILCRITICALERRORS = 0x0001


@dataclass(frozen=True)
class UsbDrive:
    root: Path                      # ex. Path("E:/")
    label: str = ""                 # nom du volume ("DJ_USB")
    is_removable: bool = False

    @property
    def db_path(self) -> Path:
        return self.root / DB_RELATIVE_PATH

    @property
    def letter(self) -> str:
        """"E" sous Windows ; chaîne vide ailleurs."""
        return self.root.drive[:1].upper() if os.name == "nt" else ""

    def __str__(self) -> str:
        shown = f"{self.letter}:" if self.letter else str(self.root)
        return f"{shown} ({self.label})" if self.label else shown


# --------------------------------------------------------------------- Windows
def _windows_roots() -> Iterator[Path]:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    bitmask = kernel32.GetLogicalDrives()
    # Évite la boîte de dialogue "Insérez un disque" sur les lecteurs de cartes vides.
    previous = kernel32.SetErrorMode(_SEM_FAILCRITICALERRORS)
    try:
        for i, letter in enumerate(string.ascii_uppercase):
            if not bitmask & (1 << i):
                continue
            root = f"{letter}:\\"
            if kernel32.GetDriveTypeW(root) in (_DRIVE_REMOVABLE, _DRIVE_FIXED):
                yield Path(root)
    finally:
        kernel32.SetErrorMode(previous)


def _windows_info(root: Path) -> tuple[str, bool]:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    label = ctypes.create_unicode_buffer(261)
    previous = kernel32.SetErrorMode(_SEM_FAILCRITICALERRORS)
    try:
        ok = kernel32.GetVolumeInformationW(str(root), label, 261, None, None, None, None, 0)
        removable = kernel32.GetDriveTypeW(str(root)) == _DRIVE_REMOVABLE
    finally:
        kernel32.SetErrorMode(previous)
    return (label.value if ok else ""), removable


# ---------------------------------------------------------- macOS / Linux (dev)
def _posix_roots() -> Iterator[Path]:
    for base, depth in (("/Volumes", 1), ("/media", 2), ("/run/media", 2), ("/mnt", 1)):
        level = [Path(base)]
        for _ in range(depth):
            level = [c for p in level if p.is_dir() for c in _safe_iterdir(p)]
        yield from (p for p in level if p.is_dir())


def _safe_iterdir(path: Path) -> List[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


# ------------------------------------------------------------------- API publique
def _make_drive(root: Path) -> UsbDrive:
    if os.name == "nt":
        label, removable = _windows_info(root)
        return UsbDrive(root, label, removable)
    return UsbDrive(root, root.name)


def find_usb_drives() -> List[UsbDrive]:
    """Tous les lecteurs qui contiennent une bibliothèque Rekordbox exportée."""
    roots = _windows_roots() if os.name == "nt" else _posix_roots()
    drives: List[UsbDrive] = []
    for root in roots:
        try:
            if (root / DB_RELATIVE_PATH).is_file():
                drives.append(_make_drive(root))
        except OSError as exc:  # lecteur illisible : on l'ignore
            log.debug("Drive %s skipped: %s", root, exc)
    return drives


def drive_from_letter(value: str) -> UsbDrive:
    """Force un lecteur : "E", "e:", "E:\\" (Windows) ou un chemin de dossier (tests/Linux)."""
    value = value.strip().strip('"')
    bare = value.rstrip(":\\/")
    if os.name == "nt" and len(bare) == 1:
        root = Path(bare.upper() + ":\\")
    else:
        root = Path(value)

    db_path = root / DB_RELATIVE_PATH
    if not db_path.is_file():
        raise DriveNotFoundError(f"No Rekordbox library found: {db_path} does not exist.")
    return _make_drive(root)


def resolve_drive(forced: Optional[str] = None, preferred: Optional[str] = None) -> UsbDrive:
    """Choisit la clé à utiliser.

    forced    : lettre/chemin imposé par l'utilisateur (prioritaire, jamais deviné).
    preferred : dernière clé utilisée (mémorisée dans les Paramètres), si encore branchée.
    Lève DriveNotFoundError (aucune clé) ou AmbiguousDriveError (plusieurs, sans préférence).
    """
    if forced:
        return drive_from_letter(forced)

    drives = find_usb_drives()
    if not drives:
        raise DriveNotFoundError(
            "No Rekordbox drive detected (PIONEER\\rekordbox\\exportLibrary.db). "
            "Plug in the drive or set its letter in Settings."
        )
    if preferred:
        wanted = preferred.strip().rstrip(":\\/").upper()
        for d in drives:
            if d.letter == wanted or str(d.root) == preferred:
                return d
    if len(drives) == 1:
        return drives[0]
    raise AmbiguousDriveError(drives)
