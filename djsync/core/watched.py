"""1.4.0-rc.5 (C160) : registre des sons arrivés par le dossier surveillé.

Rien n'est écrit dans la bibliothèque (ni commentaire, ni tag) : DJSync retient, dans ses réglages, le nom et la
taille de chaque fichier importé depuis le dossier surveillé, avec le dossier et la date. La Bibliothèque s'en sert
pour la colonne Source (« Dossier surveillé », icône d'œil, bulle « Ajouté automatiquement depuis … le … »).
Clé nom + taille (comme le registre des qualités) : elle ne dépend ni de la lettre de la clé, ni du dossier."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Optional[Dict[str, Dict[str, str]]] = None
_store_path: Optional[Path] = None


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "watched.json"


def use_store(path: Optional[Path]) -> None:
    """Tests : registre dans un autre fichier (None = celui des réglages)."""
    global _store_path, _cache
    with _lock:
        _store_path, _cache = (Path(path) if path else None), None


def _key(name: str, size: int) -> str:
    return f"{name.casefold()}|{int(size)}"


def _load() -> Dict[str, Dict[str, str]]:
    global _cache
    if _cache is None:
        try:
            data = json.loads(_file().read_text("utf-8"))
            _cache = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            _cache = {}
    return _cache


def record(files: Iterable[Tuple[str, int]], folder: str, date: str) -> int:
    """Retient des fichiers (nom, taille) arrivés depuis `folder` le `date` (AAAA-MM-JJ)."""
    with _lock:
        data = _load()
        n = 0
        for name, size in files:
            if name and size:
                data[_key(name, size)] = {"folder": folder, "date": date}
                n += 1
        if n:
            try:
                path = _file()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
            except OSError as exc:
                log.warning("Watched folder register not saved: %s", exc)
        return n


def lookup(name: str, size: int) -> Optional[Dict[str, str]]:
    if not name or not size:
        return None
    with _lock:
        return _load().get(_key(name, size))


def lookup_track(track: Any) -> Optional[Dict[str, str]]:
    """Pour un LibraryTrack (nom du fichier + taille)."""
    path = str(getattr(track, "path", "") or "").replace("\\", "/")
    return lookup(path.rsplit("/", 1)[-1], int(getattr(track, "file_size", 0) or 0))
