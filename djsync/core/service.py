"""Façade de l'Étape 1 : c'est elle que l'interface (et le contrôleur) appelle."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from ..models import Candidate, DownloadedTrack, ResolvedUrl, SearchMode, SpotifyPlaylist, SpotifyTrack, TrackResult, UrlKind
from .downloader import Downloader, ProgressCallback
from .duplicates import DuplicateChecker, FakeLibrary, LibraryProvider
from .matcher import SpotifyMatcher
from .search import ExcludeFilter, MusicSearcher
from .spotify import fetch_spotify
from .urlimport import classify_url, resolve_direct


class MusicService:
    def __init__(
        self,
        library: Optional[LibraryProvider] = None,
        ffmpeg_location: Optional[str] = None,
        searcher: Optional[MusicSearcher] = None,
        downloader: Optional[Downloader] = None,
    ) -> None:
        self._searcher = searcher
        self._searcher_lock = threading.Lock()
        self._duplicates = DuplicateChecker(library or FakeLibrary())
        self._downloader = downloader or Downloader(ffmpeg_location=ffmpeg_location)
        self._views: Dict[str, Optional[int]] = {}

    @property
    def searcher(self) -> MusicSearcher:
        with self._searcher_lock:
            if self._searcher is None:
                self._searcher = MusicSearcher()
            return self._searcher

    # ---- configuration à chaud (changement de clé, de dossier FFmpeg)
    def set_library(self, library: Optional[LibraryProvider]) -> None:
        """Branche la bibliothèque d'une clé ; None = aucune clé (pas de détection de doublons)."""
        if library is None:
            self._duplicates.set_library(FakeLibrary())
            return
        self._duplicates.set_library(library, exact_lookup=getattr(library, "find_by_source_url", None))

    def set_ffmpeg_location(self, ffmpeg_location: Optional[str]) -> None:
        self._downloader = Downloader(ffmpeg_location=ffmpeg_location)

    # ---- recherche
    def search(
        self,
        query: str,
        limit: int = 20,
        mode: SearchMode = SearchMode.ALL,
        exclude: Union[ExcludeFilter, str, Iterable[str], None] = None,
    ) -> List[TrackResult]:
        """Recherche (Titres/Vidéos, filtre de mots) + marquage des doublons."""
        results = self.searcher.search(query, limit=limit, mode=mode, exclude=exclude)
        return self._duplicates.annotate(results)

    def fetch_views(self, video_id: str) -> Optional[int]:
        """Vues d'un morceau (mises en cache). Appel réseau : à lancer hors thread UI."""
        if video_id not in self._views:
            self._views[video_id] = self.searcher.fetch_view_count(video_id)
        return self._views[video_id]

    def annotate(self, tracks: Iterable[TrackResult]) -> List[TrackResult]:
        return self._duplicates.annotate(tracks)

    # ---- import Spotify
    def match_spotify(self, source: SpotifyTrack, per_type: int = 5) -> List[Candidate]:
        """Candidats YouTube Music (Titres + Vidéos) triés par score, doublons marqués."""
        candidates = SpotifyMatcher(self.searcher).find_candidates(source, per_type=per_type)
        annotated = self._duplicates.annotate([c.track for c in candidates])
        return [Candidate(t, c.score) for t, c in zip(annotated, candidates)]

    # ---- import par URL
    @staticmethod
    def classify_url(url: str) -> UrlKind:
        return classify_url(url)

    def fetch_spotify(self, url: str) -> SpotifyPlaylist:
        """Playlist / album / titre Spotify (réseau : hors thread UI)."""
        return fetch_spotify(url)

    def resolve_direct(self, url: str) -> ResolvedUrl:
        """YouTube / SoundCloud : morceaux listés par yt-dlp, doublons marqués, SANS recherche."""
        resolved = resolve_direct(url)
        resolved.tracks = self._duplicates.annotate(resolved.tracks)
        return resolved

    # ---- téléchargement
    def download(
        self,
        track: TrackResult,
        dest_dir: Union[str, Path],
        on_progress: Optional[ProgressCallback] = None,
        tag: bool = True,
    ) -> DownloadedTrack:
        return self._downloader.download(track, dest_dir, on_progress, tag=tag)

    def refresh_library(self) -> None:
        """À appeler après un ajout/suppression en base."""
        self._duplicates.refresh()
