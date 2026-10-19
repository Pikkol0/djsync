"""Modèles de données partagés entre les modules (aucune dépendance externe)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class SearchMode(str, Enum):
    """Ce que cherche l'utilisateur (menu « Type » du popup Filtres)."""

    ALL = "all"
    SONGS = "songs"
    VIDEOS = "videos"
    ARTISTS = "artists"


SEARCH_MODE_LABELS = {
    SearchMode.ALL: "Tout",
    SearchMode.SONGS: "Titres",
    SearchMode.VIDEOS: "Vidéos",
    SearchMode.ARTISTS: "Artistes",
}


def format_duration(seconds: int) -> str:
    """m:ss (ou h:mm:ss)."""
    m, s = divmod(max(0, int(seconds or 0)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_views(n: Optional[int]) -> str:
    """1 234 -> '1,2 k' ; 1 250 000 -> '1,3 M' ; None -> '—'."""
    if n is None:
        return "—"
    for limit, unit in ((1_000_000_000, "Md"), (1_000_000, "M"), (1_000, "k")):
        if n >= limit:
            value = n / limit
            text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
            return text.replace(".", ",").removesuffix(",0") + f" {unit}"
    return str(n)


@dataclass(frozen=True)
class TrackResult:
    """Un résultat de recherche YouTube Music, prêt à être affiché dans l'UI."""

    video_id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: int = 0
    thumbnail_url: Optional[str] = None

    # "song" = titre officiel (audio du catalogue) ; "video" = clip / upload utilisateur
    result_type: str = "song"
    views: Optional[int] = None          # None = inconnu (les titres n'ont pas de vues dans la recherche)
    video_type: Optional[str] = None     # MUSIC_VIDEO_TYPE_ATV / OMV / UGC (brut, pour information)

    # Renseignés par DuplicateChecker
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None  # ex. "Daft Punk - One More Time"

    @property
    def url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def is_song(self) -> bool:
        return self.result_type == "song"

    @property
    def kind_label(self) -> str:
        return "Titre" if self.is_song else "Vidéo"

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration_seconds)

    @property
    def views_str(self) -> str:
        return format_views(self.views)

    def with_duplicate(self, duplicate_of: str) -> "TrackResult":
        return replace(self, is_duplicate=True, duplicate_of=duplicate_of)

    def with_views(self, views: Optional[int]) -> "TrackResult":
        return replace(self, views=views)


@dataclass(frozen=True)
class DownloadedTrack:
    """Résultat d'un téléchargement réussi."""

    track: TrackResult
    file_path: str


@dataclass
class DownloadProgress:
    """Évènement de progression transmis à l'UI."""

    status: str  # "downloading" | "converting" | "tagging" | "done" | "error"
    percent: float = 0.0
    message: str = field(default="")
