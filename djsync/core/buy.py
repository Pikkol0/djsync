"""Liens « Acheter » (1.4.0, C10.3) : magasins où un DJ achète ses morceaux en WAV / AIFF / FLAC.

Aucune de ces boutiques n'ouvre d'API à une application gratuite : DJSync ouvre seulement leur page de
recherche avec l'artiste et le titre déjà tapés. Le fichier acheté revient par le dossier surveillé.
"""
from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import quote_plus

STORES = (
    ("Beatport", "https://www.beatport.com/search?q={q}"),
    ("Bandcamp", "https://bandcamp.com/search?q={q}&item_type=t"),
    ("Traxsource", "https://www.traxsource.com/search?term={q}"),
    ("Juno Download", "https://www.junodownload.com/search/?q%5Ball%5D%5B%5D={q}"),
    ("Qobuz", "https://www.qobuz.com/fr-fr/search?q={q}"),
)
_NOISE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|clip|lyric|audio|visuali[sz]er|hd|4k)[^\)\]]*[\)\]]", re.I)


def query(artist: str, title: str) -> str:
    """Texte de recherche propre : « Artiste Titre » sans « (Official Video) » et autres ajouts."""
    title = _NOISE.sub("", title or "").strip()
    artist = (artist or "").strip()
    if artist and title.lower().startswith(artist.lower() + " - "):
        title = title[len(artist) + 3:]
    return " ".join(x for x in (artist, title) if x)


def links(artist: str, title: str) -> List[Tuple[str, str]]:
    """[(magasin, URL de recherche)]."""
    q = quote_plus(query(artist, title))
    return [(name, url.format(q=q)) for name, url in STORES]
