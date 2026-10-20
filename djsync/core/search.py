"""Recherche sur YouTube Music via ytmusicapi (sans authentification).

* Titres ("songs") et Vidéos sont distingués (TrackResult.result_type).
* Vues : fournies par la recherche pour les vidéos ; pour les titres il faut un appel
  supplémentaire (`fetch_view_count`) que l'application fait en arrière-plan.
* Filtre de mots exclus : `ExcludeFilter` ("remix, live"...).
"""
from __future__ import annotations

import logging
import re
import threading
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Union

from ..models import SearchMode, TrackResult

log = logging.getLogger(__name__)

# ----------------------------------------------------------------- nombre de vues
_MULTIPLIERS = {
    "k": 1_000, "t": 1_000, "tsd": 1_000,
    "m": 1_000_000, "mio": 1_000_000, "mln": 1_000_000,
    "b": 1_000_000_000, "bn": 1_000_000_000, "md": 1_000_000_000, "mrd": 1_000_000_000,
}
_NUMBER = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([a-zà-ÿ]+)?")
_GROUPED = re.compile(r"^\d{1,3}(?:[ ,.]\d{3})+(?!\d)")  # "12,345" / "12 345" / "1.234.567"


def parse_view_count(text: Union[str, int, float, None]) -> Optional[int]:
    """'1.2M views' -> 1200000 ; '845K' -> 845000 ; '12,345 views' -> 12345 ; '88 k vues' -> 88000."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    t = str(text).replace("\xa0", " ").replace(" ", " ").strip().lower()
    if not t:
        return None
    grouped = _GROUPED.match(t)
    if grouped:
        return int(re.sub(r"[ ,.]", "", grouped.group(0)))
    m = _NUMBER.match(t)
    if not m:
        return None
    number = float(m.group(1).replace(",", "."))
    return int(round(number * _MULTIPLIERS.get(m.group(2) or "", 1)))


# ------------------------------------------------------------------- mots exclus
def plain(text: str) -> str:
    """Minuscules, sans accents ni ponctuation (le contenu des parenthèses est CONSERVÉ :
    "Titre (Remix)" doit pouvoir être filtré)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def split_exclusions(text: str) -> List[str]:
    """'remix, live' ou 'remix live' -> ['remix', 'live'] ; 'radio edit, live' -> 2 expressions."""
    parts = re.split(r"[,;\n]+", text) if re.search(r"[,;\n]", text) else text.split()
    return [p.strip() for p in parts if p.strip()]


class ExcludeFilter:
    """Masque les résultats dont le TITRE ou l'ALBUM contient un des mots/expressions (mot entier)."""

    def __init__(self, words: Union[str, Iterable[str], None] = None) -> None:
        if isinstance(words, str):
            words = split_exclusions(words)
        self.words: List[str] = [w for w in (plain(x) for x in (words or [])) if w]

    def __bool__(self) -> bool:
        return bool(self.words)

    def first_hit(self, *texts: Optional[str]) -> Optional[str]:
        hay = " " + " ".join(plain(t) for t in texts if t) + " "
        return next((w for w in self.words if f" {w} " in hay), None)

    def allows(self, track: TrackResult) -> bool:
        return self.first_hit(track.title, track.album) is None


# ------------------------------------------------------------------------ recherche
def _duration_seconds(item: Dict[str, Any]) -> int:
    if item.get("duration_seconds"):
        return int(item["duration_seconds"])
    for key in ("duration", "length"):
        text = item.get(key)
        if isinstance(text, str) and re.fullmatch(r"(\d+:)*\d+", text):
            total = 0
            for part in text.split(":"):
                total = total * 60 + int(part)
            return total
    return 0


def _thumbnail(item: Dict[str, Any]) -> Optional[str]:
    thumbs = item.get("thumbnails") or item.get("thumbnail") or []
    return thumbs[-1].get("url") if thumbs and isinstance(thumbs[-1], dict) else None


