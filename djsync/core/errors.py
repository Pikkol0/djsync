"""Exceptions du module DB : l'interface (Étape 3) pourra afficher leur message tel quel."""
from __future__ import annotations

from typing import Sequence


class LibraryError(Exception):
    """Erreur de base de toutes les opérations sur la bibliothèque."""


class DriveNotFoundError(LibraryError):
    """Aucune clé / aucun lecteur contenant PIONEER\\rekordbox\\exportLibrary.db."""


class AmbiguousDriveError(LibraryError):
    """Plusieurs clés détectées : l'utilisateur doit choisir (onglet Paramètres)."""

    def __init__(self, drives: Sequence[object]) -> None:
        self.drives = list(drives)
        names = ", ".join(str(d) for d in self.drives)
        super().__init__(f"Plusieurs clés détectées ({names}) : choisissez la clé active.")


class DatabaseOpenError(LibraryError):
    """Fichier illisible : mauvaise clé, fichier corrompu, ou ce n'est pas une base OneLibrary."""


class DatabaseLockedError(LibraryError):
    """Base verrouillée par un autre processus (Rekordbox ouvert ?)."""


class ReadOnlyError(LibraryError):
    """Écriture demandée alors que la bibliothèque est ouverte en lecture seule."""


class PlaylistNotFoundError(LibraryError):
    pass


class TrackNotFoundError(LibraryError):
    pass


class DuplicatePlaylistError(LibraryError):
    pass


class UnsupportedFormatError(LibraryError):
    """Format audio que Rekordbox ne gère pas (ou que DJSync ne sait pas décrire)."""
