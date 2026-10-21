"""Diagnostic de bibliothèque (V1.1.0) : sons de mauvaise qualité ou de mauvaise source.

* Qualité : débit lu dans l'en-tête du fichier (mutagen, sans décoder). Seuils :
  MP3 < 192 kbit/s, AAC < 112 kbit/s (l'AAC 128 de YouTube Music ≈ MP3 160-192), tout autre format
  avec perte < 128 kbit/s, fréquence d'échantillonnage < 44,1 kHz. Le sans-perte (FLAC, WAV, AIFF)
  n'est jamais signalé.
* Source : le titre trahit un son tiré d'une vidéo (« Clip officiel », « Official Video », « Lyrics »,
  « Visualizer »), d'un live ou d'une version modifiée (sped up, slowed, nightcore, 8D…). Ces versions
  ont souvent une intro parlée, des bruitages, un mixage différent ou un tempo modifié.

Les doublons viennent de core/duplicates.find_duplicate_groups ; la recherche d'une version propre
à retélécharger est faite par le contrôleur (YouTube Music, repli SoundCloud).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Tuple

from .duplicates import split_display

# Seuils (kbit/s) en dessous desquels un son est « de mauvaise qualité »
MIN_MP3 = 192
MIN_AAC = 112
MIN_OTHER = 128
MIN_SAMPLE_RATE = 44100
LOSSLESS = {"flac", "wav", "aiff", "alac"}

# Mentions qui trahissent une mauvaise source, où qu'elles soient dans le titre
_STRONG = [
    r"clip officiel", r"clip video", r"official (?:music )?video", r"music video", r"video officielle",
    r"video clip", r"video oficial", r"videoclip", r"official mv", r"lyrics? video", r"video lyrics?",
    r"visuali[sz]er", r"official visual", r"audio rip", r"sped ?up", r"speed ?up", r"slowed(?: \+ reverb)?",
    r"nightcore", r"8d audio", r"bass ?boosted", r"karaoke",
]
# Mentions ambiguës (« Live Forever », « Video Games ») : seulement entre () / [] ou après « | »
_BRACKETED = [r"lyrics?", r"paroles", r"letra", r"mv", r"live", r"en live", r"live at .*", r"live from .*", r"live session", r"concert", r"performance",
              r"video", r"hd", r"hq", r"4k", r"full song", r"audio only"]

_STRONG_RE = re.compile(r"\b(?:" + "|".join(_STRONG) + r")\b")
_SEGMENTS = re.compile(r"[\(\[]([^\)\]]*)[\)\]]|\|\s*(.+)$")
_BRACKETED_RE = re.compile(r"^(?:" + "|".join(_BRACKETED) + r")\b")


@dataclass
class AudioInfo:
    codec: str = ""                 # "mp3" | "aac" | "flac" | "wav" | "aiff" | "alac" | "opus"… ("" inconnu)
    bitrate: int = 0                # kbit/s (0 = inconnu)
    sample_rate: int = 0

    @property
    def lossless(self) -> bool:
        return self.codec in LOSSLESS

    @property
    def label(self) -> str:
        if not self.codec:
            return ""
        if self.lossless:
            return self.codec.upper()
        return f"{self.codec.upper()} {self.bitrate} kbps" if self.bitrate else self.codec.upper()


@dataclass
class QualityIssue:
    track: Any                      # LibraryTrack
    kind: str                       # "bitrate" | "source"
    reason: str                     # « MP3 160 kbps » ou la mention trouvée (« clip officiel »)
    info: AudioInfo = field(default_factory=AudioInfo)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def bad_source(title: str) -> Optional[str]:
    """Mention de mauvaise source dans un titre (« clip officiel »…), None si le titre est propre."""
    text = _plain(title)
    m = _STRONG_RE.search(text)
    if m:
        return m.group(0).strip()
    for seg in _SEGMENTS.finditer(text):
        part = (seg.group(1) or seg.group(2) or "").strip(" -")
        m = _BRACKETED_RE.match(part)
        if m:
            return m.group(0).strip()
    return None


def clean_title(title: str) -> str:
    """Titre sans les mentions de mauvaise source, pour chercher une version propre."""
    out = title or ""
    for seg in list(_SEGMENTS.finditer(_plain(out)))[::-1]:
        part = (seg.group(1) or seg.group(2) or "").strip(" -")
        if _STRONG_RE.search(part) or _BRACKETED_RE.match(part):
            out = out[:seg.start()] + out[seg.end():]
    out = re.sub(r"(?i)\b(?:clip officiel|official (?:music )?video|lyrics? video|visuali[sz]er)\b", "", out)
    return " ".join(out.replace("()", "").replace("[]", "").split()).strip(" -|")


def probe(path: Path) -> AudioInfo:
    """Format, débit et fréquence lus dans l'en-tête (rapide, sans décoder)."""
    try:
        import mutagen

        f = mutagen.File(str(path))
    except Exception:  # noqa: BLE001 - fichier illisible / manquant : rien à signaler ici
        return AudioInfo()
    if f is None or getattr(f, "info", None) is None:
        return AudioInfo()
    info = f.info
    name = type(f).__name__.lower()
    codec = ""
    if "mp3" in name:
        codec = "mp3"
    elif "mp4" in name:
        raw = str(getattr(info, "codec", "") or "").lower()
        codec = "alac" if raw.startswith("alac") else "aac"
    elif "flac" in name:
        codec = "flac"
    elif "wave" in name or "wav" in name:
        codec = "wav"
    elif "aiff" in name:
        codec = "aiff"
    elif "opus" in name:
        codec = "opus"
    elif "vorbis" in name or "ogg" in name:
        codec = "vorbis"
    bitrate = int(round((getattr(info, "bitrate", 0) or 0) / 1000))
    return AudioInfo(codec=codec, bitrate=bitrate, sample_rate=int(getattr(info, "sample_rate", 0) or 0))


