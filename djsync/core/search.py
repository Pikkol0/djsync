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
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

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

    def albums(self, query: str, limit: int = 12) -> List[TrackResult]:
        """1.2.1 (C09) : albums correspondant à la recherche, une ligne chacun (`result_type` "album",
        `video_id` = identifiant de l'album à ouvrir avec `album_tracks`)."""
        out: List[TrackResult] = []
        for item in self._client().search(query, filter="albums", limit=limit) or []:
            bid = item.get("browseId")
            if not bid:
                continue
            artists = item.get("artists") or []
            artist = ", ".join(a["name"] for a in artists if a and a.get("name")) or ""
            extra = " · ".join(str(x) for x in (item.get("type"), item.get("year")) if x)
            out.append(TrackResult(video_id=bid, title=item.get("title") or "Untitled", artist=artist,
                                   album=extra or None, thumbnail_url=_thumbnail(item), result_type="album"))
        return out[:limit]

    def album_tracks(self, browse_id: str) -> List[TrackResult]:
        """Titres d'un album, dans l'ordre, avec le nom et la pochette de l'album."""
        info = self._client().get_album(browse_id) or {}
        name, thumb = info.get("title"), _thumbnail(info)
        out: List[TrackResult] = []
        for item in info.get("tracks") or []:
            track = parse_item(item, "song")
            if track is None:
                continue
            from dataclasses import replace

            changes: Dict[str, Any] = {}
            if not track.album and name:
                changes["album"] = name
            if not track.thumbnail_url and thumb:
                changes["thumbnail_url"] = thumb
            if track.artist == "Inconnu" and info.get("artists"):
                changes["artist"] = ", ".join(a["name"] for a in info["artists"] if a and a.get("name"))
            out.append(replace(track, **changes) if changes else track)
        return out

    # ---- API publique
    def search(
        self,
        query: str,
        limit: int = 20,
        mode: SearchMode = SearchMode.ALL,
        exclude: Union[ExcludeFilter, str, Iterable[str], None] = None,
        field: str = "all",
        max_seconds: int = 0,
    ) -> List[TrackResult]:
        """Cherche et renvoie des TrackResult (Titres d'abord, puis Vidéos en mode Tout).
        1.2.1 (C08) : `field` = all | title (le titre contient tous les mots) | artist (titres de
        l'artiste, pas ceux qui portent son nom) | album (albums) ; `max_seconds` écarte les mixes."""
        query = query.strip()
        if not query:
            return []
        if field == "album":
            return self.albums(query, limit)
        if field == "artist":
            mode = SearchMode.ARTISTS
        flt = exclude if isinstance(exclude, ExcludeFilter) else ExcludeFilter(exclude)
        narrowing = bool(flt) or field == "title" or max_seconds > 0
        fetch = min(limit * 2, 50) if narrowing else limit  # marge : certains résultats seront masqués
        words = plain(query).split() if field == "title" else []

        def keep(t: TrackResult) -> bool:
            if not flt.allows(t):
                return False
            if words and not all(w in plain(t.title).split() or w in plain(t.title) for w in words):
                return False
            return not (max_seconds > 0 and t.duration_seconds > max_seconds)

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
            results += [t for t in group if keep(t)][:limit]
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


# ======================================================================================
# 1.4.1 (C134, C175) : résultats « Haute qualité » : qualité annoncée et filtre unique (sans interface)
# ======================================================================================
LOSSLESS_EXTS = ("flac", "wav", "aiff", "aif", "alac", "ape", "wv")
FAMILIES = ("lossless", "mp3", "aac", "other")


class Announced:
    """Qualité annoncée d'un résultat, avant téléchargement (C175) : vérifiée après (C46)."""

    def __init__(self, fmt: str = "", kbps: Optional[int] = None, sample_rate: int = 0, bit_depth: int = 0,
                 vbr: bool = False) -> None:
        self.fmt = fmt.upper()
        self.kbps = kbps
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.vbr = vbr

    @property
    def lossless(self) -> bool:
        return self.fmt.lower() in LOSSLESS_EXTS

    @property
    def family(self) -> str:
        f = self.fmt.lower()
        if self.lossless:
            return "lossless"
        if f == "mp3":
            return "mp3"
        if f in ("m4a", "aac", "mp4"):
            return "aac"
        return "other" if f else ""

    @property
    def label(self) -> str:
        """« FLAC 16/44 », « FLAC », « MP3 320 », « MP3 VBR ≈ 245 », « AAC ≈ 128 »."""
        if not self.fmt:
            return ""
        if self.lossless:
            if self.bit_depth and self.sample_rate:
                return f"{self.fmt} {self.bit_depth}/{self.sample_rate / 1000:g}"
            return self.fmt
        if self.kbps:
            return f"{self.fmt} VBR ≈ {self.kbps}" if self.vbr else f"{self.fmt} {self.kbps}"
        return self.fmt

    @property
    def level(self) -> str:
        """« gold » (sans perte annoncé), « silver » (≥ 300 kbps annoncés), sinon ""."""
        if self.lossless:
            return "gold"
        return "silver" if (self.kbps or 0) >= 300 else ""


