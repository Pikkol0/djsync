"""Lecture d'une playlist / d'un album / d'un titre Spotify, SANS compte ni clé API.

Pourquoi pas l'API officielle : depuis février 2026, `GET /playlists/{id}/items` ne renvoie
que les playlists dont l'utilisateur est propriétaire/collaborateur, et le flux « client
credentials » (sans utilisateur) ne peut donc plus lire une playlist publique quelconque.

Méthode utilisée : la page publique « embed » (celle des lecteurs intégrables), qui contient
la liste des morceaux (100 maximum). C'est une méthode NON OFFICIELLE : si Spotify change le
format de la page, `parse_embed_html` échouera avec un message clair et l'utilisateur pourra
coller sa liste à la main (`parse_text_list`).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator, List, Optional, Tuple

import requests

from ..models import SpotifyPlaylist, SpotifyTrack

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_URL = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}(?:-[a-z]{2})?/)?(?:embed/)?|spotify:)"
    r"(playlist|album|track)[/:]([A-Za-z0-9]{22})"
)
_NEXT_DATA = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
EMBED_TRACK_LIMIT = 100


class SpotifyError(Exception):
    """Message destiné à l'utilisateur."""


def extract_spotify_id(url: str) -> Optional[Tuple[str, str]]:
    """('playlist'|'album'|'track', id) depuis une URL ou une URI Spotify, sinon None."""
    m = _URL.search(url or "")
    return (m.group(1), m.group(2)) if m else None


# ---------------------------------------------------------------------- page embed
def _walk(node: Any) -> Iterator[Any]:
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def _split_artists(subtitle: str) -> Tuple[str, ...]:
    text = (subtitle or "").replace("\xa0", " ")
    return tuple(a.strip() for a in text.split(",") if a.strip())


def _seconds(value: Any) -> int:
    return int(value) // 1000 if isinstance(value, (int, float)) else 0


def _artist_names(node: dict) -> Tuple[str, ...]:
    artists = node.get("artists")
    if isinstance(artists, list) and artists:
        names = [a.get("name") if isinstance(a, dict) else a for a in artists]
        return tuple(str(n).strip() for n in names if n)
    return _split_artists(node.get("subtitle") or "")


def _single_track(data: Any) -> Optional[SpotifyTrack]:
    """Page d'un TITRE unique : on cherche le premier objet « morceau » plausible."""
    for node in _walk(data):
        if not isinstance(node, dict):
            continue
        is_track = node.get("type") == "track" or str(node.get("uri", "")).startswith("spotify:track:")
        title = node.get("name") or node.get("title")
        if is_track and title:
            return SpotifyTrack(
                title=str(title).strip(),
                artists=_artist_names(node),
                duration_seconds=_seconds(node.get("duration") or node.get("duration_ms")),
            )
    return None


def parse_embed_html(html: str) -> SpotifyPlaylist:
    """Extrait nom + morceaux de la page embed (structure recherchée de façon tolérante)."""
    m = _NEXT_DATA.search(html)
    if not m:
        raise SpotifyError(
            "Format de page Spotify non reconnu. Utilisez « Coller une liste » "
            "(une ligne par morceau : Artiste - Titre)."
        )
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        raise SpotifyError("Données Spotify illisibles.") from exc

    entity: Optional[dict] = None
    track_list: Optional[list] = None
    for node in _walk(data):
        if isinstance(node, dict) and isinstance(node.get("trackList"), list):
            entity, track_list = node, node["trackList"]
            break
    if track_list is None:  # structure inconnue : toute liste d'objets {title, subtitle}
        for node in _walk(data):
            if isinstance(node, list) and node and all(
                isinstance(x, dict) and "title" in x and "subtitle" in x for x in node
            ):
                track_list = node
                break

    if not track_list:
        single = _single_track(data)
        if single:
            return SpotifyPlaylist(name=single.title, tracks=[single])
        raise SpotifyError("Aucun morceau trouvé (playlist vide ou privée ?).")

    tracks = []
    for item in track_list:
        title = (item.get("title") or item.get("name") or "").strip()
        if title:
            tracks.append(SpotifyTrack(
                title=title,
                artists=_artist_names(item),
                duration_seconds=_seconds(item.get("duration") or item.get("duration_ms")),
            ))
    name = str((entity or {}).get("name") or (entity or {}).get("title") or "")
    if not name:
        og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html)
        name = og.group(1) if og else "Playlist Spotify"
    return SpotifyPlaylist(name=name, tracks=tracks, truncated=len(tracks) >= EMBED_TRACK_LIMIT)


def fetch_spotify(url: str, session: Optional[requests.Session] = None, timeout: int = 15) -> SpotifyPlaylist:
    """Playlist, album ou titre unique (liste d'un seul morceau)."""
    ref = extract_spotify_id(url)
    if ref is None:
        raise SpotifyError("URL Spotify non reconnue (playlist, album ou titre : https://open.spotify.com/…).")
    kind, spotify_id = ref
    http = session or requests
    try:
        resp = http.get(
            f"https://open.spotify.com/embed/{kind}/{spotify_id}",
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "fr,en;q=0.8"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SpotifyError(f"Spotify injoignable : {exc}") from exc
    if resp.status_code == 404:
        raise SpotifyError("Contenu introuvable ou privé (seuls les contenus publics sont lisibles).")
    if resp.status_code != 200:
        raise SpotifyError(f"Spotify a répondu {resp.status_code}.")
    playlist = parse_embed_html(resp.text)
    playlist.source_url = url
    return playlist


fetch_playlist = fetch_spotify  # nom historique


# ------------------------------------------------------------------ liste collée
_SEP = re.compile(r"\s+[-–—]\s+")


def parse_text_list(text: str, name: str = "Liste collée") -> SpotifyPlaylist:
    """Une ligne par morceau : « Artiste - Titre » (ou « Artiste1, Artiste2 - Titre »)."""
    tracks: List[SpotifyTrack] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*\d+[.)]\s+", "", line).strip()  # numérotation "1. "
        if not line or line.startswith("#"):
            continue
        parts = _SEP.split(line, maxsplit=1)
        if len(parts) == 2:
            tracks.append(SpotifyTrack(title=parts[1].strip(), artists=_split_artists(parts[0])))
        else:
            tracks.append(SpotifyTrack(title=line))
    if not tracks:
        raise SpotifyError("Aucune ligne exploitable.")
    return SpotifyPlaylist(name=name, tracks=tracks)
