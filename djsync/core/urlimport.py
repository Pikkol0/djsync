"""Import par URL : reconnaît la source et prépare un téléchargement DIRECT (sans recherche).

  * Spotify    -> traité par core/spotify.py + core/matcher.py (correspondance YouTube Music) ;
  * YouTube    -> yt-dlp lit la vidéo / la playlist telle quelle ;
  * SoundCloud -> idem (titre, set/playlist, page d'artiste).

Pour YouTube/SoundCloud on utilise l'extraction « à plat » de yt-dlp : une seule requête
liste toute la playlist (titre, durée, vignette, vues) sans résoudre chaque vidéo.
"""
from __future__ import annotations

from dataclasses import dataclass

import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..models import ResolvedUrl, TrackResult, UrlKind

MAX_ENTRIES = 200

_YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "youtube-nocookie.com"}
_SOUNDCLOUD_HOSTS = {"soundcloud.com", "m.soundcloud.com", "on.soundcloud.com", "snd.sc"}
_DEEZER_SHORT = {"deezer.page.link", "dzr.page.link"}


@dataclass(frozen=True)
class Source:
    """1.3.2 (C101) : une source acceptée par l'import par lien (affichée dans l'onglet Import)."""

    key: str                  # clé de traduction : import.src_<key> (ce qui est lu)
    name: str                 # nom du service (non traduit)
    color: str                # point de couleur de la pastille (pas de logo de marque embarqué)
    example: str              # exemple de lien
    limit: int = 0            # nombre maximal de morceaux lus (0 : pas de limite propre)


# Une seule source de vérité : `classify_url` ci-dessous reconnaît exactement ces services (test).
SOURCES = (
    Source("spotify", "Spotify", "#1DB954", "open.spotify.com/playlist/…", 100),
    Source("deezer", "Deezer", "#A238FF", "deezer.com/playlist/… · link.deezer.com/…", 1000),   # 1.4.0 (C86)
    Source("youtube", "YouTube", "#FF0033", "youtube.com/watch?v=… · youtu.be/…", MAX_ENTRIES),
    Source("ytmusic", "YouTube Music", "#FF0033", "music.youtube.com/playlist?list=…", MAX_ENTRIES),
    Source("soundcloud", "SoundCloud", "#FF5500", "soundcloud.com/…/sets/…", MAX_ENTRIES),
)


def source_names() -> str:
    """« Spotify, YouTube, YouTube Music, SoundCloud » (messages et champ de lien, C101)."""
    return ", ".join(x.name for x in SOURCES)


class UrlImportError(Exception):
    """Message destiné à l'utilisateur."""


def _host(url: str) -> str:
    text = url.strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return parsed.netloc.lower().split(":")[0].removeprefix("www.")


def classify_url(url: str) -> UrlKind:
    text = (url or "").strip()
    if not text:
        return UrlKind.UNKNOWN
    if text.lower().startswith("spotify:"):
        return UrlKind.SPOTIFY
    host = _host(text)
    if host == "spotify.com" or host.endswith(".spotify.com"):
        return UrlKind.SPOTIFY
    if host in _YOUTUBE_HOSTS:
        return UrlKind.YOUTUBE
    if host in _SOUNDCLOUD_HOSTS:
        return UrlKind.SOUNDCLOUD
    if host == "deezer.com" or host.endswith(".deezer.com") or host in _DEEZER_SHORT:   # 1.4.0 (C86)
        return UrlKind.DEEZER
    return UrlKind.UNKNOWN


def source_of(kind: UrlKind) -> str:
    return "soundcloud" if kind == UrlKind.SOUNDCLOUD else "youtube"


# ------------------------------------------------------------------ titre / artiste
_TOPIC = re.compile(r"\s*-\s*Topic$", re.IGNORECASE)
_VEVO = re.compile(r"\s*VEVO$", re.IGNORECASE)
_ARTIST_TITLE = re.compile(r"^(.+?)\s[-–—]\s(.+)$")


def clean_channel(name: str) -> str:
    return _VEVO.sub("", _TOPIC.sub("", name or "")).strip()


