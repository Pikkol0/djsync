"""TOUS les modèles de données de DJSync, dans un seul fichier.

Données uniquement (aucune logique métier, aucune dépendance externe) : recherche et
téléchargement, import par URL, correspondance Spotify, bibliothèque de la clé USB, file de
téléchargements. Les comportements (scoring, choix, accès DB…) vivent dans les modules qui
importent ces classes : `core/matcher.py`, `core/urlimport.py`, `db/usb_library.py`…
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Tuple

from .core.camelot import to_camelot
from .i18n import LazyLabels, get_language, t

# ======================================================================================
# 1. Recherche & téléchargement
# ======================================================================================


class SearchMode(str, Enum):
    """Ce que cherche l'utilisateur (menu « Type » du popup Filtres)."""

    ALL = "all"
    SONGS = "songs"
    VIDEOS = "videos"
    ARTISTS = "artists"


# Libellés traduits à la lecture (suivent la langue active) : SEARCH_MODE_LABELS[mode] -> "All" / "Tout"
SEARCH_MODE_LABELS = LazyLabels(lambda: {
    SearchMode.ALL: "mode.all",
    SearchMode.SONGS: "mode.songs",
    SearchMode.VIDEOS: "mode.videos",
    SearchMode.ARTISTS: "mode.artists",
})

SOURCE_LABELS = {"ytmusic": "YouTube Music", "youtube": "YouTube", "soundcloud": "SoundCloud"}


def source_from_url(url: Optional[str]) -> str:
    """1.2.1 (C06) : source d'un son d'après son lien d'origine (« YouTube Music », « SoundCloud »…),
    "" si inconnue (son ajouté par Rekordbox ou fichier local). Nouvelles sources : une ligne ici."""
    u = (url or "").lower()
    if not u:
        return ""
    for needle, name in (("music.youtube.", "YouTube Music"), ("soundcloud.", "SoundCloud"), ("youtu", "YouTube"),
                         ("spotify.", "Spotify"), ("bandcamp.", "Bandcamp"), ("deezer.", "Deezer")):
        if needle in u:
            return name
    if len(u) == 11 and all(c.isalnum() or c in "-_" for c in u):       # identifiant de vidéo YouTube seul
        return "YouTube"
    return ""


