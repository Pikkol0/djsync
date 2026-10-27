"""Façade de l'Étape 1 : c'est elle que l'interface (et le contrôleur) appelle."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

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
        old = self._downloader
        self._downloader = Downloader(ffmpeg_location=ffmpeg_location,
                                      audio_format=getattr(old, "audio_format", "m4a"),
                                      normalize=getattr(old, "normalize", False))
        self._downloader.soundcloud_auth = dict(getattr(old, "soundcloud_auth", {}) or {})

    def set_soundcloud_auth(self, auth: Dict[str, Any]) -> None:
        """1.4.0 (C10.1) : compte SoundCloud (cookies d'un navigateur ou jeton) pour le fichier d'origine."""
        self._downloader.soundcloud_auth = dict(auth or {})

    def set_output(self, audio_format: str, normalize: bool) -> None:
        """Format des téléchargements (m4a natif | mp3 320) et normalisation du volume."""
        self._downloader.audio_format = audio_format
        self._downloader.normalize = normalize

    # ---- recherche
    def search(
        self,
        query: str,
        limit: int = 20,
        mode: SearchMode = SearchMode.ALL,
        exclude: Union[ExcludeFilter, str, Iterable[str], None] = None,
        field: str = "all",
        max_seconds: int = 0,
    ) -> List[TrackResult]:
        """Recherche (Titres/Vidéos, filtre de mots, champ, durée) + marquage des doublons."""
        results = self.searcher.search(query, limit=limit, mode=mode, exclude=exclude, field=field,
                                       max_seconds=max_seconds)
        return self._duplicates.annotate([r for r in results if not r.is_album]) + [r for r in results if r.is_album]

    def album_tracks(self, browse_id: str) -> List[TrackResult]:
        """1.2.1 (C09) : titres d'un album + marquage des doublons. Réseau : hors thread UI."""
        return self._duplicates.annotate(self.searcher.album_tracks(browse_id))

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
