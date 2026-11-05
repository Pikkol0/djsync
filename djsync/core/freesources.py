"""Sources gratuites et légales de meilleure qualité (1.4.0, C45 partie 2), pour la recherche « Haute
qualité » à côté de Soulseek :

* **Audius** : plateforme d'artistes (beaucoup d'électro), API publique sans clé ; flux 320 kbps.
* **Internet Archive** (netlabels, Free Music Archive, live autorisés) : morceaux sous licence libre,
  souvent en FLAC ; API de recherche publique sans clé.

Chaque résultat est un TrackResult ordinaire (source « audius » / « archive », lien de la page ou du
fichier) : préécoute et téléchargement passent par yt-dlp comme pour YouTube et SoundCloud, avec la
licence affichée. Réseau : à appeler hors du fil de l'interface.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from ..models import TrackResult

log = logging.getLogger(__name__)

APP = "DJSync"
TIMEOUT = 12
AUDIUS_HOSTS = "https://api.audius.co"
ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_META = "https://archive.org/metadata/{id}"
ARCHIVE_FILE = "https://archive.org/download/{id}/{name}"
# formats Internet Archive -> (extension, sans perte)
_IA_FORMATS = {"flac": ("flac", True), "24bit flac": ("flac", True), "wave": ("wav", True), "aiff": ("aiff", True),
               "vbr mp3": ("mp3", False), "320kbps mp3": ("mp3", False), "mp3": ("mp3", False)}


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    import requests

    r = requests.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": APP})
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ Audius
_AUDIUS_HOST: Dict[str, str] = {}


def _audius_host(get: Callable = _get) -> str:
    """Serveur Audius, gardé en mémoire (1.4.0-rc.4, B78 : une requête de moins par recherche)."""
    if get is _get and _AUDIUS_HOST.get("host"):
        return _AUDIUS_HOST["host"]
    hosts = (get(AUDIUS_HOSTS) or {}).get("data") or []
    if not hosts:
        raise RuntimeError("No Audius server available.")
    host = hosts[0].rstrip("/")
    if get is _get:
        _AUDIUS_HOST["host"] = host
    return host


def audius_search(query: str, limit: int = 15, get: Callable = _get) -> List[TrackResult]:
    host = _audius_host(get)
    data = (get(f"{host}/v1/tracks/search", {"query": query, "app_name": APP}) or {}).get("data") or []
    out = []
    for x in data[:limit]:
        if not x.get("is_streamable", True):
            continue
        user = x.get("user") or {}
        handle, slug = user.get("handle") or "", x.get("permalink") or ""
        link = f"https://audius.co{slug}" if slug.startswith("/") else (f"https://audius.co/{handle}/{slug}" if handle and slug
                                                                        else f"{host}/v1/tracks/{x.get('id')}/stream?app_name={APP}")
        art = x.get("artwork") or {}
        out.append(TrackResult(video_id=f"audius:{x.get('id')}", title=x.get("title") or "", artist=user.get("name") or "",
                               duration_seconds=int(x.get("duration") or 0), thumbnail_url=art.get("480x480") or None,
                               source="audius", source_url=link, genre=x.get("genre") or None,
                               license=t_license("audius", x.get("license") or ""), quality="MP3 320",
                               original_available=bool(x.get("downloadable")) or None))
    return out


# ------------------------------------------------------------------ Internet Archive
def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


ARCHIVE_ITEMS = 15        # éléments (albums, enregistrements) demandés à archive.org
ARCHIVE_PARALLEL = 8      # 1.4.0-rc.4 (B78) : fiches des éléments demandées en parallèle


def _track_no(f: Dict[str, Any]) -> int:
    m = re.match(r"\d+", str(f.get("track") or ""))
    return int(m.group()) if m else 10 ** 6


def archive_search(query: str, limit: int = 60, get: Callable = _get) -> List[TrackResult]:
    """Morceaux (fichiers) d'éléments audio d'archive.org, dans l'ordre de pertinence d'archive.org, puis
    dans l'ordre des pistes de chaque élément. 1.4.0-rc.4 (B78) : fiches demandées en parallèle ; un
    fichier est gardé si les mots sont dans le fichier OU dans l'élément (titre de l'album, artiste) ; plus
    de tri global « sans perte d'abord » (la qualité reste affichée)."""
    from concurrent.futures import ThreadPoolExecutor

    words = [w for w in _plain(query).split() if len(w) > 1]
    q = " AND ".join(f"({w})" for w in words) or query
    resp = get(ARCHIVE_SEARCH, {"q": f"({q}) AND mediatype:(audio)", "fl[]": ["identifier", "title", "creator",
                                                                             "licenseurl"],
                                "rows": ARCHIVE_ITEMS, "output": "json"})
    docs = [d for d in ((resp or {}).get("response") or {}).get("docs") or [] if d.get("identifier")]

    def meta_of(doc: Dict[str, Any]) -> Any:
        try:
            return get(ARCHIVE_META.format(id=doc["identifier"]))
        except Exception as exc:  # noqa: BLE001
            log.info("Archive metadata %s: %s", doc["identifier"], exc)
            return None

    with ThreadPoolExecutor(max_workers=ARCHIVE_PARALLEL) as pool:
        metas = list(pool.map(meta_of, docs))
    out: List[TrackResult] = []
    for doc, meta in zip(docs, metas):
        if meta is None:
            continue
        ident = doc["identifier"]
        creator = doc.get("creator")
        creator = creator[0] if isinstance(creator, list) and creator else (creator or "")
        item_hay = " " + _plain(f"{doc.get('title') or ''} {creator}") + " "
        best: Dict[str, Any] = {}
        for f in (meta or {}).get("files") or []:
            fmt = _IA_FORMATS.get(str(f.get("format") or "").lower())
            if fmt is None:
                continue
            title = f.get("title") or str(f.get("name", "")).rsplit(".", 1)[0]
            hay = " " + _plain(f"{title} {f.get('artist') or creator} {f.get('name')}") + " " + item_hay
            if words and not all(f" {w} " in hay for w in words):
                continue
            key = _plain(title)
            rank = (fmt[1], fmt[0] == "flac")
            if key not in best or rank > best[key][0]:
                best[key] = (rank, f, fmt, title)
        for rank, f, fmt, title in sorted(best.values(), key=lambda b: _track_no(b[1])):
            length = f.get("length") or "0"
            try:
                secs = int(float(length)) if ":" not in str(length) else sum(
                    int(float(p)) * 60 ** i for i, p in enumerate(reversed(str(length).split(":"))))
            except ValueError:
                secs = 0
            url = ARCHIVE_FILE.format(id=ident, name=quote(str(f.get("name", ""))))
            out.append(TrackResult(video_id=f"archive:{ident}/{f.get('name')}", title=title,
                                   artist=f.get("artist") or creator, album=doc.get("title") or None,
                                   duration_seconds=secs, source="archive", source_url=url,
                                   license=t_license("archive", doc.get("licenseurl") or ""),
                                   quality=fmt[0].upper() if fmt[1] else "MP3"))
        if len(out) >= limit:
            break
    return out[:limit]