def guess_artist_title(entry: Dict[str, Any]) -> Tuple[str, str]:
    """Meilleur (artiste, titre) : métadonnées musicales de yt-dlp si présentes, sinon
    « Artiste - Titre » dans le titre de la vidéo, sinon la chaîne/l'uploader."""
    artist, track = entry.get("artist") or entry.get("creator"), entry.get("track")
    if artist and track:
        return str(artist), str(track)
    title = str(entry.get("title") or "Untitled").strip()
    m = _ARTIST_TITLE.match(title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    uploader = clean_channel(str(entry.get("uploader") or entry.get("channel") or ""))
    return (uploader or "Inconnu"), title


def _thumbnail(entry: Dict[str, Any], video_id: str, kind: UrlKind) -> Optional[str]:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = [t for t in (entry.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    if thumbs:
        return thumbs[-1]["url"]
    if kind == UrlKind.YOUTUBE and len(video_id) == 11:
        return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    return None


def entry_to_track(entry: Dict[str, Any], kind: UrlKind) -> Optional[TrackResult]:
    """Une entrée yt-dlp -> TrackResult téléchargeable (None si privée/supprimée/inexploitable)."""
    video_id = str(entry.get("id") or "")
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or ""
    title = str(entry.get("title") or "")
    if not video_id or not url.startswith("http") or title in ("[Private video]", "[Deleted video]"):
        return None
    if kind == UrlKind.YOUTUBE and len(video_id) == 11:
        url = f"https://www.youtube.com/watch?v={video_id}"  # lien canonique, sans paramètres de playlist
    artist, name = guess_artist_title(entry)
    channel = str(entry.get("uploader") or entry.get("channel") or "")
    is_audio = kind == UrlKind.SOUNDCLOUD or bool(_TOPIC.search(channel)) or bool(entry.get("track"))
    views = entry.get("view_count")
    return TrackResult(
        video_id=video_id,
        title=name,
        artist=artist,
        album=entry.get("album") or None,
        duration_seconds=int(entry.get("duration") or 0),
        thumbnail_url=_thumbnail(entry, video_id, kind),
        result_type="song" if is_audio else "video",
        views=int(views) if isinstance(views, (int, float)) else None,
        source=source_of(kind),
        source_url=url,
    )


# ------------------------------------------------------------------ résolution (yt-dlp)
def _single_video_of_playlist_url(url: str) -> bool:
    """watch?v=X&list=Y : l'utilisateur veut la vidéo X (pas toute la liste Y)."""
    query = parse_qs(urlparse(url if "://" in url else f"https://{url}").query)
    return "v" in query and "list" in query


def resolve_direct(
    url: str,
    kind: Optional[UrlKind] = None,
    limit: int = MAX_ENTRIES,
    extractor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
) -> ResolvedUrl:
    """Liste les morceaux d'une URL YouTube/SoundCloud (1 vidéo ou toute une playlist).

    `extractor(url, opts) -> info` est injectable pour les tests ; par défaut yt-dlp.
    """
    url = url.strip()
    kind = kind or classify_url(url)
    if kind not in (UrlKind.YOUTUBE, UrlKind.SOUNDCLOUD):
        raise UrlImportError("URL not supported for a direct download (YouTube or SoundCloud).")

    single = kind == UrlKind.YOUTUBE and _single_video_of_playlist_url(url)
    opts: Dict[str, Any] = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": "in_playlist", "playlistend": limit, "noplaylist": single,
    }
    try:
        if extractor is not None:
            info = extractor(url, opts)
        else:
            import yt_dlp

            from .engine import ydl_options

            with yt_dlp.YoutubeDL(ydl_options(**opts)) as ydl:
                info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001 - yt-dlp lève des erreurs variées (réseau, privé, supprimé…)
        text = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace("ERROR: ", "").strip()
        raise UrlImportError(f"Cannot read: {text[:300] or 'URL not recognised by yt-dlp.'}") from exc
    if not info:
        raise UrlImportError("Nothing to import at this address.")

    is_playlist = info.get("_type") == "playlist" or "entries" in info
    entries: List[Dict[str, Any]] = [e for e in (info.get("entries") or []) if e] if is_playlist else [info]
    tracks = [t for t in (entry_to_track(e, kind) for e in entries) if t]
    if not tracks:
        raise UrlImportError("No playable track (private, deleted or empty content).")

    seen, unique = set(), []
    for t in tracks:  # une playlist peut contenir le même morceau deux fois
        if t.video_id not in seen:
            seen.add(t.video_id)
            unique.append(t)
    return ResolvedUrl(
        kind=kind,
        name=str(info.get("title") or (unique[0].title if len(unique) == 1 else "Import")),
        tracks=unique,
        source_url=url,
        is_playlist=is_playlist,
        note="Video + playlist link: only the video is imported." if single else "",
        truncated=is_playlist and len(entries) >= limit,
    )
