"""Pochettes au format Rekordbox sur la clé : PIONEER/Artwork/<dossier>/a<N>.jpg (+ a<N>_m.jpg).

Relevé sur un vrai export.pdb (136 pochettes) :
  * chemin « /PIONEER/Artwork/00001/a1.jpg » ; numéros croissants ; 20 par dossier
    (a1-a19 dans 00001, a20-a39 dans 00002…) : dossier = N // 20 + 1 sur 5 chiffres ;
  * Rekordbox 6+ écrit une vignette 80 x 80 (a<N>.jpg, utilisée par toutes les platines) et une
    version 240 x 240 (a<N>_m.jpg, affichée en grand par les platines récentes) ; seule la première
    est référencée dans les bases.
Le numéro est partagé par exportLibrary.db (table image) et export.pdb (table 13) : c'est le CHEMIN
qui relie les deux, leurs identifiants internes restent indépendants.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ART_ROOT = "PIONEER/Artwork"
SIZES = {"": 80, "_m": 240}
PER_FOLDER = 20
_NUM = re.compile(r"/a(\d+)(?:_m)?\.jpg$", re.I)


def make_jpegs(image: bytes) -> Optional[Dict[str, bytes]]:
    """Vignettes JPEG carrées {"": 80 px, "_m": 240 px} ; None si l'image est illisible."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image))
        img.load()
        img = img.convert("RGB")
    except Exception:  # noqa: BLE001 - pochette corrompue : le son est ajouté sans
        return None
    w, h = img.size
    if not w or not h:
        return None
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    out: Dict[str, bytes] = {}
    for suffix, size in SIZES.items():
        buf = io.BytesIO()
        img.resize((size, size), Image.LANCZOS).save(buf, "JPEG", quality=90, optimize=True)
        out[suffix] = buf.getvalue()
    return out


def rel_path(number: int, suffix: str = "") -> str:
    return f"/{ART_ROOT}/{number // PER_FOLDER + 1:05d}/a{number}{suffix}.jpg"


def number_of(path: str) -> int:
    m = _NUM.search(path or "")
    return int(m.group(1)) if m else 0


def next_number(drive_root: Path, known_paths: Iterable[str]) -> int:
    """Premier numéro libre : au-delà de tout ce que citent les bases ET de ce qui existe sur la clé
    (une pochette orpheline n'est jamais écrasée)."""
    top = max((number_of(p) for p in known_paths), default=0)
    root = Path(drive_root) / ART_ROOT
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir():
                for f in folder.glob("a*.jpg"):
                    top = max(top, number_of("/" + f.name))
    return top + 1


def write(drive_root: Path, number: int, jpegs: Dict[str, bytes]) -> List[Path]:
    """Écrit les fichiers (écriture atomique) ; renvoie les chemins créés (pour annulation)."""
    written: List[Path] = []
    for suffix, data in jpegs.items():
        target = Path(drive_root) / rel_path(number, suffix).lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".djsync-tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        written.append(target)
    return written
