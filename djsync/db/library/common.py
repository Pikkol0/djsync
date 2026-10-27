"""Gestion de PIONEER/rekordbox/exportLibrary.db (OneLibrary / Device Library Plus).

Points clés, vérifiés sur une vraie base de clé USB :
  * la base est chiffrée en SQLCipher 4 (le module `sqlite3` standard ne peut PAS l'ouvrir) ;
  * elle est en mode WAL ; le -wal est chiffré lui aussi ;
  * les chemins sont stockés relatifs à la racine de la clé, en "/", ex. "/Contents/Artiste/Album/x.mp3" ;
  * playlist.attribute : 0 = playlist, 1 = dossier, 4 = playlist intelligente ;
  * un son ajouté sans analyse laisse NULL : analysisDataFilePath, analysedBits, masterDbId,
    masterContentId, contentLink (même choix que pyrekordbox) ;
  * color_id et artist_id_lyricist valent 0 (et non NULL) pour un son sans valeur : c'est la
    convention des sons créés par Rekordbox lui-même (constaté sur une vraie clé : 213 sons natifs
    sur 213 ont 0). La V1.1-A les mettait à NULL par erreur ; rétabli ;
  * V1.1-A4 : chaque son ajouté est ANALYSÉ localement (djsync/analysis : BPM + grille, tonalité,
    formes d'onde ANLZ écrites dans PIONEER/USBANLZ) et reçoit sa POCHETTE (PIONEER/Artwork) ; la
    date d'ajout suit le format des sons natifs de la clé. analysisDataFilePath, bpmx100, key_id et
    image_id sont donc renseignés ; en cas d'échec de l'analyse, le son est ajouté comme avant ;
  * V1.1-A3 : si la clé contient aussi l'ancien format (PIONEER/rekordbox/export.pdb, lu par les
    platines CDJ/XDJ « historiques »), chaque écriture est répercutée dans ce fichier APRÈS le commit de
    exportLibrary.db (voir djsync/db/pdb/). export.pdb n'est jamais créé, seulement mis à jour s'il est
    reconnu ; en cas d'échec, l'écriture OneLibrary reste valide et `pdb_state` passe à « stale ».

Sécurité des données :
  * sauvegarde chiffrée de la base avant la première écriture de chaque session ;
  * chaque modification = une transaction (BEGIN IMMEDIATE ... COMMIT), annulée si erreur ;
  * après chaque commit, `wal_checkpoint(TRUNCATE)` : le fichier principal contient tout et le
    -wal est vidé, car un lecteur/une platine qui ignore le WAL ne verrait sinon rien de neuf.
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from sqlcipher3 import dbapi2 as sqlcipher

from .._key import get_default_key
from ..base import KEEP, LibraryBackend
from ..errors import (
    DatabaseLockedError,
    DatabaseOpenError,
    DuplicatePlaylistError,
    LibraryError,
    PlaylistNotFoundError,
    ReadOnlyError,
    TrackNotFoundError,
    UnsupportedFormatError,
)
from ...core.camelot import to_camelot
from ...models import FOLDER_KIND, PLAYLIST_KIND, LibraryTrack, PlaylistInfo
from .. import artwork as _art
from ..pdb import PdbDatabase, PdbError, PdbStore, Summary as PdbSummary, TrackMeta
from ..pdb import sync as pdb_sync_mod
from ..pdb.sync import PLAYLIST_DELETED, TRACK_DELETED, TRACK_FIELDS
from ..usb import UsbDrive, drive_from_letter

log = logging.getLogger(__name__)

# Extension -> content.fileType (codes constatés dans la base + enum pyrekordbox)
FILE_TYPES = {".mp3": 1, ".m4a": 4, ".aac": 4, ".flac": 5, ".wav": 11, ".aiff": 12, ".aif": 12}
REQUIRED_TABLES = {"content", "playlist", "playlist_content", "artist", "album", "property"}
# Tables annexes qui référencent un son : nettoyées à la suppression d'un son
_CONTENT_REFS = ("cue", "history_content", "myTag_content")
_VIDEO_ID = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#\s]*&)?v=|embed/|shorts/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
)

# (colonne de content, table référencée, colonne id) : clés étrangères vérifiées par diagnose()/repair()
_CONTENT_FKS = (
    ("artist_id_artist", "artist", "artist_id"), ("artist_id_remixer", "artist", "artist_id"),
    ("artist_id_originalArtist", "artist", "artist_id"), ("artist_id_composer", "artist", "artist_id"),
    ("artist_id_lyricist", "artist", "artist_id"), ("album_id", "album", "album_id"),
    ("genre_id", "genre", "genre_id"), ("label_id", "label", "label_id"), ("key_id", "key", "key_id"),
    ("color_id", "color", "color_id"), ("image_id", "image", "image_id"),
)
LEGACY_DB_NAMES = ("export.pdb", "exportExt.pdb")
PdbOp = Callable[[PdbDatabase], None]
PdbPath = Tuple[str, ...]

def _meta_select(has_key: bool, has_image: bool) -> str:
    """SELECT des métadonnées utiles à export.pdb. Colonnes 0..16 comme en V1.1-A3, puis
    17 = tonalité, 18 = chemin de la pochette, 19 = chemin d'analyse (V1.1-A4)."""
    return (
        "SELECT c.content_id, COALESCE(c.title,''), COALESCE(a.name,''), COALESCE(al.name,''), COALESCE(c.length,0), "
        "COALESCE(c.bpmx100,0), COALESCE(c.fileSize,0), COALESCE(c.bitrate,0), COALESCE(c.bitDepth,16), "
        "COALESCE(c.samplingRate,44100), COALESCE(c.fileType,0), COALESCE(c.dateAdded,''), COALESCE(c.djComment,''), "
        "COALESCE(c.trackNo,0), COALESCE(c.discNo,0), COALESCE(c.releaseYear,0), c.path, "
        + ("COALESCE(k.name,'')" if has_key else "''") + ", "
        + ("COALESCE(im.path,'')" if has_image else "''") + ", COALESCE(c.analysisDataFilePath,'') FROM content c "
        "LEFT JOIN artist a ON a.artist_id = c.artist_id_artist LEFT JOIN album al ON al.album_id = c.album_id "
        + ("LEFT JOIN key k ON k.key_id = c.key_id " if has_key else "")
        + ("LEFT JOIN image im ON im.image_id = c.image_id " if has_image else "")
    )


