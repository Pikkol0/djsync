"""Contrat commun à toutes les bibliothèques (clé USB aujourd'hui, base locale du PC demain).

L'interface graphique ne dépend que de `LibraryBackend` : pour gérer la base locale de
Rekordbox (master.db) plus tard, il suffira d'écrire une seconde classe qui l'implémente.
Il étend `LibraryProvider` (djsync.core.duplicates) : le détecteur de doublons de l'Étape 1
s'y branche directement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ContextManager, Iterable, List, Optional, Sequence, Tuple

from .models import LibraryTrack, PlaylistInfo


class LibraryBackend(ABC):
    # ---- contrat LibraryProvider (Étape 1)
    @abstractmethod
    def iter_tracks(self) -> Iterable[Tuple[str, str]]: ...

    # ---- playlists
    @abstractmethod
    def list_playlists(self) -> List[PlaylistInfo]: ...
    @abstractmethod
    def create_playlist(self, name: str, parent_id: int = 0) -> PlaylistInfo: ...
    @abstractmethod
    def rename_playlist(self, playlist_id: int, new_name: str) -> None: ...
    @abstractmethod
    def delete_playlist(self, playlist_id: int) -> None: ...

    # ---- sons
    @abstractmethod
    def list_tracks(self) -> List[LibraryTrack]: ...
    @abstractmethod
    def get_playlist_tracks(self, playlist_id: int) -> List[LibraryTrack]: ...
    @abstractmethod
    def find_by_source_url(self, url_or_video_id: str) -> Optional[LibraryTrack]: ...
    @abstractmethod
    def add_track(
        self,
        file_path: Path,
        title: str,
        artist: str,
        album: Optional[str] = None,
        source_url: Optional[str] = None,
        playlist_ids: Sequence[int] = (),
    ) -> LibraryTrack: ...
    @abstractmethod
    def delete_track(self, content_id: int, delete_file: bool = True) -> bool:
        """Renvoie True si le fichier physique a bien été supprimé."""
        ...

    # ---- contenu des playlists
    @abstractmethod
    def add_to_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> int: ...
    @abstractmethod
    def remove_from_playlist(self, playlist_id: int, content_ids: Sequence[int]) -> None: ...
    @abstractmethod
    def move_tracks(
        self, content_ids: Sequence[int], from_playlist_id: int, to_playlist_id: int
    ) -> None: ...
    @abstractmethod
    def reorder_track(self, playlist_id: int, content_id: int, new_position: int) -> None: ...
    @abstractmethod
    def set_playlist_order(self, playlist_id: int, content_ids: Sequence[int]) -> None:
        """Enregistre l'ordre par défaut (champ sequence) d'une playlist."""
        ...
    @abstractmethod
    def batch(self) -> ContextManager[None]:
        """Regroupe plusieurs écritures sous une seule sauvegarde."""
        ...
