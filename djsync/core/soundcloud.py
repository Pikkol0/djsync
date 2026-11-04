"""SoundCloud, fichier d'origine (1.4.0, C10.1).

Quand l'artiste autorise le téléchargement, SoundCloud garde le fichier qu'il a envoyé (souvent WAV ou
FLAC). yt-dlp sait le récupérer (format « download »), mais SoundCloud ne le donne qu'à un compte
connecté : DJSync passe à yt-dlp soit les cookies d'un navigateur où l'utilisateur est connecté, soit
le jeton « oauth_token » de son compte. Sans compte, le flux habituel (m4a / mp3) est téléchargé.

`original_available` lit seulement les drapeaux publics du morceau (`downloadable`,
`has_downloads_left`) : aucune connexion nécessaire pour savoir s'il y a un fichier d'origine.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

BROWSERS = ("chrome", "firefox", "edge", "brave", "safari", "opera", "vivaldi", "chromium")


def auth_options(browser: str = "", token: str = "") -> Dict[str, Any]:
    """Options yt-dlp du compte SoundCloud (vide : pas de compte)."""
    token = (token or "").strip()
    if token:
        return {"username": "oauth", "password": token}
    browser = (browser or "").strip().lower()
    if browser in BROWSERS:
        return {"cookiesfrombrowser": (browser,)}
    return {}


# 1.4.0 (C45) : services de « Free Download » (téléchargement gratuit contre un abonnement ou un like)
FREE_GATES = ("hypeddit.com", "toneden.io", "gate.fm", "fanlink.to", "show.co", "edmdistrict", "click.dj",
              "lnk.to", "dropbox.com", "drive.google.com", "wetransfer.com", "we.tl", "bandcamp.com")
_FREE_WORDS = ("free", "gratuit", "download", "dl", "telecharg")   # titre comparé sans accents


def free_download(info: Dict[str, Any]) -> Optional[str]:
    """Lien « Free Download » mis par l'artiste dans le bouton d'achat du morceau (purchase_url), ou None
    s'il s'agit d'un vrai lien d'achat (Beatport, iTunes…)."""
    url = str(info.get("purchase_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    import unicodedata

    title = unicodedata.normalize("NFKD", str(info.get("purchase_title") or "").lower())
    title = "".join(c for c in title if not unicodedata.combining(c))
    if any(w in title for w in _FREE_WORDS) or any(g in url.lower() for g in FREE_GATES):
        return url
    return None


def track_info(url: str) -> Dict[str, Any]:
    """{"original": True/False/None, "free_url": lien ou None} : drapeaux publics du morceau (réseau)."""
    out: Dict[str, Any] = {"original": None, "free_url": None}
    if not url or "soundcloud.com" not in url:
        return out
    try:
        import yt_dlp

        from .engine import ydl_options

        with yt_dlp.YoutubeDL(ydl_options(quiet=True, no_warnings=True, skip_download=True)) as ydl:
            ie = ydl.get_info_extractor("Soundcloud")
            ie.initialize()                                          # identifiant client (mis en cache par yt-dlp)
            info = ie._call_api(ie._resolv_url(url), None)           # noqa: SLF001 - API interne de yt-dlp
        if not isinstance(info, dict) or info.get("kind") not in (None, "track"):
            return out
        out["original"] = bool(info.get("downloadable") and info.get("has_downloads_left", True))
        out["free_url"] = free_download(info)
    except Exception as exc:  # noqa: BLE001 - simple indication : jamais d'erreur visible
        log.info("SoundCloud check failed for %s: %s", url, exc)
    return out


def original_available(url: str) -> Optional[bool]:
    """True si l'artiste autorise le téléchargement du fichier d'origine, False sinon, None si on ne
    sait pas (réseau, format de réponse inattendu). Réseau : à appeler hors du fil de l'interface."""
    return track_info(url)["original"]


# 1.4.0-rc.2 (B64) : détail des sons d'une playlist (la liste rapide ne donne que leur numéro)
API_TRACKS = "https://api-v2.soundcloud.com/tracks"
BATCH = 50


def is_protected(info: Dict[str, Any]) -> bool:
    """Son chiffré (DRM) ou bloqué : aucun flux lisible sans protection."""
    if str(info.get("policy") or "").upper() in ("BLOCK", "SNIP"):
        return True
    codings = (info.get("media") or {}).get("transcodings") or []
    protocols = [str((c.get("format") or {}).get("protocol") or "") for c in codings if isinstance(c, dict)]
    return bool(protocols) and all(p.startswith(("ctr-", "cbc-")) for p in protocols)


def entry_from_api(info: Dict[str, Any]) -> Dict[str, Any]:
    """Réponse de l'API -> entrée au format yt-dlp (titre, artiste, durée, lien, pochette, protégé)."""
    meta = info.get("publisher_metadata") or {}
    user = info.get("user") or {}
    out: Dict[str, Any] = {
        "id": str(info.get("id") or ""),
        "title": info.get("title") or "",
        "uploader": user.get("username") or "",
        "duration": (info.get("duration") or info.get("full_duration") or 0) / 1000.0,
        "webpage_url": info.get("permalink_url") or "",
        "thumbnail": info.get("artwork_url") or user.get("avatar_url"),
        "view_count": info.get("playback_count"),
        "drm": is_protected(info),
    }
    if meta.get("artist"):
        out["artist"] = meta["artist"]
        out["track"] = info.get("title") or ""
    return out


def tracks_details(ids: List[str], fetch: Optional[Callable[[str, Dict[str, str]], Any]] = None) -> Dict[str, Dict[str, Any]]:
    """{id: entrée} pour les sons demandés, par lots de 50 ; les lots en échec sont simplement sautés."""
    if fetch is None:
        import yt_dlp

        from .engine import ydl_options

        ydl = yt_dlp.YoutubeDL(ydl_options(quiet=True, no_warnings=True, skip_download=True))
        ie = ydl.get_info_extractor("Soundcloud")
        ie.initialize()

        def fetch(url: str, query: Dict[str, str]) -> Any:
            return ie._call_api(url, None, query=query, fatal=False)   # noqa: SLF001 - API interne de yt-dlp
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(ids), BATCH):
        chunk = [x for x in ids[i:i + BATCH] if x]
        try:
            data = fetch(API_TRACKS, {"ids": ",".join(chunk)}) or []
        except Exception as exc:  # noqa: BLE001
            log.info("SoundCloud details failed for %d tracks: %s", len(chunk), exc)
            continue
        for info in data if isinstance(data, list) else []:
            if isinstance(info, dict) and info.get("id"):
                out[str(info["id"])] = entry_from_api(info)
    return out
