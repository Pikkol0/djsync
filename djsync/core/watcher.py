"""Dossier surveillé (1.4.0, C10.3) : les fichiers audio déposés dans un dossier (achats Bandcamp,
Beatport, record pools, promos, téléchargements « Free Download ») sont importés tout seuls.

Un fichier n'est pris que lorsqu'il ne bouge plus (même taille et même date pendant deux passages) :
un téléchargement en cours n'est jamais importé à moitié. Il est ensuite rangé dans le sous-dossier
« DJSync imported » (jamais supprimé) pour ne pas être pris deux fois ; c'est de là qu'il est importé.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Tuple

from .importer import is_audio

log = logging.getLogger(__name__)

DONE_DIR = "DJSync imported"
PARTIAL = (".part", ".crdownload", ".download", ".tmp", ".djsync-part")
MIN_AGE = 3.0          # secondes sans changement avant import


class FolderWatch:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self._seen: Dict[str, Tuple[int, float]] = {}

    def _candidates(self) -> List[Path]:
        out: List[Path] = []
        if not self.folder.is_dir():
            return out
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if d != DONE_DIR and not d.startswith(".")]
            for f in files:
                p = Path(root) / f
                if is_audio(p) and not f.lower().endswith(PARTIAL):
                    out.append(p)
        return out

    def stable_files(self, now: float = 0.0) -> List[Path]:
        """Fichiers prêts : inchangés depuis le passage précédent et depuis MIN_AGE secondes."""
        now = now or time.time()
        ready: List[Path] = []
        current: Dict[str, Tuple[int, float]] = {}
        for p in self._candidates():
            try:
                st = p.stat()
            except OSError:
                continue
            sig = (st.st_size, st.st_mtime)
            current[str(p)] = sig
            if st.st_size > 0 and self._seen.get(str(p)) == sig and now - st.st_mtime >= MIN_AGE:
                ready.append(p)
        self._seen = current
        return ready

    def take(self, path: Path) -> Path:
        """Range le fichier dans « DJSync imported » (même sous-dossier relatif) ; renvoie le nouveau chemin."""
        rel = path.relative_to(self.folder)
        target = self.folder / DONE_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        k = 2
        while target.exists():
            target = target.with_name(f"{path.stem} ({k}){path.suffix}")
            k += 1
        shutil.move(str(path), str(target))
        self._seen.pop(str(path), None)
        return target
