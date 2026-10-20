"""Pochettes : extraction depuis les tags d'un fichier audio, miniatures carrées.

Fonctions pures (aucun widget) : elles s'exécutent en thread d'arrière-plan.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


def extract_embedded_cover(path: Union[str, Path]) -> Optional[bytes]:
    """Pochette intégrée à un fichier (m4a/mp4, mp3, flac, wav-ID3), ou None."""
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4

    path = str(path)
    suffix = Path(path).suffix.lower()
    try:
        if suffix in (".m4a", ".mp4", ".aac"):
            covers = (MP4(path).tags or {}).get("covr")
            return bytes(covers[0]) if covers else None
        if suffix == ".flac":
            pics = FLAC(path).pictures
            return pics[0].data if pics else None
        if suffix in (".mp3", ".wav", ".aif", ".aiff"):
            tags = ID3(path)
            pics = tags.getall("APIC")
            return pics[0].data if pics else None
        audio = mutagen.File(path)  # ogg/opus & co
        pics = getattr(audio, "pictures", None)
        return pics[0].data if pics else None
    except Exception as exc:  # noqa: BLE001 - fichier sans tags, tronqué... : pas de pochette
        log.debug("No artwork in %s: %s", path, exc)
        return None


def square_thumb(data: Union[bytes, Image.Image], size: int) -> Image.Image:
    """Recadre au centre en carré puis redimensionne (size x size, RGB)."""
    img = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    return img.resize((size, size), Image.LANCZOS)


def placeholder(size: int, bg: str = "#1A1A20", fg: str = "#3A3A46") -> Image.Image:
    """Carré sombre avec une note de musique dessinée (sans dépendre d'une police)."""
    k = 4  # supersampling pour des bords lisses
    big = Image.new("RGB", (size * k, size * k), bg)
    d = ImageDraw.Draw(big)
    u = size * k / 10
    d.ellipse((2.6 * u, 6.2 * u, 4.6 * u, 8.0 * u), fill=fg)               # tête de note
    d.rectangle((4.2 * u, 2.2 * u, 4.7 * u, 7.2 * u), fill=fg)              # hampe
    d.polygon([(4.7 * u, 2.2 * u), (7.4 * u, 3.2 * u), (7.4 * u, 4.4 * u), (4.7 * u, 3.4 * u)], fill=fg)  # crochet
    return big.resize((size, size), Image.LANCZOS)


def icon(name: str, size: int, color: str) -> Image.Image:
    """Icônes de transport dessinées en code (play, pause, stop) : pas de police à installer."""
    k = 6
    big = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    u = size * k / 10
    if name == "play":
        d.polygon([(2.8 * u, 1.6 * u), (8.6 * u, 5 * u), (2.8 * u, 8.4 * u)], fill=color)
    elif name == "pause":
        d.rounded_rectangle((2.4 * u, 1.8 * u, 4.2 * u, 8.2 * u), radius=0.3 * u, fill=color)
        d.rounded_rectangle((5.8 * u, 1.8 * u, 7.6 * u, 8.2 * u), radius=0.3 * u, fill=color)
    elif name == "stop":
        d.rounded_rectangle((2.2 * u, 2.2 * u, 7.8 * u, 7.8 * u), radius=0.5 * u, fill=color)
    elif name == "volume":
        d.polygon([(1.2 * u, 3.9 * u), (3.2 * u, 3.9 * u), (5.4 * u, 1.9 * u), (5.4 * u, 8.1 * u),
                   (3.2 * u, 6.1 * u), (1.2 * u, 6.1 * u)], fill=color)
        d.arc((4.2 * u, 3.0 * u, 7.2 * u, 7.0 * u), -50, 50, fill=color, width=int(0.5 * u))
        d.arc((4.6 * u, 1.6 * u, 9.2 * u, 8.4 * u), -50, 50, fill=color, width=int(0.5 * u))
    return big.resize((size, size), Image.LANCZOS)
