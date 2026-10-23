"""Module DB : accès à la bibliothèque Rekordbox d'une clé USB (exportLibrary.db)."""
from .base import LibraryBackend
from .errors import (
    AmbiguousDriveError,
    DatabaseLockedError,
    DatabaseOpenError,
    DriveNotFoundError,
    DuplicatePlaylistError,
    LibraryError,
    PlaylistNotFoundError,
    ReadOnlyError,
    TrackNotFoundError,
    UnsupportedFormatError,
)
from ..models import LibraryTrack, PlaylistInfo
from .usb import UnpreparedDrive, UsbDrive, drive_from_letter, find_unprepared_drives, find_usb_drives, resolve_drive
from .usb_library import PdbStatus, RekordboxUsbLibrary, extract_video_id

__all__ = [
    "LibraryBackend", "RekordboxUsbLibrary", "PdbStatus", "LibraryTrack", "PlaylistInfo",
    "UsbDrive", "UnpreparedDrive", "find_usb_drives", "find_unprepared_drives", "drive_from_letter", "resolve_drive", "extract_video_id",
    "LibraryError", "DriveNotFoundError", "AmbiguousDriveError", "DatabaseOpenError",
    "DatabaseLockedError", "ReadOnlyError", "PlaylistNotFoundError", "TrackNotFoundError",
    "DuplicatePlaylistError", "UnsupportedFormatError",
]
