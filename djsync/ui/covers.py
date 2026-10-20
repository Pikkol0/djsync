"""Chargement ASYNCHRONE des pochettes/miniatures (réseau ou fichier), avec cache.

Le travail lourd (téléchargement, décodage, recadrage) se fait dans un thread ; seule la
création de l'image Tk (PhotoImage) se fait dans le thread UI.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import requests
from PIL import Image, ImageTk

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
        self._placeholder: Optional[ImageTk.PhotoImage] = None

    @property
    def size(self) -> int:
        return theme.tkpx(theme.COVER_SIZE)

    def placeholder_photo(self) -> ImageTk.PhotoImage:
        if self._placeholder is None:
            self._placeholder = ImageTk.PhotoImage(placeholder(self.size))
        return self._placeholder

    def request(self, ref: CoverRef, callback: Callable[[ImageTk.PhotoImage], None]) -> None:
        """callback(photo) sera appelé dans le thread UI (tout de suite si déjà en cache)."""
        cached = self._photos.get(ref.key)
        if cached is not None:
            self._photos.move_to_end(ref.key)
            callback(cached)
            return
        waiting = self._pending.get(ref.key)
        if waiting is not None:
            waiting.append(callback)
            return
        self._pending[ref.key] = [callback]
        size = self.size

        def produce() -> Image.Image:
            data = ref.loader()
            return square_thumb(data, size) if data else placeholder(size)

        self._dispatcher.submit(
            produce,
            on_ok=lambda img: self._done(ref.key, img),
            on_err=lambda _e: self._done(ref.key, None),
            pool="cover",
        )

    def _done(self, key: str, img: Optional[Image.Image]) -> None:
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