def parse_item(item: Dict[str, Any], default_type: str = "song") -> Optional[TrackResult]:
    """Convertit un résultat brut ytmusicapi en TrackResult (None si inexploitable)."""
    video_id = item.get("videoId")
    if not video_id or item.get("isAvailable") is False:
        return None
    result_type = item.get("resultType") or default_type
    artists = item.get("artists") or ([{"name": item["author"]}] if item.get("author") else [])
    artist = ", ".join(a["name"] for a in artists if a and a.get("name")) or "Inconnu"
    album = item.get("album")
    return TrackResult(
        video_id=video_id,
        title=item.get("title") or "Untitled",
        artist=artist,
        album=album.get("name") if isinstance(album, dict) else (album or None),
        duration_seconds=_duration_seconds(item),
        thumbnail_url=_thumbnail(item),
        result_type="song" if result_type == "song" else "video",
        views=parse_view_count(item.get("views")),
        video_type=item.get("videoType"),
    )


def _dedupe(tracks: Iterable[TrackResult]) -> List[TrackResult]:
    seen, out = set(), []
    for t in tracks:
        if t.video_id not in seen:
            seen.add(t.video_id)
            out.append(t)
    return out


class MusicSearcher:
    def __init__(self, client: Any = None) -> None:
        self._yt = client            # injectable (tests)
        self._lock = threading.Lock()

    def _client(self) -> Any:
        """Créé au premier usage (et dans le thread appelant) : l'appli démarre hors ligne."""
        with self._lock:
            if self._yt is None:
                from ytmusicapi import YTMusic

                self._yt = YTMusic()
            return self._yt

    # ---- appels bruts
    def _fetch(self, query: str, kind: str, limit: int) -> List[TrackResult]:
        default = "song" if kind == "songs" else "video"
        raw = self._client().search(query, filter=kind, limit=limit)
        return [t for t in (parse_item(i, default) for i in raw) if t]

    def _artist_tracks(self, query: str, limit: int) -> List[TrackResult]:
        """Mode « Artistes » : on prend l'artiste le plus pertinent et on liste ses morceaux."""
        yt = self._client()
        artists = yt.search(query, filter="artists", limit=3)
        browse_id = next((a.get("browseId") for a in artists if a.get("browseId")), None)
        if not browse_id:
            return []
        info = yt.get_artist(browse_id)
        songs = info.get("songs") or {}
        items = list(songs.get("results") or [])
        if songs.get("browseId") and len(items) < limit:
            try:  # liste complète des titres de l'artiste
                items = yt.get_playlist(songs["browseId"], limit=limit).get("tracks") or items
            except Exception as exc:  # noqa: BLE001 - on garde au moins les titres du résumé
                log.warning("Full artist list unavailable: %s", exc)
        found = [parse_item(i, "song") for i in items]
        videos = (info.get("videos") or {}).get("results") or []
        found += [parse_item(i, "video") for i in videos]
        return [t for t in found if t]

    # ---- API publique
    def search(
        self,
        query: str,
        limit: int = 20,
        mode: SearchMode = SearchMode.ALL,
        exclude: Union[ExcludeFilter, str, Iterable[str], None] = None,
    ) -> List[TrackResult]:
        """Cherche et renvoie des TrackResult (Titres d'abord, puis Vidéos en mode Tout)."""
        query = query.strip()
        if not query:
            return []
        flt = exclude if isinstance(exclude, ExcludeFilter) else ExcludeFilter(exclude)
        fetch = min(limit * 2, 50) if flt else limit  # marge : certains résultats seront masqués

        if mode == SearchMode.SONGS:
            groups = [self._fetch(query, "songs", fetch)]
        elif mode == SearchMode.VIDEOS:
            groups = [self._fetch(query, "videos", fetch)]
        elif mode == SearchMode.ARTISTS:
            groups = [self._artist_tracks(query, fetch)]
        else:
            groups = [self._fetch(query, "songs", fetch), self._fetch(query, "videos", fetch)]

        results: List[TrackResult] = []
        for group in groups:
            results += [t for t in group if flt.allows(t)][:limit]
        results = _dedupe(results)
        log.info("Search %r (%s): %d results", query, mode.value, len(results))
        return results

    def fetch_view_count(self, video_id: str) -> Optional[int]:
        """Nombre de vues/lectures d'un morceau (1 requête). None si indisponible."""
        try:
            details = self._client().get_song(video_id).get("videoDetails") or {}
            return parse_view_count(details.get("viewCount"))
        except Exception as exc:  # noqa: BLE001 - purement informatif, jamais bloquant
            log.debug("Views unavailable for %s: %s", video_id, exc)
            return None
