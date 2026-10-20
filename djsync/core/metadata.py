"""Métadonnées complémentaires d'un son (V0.3.0) : album, année / date de sortie, genre, label,
numéro de piste, ISRC — tout ce que Rekordbox sait afficher et que YouTube ne donne pas.

Source : l'API publique de Deezer (sans compte ni clé). On cherche « artiste + titre », on garde le
meilleur résultat (titre et artiste proches, durée à ±10 s), puis on lit la piste et son album.
Ne lève jamais : sans réseau ou sans correspondance fiable, le son garde ce qu'il avait.
Les champs déjà renseignés (album YouTube Music…) ne sont pas écrasés.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Dict, Optional

import requests
from rapidfuzz import fuzz

from ..models import TrackResult
from .duplicates import normalize, split_display

log = logging.getLogger(__name__)

API = "https://api.deezer.com"
_session = requests.Session()
# « (Clip officiel) », « [Official Video] », « (Lyrics) »… : retirés avant la recherche
_NOISE = re.compile(r"[\(\[][^\)\]]*(clip|vid.?.?o|lyric|audio|visual|officiel|official|paroles|hd|4k)[^\)\]]*[\)\]]",
                    re.IGNORECASE)


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Remplaçable dans les tests : `metadata._get = fake`."""
    resp = _session.get(API + path, params=params, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise ValueError(str(data["error"]))
    return data


def clean_title(title: str) -> str:
    return re.sub(r"\s{2,}", " ", _NOISE.sub("", title or "")).strip(" -")


def _score(hit: Dict[str, Any], title: str, artist: str, duration: int) -> float:
    t = fuzz.token_set_ratio(normalize(title), normalize(hit.get("title") or ""))
    a = fuzz.token_set_ratio(normalize(artist), normalize((hit.get("artist") or {}).get("name") or "")) if artist else 70
    if duration and hit.get("duration") and abs(int(hit["duration"]) - duration) > 10:
        return 0.0
    return min(t, a) if t >= 80 and a >= 70 else 0.0


def lookup(title: str, artist: str, duration: int = 0) -> Dict[str, Any]:
    """{album, year, release_date, genre, label, track_no, isrc} (clés absentes si inconnues)."""
    title, artist = split_display(title, artist)
    title = clean_title(title)
    if not title:
        return {}
    main_artist = re.split(r",|&| feat\.? | ft\.? | x ", artist or "", maxsplit=1, flags=re.IGNORECASE)[0].strip()
    queries = [f'artist:"{main_artist}" track:"{title}"'] if main_artist else []
    queries.append(f"{main_artist} {title}".strip())
    best, best_score = None, 0.0
    for q in queries:
        for hit in (_get("/search", {"q": q, "limit": 8}).get("data") or []):
            s = _score(hit, title, main_artist, duration)
            if s > best_score:
                best, best_score = hit, s
        if best is not None:
            break
    if best is None:
        return {}
    out: Dict[str, Any] = {}
    track = _get(f"/track/{best['id']}")
    album = track.get("album") or best.get("album") or {}
    if album.get("title"):
        out["album"] = album["title"]
    if track.get("track_position"):
        out["track_no"] = int(track["track_position"])
    if track.get("isrc"):
        out["isrc"] = str(track["isrc"])
    date = track.get("release_date") or ""
    if album.get("id"):
        try:
            full = _get(f"/album/{album['id']}")
            genres = (full.get("genres") or {}).get("data") or []
            if genres and genres[0].get("name"):
                out["genre"] = genres[0]["name"]
            if full.get("label"):
                out["label"] = full["label"]
            date = full.get("release_date") or date
        except Exception as exc:  # noqa: BLE001 - album illisible : piste seule
            log.debug("Deezer album %s: %s", album.get("id"), exc)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date) and not date.startswith("0000"):
        out["release_date"], out["year"] = date, int(date[:4])
    return out


def enrich(track: TrackResult) -> TrackResult:
    """Copie de `track` complétée (album si absent, année, genre, label, n° de piste, ISRC)."""
    try:
        found = lookup(track.title, track.artist, track.duration_seconds)
    except Exception as exc:  # noqa: BLE001 - hors ligne, API indisponible…
        log.info("Metadata lookup failed for %s: %s", track.title, exc)
        return track
    if not found:
        return track
    return replace(
        track,
        album=track.album or found.get("album"),
        year=track.year or found.get("year", 0),
        release_date=track.release_date or found.get("release_date"),
        genre=track.genre or found.get("genre"),
        label=track.label or found.get("label"),
        track_no=track.track_no or found.get("track_no", 0),
        isrc=track.isrc or found.get("isrc"),
    )