# Formats de date relevés : « 2024-10-18 » (date seule) ou horodatage complet
# « 2025-04-12 19:11:29.274 +00:00 » (format des bases OneLibrary d'après pyrekordbox).
_DATE_FULL = re.compile(r"^(\d{4}-\d{2}-\d{2})([ T])(\d{2}:\d{2}:\d{2})(\.\d+)?(\s*)(Z|[+-]\d{2}:?\d{2})?")
_CAMELOT_NAME = re.compile(r"^(0?[1-9]|1[0-2])[AB]$", re.I)


def format_date_like(sample: Optional[str], now: Optional[datetime] = None) -> str:
    """Date d'ajout « maintenant », dans la même forme que `sample` (une date d'un son natif).

    sample None (base sans son natif, ex. clé vide préparée par Rekordbox) : date seule « AAAA-MM-JJ »,
    la forme qu'écrit Rekordbox 7 dans exportLibrary.db. (Jusqu'à la 1.3.0-rc.1 : horodatage complet UTC,
    que Rekordbox n'écrit pas ; sur une clé vide, Rekordbox jugeait alors la bibliothèque corrompue, B13.)"""
    now = now or datetime.now(timezone.utc)
    if sample is None or len(sample.strip()) == 10:
        return now.astimezone().strftime("%Y-%m-%d")
    m = _DATE_FULL.match(sample.strip()) if sample else None
    if sample is not None and m is None:
        return now.astimezone().strftime("%Y-%m-%d")
    sep, frac, space, tz = (m.group(2), m.group(4) or "", m.group(5) or "", m.group(6)) if m else (" ", ".000", " ", "+00:00")
    if tz in ("Z", "+00:00", "+0000", "-00:00"):
        moment = now.astimezone(timezone.utc)
    else:
        moment = now.astimezone()
    text = moment.strftime(f"%Y-%m-%d{sep}%H:%M:%S")
    if frac:
        digits = len(frac) - 1
        text += "." + f"{moment.microsecond:06d}"[:digits].ljust(digits, "0")
    if tz is not None:
        if tz == "Z":
            text += "Z"
        else:
            off = moment.strftime("%z") or "+0000"
            text += space + (off if ":" not in tz else f"{off[:3]}:{off[3:]}")
    return text


