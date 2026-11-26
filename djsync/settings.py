"""Réglages de l'application (JSON, écriture atomique).

Emplacement : %APPDATA%\\DJSync\\settings.json sous Windows, ~/.config/djsync/ ailleurs
(variable d'environnement DJSYNC_HOME pour le changer : tests, version portable).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional
from .core import durable  # 1.4.3 (A7-4) : écriture sûre (exFAT sous macOS)

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


# 1.4.1 (C143) : qualité des téléchargements (une seule liste) ; réglages remplacés, plus jamais écrits
DOWNLOAD_QUALITIES = ("original", "yt_best", "mp3_320", "mp3_256", "mp3_192", "mp3_128")
RETIRED = ("audio_format", "youtube_best", "normalize_volume")


@dataclass
class Settings:
    first_run = False               # 1.3.2 (C54) : attribut de classe, jamais enregistré (pas un champ)
    forced_drive: str = ""          # lettre/chemin imposé par l'utilisateur (prioritaire)
    active_drive: str = ""          # dernière clé utilisée
    contents_dir: str = "Contents"  # dossier de destination des sons, relatif à la racine de la clé
    ffmpeg_location: str = ""       # dossier contenant ffmpeg(.exe) ; vide = PATH
    exclude_words: str = ""         # ex. "remix, live"
    search_mode: str = "all"        # all | songs | videos | artists
    fetch_views: bool = True        # charger les vues des Titres en arrière-plan
    fetch_metadata: bool = True     # V0.3.0 : album, année, genre, label… (Deezer) au téléchargement
    spotify_preference: str = "auto"
    backup_keep: int = 10           # 1.4.4 (C235) : déduit de backup_level
    backup_level: str = ""          # 1.4.4 (C235) : light | normal | full ("" : repris de backup_keep)
    volume: float = 0.8
    geometry: str = ""
    # ---- V1.1
    language: str = DEFAULT_LANGUAGE   # "en" (défaut) | "fr"
    theme: str = DEFAULT_THEME         # identifiant de palette (voir ui/theme.PALETTES)
    background: str = "default"        # 1.4.3 (C53) : default | high_contrast | bright | oled
    write_tags: bool = False           # 1.4.3 (S05) : BPM et tonalité écrits dans les fichiers après l'analyse
    auto_gain: bool = True             # 1.4.3 (C109) : volume égalisé entre les sons (lecteur de DJSync)
    zoom: int = ZOOM_DEFAULT           # 80..200 (%) : zoom choisi par l'utilisateur
    last_tab: str = "home"             # onglet rouvert au prochain démarrage
    # ---- V1.1-A3
    pdb_sync: str = "auto"             # "auto" : met aussi à jour export.pdb s'il existe | "off"
    pdb_allow_growth: bool = True      # V1.0.0 : ajout de pages à export.pdb (validé, voir docs/export_pdb.md)
    # ---- V1.1-A4
    analyze_on_add: bool = False       # V0.2.0 ; inutilisé depuis la 1.3.0-rc.3 (remplacé par les deux ci-dessous)
    # 1.3.0-rc.3 (C32) : analyse automatique après chaque téléchargement, par la file en arrière-plan
    analyze_after_download_usb: bool = True     # clé USB
    analyze_after_download_local: bool = True   # bibliothèque Rekordbox de l'ordinateur
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
    # 1.4.1 (C143) : `download_quality` remplace les trois réglages ci-dessous, lus une version encore pour la
    # reprise, puis plus jamais écrits (« Même volume » retiré : décision du 05/11).
    download_quality: str = ""         # original | yt_best | mp3_320 | mp3_256 | mp3_192 | mp3_128
    audio_format: str = "m4a"          # ancien : m4a | mp3 (lu pour la reprise, puis déduit de download_quality)
    normalize_volume: bool = False     # ancien : ignoré
    merge_undo_s: int = 10             # 1.3.2 (C82) : délai pour annuler une fusion de doublons (5, 10, 30 s)
    auto_cue: bool = True              # mémoire cue sur le premier temps fort à l'analyse
    # 1.4.1 (C131, D20) : ce que « Analyser à nouveau » refait sur un son analysé par Rekordbox
    # (grid, key, waves) ; tant que le choix n'a pas été fait (fenêtre ou Paramètres), ces sons sont laissés tels quels.
    reanalyze_rekordbox: list = field(default_factory=lambda: ["grid"])
    waveform_style: str = "3band"      # 1.4.1 (C77) : « blue » | « rgb » | « 3band », comme Rekordbox
    reanalyze_rekordbox_asked: bool = False
    # 1.4.3 (C16) : grille des sons dont le tempo change : « auto » (variable ou par passage) | « never » (fixe)
    tempo_grid: str = "auto"
    # 1.4.3 (A07, C156) : sur l'ordinateur, « Supprimer » envoie aussi à la corbeille les fichiers que DJSync n'a pas
    # téléchargés ; coché, ces sons sont seulement retirés de Rekordbox (comme avant la 1.4.3)
    protect_foreign: bool = False
    # 1.4.3 (C214) : vues de colonnes de la Bibliothèque : {"current", "custom": {id: {name, shown}},
    # "saved": {vue d'origine: shown}, "by_list": {clé|liste: id}}
    library_views: dict = field(default_factory=dict)
    local_hosts: list = field(default_factory=list)   # version portable : PC dont la bibliothèque a été acceptée
    diag_ignored: list = field(default_factory=list)  # V1.1.0 : problèmes du diagnostic marqués « ignorer »
    check_updates: bool = True                        # V1.2.0 : nouvelle version de DJSync ? (une fois par jour)
    last_update_check: float = 0.0
    update_channel: str = "auto"       # 1.2.0-rc.4 : auto (version de test -> versions de test) | stable | test
    # ---- 1.2.1
    table_layouts: dict = field(default_factory=dict)   # {vue: {"hidden": [...], "widths": {col: px à 100 %}}}
    playlist_sorts: dict = field(default_factory=dict)  # {playlist: [colonne, décroissant]} (tri retenu)
    search_field: str = "all"          # recherche : all | title | artist | album
    search_hide_owned: bool = False    # recherche : masquer ce qui est déjà dans la bibliothèque
    search_tab: str = "search"         # 1.4.3 (C202) : dernier onglet de « Rechercher » (search | hq | import)
    search_max_minutes: int = 0        # recherche : durée maximale (0 = pas de limite ; exclut les mixes)
    feedback_id: str = ""              # onglet Retours : identifiant aléatoire (limites d'envoi)
    # ---- 1.2.2
    genre_playlists: dict = field(default_factory=dict)   # {bibliothèque: config des playlists par genre}
    # ---- 1.2.3
    scrolling_wave: bool = True        # forme d'onde défilante (tête de lecture au centre) dans le lecteur
    audio_latency_ms: int = 0          # 1.3.0-rc.3 (C39) : retard de sortie en plus (Bluetooth…), pour les curseurs
    grid_fixed_cursor: bool = False    # 1.3.0-rc.3 (B17) : Grille et cues, curseur fixe au centre (sinon volant)
    dup_auto_verify: bool = True       # 1.4.4 (C236) : Doublons, groupes vérifiés par le son sans attendre
    grid_wave_height: int = 0          # 1.4.4 (C233) : hauteur de la forme d'onde de Grille et cues (0 = automatique)
    grid_magnet: int = 0               # 1.4.1 (C92) : aimant de Grille et cues (0 = coupé, 1 = au temps, 4 = au quart)
    error_reports: str = "ask"         # rapports d'erreur à l'auteur : ask (demander) | always | never
    # ---- V1.0.0
    player_format: str = ""            # 1.4.0 (C26 sens C) : FLAC enregistrés sur la clé en "wav" / "aiff"
    youtube_best: bool = False         # 1.4.0 (C48) : meilleur flux YouTube (AAC 256), plus lourd
    light_mode: str = "auto"           # 1.4.0 (C65) : mode léger auto | on | off
    light_prompt_off: bool = False     # 1.4.0 (C65) : ne plus proposer le mode léger au démarrage
    light_offered: list = field(default_factory=list)  # 1.4.2 (C174) : PC (identifiants hachés) où il a été proposé
    set_players: str = "all"           # 1.4.2 (C67) : platines visées par « Prêt pour le set ? »
    mytags_column_shown: bool = False  # 1.4.2 (C113) : colonne My Tags affichée d'elle-même une fois
    tour_state: str = ""               # 1.4.2 (C178) : visite guidée "" | later | done | never
    youtube_browser: str = ""          # navigateur connecté à YouTube (Premium : AAC 256 natif)
    improve_threshold: int = 256       # 1.4.0 (C47) : « Améliorer ma bibliothèque » sous ce débit réel (kbps)
    free_sources: list = field(default_factory=lambda: ["archive", "audius"])   # 1.4.0 (C45) : recherche Haute qualité
    hq_filters: dict = field(default_factory=dict)     # 1.4.1 (C134) : filtres de la page Haute qualité
    soulseek_enabled: bool = False     # 1.4.0 (C10.2) : désactivé par défaut
    soulseek_accepted: bool = False    # avertissement (VPN, droits, fiabilité) accepté une fois
    soulseek_user: str = ""
    soulseek_password: str = ""
    # 1.4.0-rc.2 (B60) : partagé par défaut : beaucoup de pairs refusent (« Banned ») ceux qui ne partagent rien
    soulseek_share: bool = True        # partager le dossier musique de la bibliothèque ouverte
    soulseek_port: int = 0             # 0 = port par défaut d'aioslsk
    watch_folder: str = ""             # 1.4.0 (C10.3) : dossier surveillé (vide = désactivé)
    watch_playlist: bool = True        # ranger les sons importés du dossier dans la playlist « Dossier surveillé »
    watch_first_done: bool = False     # 1.4.0-rc.5 (C160) : message du tout premier son importé déjà montré
    # 1.4.2 (B102) : bibliothèque que remplit le dossier surveillé : « local » (bibliothèque de l'ordinateur,
    # par défaut) ou « usb » (la clé ouverte). Si elle n'est pas ouverte, les fichiers attendent dans le dossier.
    watch_target: str = "local"
    # 1.4.2 (B103) : le Diagnostic ne calcule plus rien à l'ouverture (bouton « Analyser maintenant ») ;
    # coché, il recalcule à chaque ouverture comme avant. Derniers chiffres gardés par bibliothèque, avec leur date.
    diag_auto: bool = False
    uni_scope: str = "problems"         # 1.4.2 (C198) : dernière portée d'Uniformiser (présélectionnée)
    uni_scope_playlist: str = ""
    diag_last: dict = field(default_factory=dict)
    watch_scanned: str = ""            # 1.4.1 (B95) : dossier (et bibliothèque) déjà rattrapés à l'activation
    soundcloud_original: bool = True   # 1.4.0 (C10.1) : fichier d'origine SoundCloud quand l'artiste le permet
    soundcloud_browser: str = ""       # navigateur où l'utilisateur est connecté à SoundCloud (cookies)
    soundcloud_token: str = ""         # ou jeton « oauth_token » du compte
    suggestions_open: bool = False     # 1.3.1 (C30) : panneau « Suggestions » de la Bibliothèque
    auto_lists_open: bool = True       # 1.4.2 (C188) : groupe « Listes automatiques » déplié
    panels_folded: dict = field(default_factory=dict)  # 1.4.2 (C189) : {"downloads"|"analysis": replié}
    suggest_tolerance: int = 6         # 1.3.1 (C30) : écart de BPM accepté (%)
    settings_section: str = "general"  # 1.3.1 (C28) : dernière section ouverte des Paramètres
    settings_version: int = 0          # migrations des réglages enregistrés
    # ---- 1.3.2
    welcome_done: bool = False         # C54 : accueil du premier lancement vu (ou passé)
    diag_tab: str = "one"              # 1.3.2-rc.3 (C127) : dernier onglet du Diagnostic ; 1.4.1 (C140) : « Un son »
    start_menu_shortcut: bool = False  # C70 : raccourci menu Démarrer / Applications / menu Linux
    # ---- 1.4.4
    show_tooltips: bool = True         # C219 : infobulles au survol (les ⓘ restent toujours disponibles)
    track_info_open: bool = False      # C138 : volet « Infos » d'un son ouvert dans la Bibliothèque
    track_info_width: int = 0          # C138 : largeur choisie du volet (0 : par défaut)

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
            settings.first_run = True              # 1.3.2 (C54) : vrai premier lancement (pas une mise à jour)
            return settings
        except (OSError, json.JSONDecodeError) as exc:
            # 1.4.3 (A6-10) : la copie illisible est gardée à part, puis le dernier bon fichier (.bak) est repris
            log.warning("Unreadable settings (%s): kept aside, trying the last good copy.", exc)
            try:
                from datetime import datetime

                shutil.copy2(path, path.with_name(f"settings-unreadable-{datetime.now():%Y%m%d-%H%M%S}.json"))
            except OSError:
                log.debug("Ignored error in load", exc_info=True)  # 1.4.3 (A3-4)
            bak = path.with_name(path.name + ".bak")
            try:
                raw = json.loads(bak.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("not an object")
                log.warning("Settings restored from %s", bak.name)
            except (OSError, ValueError) as exc2:
                log.warning("No usable settings backup (%s): using defaults.", exc2)
                return settings
        for f in fields(cls):
            if f.name in raw and isinstance(raw[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, raw[f.name])  # type incorrect : on garde la valeur par défaut
        if "welcome_done" not in raw:                   # 1.3.2 (C54) : mise à jour d'une version d'avant
            settings.welcome_done = True
        settings.normalize()
        return settings

    def normalize(self) -> "Settings":
        """Valeurs hors limites / inconnues ramenées à des valeurs valides (fichier édité à la main)."""
        if self.search_tab not in ("search", "hq", "import"):
            self.search_tab = "search"
        self.zoom = clamp_zoom(self.zoom)
        self.show_tooltips = bool(self.show_tooltips)                                              # 1.4.4 (C219)
        self.language = self.language if self.language in LANGUAGE_CODES else DEFAULT_LANGUAGE
        self.pdb_sync = self.pdb_sync if self.pdb_sync in ("auto", "off") else "auto"
        self.sidebar_compact = self.sidebar_compact if self.sidebar_compact in ("auto", "on", "off") else "auto"
        self.key_notation = self.key_notation if self.key_notation in ("auto", "camelot", "musical") else "auto"
        self.set_players = self.set_players if self.set_players in ("all", "recent", "nxs2", "old") else "all"
        if not isinstance(self.light_offered, list):
            self.light_offered = []
        self.volume = max(0.0, min(1.0, float(self.volume)))
        self.audio_latency_ms = max(-200, min(2000, int(self.audio_latency_ms or 0)))
        if self.settings_version < 1:      # V1.0.0 : l'ajout de pages à export.pdb devient le défaut
            self.pdb_allow_growth = True   # (sans lui, une clé exportée par Rekordbox est pleine en ~15 sons)
            self.settings_version = 1
        if self.settings_version < 2:      # 1.3.0-rc.3 (C32) : analyse après téléchargement activée pour tous
            self.analyze_after_download_usb = self.analyze_after_download_local = True
            self.settings_version = 2
        self.audio_format = self.audio_format if self.audio_format in ("m4a", "mp3") else "m4a"
        if self.download_quality not in DOWNLOAD_QUALITIES:          # 1.4.1 (C143) : reprise, sans question
            self.download_quality = ("mp3_320" if self.audio_format == "mp3"
                                     else "yt_best" if self.youtube_best else "original")
        # anciens réglages déduits du nouveau (lus ailleurs : qualité attendue, accueil) ; jamais écrits
        self.audio_format = "mp3" if self.download_quality.startswith("mp3") else "m4a"
        self.youtube_best = self.download_quality == "yt_best"
        self.normalize_volume = False
        self.update_channel = self.update_channel if self.update_channel in ("auto", "stable", "test") else "auto"
        self.error_reports = self.error_reports if self.error_reports in ("ask", "always", "never") else "ask"
        self.table_layouts = self.table_layouts if isinstance(self.table_layouts, dict) else {}
        self.library_views = self.library_views if isinstance(self.library_views, dict) else {}       # C214
        self.playlist_sorts = dict(list(self.playlist_sorts.items())[-500:]) if isinstance(self.playlist_sorts, dict) else {}
        self.search_field = self.search_field if self.search_field in ("all", "title", "artist", "album") else "all"
        if self.search_mode == "artists":          # 1.2.1 : « Artistes » passe du popup au champ de recherche
            self.search_field, self.search_mode = "artist", "all"
        self.search_max_minutes = max(0, min(600, int(self.search_max_minutes or 0)))
        self.genre_playlists = self.genre_playlists if isinstance(self.genre_playlists, dict) else {}
        self.hq_filters = self.hq_filters if isinstance(self.hq_filters, dict) else {}
        self.panels_folded = self.panels_folded if isinstance(self.panels_folded, dict) else {}
        self.local_hosts = [str(h) for h in self.local_hosts][:50]
        self.diag_ignored = [str(k) for k in self.diag_ignored][-500:]
        if self.merge_undo_s not in (5, 10, 30):
            self.merge_undo_s = 10
        parts = self.reanalyze_rekordbox if isinstance(self.reanalyze_rekordbox, list) else ["grid"]
        self.reanalyze_rekordbox = [p for p in ("grid", "key", "waves") if p in parts]      # 1.4.1 (C131)
        if self.waveform_style not in ("blue", "rgb", "3band"):                                  # 1.4.1 (C77)
            self.waveform_style = "3band"
        if self.tempo_grid not in ("auto", "never"):                                               # 1.4.3 (C16)
            self.tempo_grid = "auto"
        from .db import backup_levels                                                                # 1.4.4 (C235)

        if self.backup_level not in backup_levels.LEVELS:
            self.backup_level = backup_levels.from_copies(int(self.backup_keep or 10))
        self.backup_keep = backup_levels.LEVELS[self.backup_level]["copies"]
        backup_levels.set_level(self.backup_level)
        return self

    def native_parts(self) -> tuple:
        """1.4.1 (C131, D20) : ce qu'une réanalyse refait sur un son de Rekordbox ; rien tant que le choix
        n'a pas été fait."""
        return tuple(self.reanalyze_rekordbox) if self.reanalyze_rekordbox_asked else ()

    # 1.3.2 (C57) : « Rétablir les réglages par défaut ». Jamais touchés : ce qui n'est pas un réglage mais
    # un état ou une mémoire (fenêtre, onglets, colonnes, tris, choix « ignorer », identifiants).
    KEEP_ALWAYS = ("geometry", "maximized", "last_tab", "table_layouts", "playlist_sorts", "feedback_id",
                   "diag_ignored", "genre_playlists", "local_hosts", "settings_section", "settings_version",
                   "last_update_check", "active_drive", "welcome_done", "start_menu_shortcut",
                   "diag_tab", "auto_lists_open", "panels_folded", "library_views")
    # Gardés si l'utilisateur le souhaite (case cochée par défaut) : langue, dossiers et bibliothèques.
    KEEP_CHOICES = ("language", "forced_drive", "contents_dir", "ffmpeg_location", "local_db_dir", "local_music_dir")

    def reset_to_defaults(self, keep_choices: bool = True) -> dict:
        """Remet les réglages aux valeurs d'origine ; renvoie l'ancien contenu (pour « Annuler »)."""
        old = asdict(self)
        fresh = type(self)()
        keep = set(self.KEEP_ALWAYS) | (set(self.KEEP_CHOICES) if keep_choices else set())
        for f in fields(self):
            if f.name not in keep:
                setattr(self, f.name, getattr(fresh, f.name))
        self.normalize()
        return old

    def restore(self, values: dict) -> None:
        for f in fields(self):
            if f.name in values:
                setattr(self, f.name, values[f.name])
        self.normalize()

    def save(self, path: Optional[Path] = None) -> None:
        path = path or self.path()
        self.normalize()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            data = {k: v for k, v in asdict(self).items() if k not in RETIRED}     # 1.4.1 (C143)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, indent=2, ensure_ascii=False))
                fh.flush()
                durable.flush_fd(fh.fileno())                  # 1.4.3 (A6-10)
            if path.is_file():                         # 1.4.3 (A6-10) : dernier bon fichier gardé
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    shutil.copy2(path, path.with_name(path.name + ".bak"))
                except (OSError, ValueError):
                    log.debug("Ignored error in save", exc_info=True)  # 1.4.3 (A3-4)
            durable.replace(tmp, path)
        except OSError as exc:
            log.warning("Settings not saved: %s", exc)
