"""Réglages de l'application (JSON, écriture atomique).

Emplacement : %APPDATA%\\DJSync\\settings.json sous Windows, ~/.config/djsync/ ailleurs
(variable d'environnement DJSYNC_HOME pour le changer : tests, version portable).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def settings_dir() -> Path:
    override = os.environ.get("DJSYNC_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "DJSync"
    return Path.home() / ".config" / "djsync"


@dataclass
class Settings:
    forced_drive: str = ""          # lettre/chemin imposé par l'utilisateur (prioritaire)
    active_drive: str = ""          # dernière clé utilisée
    contents_dir: str = "Contents"  # dossier de destination des sons, relatif à la racine de la clé
    ffmpeg_location: str = ""       # dossier contenant ffmpeg(.exe) ; vide = PATH
    exclude_words: str = ""         # ex. "remix, live"
    search_mode: str = "all"        # all | songs | videos | artists
    fetch_views: bool = True        # charger les vues des Titres en arrière-plan
    spotify_preference: str = "auto"
    backup_keep: int = 10
    volume: float = 0.8
    geometry: str = ""

    @classmethod
    def path(cls) -> Path:
        return settings_dir() / "settings.json"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Settings":
        path = path or cls.path()
        settings = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Réglages illisibles (%s) : valeurs par défaut.", exc)
            return settings
        for f in fields(cls):
            if f.name in raw and isinstance(raw[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, raw[f.name])  # type incorrect : on garde la valeur par défaut
        return settings

    def save(self, path: Optional[Path] = None) -> None:
        path = path or self.path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("Réglages non enregistrés : %s", exc)
