"""Import des playlists publiques d'Apple Music, Tidal et Amazon Music (1.4.3, C94 ; C184 fusionnée).

Comme pour Spotify et Deezer, DJSync ne lit que la liste (titre, artiste, album, durée) d'une playlist, d'un
album ou d'un titre PUBLIC, sans compte ; chaque son est ensuite cherché sur YouTube Music (`core/matcher.py`).

* Apple Music : la page publique (music.apple.com/…/playlist/…, /album/…) contient ses données en JSON
  (`serialized-server-data`, sinon `application/ld+json`) ; 300 sons au plus, ce que la page donne.
* Tidal : API publique du site (api.tidal.com, jeton public du lecteur web), par pages de 100 ;
  2 000 sons au plus.
* Amazon Music : la page publique, quand elle porte sa liste en `application/ld+json` ; sinon message clair
  (Amazon ne donne pas toujours la liste sans compte).

Aucune de ces sources n'a de clé à demander ni de serveur DJSync : si un service change sa page, l'import de
ce service s'arrête avec un message, le reste de DJSync n'est pas touché.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..models import SpotifyPlaylist, SpotifyTrack

MAX_TRACKS = 2000
TIDAL_API = "https://api.tidal.com/v1"
TIDAL_TOKEN = "CzET4vdadNUFQ5JU"          # jeton public du lecteur web de Tidal (pas un compte)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.8"}

APPLE_HOSTS = ("music.apple.com", "embed.music.apple.com", "itunes.apple.com")
TIDAL_HOSTS = ("tidal.com", "listen.tidal.com", "embed.tidal.com")
AMAZON_HOSTS = ("music.amazon.com", "music.amazon.fr", "music.amazon.de", "music.amazon.co.uk", "music.amazon.it",
                "music.amazon.es", "music.amazon.ca", "music.amazon.co.jp", "amazon.com", "amazon.fr")

_TIDAL_URL = re.compile(r"tidal\.com/(?:browse/)?(?:[a-z]{2}/)?(playlist|album|track)s?/([0-9a-f-]{6,})", re.I)
_JSON_SCRIPT = re.compile(r'<script[^>]*(?:id="serialized-server-data"|type="application/(?:ld\+)?json")[^>]*>(.*?)'
                          r"</script>", re.S | re.I)


class StreamingImportError(Exception):
    """Message pour l'utilisateur. `private` : contenu privé, supprimé ou illisible sans compte."""

    def __init__(self, message: str, private: bool = False) -> None:
        super().__init__(message)
        self.private = private


def service_of(host: str) -> Optional[str]:
    host = host.lower().removeprefix("www.")
    if host in APPLE_HOSTS:
        return "apple"
    if host in TIDAL_HOSTS:
        return "tidal"
    if host in AMAZON_HOSTS and host.startswith("music."):
        return "amazon"
    return None