def low_quality(info: AudioInfo) -> Optional[str]:
    """Raison (« MP3 160 kbps ») si le fichier est sous les seuils, sinon None."""
    if not info.codec or info.lossless:
        return None
    if info.sample_rate and info.sample_rate < MIN_SAMPLE_RATE:
        return f"{info.label} · {info.sample_rate / 1000:g} kHz"
    if not info.bitrate:
        return None
    minimum = MIN_MP3 if info.codec == "mp3" else MIN_AAC if info.codec == "aac" else MIN_OTHER
    return info.label if info.bitrate < minimum else None


def find_issues(tracks: Iterable[Any], path_of: Callable[[Any], Path],
                prober: Optional[Callable[[Path], AudioInfo]] = None,
                progress: Optional[Callable[[int, int], None]] = None) -> List[QualityIssue]:
    """Sons à remplacer : mauvaise source d'abord (titre), puis débit trop faible. Un son n'apparaît
    qu'une fois (la mauvaise source l'emporte : la retélécharger règle aussi la qualité)."""
    prober = prober or probe
    items = list(tracks)
    issues: List[QualityIssue] = []
    for i, track in enumerate(items):
        info = prober(path_of(track))
        reason = bad_source(track.title)
        if reason:
            issues.append(QualityIssue(track, "source", reason, info))
        else:
            bad = low_quality(info)
            if bad:
                issues.append(QualityIssue(track, "bitrate", bad, info))
        if progress and (i % 25 == 0 or i == len(items) - 1):
            progress(i + 1, len(items))
    return issues


def search_terms(track: Any) -> Tuple[str, str]:
    """(titre, artiste) propres pour chercher une version de remplacement."""
    title, artist = split_display(track.title, track.artist)
    return clean_title(title) or title, artist


def acceptable_alternative(candidate_title: str) -> bool:
    """Une proposition de remplacement ne doit pas être elle-même une mauvaise source."""
    return bad_source(candidate_title) is None
