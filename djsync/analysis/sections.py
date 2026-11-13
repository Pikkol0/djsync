"""« Proposer des cues » sur les vraies parties du son (1.4.1, C71).

Chaque mesure de la grille est résumée par son spectre (24 bandes log, 30 Hz - 11 kHz). Un changement de
partie (intro, couplet, refrain, drop, break, outro) est un écart net entre les 2 et 4 mesures qui précèdent
une mesure et celles qui la suivent : timbre (spectre centré-réduit) + énergie (moyenne et basses). Les
phrases de 4, 8 et 16 mesures depuis le premier temps de la grille sont favorisées.

Proposition : A sur le premier temps de la grille, puis les changements les plus nets, au moins 4 mesures
d'écart, jusqu'à 8 pads, sur les pads libres seulement ; jamais à moins d'un demi-temps d'un cue existant.
Aucun changement net (pic à moins de 2 × la médiane) : A seul.

Mesuré le 13/11 sur 16 sons de la clé de l'auteur, cues posés à la main (89 hot cues), à une mesure près :
ancien pas de 32 mesures : justesse 36 %, couverture 24 % ; cette méthode : 56 % et 72 % (validation
croisée en laissant un son de côté : 54 % et 67 %).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

BANDS = 24
WINDOWS = ((2, 0.5), (4, 1.0))         # (mesures de chaque côté, poids)
ENERGY_WEIGHT = 2.0
BASS_WEIGHT = 1.0
PHRASE_BONUS = {16: 1.4, 8: 1.2, 4: 1.2}
RELATIVE_FLOOR = 0.35                  # un changement retenu vaut au moins 35 % du plus net
MIN_GAP_BARS = 4
MAX_CUES = 8
CLEAR_RATIO = 2.0                      # pic / médiane en dessous : aucun changement net


def bar_times(beats: Sequence[Tuple[int, int, int]]) -> List[float]:
    """Débuts de mesure (s) : les temps numérotés 1 de la grille."""
    return [ms / 1000.0 for n, _t, ms in beats if n == 1]


def bar_features(x: np.ndarray, sr: int, bars: Sequence[float]) -> np.ndarray:
    """Spectre moyen de chaque mesure : (mesures × 24 bandes log)."""
    n_fft, hop = 2048, 1024
    if x.size < n_fft or len(bars) < 2:
        return np.zeros((len(bars), BANDS), np.float32)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    edges = np.geomspace(30, min(11000, sr / 2 - 1), BANDS + 1)
    groups = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(edges[:-1], edges[1:])]
    view = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    win = np.hanning(n_fft).astype(np.float32)
    rows = []
    for i in range(0, view.shape[0], 2048):
        power = np.abs(np.fft.rfft(view[i:i + 2048] * win, axis=1)) ** 2
        rows.append(np.stack([np.log1p(power[:, g].mean(1)) if g.any() else np.zeros(power.shape[0])
                              for g in groups], 1))
    spec = np.concatenate(rows).astype(np.float32)
    fps = sr / hop
    step = float(np.median(np.diff(bars)))
    ends = list(bars[1:]) + [bars[-1] + step]
    out = np.zeros((len(bars), BANDS), np.float32)
    for k, (a, b) in enumerate(zip(bars, ends)):
        i = int(a * fps)
        j = max(i + 1, int(b * fps))
        if i < spec.shape[0]:
            out[k] = spec[i:j].mean(0)
    return out


def change_scores(features: np.ndarray) -> np.ndarray:
    """Netteté du changement de partie au début de chaque mesure (phrases favorisées)."""
    n = features.shape[0]
    if n < 3:
        return np.zeros(n)
    z = (features - features.mean(0)) / (features.std(0) + 1e-6)
    energy = features.mean(1)
    bass = features[:, :6].mean(1)
    score = np.zeros(n)
    for w, weight in WINDOWS:
        for b in range(1, n):
            lo, hi = max(0, b - w), min(n, b + w)
            if hi - b < 1:
                continue
            timbre = float(np.linalg.norm(z[b:hi].mean(0) - z[lo:b].mean(0))) / np.sqrt(z.shape[1])
            level = abs(energy[b:hi].mean() - energy[lo:b].mean()) + BASS_WEIGHT * abs(bass[b:hi].mean() - bass[lo:b].mean())
            score[b] += weight * (timbre + ENERGY_WEIGHT * level)
    bonus = np.array([next((v for k, v in PHRASE_BONUS.items() if b % k == 0), 1.0) for b in range(n)])
    return score * bonus


def propose_bars(features: np.ndarray, limit: int = MAX_CUES) -> Tuple[List[int], bool]:
    """(numéros de mesure proposés, changement net trouvé). La mesure 0 (A) est toujours proposée."""
    n = features.shape[0]
    if n == 0:
        return [], False
    score = change_scores(features)
    inner = score[1:]
    if inner.size == 0 or not np.any(inner > 0):
        return [0], False
    if float(inner.max()) < CLEAR_RATIO * float(np.median(inner[inner > 0])):
        return [0], False
    picks = [0]
    top = float(score.max())
    for b in np.argsort(-score):
        if len(picks) >= limit or score[b] < RELATIVE_FLOOR * top:
            break
        if b == 0:
            continue
        if all(abs(int(b) - p) >= MIN_GAP_BARS for p in picks):
            picks.append(int(b))
    return sorted(picks), True


def propose_ms(x: np.ndarray, sr: int, beats: Sequence[Tuple[int, int, int]],
               limit: int = MAX_CUES) -> Tuple[List[int], bool]:
    """Positions proposées (ms, sur un premier temps de la grille) et changement net trouvé."""
    bars = bar_times(beats)
    if not bars:
        return [], False
    picked, clear = propose_bars(bar_features(x, sr, bars), limit)
    return [int(round(bars[b] * 1000)) for b in picked], clear


def propose_for_file(path: str, beats: Sequence[Tuple[int, int, int]], ffmpeg: Optional[str] = None,
                     limit: int = MAX_CUES) -> Tuple[List[int], bool]:
    from .decode import ANALYSIS_SR, decode

    audio = decode(path, ffmpeg, ANALYSIS_SR)
    return propose_ms(audio.samples, audio.sr, beats, limit)