def format_duration(seconds: int) -> str:
    """m:ss (ou h:mm:ss)."""
    m, s = divmod(max(0, int(seconds or 0)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_views(n: Optional[int]) -> str:
    """1 234 -> '1.2 k' (EN) / '1,2 k' (FR) ; 1 250 000 -> '1.3 M' ; None -> '—'."""
    if n is None:
        return "—"
    for limit, unit in ((1_000_000_000, "Md"), (1_000_000, "M"), (1_000, "k")):
        if n >= limit:
            value = n / limit
            text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
            sep = "," if get_language() == "fr" else "."
            return text.replace(".", sep).removesuffix(sep + "0") + f" {unit}"
    return str(n)


@dataclass(frozen=True)
class TrackResult:
    """Un morceau téléchargeable : résultat de recherche YouTube Music, ou entrée d'une URL
    YouTube / SoundCloud importée directement."""

    video_id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: int = 0
    thumbnail_url: Optional[str] = None

    # "song" = titre officiel (audio du catalogue) ; "video" = clip / upload utilisateur
    result_type: str = "song"
    views: Optional[int] = None          # None = inconnu (les titres n'ont pas de vues dans la recherche)
    video_type: Optional[str] = None     # MUSIC_VIDEO_TYPE_ATV / OMV / UGC (brut, pour information)

    # D'où vient le morceau : "ytmusic" (recherche) | "youtube" | "soundcloud" (import d'URL)
    source: str = "ytmusic"
    source_url: Optional[str] = None     # URL exacte à télécharger (import direct)

    # Métadonnées complémentaires (V0.3.0, core/metadata.py) : écrites dans les tags et la base
    year: int = 0
    release_date: Optional[str] = None
    genre: Optional[str] = None
    label: Optional[str] = None
    track_no: int = 0
    isrc: Optional[str] = None

    # Renseignés par DuplicateChecker
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None   # ex. "Daft Punk - One More Time"

    @property
    def url(self) -> str:
        return self.source_url or f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def is_song(self) -> bool:
        return self.result_type == "song"

    @property
    def is_album(self) -> bool:
        """1.2.1 (C09) : ligne « album » de la recherche (video_id = identifiant de l'album)."""
        return self.result_type == "album"

    @property
    def kind_label(self) -> str:
        if self.is_album:
            return t("track.album_kind")
        return t("track.song") if self.is_song else t("track.video")

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration_seconds)

    @property
    def views_str(self) -> str:
        return format_views(self.views)

    def with_duplicate(self, duplicate_of: str) -> "TrackResult":
        return replace(self, is_duplicate=True, duplicate_of=duplicate_of)

    def with_views(self, views: Optional[int]) -> "TrackResult":
        return replace(self, views=views)


@dataclass(frozen=True)
class DownloadedTrack:
    """Résultat d'un téléchargement réussi."""

    track: TrackResult
    file_path: str


@dataclass
class DownloadProgress:
    """Évènement de progression transmis à l'UI."""

    status: str  # "downloading" | "converting" | "tagging" | "done" | "error"
    percent: float = 0.0
    message: str = field(default="")


# ======================================================================================
# 2. Import par URL (Spotify / YouTube / SoundCloud)
# ======================================================================================


class UrlKind(str, Enum):
    SPOTIFY = "spotify"          # -> correspondance via YouTube Music
    YOUTUBE = "youtube"          # -> téléchargement direct (yt-dlp)
    SOUNDCLOUD = "soundcloud"    # -> téléchargement direct (yt-dlp)
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SpotifyTrack:
    title: str
    artists: Tuple[str, ...] = ()
    album: Optional[str] = None
    duration_seconds: int = 0

    @property
    def artist(self) -> str:
        return ", ".join(self.artists)

    @property
    def display(self) -> str:
        return f"{self.artist} – {self.title}" if self.artists else self.title

    @property
    def query(self) -> str:
        """Requête de recherche YouTube Music : artiste principal + titre."""
        return f"{self.artists[0]} {self.title}".strip() if self.artists else self.title


@dataclass
class SpotifyPlaylist:
    name: str
    tracks: List[SpotifyTrack] = field(default_factory=list)
    source_url: str = ""
    truncated: bool = False  # True si Spotify n'a donné que les 100 premiers morceaux


@dataclass
class ResolvedUrl:
    """Contenu d'une URL YouTube/SoundCloud (titre unique ou playlist), prêt à télécharger."""

    kind: UrlKind
    name: str
    tracks: List[TrackResult] = field(default_factory=list)
    source_url: str = ""
    is_playlist: bool = False
    note: str = ""           # information à afficher (ex. « seule la vidéo est importée »)
    truncated: bool = False


# ======================================================================================
# 3. Correspondance Spotify -> YouTube Music
# ======================================================================================

OK_SCORE = 75.0      # correspondance fiable
LOW_SCORE = 55.0     # plausible : à vérifier par l'utilisateur


class MatchPreference(str, Enum):
    AUTO = "auto"
    SONG = "song"
    VIDEO = "video"


PREFERENCE_LABELS = LazyLabels(lambda: {
    MatchPreference.AUTO: "match.auto",
    MatchPreference.SONG: "match.song",
    MatchPreference.VIDEO: "match.video",
})


@dataclass
class Candidate:
    track: TrackResult
    score: float


@dataclass
class MatchResult:
    """Un morceau Spotify et ses candidats YouTube Music (triés par score décroissant)."""

    source: SpotifyTrack
    candidates: List[Candidate] = field(default_factory=list)
    chosen: Optional[int] = None        # index dans candidates
    manual: bool = False                # choisi à la main : la préférence ne le modifie plus

    @property
    def candidate(self) -> Optional[Candidate]:
        return self.candidates[self.chosen] if self.chosen is not None else None

    @property
    def status(self) -> str:
        """'ok' | 'review' | 'missing' | 'duplicate' (déjà en bibliothèque)."""
        c = self.candidate
        if c is None:
            return "missing"
        if c.track.is_duplicate:
            return "duplicate"
        return "ok" if c.score >= OK_SCORE else "review"

    def cycle(self) -> None:
        """Candidat suivant (choix manuel)."""
        if self.candidates:
            self.chosen = 0 if self.chosen is None else (self.chosen + 1) % len(self.candidates)
            self.manual = True


# ======================================================================================
# 4. Bibliothèque de la clé USB (exportLibrary.db)
# ======================================================================================

# Valeurs de playlist.attribute dans exportLibrary.db
PLAYLIST_KIND = 0
FOLDER_KIND = 1
SMART_PLAYLIST_KIND = 4


@dataclass(frozen=True)
class PlaylistInfo:
    playlist_id: int
    name: str
    parent_id: int          # 0 = racine
    kind: int               # 0 playlist, 1 dossier, 4 playlist intelligente
    sequence: int           # ordre d'affichage parmi ses frères
    track_count: int

    @property
    def is_folder(self) -> bool:
        return self.kind == FOLDER_KIND

    @property
    def is_editable(self) -> bool:
        """Seules les playlists classiques acceptent des ajouts/retraits de sons."""
        return self.kind == PLAYLIST_KIND


@dataclass(frozen=True)
class LibraryTrack:
    content_id: int
    title: str
    artist: str
    album: Optional[str]
    duration_seconds: int
    path: str                        # relatif à la racine de la clé, ex. "/Contents/X/Y/z.m4a"
    bpm: float                       # 0.0 tant que le son n'est pas analysé
    file_type: int
    source_url: Optional[str]        # URL d'origine stockée dans djComment, si connue
    date_added: str
    is_analysed: bool
    artwork_path: Optional[str] = None   # pochette Rekordbox (ex. "/PIONEER/Artwork/00001/b1.jpg")
    sequence: int = 0                    # position dans la playlist (0 hors vue playlist)
    key: Optional[str] = None            # tonalité Rekordbox brute ("Am", "F#m"…), None si non analysé
    analysis_path: Optional[str] = None  # ".../ANLZ0000.DAT" (formes d'onde du lecteur, éditeur de grille)

    @property
    def camelot(self) -> Optional[str]:
        """Tonalité en notation Camelot ("8A"), None si inconnue."""
        return to_camelot(self.key)

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title


# ======================================================================================
# 5. File de téléchargements (historique de la session)
# ======================================================================================

JOB_STATUS_LABELS = LazyLabels(lambda: {
    "queued": "job.queued",
    "downloading": "job.downloading",
    "converting": "job.converting",
    "tagging": "job.tagging",
    "adding": "job.adding",
    "done": "job.done",
    "error": "job.error",
})


@dataclass
class DownloadJob:
    id: int
    track: TrackResult
    playlist_ids: List[int] = field(default_factory=list)
    playlist_names: List[str] = field(default_factory=list)
    status: str = "queued"
    percent: float = 0.0
    message: str = ""
    file_path: Optional[str] = None
    content_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    library: Any = field(default=None, repr=False, compare=False)  # clé visée (fixée à l'ajout)
    replace_ids: List[int] = field(default_factory=list)   # V1.1.0 : sons remplacés une fois téléchargé
    reanalyse: bool = False                                # … et analyser le nouveau (l'ancien l'était)

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "error")

    @property
    def is_active(self) -> bool:
        return self.status in ("downloading", "converting", "tagging", "adding")

    @property
    def progress(self) -> float:
        """1.2.1 (C21) : avancement de 0 à 1 (téléchargement = 80 %, puis conversion, tags, ajout)."""
        return {"queued": 0.0, "downloading": 0.8 * max(0.0, min(100.0, self.percent)) / 100.0, "converting": 0.85,
                "tagging": 0.92, "adding": 0.96}.get(self.status, 1.0)

    @property
    def status_label(self) -> str:
        label = JOB_STATUS_LABELS.get(self.status, self.status)
        return f"{label} {self.percent:.0f} %" if self.status == "downloading" else label
