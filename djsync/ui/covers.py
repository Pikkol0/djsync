"""Chargement ASYNCHRONE des pochettes (réseau ou fichier) pour la barre de lecture.

V0.3.0 : les tableaux n'affichent plus de pochette par ligne (chargement coûteux, peu utile) ;
seule la barre de lecture en montre une. Le travail lourd (téléchargement, décodage, recadrage) se
fait dans un thread ; la conversion en QPixmap se fait dans le thread UI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

import requests
from PIL import Image

from ..audio.covers import extract_embedded_cover, placeholder, square_thumb

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
    def __init__(self, dispatcher: Any) -> None:
        self._dispatcher = dispatcher

    def clear(self) -> None:
        """Compatibilité (plus de cache d'images Tk)."""

    def load_pil(self, ref: Optional[CoverRef], size: int, on_ok: Callable[[Image.Image], None]) -> None:
        """Image PIL carrée. Toujours rappelé (placeholder si échec)."""
        def produce() -> Image.Image:
            data = ref.loader() if ref else None
            return square_thumb(data, size) if data else placeholder(size)

        self._dispatcher.submit(produce, on_ok=on_ok, on_err=lambda _e: on_ok(placeholder(size)), pool="cover")
