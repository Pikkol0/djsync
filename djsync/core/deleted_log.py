"""1.4.4 (C223) : sons supprimés gardés dans une petite liste, pour les retrouver et les retélécharger.

À chaque suppression : titre, artiste, lien d'origine (s'il existe) et date, notés dans le dossier DJSync de la
bibliothèque concernée (`DJSync_Backups` sur la clé ou dans le dossier de sauvegarde de master.db) :
`deleted_tracks.json`. Environ 200 octets par son ; pas de limite. Rien n'est écrit dans export.pdb ni dans les
bases Rekordbox.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

log = logging.getLogger(__name__)

FILE_NAME = "deleted_tracks.json"


@dataclass
class DeletedTrack:
    title: str
    artist: str = ""
    url: str = ""
    date: str = ""                # ISO, à la seconde

    @property
    def query(self) -> str:
        """« Artiste - Titre » (ou le titre seul) : ligne de recherche quand il n'y a pas de lien."""
        return f"{self.artist} - {self.title}" if self.artist else self.title

    def key(self) -> tuple:
        return (self.title, self.artist, self.url, self.date)


class DeletedLog:
    """Liste persistante (JSON, écriture atomique) ; sûre entre fils."""

    def __init__(self, folder: Path) -> None:
        self.path = Path(folder) / FILE_NAME
        self._lock = threading.Lock()

    def entries(self) -> List[DeletedTrack]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            log.warning("Deleted tracks list unreadable (%s): %s", self.path, exc)
            return []
        out = []
        for d in data if isinstance(data, list) else []:
            if isinstance(d, dict) and d.get("title"):
                out.append(DeletedTrack(str(d.get("title", "")), str(d.get("artist", "")), str(d.get("url", "") or ""),
                                        str(d.get("date", ""))))
        return out

    def _save(self, items: List[DeletedTrack]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps([asdict(x) for x in items], ensure_ascii=False, indent=0), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, tracks: Iterable[object], when: Optional[datetime] = None) -> int:
        """Ajoute des sons (LibraryTrack ou équivalent : title, artist, source_url). Renvoie le nombre ajouté."""
        stamp = (when or datetime.now()).isoformat(timespec="seconds")
        new = [DeletedTrack(str(getattr(x, "title", "") or ""), str(getattr(x, "artist", "") or ""),
                            str(getattr(x, "source_url", "") or ""), stamp) for x in tracks]
        new = [x for x in new if x.title]
        if not new:
            return 0
        with self._lock:
            items = self.entries()
            self._save(new + items)                       # les plus récents d'abord
        return len(new)

    def remove(self, gone: Iterable[DeletedTrack]) -> None:
        keys = {x.key() for x in gone}
        with self._lock:
            self._save([x for x in self.entries() if x.key() not in keys])

    def clear(self) -> None:
        with self._lock:
            self._save([])


def search(items: List[DeletedTrack], text: str) -> List[DeletedTrack]:
    words = (text or "").casefold().split()
    return [x for x in items if all(w in f"{x.title} {x.artist} {x.url}".casefold() for w in words)]
