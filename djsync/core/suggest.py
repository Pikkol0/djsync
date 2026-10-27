"""Suggestions pour enchaîner (1.3.1, C30) : sons compatibles avec un son de référence.

Score sur 100 :
  * tonalité (60) : même clé 60, ±1 sur la roue ou relative 45, ±2 (option « énergie ») 20 ;
  * BPM (40) : 40 à BPM égal, 0 à la limite de tolérance (±6 % par défaut). Moitié et double
    acceptés (70 ↔ 140) : on compare au tempo le plus proche parmi ×½, ×1, ×2 ;
  * genre identique : petit bonus (+5).
Un son hors tolérance de BPM, ou de clé non compatible, n'est pas proposé. Sans tonalité connue
(son non analysé), seul le BPM compte, sur 40.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from .camelot import neighbors, to_camelot

DEFAULT_TOLERANCE = 6.0          # % de BPM
KEY_SAME, KEY_NEAR, KEY_FAR = 60, 45, 20
BPM_MAX = 40
GENRE_BONUS = 5


@dataclass
class Suggestion:
    track: Any
    score: float
    key_reason: str               # same | near | relative | far | none
    bpm_gap: Optional[float]      # % d'écart (signé) au tempo de référence ramené (×½ / ×2), None : inconnu
    ratio: float = 1.0            # 0.5 / 1 / 2 : tempo comparé à moitié ou au double


def _wheel(code: str) -> Tuple[int, str]:
    return int(code[:-1]), code[-1]


def key_relation(ref: Optional[str], other: Optional[str], energy: bool = False) -> str:
    """same | near (±1) | relative | far (±2, si `energy`) | none (incompatible ou inconnue)."""
    a, b = to_camelot(ref), to_camelot(other)
    if not a or not b:
        return "none"
    if a == b:
        return "same"
    na, la = _wheel(a)
    nb, lb = _wheel(b)
    if na == nb and la != lb:
        return "relative"
    if b in neighbors(a):
        return "near"
    if energy and la == lb and min((na - nb) % 12, (nb - na) % 12) == 2:
        return "far"
    return "none"


def bpm_gap(ref: float, other: float) -> Tuple[Optional[float], float]:
    """(écart en %, rapport) au tempo le plus proche parmi ×½, ×1, ×2 de `other`."""
    if not ref or not other:
        return None, 1.0
    best: Tuple[float, float] = (1e9, 1.0)
    for ratio in (1.0, 0.5, 2.0):
        gap = (other * ratio - ref) / ref * 100.0
        if abs(gap) < abs(best[0]):
            best = (gap, ratio)
    return round(best[0], 1), best[1]


def score(ref: Any, other: Any, tolerance: float = DEFAULT_TOLERANCE, energy: bool = False) -> Optional[Suggestion]:
    """Suggestion pour `other` par rapport à `ref` (LibraryTrack), None si incompatible."""
    if other.content_id == ref.content_id:
        return None
    gap, ratio = bpm_gap(ref.bpm, other.bpm)
    if gap is None or abs(gap) > tolerance:
        return None
    rel = key_relation(ref.camelot, other.camelot, energy)
    known = bool(to_camelot(ref.camelot))
    if known and rel == "none":
        return None
    points = {"same": KEY_SAME, "near": KEY_NEAR, "relative": KEY_NEAR, "far": KEY_FAR}.get(rel, 0)
    points += BPM_MAX * (1 - abs(gap) / tolerance) if tolerance else BPM_MAX
    if getattr(ref, "genre", "") and (getattr(other, "genre", "") or "").casefold() == ref.genre.casefold():
        points += GENRE_BONUS
    if ratio != 1.0:
        points -= 5                                   # moitié / double : un peu moins direct
    return Suggestion(other, round(points, 1), rel, gap, ratio)


def suggestions(ref: Any, tracks: Iterable[Any], limit: int = 20, tolerance: float = DEFAULT_TOLERANCE,
                energy: bool = False, exclude: Iterable[int] = ()) -> List[Suggestion]:
    """Meilleurs sons pour enchaîner après `ref`, du plus au moins compatible (un seul par fichier)."""
    skip = set(exclude)
    out: List[Suggestion] = []
    seen = set()
    for x in tracks:
        if x.content_id in skip or (x.path or x.content_id) in seen:
            continue
        s = score(ref, x, tolerance, energy)
        if s is not None:
            out.append(s)
            seen.add(x.path or x.content_id)
    out.sort(key=lambda s: (-s.score, abs(s.bpm_gap or 0), s.track.title.casefold()))
    return out[:limit]
