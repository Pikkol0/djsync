"""1.4.4 (C15) : mode live, voie XML seule (sans Qt).

Pendant un set, Rekordbox ouvert : DJSync télécharge et analyse un son, puis l'écrit dans `djsync-live.xml`
(« Bibliothèque rekordbox xml » de Rekordbox, relue avec son bouton Actualiser). Rien n'est écrit dans master.db ni
sur une clé pendant le live. Le live est gardé dans un petit registre (`live/AAAA-MM-JJ.json`) pour survivre à une
fermeture de DJSync ; « Terminer le live » (Rekordbox fermé) range les sons dans la bibliothèque de l'ordinateur sans
doublon (un son déjà importé par Rekordbox en le glissant sur un deck est seulement ajouté à la playlist).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

log = logging.getLogger(__name__)

XML_NAME = "djsync-live.xml"
PLAYLIST_PREFIX = "DJSync Live"
FOLDER_NAME = "Live"
STATES = ("queued", "downloading", "analysing", "ready", "error")


@dataclass
class LiveTrack:
    key: str                                  # lien d'origine (ou titre + artiste)
    title: str
    artist: str
    album: str = ""
    url: str = ""
    source: str = ""
    path: str = ""                            # fichier sur l'ordinateur
    status: str = "queued"
    error: str = ""
    added_at: str = ""                        # heure (HH:MM)
    ready_at: str = ""
    seconds: float = 0.0                      # temps entre la demande et « prêt »
    duration: float = 0.0
    bpm: float = 0.0
    key_name: str = ""                        # tonalité (« Am »)
    beats: List[Tuple[int, int, int]] = field(default_factory=list)      # (numéro, tempo x100, ms)
    cues: List[Tuple[int, int, str]] = field(default_factory=list)        # (pad 0 = mémoire, ms, nom)
    existing: bool = False                    # déjà dans la bibliothèque : pas téléchargé

    @property
    def ready(self) -> bool:
        return self.status == "ready" and bool(self.path)


@dataclass
class LiveSession:
    date: str                                 # date du DÉBUT du live (un set après minuit la garde)
    tracks: List[LiveTrack] = field(default_factory=list)
    done: bool = False                        # rangé dans la bibliothèque
    started: float = 0.0

    @property
    def playlist_name(self) -> str:
        return f"{PLAYLIST_PREFIX} – {self.date}"

    def find(self, key: str) -> Optional[LiveTrack]:
        k = norm_key(key)
        return next((t for t in self.tracks if norm_key(t.key) == k), None)


def norm_key(text: str) -> str:
    return " ".join((text or "").casefold().split())


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------------------------- registre
def live_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "live"


def xml_path(data_dir: Path) -> Path:
    return Path(data_dir) / XML_NAME


def _atomic_write(path: Path, data: bytes) -> None:
    """Fichier temporaire du même dossier puis renommage : jamais de fichier à moitié écrit (Rekordbox peut lire
    le XML pendant que DJSync l'écrit)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:                 # Windows : fichier lu au même instant, on réessaie
                if attempt == 4:
                    raise
                time.sleep(0.1)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save(session: LiveSession, data_dir: Path) -> Path:
    path = live_dir(data_dir) / f"{session.date}.json"
    _atomic_write(path, json.dumps(asdict(session), ensure_ascii=False, indent=1).encode("utf-8"))
    return path


def load(path: Path) -> Optional[LiveSession]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        tracks = []
        for t in raw.get("tracks", []):
            t = dict(t)
            t["beats"] = [tuple(b) for b in t.get("beats", [])]
            t["cues"] = [tuple(c) for c in t.get("cues", [])]
            known = {k: v for k, v in t.items() if k in LiveTrack.__dataclass_fields__}
            tracks.append(LiveTrack(**known))
        return LiveSession(str(raw["date"]), tracks, bool(raw.get("done", False)), float(raw.get("started", 0.0)))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Live register %s not read: %s", path, exc)
        return None


def open_session(data_dir: Path) -> Optional[LiveSession]:
    """Live pas encore rangé (le plus récent), à reprendre (fermeture de DJSync, set après minuit)."""
    folder = live_dir(data_dir)
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob("*.json"), reverse=True):
        s = load(path)
        if s is not None and not s.done:
            return s
    return None


def current(data_dir: Path) -> LiveSession:
    """Live en cours, sinon un nouveau live daté d'aujourd'hui."""
    return open_session(data_dir) or LiveSession(today(), started=time.time())


# ------------------------------------------------------------------------------- XML (Rekordbox)
def location(path: str) -> str:
    """Location d'un son dans un XML Rekordbox : file://localhost/C:/… (Windows) ou file://localhost/Users/… (Mac),
    encodée (espaces, accents)."""
    p = str(path).replace("\\", "/")
    if sys.platform != "win32" and not (len(p) > 1 and p[1] == ":"):
        p = p.lstrip("/")
    return "file://localhost/" + quote(p, safe="/:")


