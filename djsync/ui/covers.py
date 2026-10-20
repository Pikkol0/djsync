"""Chargement ASYNCHRONE des pochettes/miniatures (réseau ou fichier), avec cache.

Le travail lourd (téléchargement, décodage, recadrage) se fait dans un thread ; seule la
création de l'image Tk (PhotoImage) se fait dans le thread UI.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import requests
from PIL import Image, ImageDraw, ImageFont, ImageTk

from ..audio.covers import extract_embedded_cover, placeholder, square_thumb
from . import theme

log = logging.getLogger(__name__)

_session = requests.Session()


def fetch_url_bytes(url: str) -> Optional[bytes]:
    """Remplaçable dans les tests : `covers.fetch_url_bytes = fake`."""
    resp = _session.get(url, timeout=8)
    resp.raise_for_status()
    return resp.content


@dataclass(frozen=True)
class CoverRef:
    """Où trouver une pochette : `key` identifie le cache, `loader` produit octets/Image/None
    (exécuté dans un thread de travail : jamais de widget dedans)."""

    key: str
    loader: Callable[[], Union[bytes, Image.Image, None]]


BADGE_W = 34          # largeur (unités logiques) de la pastille Camelot à droite de la pochette
Badge = Optional[Tuple[str, str]]


@lru_cache(maxsize=8)
def _badge_font(px: int) -> Any:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:          # Pillow < 10.1
        return ImageFont.load_default()


def with_badge(cover: Image.Image, badge: Badge, scale: float) -> Image.Image:
    """Pochette + pastille Camelot colorée à droite (colonne #0 des tableaux de la bibliothèque)."""
    size = cover.size[1]
    bw, gap = int(round(BADGE_W * scale)), int(round(6 * scale))
    out = Image.new("RGBA", (size + gap + bw, size), (0, 0, 0, 0))
    out.paste(cover.convert("RGBA"), (0, 0))
    if badge and badge[0]:
        text, color = badge
        h = int(round(20 * scale))
        y0 = (size - h) // 2
        d = ImageDraw.Draw(out)
        d.rounded_rectangle((size + gap, y0, size + gap + bw - 1, y0 + h), radius=int(6 * scale), fill=color)
        font = _badge_font(max(8, int(round(11 * scale))))
        fg = theme.on_color(color)
        try:
            box = d.textbbox((0, 0), text, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
            d.text((size + gap + (bw - tw) / 2 - box[0], y0 + (h - th) / 2 - box[1]), text, font=font, fill=fg)
        except AttributeError:
            d.text((size + gap + 4, y0 + 2), text, font=font, fill=fg)
    return out


def url_cover(url: Optional[str]) -> Optional[CoverRef]:
    return CoverRef(f"url:{url}", lambda: fetch_url_bytes(url)) if url else None


def file_cover(image_path: Optional[Path], audio_path: Optional[Path], key: str) -> CoverRef:
    """Pochette Rekordbox de la clé si elle existe, sinon pochette intégrée au fichier audio."""
    def load() -> Optional[bytes]:
        if image_path and image_path.is_file():
            return image_path.read_bytes()
        return extract_embedded_cover(audio_path) if audio_path and audio_path.is_file() else None

    return CoverRef(key, load)


class CoverLoader:
    """Cache LRU de PhotoImage pour les tableaux ; dédoublonne les requêtes en cours."""

    def __init__(self, dispatcher: Any, max_items: int = 1200) -> None:
        self._dispatcher = dispatcher
        self._photos: "OrderedDict[str, ImageTk.PhotoImage]" = OrderedDict()
        self._pending: Dict[str, List[Callable[[ImageTk.PhotoImage], None]]] = {}
        self._max = max_items
        self._placeholders: Dict[Any, ImageTk.PhotoImage] = {}
        self._generation = 0

    @property
    def size(self) -> int:
        return theme.tkpx(theme.COVER_SIZE)

    def clear(self) -> None:
        """Vide le cache (changement d'échelle : les images doivent être refaites à la bonne taille)."""
        self._photos.clear()
        self._placeholders.clear()
        self._pending.clear()
        self._generation += 1

    def placeholder_photo(self, badge: Badge = None) -> ImageTk.PhotoImage:
        key = badge or ""
        if key not in self._placeholders:
            img = placeholder(self.size)
            if badge is not None:
                img = with_badge(img, badge, self.size / max(theme.COVER_SIZE, 1))
            self._placeholders[key] = ImageTk.PhotoImage(img)
        return self._placeholders[key]

    def request(self, ref: CoverRef, callback: Callable[[ImageTk.PhotoImage], None], badge: Badge = None) -> None:
        """callback(photo) sera appelé dans le thread UI (tout de suite si déjà en cache).
        `badge` : (texte, couleur) dessiné à droite de la pochette (tableaux à pastille Camelot)."""
        key = f"{ref.key}|{badge[0]}" if badge is not None else ref.key
        cached = self._photos.get(key)
        if cached is not None:
            self._photos.move_to_end(key)
            callback(cached)
            return
        waiting = self._pending.get(key)
        if waiting is not None:
            waiting.append(callback)
            return
        self._pending[key] = [callback]
        size, gen = self.size, self._generation
        scale = size / max(theme.COVER_SIZE, 1)

        def produce() -> Image.Image:
            data = ref.loader()
            img = square_thumb(data, size) if data else placeholder(size)
            return with_badge(img, badge, scale) if badge is not None else img

        def fallback() -> Image.Image:
            img = placeholder(size)
            return with_badge(img, badge, scale) if badge is not None else img

        self._dispatcher.submit(
            produce,
            on_ok=lambda img: self._done(key, img, gen),
            on_err=lambda _e: self._done(key, fallback(), gen),
            pool="cover",
        )

    def _done(self, key: str, img: Optional[Image.Image], gen: int = -1) -> None:
        if gen != self._generation and gen != -1:
            return                          # image à l'ancienne échelle : ignorée
        photo = ImageTk.PhotoImage(img if img is not None else placeholder(self.size))
        self._photos[key] = photo
        while len(self._photos) > self._max:
            self._photos.popitem(last=False)
        for callback in self._pending.pop(key, []):
            callback(photo)

    def load_pil(self, ref: Optional[CoverRef], size: int, on_ok: Callable[[Image.Image], None]) -> None:
        """Image PIL carrée (grande taille : barre de lecture). Toujours rappelé, placeholder si échec."""
        def produce() -> Image.Image:
            data = ref.loader() if ref else None
            return square_thumb(data, size) if data else placeholder(size)

        self._dispatcher.submit(produce, on_ok=on_ok, on_err=lambda _e: on_ok(placeholder(size)), pool="cover")