def _get(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
    import requests

    resp = requests.get(url, headers={**HEADERS, **(headers or {})}, params=params, timeout=20)
    if resp.status_code in (401, 403, 404):
        raise StreamingImportError(f"HTTP {resp.status_code}", private=True)
    resp.raise_for_status()
    return resp


# --------------------------------------------------------------------------------- outils
def _iso_duration(text: Any) -> int:
    """« PT3M25S » -> 205."""
    m = re.match(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", str(text or ""))
    if not m:
        return 0
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + int(float(s or 0))


def _walk(node: Any) -> Iterable[Dict[str, Any]]:
    stack = [node]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            yield x
            stack.extend(reversed(list(x.values())))
        elif isinstance(x, list):
            stack.extend(reversed(x))


def _scripts(page: str) -> List[Any]:
    out = []
    for raw in _JSON_SCRIPT.findall(page):
        try:
            out.append(json.loads(html.unescape(raw.strip())))
        except ValueError:
            continue
    return out


def _title_of(page: str) -> str:
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page) or re.search(r"<title>(.*?)</title>", page, re.S)
    return html.unescape(m.group(1)).split(" - ")[0].split(" | ")[0].strip() if m else ""


def _ld_tracks(data: Any) -> Tuple[str, List[SpotifyTrack]]:
    """Liste schema.org (MusicPlaylist / MusicAlbum : `track`, MusicRecording)."""
    name, tracks = "", []
    for d in _walk(data):
        kind = d.get("@type")
        if kind in ("MusicPlaylist", "MusicAlbum") and not name:
            name = str(d.get("name") or "")
        if kind == "MusicRecording" and d.get("name"):
            by = d.get("byArtist")
            artists = [a.get("name") for a in (by if isinstance(by, list) else [by]) if isinstance(a, dict) and a.get("name")]
            album = (d.get("inAlbum") or {}).get("name") if isinstance(d.get("inAlbum"), dict) else None
            tracks.append(SpotifyTrack(str(d["name"]), tuple(artists), album, _iso_duration(d.get("duration"))))
    return name, tracks


# --------------------------------------------------------------------------------- Apple Music
def parse_apple(page: str) -> SpotifyPlaylist:
    name, tracks = "", []
    scripts = _scripts(page)
    for data in scripts:                                  # données du site (titre, artistName, durée en ms)
        for d in _walk(data):
            if d.get("title") and d.get("artistName") and ("duration" in d or "contentDescriptor" in d):
                tracks.append(SpotifyTrack(str(d["title"]), (str(d["artistName"]),),
                                           d.get("tertiaryLinks", [{}])[0].get("title") if isinstance(d.get("tertiaryLinks"), list) and d.get("tertiaryLinks") else None,
                                           int((d.get("duration") or 0) / 1000)))
    if not tracks:
        for data in scripts:
            n, tr = _ld_tracks(data)
            name = name or n
            tracks += tr
    tracks = _dedupe(tracks)
    if not tracks:
        raise StreamingImportError("No track found in the Apple Music page (public playlist?).", private=True)
    return SpotifyPlaylist(name=name or _title_of(page) or "Apple Music", tracks=tracks[:MAX_TRACKS],
                           truncated=len(tracks) > MAX_TRACKS)


def _dedupe(tracks: List[SpotifyTrack]) -> List[SpotifyTrack]:
    """Une même ligne peut apparaître deux fois dans les données de la page (liste + aperçu)."""
    seen, out = set(), []
    for t in tracks:
        key = (t.title.casefold(), t.artist.casefold(), t.duration_seconds)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def fetch_apple(url: str, get: Callable = _get) -> SpotifyPlaylist:
    page = get(url).text
    playlist = parse_apple(page)
    playlist.source_url = url
    return playlist


# --------------------------------------------------------------------------------- Tidal
def tidal_ref(url: str) -> Optional[Tuple[str, str]]:
    m = _TIDAL_URL.search(url or "")
    return (m.group(1).lower(), m.group(2)) if m else None


def _tidal_track(item: Dict[str, Any]) -> Optional[SpotifyTrack]:
    t = item.get("item") if isinstance(item.get("item"), dict) else item
    if item.get("type") not in (None, "track") or not t.get("title"):
        return None
    title = str(t["title"]) + (f" ({t['version']})" if t.get("version") else "")
    artists = tuple(a.get("name") for a in t.get("artists") or [] if a.get("name")) or \
        ((t.get("artist") or {}).get("name"),)
    return SpotifyTrack(title, tuple(a for a in artists if a), (t.get("album") or {}).get("title"),
                        int(t.get("duration") or 0))


def fetch_tidal(url: str, get: Callable = _get, country: str = "US") -> SpotifyPlaylist:
    ref = tidal_ref(url)
    if ref is None:
        raise StreamingImportError("Unknown Tidal link (playlist, album or track: https://tidal.com/…).")
    kind, ident = ref
    head = {"x-tidal-token": TIDAL_TOKEN}
    base = {"countryCode": country}
    if kind == "track":
        t = _tidal_track(get(f"{TIDAL_API}/tracks/{ident}", head, base).json())
        if t is None:
            raise StreamingImportError("No track found.", private=True)
        return SpotifyPlaylist(name=t.title, tracks=[t], source_url=url)
    meta = get(f"{TIDAL_API}/{kind}s/{ident}", head, base).json()
    total = int(meta.get("numberOfTracks") or 0)
    tracks: List[SpotifyTrack] = []
    offset = 0
    while offset < MAX_TRACKS:
        page = get(f"{TIDAL_API}/{kind}s/{ident}/items", head, {**base, "limit": 100, "offset": offset}).json()
        items = page.get("items") or []
        tracks += [t for t in (_tidal_track(i) for i in items) if t is not None]
        offset += 100
        if not items or offset >= int(page.get("totalNumberOfItems") or total or 0):
            break
    if not tracks:
        raise StreamingImportError("No track found (empty or private playlist?).", private=True)
    return SpotifyPlaylist(name=str(meta.get("title") or "Tidal"), tracks=tracks[:MAX_TRACKS],
                           truncated=(total or len(tracks)) > len(tracks[:MAX_TRACKS]), source_url=url)


# --------------------------------------------------------------------------------- Amazon Music
def parse_amazon(page: str) -> SpotifyPlaylist:
    name, tracks = "", []
    for data in _scripts(page):
        n, tr = _ld_tracks(data)
        name = name or n
        tracks += tr
    tracks = _dedupe(tracks)
    if not tracks:
        raise StreamingImportError("Amazon Music did not give the list without an account.", private=True)
    return SpotifyPlaylist(name=name or _title_of(page) or "Amazon Music", tracks=tracks[:MAX_TRACKS],
                           truncated=len(tracks) > MAX_TRACKS)


def fetch_amazon(url: str, get: Callable = _get) -> SpotifyPlaylist:
    playlist = parse_amazon(get(url).text)
    playlist.source_url = url
    return playlist


def fetch(service: str, url: str, get: Callable = _get) -> SpotifyPlaylist:
    try:
        return {"apple": fetch_apple, "tidal": fetch_tidal, "amazon": fetch_amazon}[service](url, get=get)
    except StreamingImportError:
        raise
    except Exception as exc:  # noqa: BLE001 - réseau, page changée
        raise StreamingImportError(f"{service}: {exc}") from exc
