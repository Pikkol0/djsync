"""Import d'une playlist, d'un album ou d'un titre Deezer PUBLIC (1.4.0, C86), sans compte ni clé.

L'API publique de Deezer (déjà utilisée pour les métadonnées, `core/metadata.py`) donne le contenu d'une
playlist publique : `GET https://api.deezer.com/playlist/{id}` (titre, artiste, album, durée), suite des
morceaux par pages (`tracks.next`). Le résultat a la même forme qu'une playlist Spotify : la même
correspondance YouTube Music s'applique ensuite (`core/matcher.py`).

Une playlist privée (ou supprimée) répond par une erreur « no data » : message clair demandant de la
rendre publique. Les liens courts (deezer.page.link, link.deezer.com, dzr.page.link) sont suivis.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

import requests

from ..models import SpotifyPlaylist, SpotifyTrack

API = "https://api.deezer.com"
MAX_TRACKS = 1000
SHORT_HOSTS = ("deezer.page.link", "link.deezer.com", "dzr.page.link")
_URL = re.compile(r"deezer\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(playlist|album|track)/(\d+)", re.IGNORECASE)


class DeezerError(Exception):
    """Message destiné à l'utilisateur. `private` : contenu privé ou introuvable."""

    def __init__(self, message: str, private: bool = False) -> None:
        super().__init__(message)
        self.private = private


def extract_deezer_ref(url: str) -> Optional[Tuple[str, str]]:
    m = _URL.search(url or "")
    return (m.group(1).lower(), m.group(2)) if m else None


def is_short_link(url: str) -> bool:
    return any(h in (url or "").lower() for h in SHORT_HOSTS)


def _track(item: dict) -> Optional[SpotifyTrack]:
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    artist = str((item.get("artist") or {}).get("name") or "").strip()
    album = (item.get("album") or {}).get("title")
    return SpotifyTrack(title=title, artists=(artist,) if artist else (), album=album or None,
                        duration_seconds=int(item.get("duration") or 0))


def _check(data: Any) -> dict:
    if not isinstance(data, dict):
        raise DeezerError("Unreadable Deezer answer.")
    err = data.get("error")
    if err:
        code = int(err.get("code") or 0) if isinstance(err, dict) else 0
        # 800 = « no data » : playlist privée, supprimée ou mauvais identifiant
        raise DeezerError(str(err.get("message") if isinstance(err, dict) else err), private=code in (800, 0))
    return data


def parse_deezer(kind: str, data: dict, pages: Optional[List[dict]] = None) -> SpotifyPlaylist:
    """Contenu lu dans la réponse de l'API (et ses pages suivantes de morceaux)."""
    data = _check(data)
    if kind == "track":
        t = _track(data)
        if t is None:
            raise DeezerError("No track found.")
        return SpotifyPlaylist(name=t.title, tracks=[t])
    items = list((data.get("tracks") or {}).get("data") or [])
    for page in pages or []:
        items += list(page.get("data") or [])
    album = data.get("title") if kind == "album" else None
    tracks = []
    for item in items[:MAX_TRACKS]:
        t = _track(item)
        if t is not None:
            if album and not t.album:
                t = SpotifyTrack(t.title, t.artists, album, t.duration_seconds)
            tracks.append(t)
    if not tracks:
        raise DeezerError("No track found (empty or private playlist?).", private=True)
    total = int(data.get("nb_tracks") or len(items))
    return SpotifyPlaylist(name=str(data.get("title") or "Deezer"), tracks=tracks, truncated=total > len(tracks))


def fetch_deezer(url: str, session: Optional[Any] = None, timeout: int = 15) -> SpotifyPlaylist:
    http = session or requests
    if is_short_link(url):
        try:
            url = http.get(url, timeout=timeout, allow_redirects=True).url
        except requests.RequestException as exc:
            raise DeezerError(f"Deezer unreachable: {exc}") from exc
    ref = extract_deezer_ref(url)
    if ref is None:
        raise DeezerError("Unknown Deezer link (playlist, album or track: https://www.deezer.com/…).")
    kind, ident = ref
    try:
        resp = http.get(f"{API}/{kind}/{ident}", timeout=timeout)
        data = resp.json()
        pages: List[dict] = []
        nxt = (data.get("tracks") or {}).get("next") if isinstance(data, dict) else None
        count = len(((data.get("tracks") or {}).get("data") or [])) if isinstance(data, dict) else 0
        while nxt and count < MAX_TRACKS:
            page = http.get(nxt, timeout=timeout).json()
            pages.append(page)
            count += len(page.get("data") or [])
            nxt = page.get("next")
    except requests.RequestException as exc:
        raise DeezerError(f"Deezer unreachable: {exc}") from exc
    except ValueError as exc:
        raise DeezerError("Unreadable Deezer answer.") from exc
    playlist = parse_deezer(kind, data, pages)
    playlist.source_url = url
    return playlist
