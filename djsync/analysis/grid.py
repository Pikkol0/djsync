"""Édition d'une grille de temps (comme le mode « GRID » de Rekordbox) : fonctions pures.

Une grille = liste de (n° du temps dans la mesure 1-4, tempo x100, position ms), croissante.
  * `shift`      : décale toute la grille (corrige un décalage constant) ;
  * `set_downbeat` : le temps choisi devient le 1er temps de mesure (renumérotation) ;
  * `set_bpm`    : grille constante au BPM donné, ancrée sur un temps (grille fausse d'un BPM) ;
  * `extend`     : complète la grille jusqu'au début et à la fin du morceau.
"""
from __future__ import annotations

from bisect import bisect_left
from typing import List, Sequence, Tuple

Beat = Tuple[int, int, int]


def _interval(tempo_x100: int) -> float:
    return 60000.0 * 100 / max(1, tempo_x100)


def extend(beats: Sequence[Beat], duration_ms: int) -> List[Beat]:
    """Ajoute des temps avant le premier (jusqu'à 0) et après le dernier (jusqu'à la fin), au tempo
    des extrémités, en poursuivant la numérotation 1-4. Retire ce qui sort de [0, durée]."""
    out = [b for b in beats if 0 <= b[2] <= max(duration_ms, beats[-1][2] if beats else 0)]
    if not out:
        return []
    first_n, first_t, first_ms = out[0]
    step = _interval(first_t)
    pre: List[Beat] = []
    k = 1
    while first_ms - k * step >= 0:
        pre.append(((first_n - 1 - k) % 4 + 1, first_t, int(round(first_ms - k * step))))
        k += 1
    pre.reverse()
    last_n, last_t, last_ms = out[-1]
    step = _interval(last_t)
    post: List[Beat] = []
    k = 1
    while duration_ms and last_ms + k * step <= duration_ms:
        post.append(((last_n - 1 + k) % 4 + 1, last_t, int(round(last_ms + k * step))))
        k += 1
    return pre + out + post


def shift(beats: Sequence[Beat], delta_ms: int, duration_ms: int) -> List[Beat]:
    """Décale toute la grille de `delta_ms` (positif = plus tard)."""
    moved = [(n, t, ms + int(delta_ms)) for n, t, ms in beats]
    inside = [b for b in moved if b[2] >= 0]
    if not inside:
        return list(beats)
    return extend(inside, duration_ms)


def set_downbeat(beats: Sequence[Beat], index: int) -> List[Beat]:
    """Le temps `index` devient un 1er temps de mesure ; les autres suivent (cycle 1-4)."""
    if not 0 <= index < len(beats):
        return list(beats)
    return [((k - index) % 4 + 1, t, ms) for k, (_n, t, ms) in enumerate(beats)]


def set_bpm(beats: Sequence[Beat], bpm: float, anchor_index: int, duration_ms: int) -> List[Beat]:
    """Grille CONSTANTE à `bpm`, qui garde la position et le numéro du temps d'ancrage."""
    if not beats or bpm <= 0:
        return list(beats)
    anchor_index = max(0, min(anchor_index, len(beats) - 1))
    n, _t, ms = beats[anchor_index]
    tempo = int(round(bpm * 100))
    return extend([(n, tempo, ms)], duration_ms)


def bar_at(beats: Sequence[Beat], ms: float, duration_ms: int) -> Tuple[List[Beat], int]:
    """Un temps tombe exactement à `ms` et devient un 1er temps de mesure (toute la grille est décalée
    d'autant). Renvoie (grille, indice de ce temps)."""
    if not beats:
        return list(beats), -1
    i = nearest(beats, ms)
    moved = shift(beats, int(round(ms - beats[i][2])), duration_ms)
    j = nearest(moved, ms)
    return set_downbeat(moved, j), j


def scale_tempo(beats: Sequence[Beat], factor: float, anchor_index: int, duration_ms: int) -> List[Beat]:
    """BPM x `factor` (2 ou 0,5) : grille constante ancrée sur le temps `anchor_index`."""
    if not beats:
        return list(beats)
    tempos = sorted(b[1] for b in beats)
    return set_bpm(beats, tempos[len(tempos) // 2] / 100.0 * factor, anchor_index, duration_ms)


def nearest(beats: Sequence[Beat], ms: float) -> int:
    """Indice du temps le plus proche de `ms`."""
    if not beats:
        return -1
    pos = [b[2] for b in beats]
    i = bisect_left(pos, ms)
    if i == 0:
        return 0
    if i >= len(pos):
        return len(pos) - 1
    return i if pos[i] - ms < ms - pos[i - 1] else i - 1