@dataclass
class _Extras:
    """Résultat de l'analyse et de la pochette, préparé AVANT la transaction (calcul long)."""

    analysis: Any = None                    # djsync.analysis.AnalysisResult
    anlz_path: Optional[str] = None
    jpegs: Optional[Dict[str, bytes]] = None
    problems: List[str] = field(default_factory=list)
    written: List[Path] = field(default_factory=list)   # fichiers créés (supprimés si la base refuse)
    cue_ms: Optional[int] = None            # V0.5.0 : mémoire automatique (premier temps fort)


@dataclass
class PdbStatus:
    """État de export.pdb par rapport à exportLibrary.db (affiché dans Paramètres)."""

    state: str                  # off | absent | unsupported | stale | ok
    detail: str = ""
    pdb_tracks: int = 0
    ol_tracks: int = 0
    missing_tracks: int = 0
    missing_playlists: int = 0
    # 1.3.0-rc.2 : écarts complets (voir db/pdb/sync.py)
    different_playlists: int = 0     # contenu ou ordre différent
    changed_tracks: int = 0          # infos modifiées pas encore recopiées, ou analyse manquante
    pending_removals: int = 0        # sons / playlists supprimés ou renommés encore présents


# 1.3.1 (C37) : colonnes supplémentaires de content (index 13 à 23 du SELECT des sons)
_EXTRA_COLS = ("releaseYear", "bitrate", "samplingRate", "rating", "color_id", "djPlayCount", "dateCreated", "fileSize")


def _track_select(has_key: bool, with_sequence: bool = False, content_cols: Optional[set] = None,
                  tables: Optional[set] = None) -> str:
    """SELECT commun des sons. Colonnes : 0..11 comme avant, 12 = tonalité, 13 = genre, 14 = label,
    15..22 = _EXTRA_COLS, 23 = position (playlist). `content_cols` / `tables` : colonnes de content et
    tables présentes (None = toutes) ; une colonne absente donne NULL."""
    def has(col: str) -> bool:
        return content_cols is None or col in content_cols

    genre = tables is None or "genre" in tables
    lab = tables is None or "label" in tables
    extras = [
        "g.name" if genre and has("genre_id") else "NULL",
        "lb.name" if lab and has("label_id") else "NULL",
    ] + [f"c.{c}" if has(c) else "NULL" for c in _EXTRA_COLS]
    return (
        "SELECT c.content_id, c.title, COALESCE(a.name, ''), al.name, COALESCE(c.length, 0), c.path, "
        "COALESCE(c.bpmx100, 0), COALESCE(c.fileType, 0), c.djComment, "
        "COALESCE(c.dateAdded, ''), c.analysisDataFilePath, im.path, "
        + ("k.name" if has_key else "NULL") + ", " + ", ".join(extras)
        + (", pc.sequenceNo" if with_sequence else "")
        + " FROM content c "
        "LEFT JOIN artist a  ON a.artist_id  = c.artist_id_artist "
        "LEFT JOIN album  al ON al.album_id  = c.album_id "
        "LEFT JOIN image  im ON im.image_id  = c.image_id "
        + ("LEFT JOIN key k ON k.key_id = c.key_id " if has_key else "")
        + ("LEFT JOIN genre g ON g.genre_id = c.genre_id " if genre and has("genre_id") else "")
        + ("LEFT JOIN label lb ON lb.label_id = c.label_id " if lab and has("label_id") else "")
    )


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extrait l'identifiant YouTube (11 caractères) d'une URL, ou le renvoie s'il est déjà nu."""
    text = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = _VIDEO_ID.search(text)
    return m.group(1) if m else None


def _safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned[:100] or fallback




__all__ = [_n for _n in dir() if not _n.startswith("__")]