def tempo_points(beats: Sequence[Tuple[int, int, int]]) -> List[Tuple[float, float, int]]:
    """TEMPO du XML : (début s, BPM, numéro du temps) au 1er temps et à chaque changement de tempo (grille par
    passage ou rampe, comme PQTZ)."""
    out: List[Tuple[float, float, int]] = []
    last = None
    for n, tempo, ms in beats:
        if tempo != last:
            out.append((round(ms / 1000.0, 3), round(tempo / 100.0, 2), int(n)))
            last = tempo
    return out


def build_xml(session: LiveSession) -> bytes:
    """XML du live : une piste par son prêt, une playlist « DJSync Live – AAAA-MM-JJ »."""
    from pyrekordbox import RekordboxXml

    xml = RekordboxXml(name="DJSync", version="1", company="DJSync")
    ready = [t for t in session.tracks if t.ready]
    ids = []
    for t in ready:
        tr = xml.add_track(t.path)
        tr._element.set("Location", location(t.path))         # Location écrite par nous (Mac : un seul « / »)
        tr.set("Name", t.title or Path(t.path).stem)
        if t.artist:
            tr.set("Artist", t.artist)
        if t.album:
            tr.set("Album", t.album)
        if t.duration:
            tr.set("TotalTime", int(round(t.duration)))
        if t.bpm:
            tr.set("AverageBpm", round(float(t.bpm), 2))
        if t.key_name:
            tr.set("Tonality", t.key_name)
        tr.set("Kind", (Path(t.path).suffix.lstrip(".").upper() or "MP3") + " File")
        for start, bpm, n in tempo_points(t.beats):
            tr.add_tempo(Inizio=start, Bpm=bpm, Metro="4/4", Battito=n)
        for slot, ms, name in t.cues:
            tr.add_mark(Name=name or "", Type="cue", Start=round(ms / 1000.0, 3), Num=(slot - 1) if slot else -1)
        ids.append(tr.TrackID)
    pl = xml.add_playlist(session.playlist_name)
    for i in ids:
        pl.add_track(i)
    return xml.tostring().encode("utf-8")


def write_xml(session: Optional[LiveSession], data_dir: Path) -> Path:
    """Réécrit djsync-live.xml (remplacement atomique). Sans live (ou live rangé) : XML vide."""
    path = xml_path(data_dir)
    _atomic_write(path, build_xml(session if session is not None and not session.done else LiveSession(today())))
    return path


# ------------------------------------------------------------------------------- rapprochements
def same_track(a_title: str, a_artist: str, b_title: str, b_artist: str) -> bool:
    """Même titre et même artiste (normalisés), comme « déjà là »."""
    from .duplicates import normalize

    return bool(a_title) and normalize(a_title) == normalize(b_title) and normalize(a_artist) == normalize(b_artist)


def find_existing(tracks: Sequence[Any], url: str, title: str, artist: str) -> Optional[Any]:
    """Son déjà dans une bibliothèque : lien d'origine, sinon titre + artiste."""
    if url:
        for t in tracks:
            if getattr(t, "source_url", None) and norm_key(t.source_url) == norm_key(url):
                return t
    for t in tracks:
        if same_track(title, artist, getattr(t, "title", ""), getattr(t, "artist", "")):
            return t
    return None


def same_path(a: str, b: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (TypeError, ValueError):
        return False


def tidy_plan(session: LiveSession, collection: Sequence[Any]) -> List[Tuple[LiveTrack, Optional[Any]]]:
    """« Terminer le live » : pour chaque son prêt, le son déjà dans la collection au même chemin (importé par
    Rekordbox en le glissant sur un deck, ou déjà là avant le live), sinon None (à ajouter)."""
    by_path: Dict[str, Any] = {}
    for t in collection:
        p = getattr(t, "path", "") or ""
        if p:
            by_path[os.path.normcase(os.path.abspath(p))] = t
    out = []
    for t in session.tracks:
        if not t.ready:
            continue
        out.append((t, by_path.get(os.path.normcase(os.path.abspath(t.path)))))
    return out


def clock() -> str:
    return datetime.now().strftime("%H:%M")


def beats_of(analysis: Any) -> List[Tuple[int, int, int]]:
    """Grille d'une analyse (analysis.analyze_file) au format PQTZ (numéro, tempo x100, ms)."""
    grid = analysis.grid
    tempos = grid.beat_tempos()
    return [(int(n), int(round(b * 100)), int(round(t * 1000))) for (n, t), b in zip(grid.beats, tempos)]


__all__ = ["LiveTrack", "LiveSession", "build_xml", "write_xml", "save", "load", "current", "open_session",
           "location", "tempo_points", "find_existing", "tidy_plan", "xml_path", "beats_of"]
