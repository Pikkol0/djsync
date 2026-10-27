"""« Améliorer ma bibliothèque » (1.4.0, C47) : pour chaque son de qualité insuffisante, chercher une
meilleure version dans les sources Haute qualité (Internet Archive, Audius, Soulseek s'il est activé)
et proposer le gain (« MP3 128 → FLAC »). Rien n'est remplacé sans validation.

La qualité d'un son est sa VRAIE qualité quand le spectre a été mesuré (C46), sinon son débit annoncé.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

LOSSLESS_RANK = 10_000


def rank_of(info: Any) -> int:
    """Rang de qualité d'un fichier de la bibliothèque (AudioInfo) : sans perte réel > débit."""
    if info is None or not getattr(info, "codec", ""):
        return 0
    if info.real_lossless:
        return LOSSLESS_RANK
    return int(info.effective_kbps or info.bitrate or 0)


def label_of(info: Any) -> str:
    if info is None or not getattr(info, "codec", ""):
        return "?"
    if info.real_lossless:
        return info.codec.upper()
    kbps = info.effective_kbps or info.bitrate
    real = " (≈)" if info.fake else ""
    return f"{info.codec.upper()} {kbps}{real}" if kbps else info.codec.upper()


def candidate_rank(track: Any) -> int:
    """Rang de qualité annoncé d'un résultat Haute qualité (TrackResult)."""
    r = getattr(track, "slsk", None)
    if r is not None:
        return LOSSLESS_RANK if r.lossless else int(r.bitrate or 0)
    q = (getattr(track, "quality", "") or "").upper()
    if q in ("FLAC", "WAV", "AIFF"):
        return LOSSLESS_RANK
    import re

    m = re.search(r"\b(\d{2,4})\b", q)                # « MP3 320 » -> 320 (le 3 de « MP3 » ne compte pas)
    return int(m.group(1)) if m else 0


def candidate_label(track: Any) -> str:
    r = getattr(track, "slsk", None)
    if r is not None:
        return r.quality_label()
    return getattr(track, "quality", "") or "?"


@dataclass
class Weak:
    track: Any                   # LibraryTrack
    info: Any                    # AudioInfo
    finds: List[Any] = field(default_factory=list)      # TrackResult, du meilleur au moins bon
    searched: bool = False

    @property
    def best(self) -> Optional[Any]:
        return self.finds[0] if self.finds else None

    @property
    def gain(self) -> str:
        b = self.best
        return f"{label_of(self.info)} → {candidate_label(b)}" if b is not None else ""


def weak_tracks(tracks: Sequence[Any], infos: dict, threshold: int = 256, lossless_only: bool = False) -> List[Weak]:
    """Sons sous le seuil (kbps réels) ; `lossless_only` : tout ce qui n'est pas un vrai sans perte."""
    out = []
    for x in tracks:
        info = infos.get(x.content_id)
        r = rank_of(info)
        if r == 0:
            continue
        if r < (LOSSLESS_RANK if lossless_only else threshold):
            out.append(Weak(x, info))
    out.sort(key=lambda w: rank_of(w.info))
    return out


def better_finds(weak: Weak, finds: Sequence[Any], max_gap: int = 10) -> List[Any]:
    """Résultats meilleurs que le son actuel, de même durée (± `max_gap` s), meilleurs d'abord."""
    current = rank_of(weak.info)
    dur = int(getattr(weak.track, "duration_seconds", 0) or 0)
    keep = []
    for f in finds:
        if candidate_rank(f) <= current:
            continue
        d = int(getattr(f, "duration_seconds", 0) or 0)
        if dur and d and abs(d - dur) > max_gap:
            continue
        keep.append(f)
    keep.sort(key=lambda f: (candidate_rank(f), getattr(f, "source", "") != "soulseek"), reverse=True)
    return keep


def sure(weak: Weak) -> bool:
    """Remplacement « sûr » (pour « Remplacer tout ce qui est sûr ») : sans perte, durée à ± 3 s."""
    b = weak.best
    if b is None or candidate_rank(b) < LOSSLESS_RANK:
        return False
    dur, d = int(weak.track.duration_seconds or 0), int(b.duration_seconds or 0)
    return bool(dur and d and abs(dur - d) <= 3)