def announced(track: TrackResult) -> Announced:
    r = getattr(track, "slsk", None)
    if r is not None:
        return Announced(r.ext, r.bitrate or None, r.sample_rate, r.bit_depth, bool(getattr(r, "vbr", False)))
    q = (track.quality or "").strip()
    if q:
        parts = q.split()
        kbps = next((int(p) for p in parts[1:] if p.isdigit()), None)
        return Announced(parts[0], kbps)
    if track.source in ("ytmusic", "youtube"):
        return Announced("m4a", None)
    return Announced()


def source_key(track: TrackResult) -> str:
    return "soulseek" if getattr(track, "slsk", None) is not None else (track.source or "")


@dataclass
class ResultFilter:
    """Filtre des résultats (C134). Champ vide ou à 0 : pas de condition. Valeur inconnue d'un résultat :
    gardé pour la durée (souvent absente chez Soulseek), écarté pour un débit minimum (sauf sans perte)."""

    sources: Tuple[str, ...] = ()              # « archive », « audius », « soulseek », « ytmusic »…
    kind: str = "all"                          # « all », « album », « track »
    families: Tuple[str, ...] = ()             # parmi FAMILIES
    min_kbps: int = 0
    duration_s: int = 0
    tolerance_s: int = 5
    free_slot: bool = False                    # Soulseek : place libre chez le pair
    min_speed_kbs: int = 0                     # Soulseek : vitesse d'envoi minimum (ko/s)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ResultFilter":
        data = dict(data or {})
        out = cls()
        for k in ("sources", "families"):
            if isinstance(data.get(k), (list, tuple)):
                setattr(out, k, tuple(str(x) for x in data[k]))
        if data.get("kind") in ("all", "album", "track"):
            out.kind = data["kind"]
        for k in ("min_kbps", "duration_s", "tolerance_s", "min_speed_kbs"):
            try:
                setattr(out, k, max(0, int(data.get(k, getattr(out, k)))))
            except (TypeError, ValueError):
                pass
        out.free_slot = bool(data.get("free_slot", False))
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"sources": list(self.sources), "kind": self.kind, "families": list(self.families),
                "min_kbps": self.min_kbps, "duration_s": self.duration_s, "tolerance_s": self.tolerance_s,
                "free_slot": self.free_slot, "min_speed_kbs": self.min_speed_kbs}

    @property
    def active(self) -> bool:
        return self.to_dict() != ResultFilter().to_dict()


def passes(track: TrackResult, f: ResultFilter) -> bool:
    """Le résultat passe-t-il le filtre ? (Une ligne d'album passe si l'un de ses titres passe, C147.)"""
    if f.sources and source_key(track) not in f.sources:
        return False
    if f.kind == "album" and not track.is_album:
        return False
    if track.is_album:
        if f.kind == "track":
            return False
        children = list(getattr(track, "tracks", ()) or ())
        return not children or any(passes(c, replace_kind(f)) for c in children)
    if f.kind == "track" and track.is_album:
        return False
    a = announced(track)
    if f.families and a.family not in f.families:
        return False
    if f.min_kbps and not a.lossless and (a.kbps or 0) < f.min_kbps:
        return False
    if f.duration_s and track.duration_seconds and abs(track.duration_seconds - f.duration_s) > f.tolerance_s:
        return False
    r = getattr(track, "slsk", None)
    if r is not None:
        if f.free_slot and not r.free_slot:
            return False
        if f.min_speed_kbs and (r.speed or 0) < f.min_speed_kbs * 1000:
            return False
    return True


def replace_kind(f: ResultFilter) -> ResultFilter:
    from dataclasses import replace as _replace

    return _replace(f, kind="all")


def filter_results(results: Iterable[TrackResult], f: ResultFilter) -> List[TrackResult]:
    return [x for x in results if passes(x, f)]
