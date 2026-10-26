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
from typing import Any, Dict, List, Optional, Tuple

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


_ARTIST_SPLIT = re.compile(r",|&| feat\.? | ft\.? | x |\bet\b", re.IGNORECASE)
_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
SURE = 90


def _names(artist: str) -> List[str]:
    return [n.strip() for n in _ARTIST_SPLIT.split(artist or "") if n.strip()]


def queries(title: str, artist: str) -> List[Tuple[str, List[str]]]:
    """1.3.0 (C25) : recherches Deezer à essayer dans l'ordre, chacune avec les noms d'artistes qui
    servent à juger les résultats ([] = titre seul, jugé sur la durée)."""
    names = _names(artist)
    bare = _BRACKETS.sub("", title).strip() or title
    out: List[Tuple[str, List[str]]] = []
    if names:
        out.append((f'artist:"{names[0]}" track:"{title}"', names))
        out.append((f"{names[0]} {title}", names))
        for n in names[1:3]:                                   # chaque artiste invité
            out.append((f'artist:"{n}" track:"{bare}"', names))
        if bare != title:
            out.append((f"{names[0]} {bare}", names))
    if " - " in bare:                                         # « Titre - Artiste » inversé
        a, b = (x.strip() for x in bare.split(" - ", 1))
        out.append((f'artist:"{b}" track:"{a}"', [b] + names))
        out.append((f'artist:"{a}" track:"{b}"', [a] + names))
    out.append((bare, []))                                     # titre seul : jugé sur la durée
    seen, uniq = set(), []
    for q, n in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append((q, n))
    return uniq


def score_hit(hit: Dict[str, Any], title: str, names: List[str], duration: int) -> float:
    """0-100. Avec artiste : titre ≥ 80 et artiste ≥ 70 (durée à ± 10 s). Titre seul : durée à ± 3 s
    exigée et score plafonné sous « sûr » (toujours à vérifier)."""
    ht = normalize(hit.get("title") or "")
    t1 = fuzz.token_set_ratio(normalize(title), ht)
    t2 = fuzz.token_set_ratio(normalize(_BRACKETS.sub("", title)), normalize(_BRACKETS.sub("", hit.get("title") or "")))
    tscore = max(t1, t2)
    gap = abs(int(hit.get("duration") or 0) - duration) if duration and hit.get("duration") else None
    if names:
        hit_artist = normalize((hit.get("artist") or {}).get("name") or "")
        a = max(fuzz.token_set_ratio(normalize(n), hit_artist) for n in names)
        if gap is not None and gap > 10:
            return 0.0
        return float(min(tscore, a)) if tscore >= 80 and a >= 70 else 0.0
    if gap is None or gap > 3 or tscore < 90:
        return 0.0
    return min(float(tscore), SURE - 5.0)


def _light(hit: Dict[str, Any], score: float) -> Dict[str, Any]:
    album = hit.get("album") or {}
    return {"id": hit.get("id"), "title": hit.get("title_short") or hit.get("title") or "",
            "artists": [(hit.get("artist") or {}).get("name") or ""], "album": album.get("title") or "",
            "cover": album.get("cover_medium") or album.get("cover_big") or "", "duration": int(hit.get("duration") or 0),
            "score": round(score)}


def details_for(track_id: Any, score: float = 100.0) -> Dict[str, Any]:
    """Tout ce que l'Uniformiser propose pour une piste Deezer choisie : {title, artists (principal puis
    invités), album, year, release_date, genre, label, track_no, isrc, cover, score, sure}."""
    track = _get(f"/track/{track_id}")
    album = track.get("album") or {}
    out: Dict[str, Any] = {"title": track.get("title_short") or track.get("title") or "",
                           "score": round(score), "sure": score >= SURE, "id": track_id}
    names = [c.get("name") for c in (track.get("contributors") or []) if c.get("name")]
    main = (track.get("artist") or {}).get("name")
    out["artists"] = list(dict.fromkeys(([main] if main else []) + [n for n in names if n != main]))
    if album.get("title"):
        out["album"] = album["title"]
    cover = album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium")
    if cover:
        out["cover"] = cover
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
        except Exception as exc:  # noqa: BLE001
            log.debug("Deezer album %s: %s", album.get("id"), exc)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date) and not date.startswith("0000"):
        out["release_date"], out["year"] = date, int(date[:4])
    return out


def match(title: str, artist: str, duration: int = 0, cleaned: bool = False) -> Dict[str, Any]:
    """Meilleure correspondance Deezer (1.2.2, recherche en cascade depuis la 1.3.0) avec tout ce que
    l'Uniformiser propose (voir `details_for`) et `candidates` : les 5 meilleurs résultats vus (légers).
    {} sans correspondance. Peut lever (réseau)."""
    import time

    if not cleaned:
        title, artist = split_display(title, artist)
        title = clean_title(title)
    if not title:
        return {}
    best, best_score = None, 0.0
    seen: Dict[Any, Dict[str, Any]] = {}
    for i, (q, names) in enumerate(queries(title, artist)):
        if i:
            time.sleep(0.08)                                   # Deezer : ~50 requêtes / 5 s
        for hit in (_get("/search", {"q": q, "limit": 8}).get("data") or []):
            sc = score_hit(hit, title, names, duration)
            if sc > 0 and (hit.get("id") not in seen or seen[hit.get("id")]["score"] < sc):
                seen[hit.get("id")] = _light(hit, sc)
            if sc > best_score:
                best, best_score = hit, sc
        if best_score >= SURE:
            break
    if best is None:
        return {}
    out = details_for(best["id"], best_score)
    out["candidates"] = sorted(seen.values(), key=lambda c: -c["score"])[:5]
    return out


def search_candidates(text: str, duration: int = 0, limit: int = 5) -> List[Dict[str, Any]]:
    """« Chercher autrement » (C25) : recherche libre, résultats légers classés (texte + durée)."""
    text = (text or "").strip()
    if not text:
        return []
    out = []
    for hit in (_get("/search", {"q": text, "limit": 15}).get("data") or []):
        label_ = f"{(hit.get('artist') or {}).get('name') or ''} {hit.get('title') or ''}"
        sc = float(fuzz.token_set_ratio(normalize(text), normalize(label_)))
        if duration and hit.get("duration"):
            gap = abs(int(hit["duration"]) - duration)
            sc -= 0 if gap <= 3 else min(30, gap)
        out.append(_light(hit, max(0.0, sc)))
    return sorted(out, key=lambda c: -c["score"])[:limit]


def cover_candidates(title: str, artist: str, limit: int = 6) -> List[Dict[str, str]]:
    """1.2.2 : pochettes possibles (Deezer) pour l'éditeur d'infos : [{url, album, artist}], sans doublon."""
    title, artist = split_display(title, artist)
    q = f"{artist} {clean_title(title)}".strip()
    out: List[Dict[str, str]] = []
    seen = set()
    for hit in (_get("/search", {"q": q, "limit": 15}).get("data") or []):
        album = hit.get("album") or {}
        url = album.get("cover_xl") or album.get("cover_big")
        if url and album.get("id") not in seen:
            seen.add(album.get("id"))
            out.append({"url": url, "album": album.get("title") or "", "artist": (hit.get("artist") or {}).get("name") or ""})
        if len(out) >= limit:
            break
    return out


def download_image(url: str) -> bytes:
    resp = _session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.content


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