def t_license(source: str, raw: str) -> str:
    """« CC BY-NC 4.0 », « Tous droits réservés (écoute et téléchargement autorisés par l'artiste) »…"""
    m = re.search(r"creativecommons\.org/(licenses|publicdomain)/([a-z\-]+)/?([\d.]+)?", raw or "", re.I)
    if m:
        kind = m.group(2).upper()
        return "CC0" if m.group(1) == "publicdomain" else f"CC {kind}" + (f" {m.group(3)}" if m.group(3) else "")
    return raw.strip() or ("Audius" if source == "audius" else "")


def search_all(query: str, sources: List[str], get: Callable = _get,
               partial: Optional[Callable[[str, List[TrackResult]], None]] = None) -> List[TrackResult]:
    """Les sources demandées en même temps (1.4.0-rc.4, B78) ; une source en panne n'empêche pas les
    autres. `partial(nom, résultats)` est appelé dès qu'une source a répondu (depuis son fil)."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    wanted = [(n, fn) for n, fn in (("archive", archive_search), ("audius", audius_search)) if n in sources]

    def one(item: Any) -> List[TrackResult]:
        name, fn = item
        start = time.monotonic()
        try:
            found = fn(query, get=get)
        except Exception as exc:  # noqa: BLE001 - hors ligne, API changée…
            log.info("%s search failed: %s", name, exc)
            found = []
        log.info("Free source %s: %d result(s) in %.1f s", name, len(found), time.monotonic() - start)
        if partial is not None:
            partial(name, found)
        return found

    if not wanted:
        return []
    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        results = list(pool.map(one, wanted))
    return [x for r in results for x in r]
