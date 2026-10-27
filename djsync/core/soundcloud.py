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
from typing import Any, Dict, Optional

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


def original_available(url: str) -> Optional[bool]:
    """True si l'artiste autorise le téléchargement du fichier d'origine, False sinon, None si on ne
    sait pas (réseau, format de réponse inattendu). Réseau : à appeler hors du fil de l'interface."""
    if not url or "soundcloud.com" not in url:
        return None
    try:
        import yt_dlp

        from .engine import ydl_options

        with yt_dlp.YoutubeDL(ydl_options(quiet=True, no_warnings=True, skip_download=True)) as ydl:
            ie = ydl.get_info_extractor("Soundcloud")
            ie.initialize()                                          # identifiant client (mis en cache par yt-dlp)
            info = ie._call_api(ie._resolv_url(url), None)           # noqa: SLF001 - API interne de yt-dlp
        if not isinstance(info, dict) or info.get("kind") not in (None, "track"):
            return None
        return bool(info.get("downloadable") and info.get("has_downloads_left", True))
    except Exception as exc:  # noqa: BLE001 - simple indication : jamais d'erreur visible
        log.info("SoundCloud original check failed for %s: %s", url, exc)
        return None
