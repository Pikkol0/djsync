"""Réglages de l'application (JSON, écriture atomique).

Emplacement : %APPDATA%\\DJSync\\settings.json sous Windows, ~/.config/djsync/ ailleurs
(variable d'environnement DJSYNC_HOME pour le changer : tests, version portable).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def settings_dir() -> Path:
    override = os.environ.get("DJSYNC_HOME")
    if override:
        return Path(override)
    from .portable import portable_data_dir     # import tardif : portable.py n'importe pas settings
    portable = portable_data_dir()
    if portable is not None:
        return portable
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "DJSync"
    return Path.home() / ".config" / "djsync"


ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 80, 200, 10    # pourcentage d'affichage (option « Zoom de l'interface »)
ZOOM_DEFAULT = 100
DEFAULT_LANGUAGE = "en"
DEFAULT_THEME = "violet_light"
LANGUAGE_CODES = ("en", "fr")


def clamp_zoom(value: object) -> int:
    """Ramène n'importe quelle valeur dans [80, 200] (entier)."""
    try:
        return max(ZOOM_MIN, min(ZOOM_MAX, int(round(float(value)))))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ZOOM_DEFAULT


@dataclass
class Settings:
    forced_drive: str = ""          # lettre/chemin imposé par l'utilisateur (prioritaire)
    active_drive: str = ""          # dernière clé utilisée
    contents_dir: str = "Contents"  # dossier de destination des sons, relatif à la racine de la clé
    ffmpeg_location: str = ""       # dossier contenant ffmpeg(.exe) ; vide = PATH
    exclude_words: str = ""         # ex. "remix, live"
    search_mode: str = "all"        # all | songs | videos | artists
    fetch_views: bool = True        # charger les vues des Titres en arrière-plan
    fetch_metadata: bool = True     # V0.3.0 : album, année, genre, label… (Deezer) au téléchargement
    spotify_preference: str = "auto"
    backup_keep: int = 10
    volume: float = 0.8
    geometry: str = ""
    # ---- V1.1
    language: str = DEFAULT_LANGUAGE   # "en" (défaut) | "fr"
    theme: str = DEFAULT_THEME         # identifiant de palette (voir ui/theme.PALETTES)
    zoom: int = ZOOM_DEFAULT           # 80..200 (%) : zoom choisi par l'utilisateur
    last_tab: str = "home"             # onglet rouvert au prochain démarrage
    # ---- V1.1-A3
    pdb_sync: str = "auto"             # "auto" : met aussi à jour export.pdb s'il existe | "off"
    pdb_allow_growth: bool = True      # V1.0.0 : ajout de pages à export.pdb (validé, voir docs/export_pdb.md)
    # ---- V1.1-A4
    analyze_on_add: bool = False       # V0.2.0 : désactivé par défaut (menu Analyse) ; True = à chaque ajout
    key_notation: str = "auto"         # auto (celle de la clé) | camelot (« 8A ») | musical (« Am »)
    # ---- V0.2.0
    zoom_auto: bool = True             # inutilisé depuis la V0.3.0 (conservé pour les anciens réglages)
    sidebar_compact: str = "auto"      # auto (repliée si fenêtre étroite) | on | off
    harmonic_filter: bool = False      # dernier état du filtre « compatibles harmoniquement »
    # ---- V0.2.2
    maximized: bool = False            # fenêtre rouverte agrandie si elle l'était à la fermeture
    # ---- V0.4.0 : bibliothèque Rekordbox de cet ordinateur
    local_db_dir: str = ""             # dossier de master.db ; vide = emplacement standard de Rekordbox
    local_music_dir: str = ""          # dossier des sons téléchargés ; vide = Musique/DJSync
    # ---- V0.5.0
    audio_format: str = "m4a"          # m4a (flux d'origine, sans perte) | mp3 (MP3 320, ré-encodé)
    normalize_volume: bool = False     # même sonie pour tous les sons téléchargés (gain fixe, ré-encodage)
    auto_cue: bool = True              # mémoire cue sur le premier temps fort à l'analyse
    local_hosts: list = field(default_factory=list)   # version portable : PC dont la bibliothèque a été acceptée
    # ---- V1.0.0
    settings_version: int = 0          # migrations des réglages enregistrés

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
            log.warning("Unreadable settings (%s): using defaults.", exc)
            return settings
        for f in fields(cls):
            if f.name in raw and isinstance(raw[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, raw[f.name])  # type incorrect : on garde la valeur par défaut
        settings.normalize()
        return settings

    def normalize(self) -> "Settings":
        """Valeurs hors limites / inconnues ramenées à des valeurs valides (fichier édité à la main)."""
        self.zoom = clamp_zoom(self.zoom)
        self.language = self.language if self.language in LANGUAGE_CODES else DEFAULT_LANGUAGE
        self.pdb_sync = self.pdb_sync if self.pdb_sync in ("auto", "off") else "auto"
        self.sidebar_compact = self.sidebar_compact if self.sidebar_compact in ("auto", "on", "off") else "auto"
        self.key_notation = self.key_notation if self.key_notation in ("auto", "camelot", "musical") else "auto"
        self.volume = max(0.0, min(1.0, float(self.volume)))
        if self.settings_version < 1:      # V1.0.0 : l'ajout de pages à export.pdb devient le défaut
            self.pdb_allow_growth = True   # (sans lui, une clé exportée par Rekordbox est pleine en ~15 sons)
            self.settings_version = 1
        self.audio_format = self.audio_format if self.audio_format in ("m4a", "mp3") else "m4a"
        self.local_hosts = [str(h) for h in self.local_hosts][:50]
        return self

    def save(self, path: Optional[Path] = None) -> None:
        path = path or self.path()
        self.normalize()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("Settings not saved: %s", exc)
