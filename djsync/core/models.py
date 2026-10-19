"""Objets renvoyés par le module DB (indépendants de SQLite : l'UI ne voit que ça)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Valeurs de playlist.attribute dans exportLibrary.db
PLAYLIST_KIND = 0
FOLDER_KIND = 1
SMART_PLAYLIST_KIND = 4


@dataclass(frozen=True)
class PlaylistInfo:
    playlist_id: int
    name: str
    parent_id: int          # 0 = racine
    kind: int               # 0 playlist, 1 dossier, 4 playlist intelligente
    sequence: int           # ordre d'affichage parmi ses frères
    track_count: int

    @property
    def is_folder(self) -> bool:
        return self.kind == FOLDER_KIND

    @property
    def is_editable(self) -> bool:
        """Seules les playlists classiques acceptent des ajouts/retraits de sons."""
        return self.kind == PLAYLIST_KIND


@dataclass(frozen=True)
class LibraryTrack:
    content_id: int
    title: str
    artist: str
    album: Optional[str]
    duration_seconds: int
    path: str                       # relatif à la racine de la clé, ex. "/Contents/X/Y/z.mp3"
    bpm: float                      # 0.0 tant que le son n'est pas analysé
    file_type: int
    source_url: Optional[str]       # URL YouTube stockée dans djComment, si connue
    date_added: str
    is_analysed: bool
    artwork_path: Optional[str] = None   # pochette Rekordbox (ex. "/PIONEER/Artwork/00001/b1.jpg")
    sequence: int = 0                    # position dans la playlist (0 hors vue playlist)

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title
