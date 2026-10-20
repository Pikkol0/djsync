"""BPM et grille de temps (beatgrid), en numpy pur.

Méthode (classique, robuste sur les musiques à tempo constant : rap, house, techno, pop…) :
  1. enveloppe d'attaques : flux spectral (log-magnitude, différence positive) à ~86 images/s,
     plus une enveloppe « basses » (< 150 Hz) pour repérer les temps forts ;
  2. tempo grossier : autocorrélation de l'enveloppe, renforcée par ses multiples (2, 3, 4 temps),
     pondérée par un a priori doux (log-normal centré sur 115 BPM) ;
  3. tempo FIN et phase : transformée de Fourier de l'enveloppe à la période exacte du tempo,
     sur TOUT le morceau. L'amplitude n'est forte que si la grille reste en phase du début à la
     fin, ce qui donne une précision de l'ordre du centième de BPM ; l'argument donne la position
     des temps à une fraction d'image près ;
  4. arrondi à l'entier si l'entier est (presque) aussi cohérent : la plupart des productions sont
     à tempo entier, c'est ce que fait aussi Rekordbox ;
  5. premier temps de la mesure : le décalage (0-3) qui concentre le plus d'énergie de basses.

Comme Rekordbox en mode « grille constante », on renvoie une grille à tempo unique.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

N_FFT = 1024
HOP = 256
BPM_MIN, BPM_MAX = 70.0, 180.0      # plage de sortie (comme les réglages par défaut des logiciels DJ)
# Avance systématique du flux spectral sur l'attaque réelle (fenêtre de Hann + compression log :
# le pic de différence arrive ~1,3 image AVANT l'attaque). Mesurée sur des attaques synthétiques
# franches (kick/snare) à 124, 128 et 140 BPM : 14 à 16 ms ; on compense 15 ms.
ONSET_LATENCY = 0.015


@dataclass
class BeatGrid:
    bpm: float = 0.0                                   # 0 = pas de tempo détecté
    first_beat: float = 0.0                            # secondes
    downbeat_offset: int = 0                           # numéro (0..3) du 1er temps de la grille dans la mesure
    confidence: float = 0.0                            # 0..1
    beats: List[Tuple[int, float]] = field(default_factory=list)   # (1..4, secondes)

    @property
    def bpmx100(self) -> int:
        return int(round(self.bpm * 100))


def _frames(x: np.ndarray, n_fft: int, hop: int):
    """Spectres de magnitude par blocs (mémoire bornée même pour un mix d'une heure)."""
    if x.size < n_fft:
        x = np.pad(x, (0, n_fft - x.size))
    view = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]     # aucune copie
    win = np.hanning(n_fft).astype(np.float32)
    for start in range(0, view.shape[0], 512):
        yield np.abs(np.fft.rfft(view[start:start + 512] * win, axis=1)).astype(np.float32)


def onset_envelopes(x: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray, float]:
    """(enveloppe globale, enveloppe des basses, images par seconde)."""
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    band = (freqs >= 30) & (freqs <= 8000)
    bass = (freqs >= 30) & (freqs <= 150)
    prev = None
    full, low = [], []
    for mag in _frames(x, N_FFT, HOP):
        lm = np.log1p(100.0 * mag)
        if prev is None:
            prev = lm[:1]
        d = np.diff(np.concatenate([prev, lm], axis=0), axis=0)
        d = np.maximum(d, 0.0)
        full.append(d[:, band].sum(axis=1))
        low.append(d[:, bass].sum(axis=1))
        prev = lm[-1:]
    fps = sr / HOP
    env, benv = np.concatenate(full), np.concatenate(low)

    def clean(e: np.ndarray) -> np.ndarray:
        w = max(1, int(fps * 0.4))
        local = np.convolve(e, np.ones(w) / w, mode="same")
        e = np.maximum(e - local, 0.0)
        s = e.std()
        return (e / s).astype(np.float64) if s > 0 else e.astype(np.float64)

    return clean(env), clean(benv), fps


def _autocorr(env: np.ndarray) -> np.ndarray:
    n = env.size
    f = np.fft.rfft(env - env.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    return ac / ac[0] if ac[0] > 0 else ac


def _coarse_tempo(env: np.ndarray, fps: float) -> Tuple[float, float]:
    ac = _autocorr(env)
    cands = np.arange(BPM_MIN / 2, BPM_MAX * 2 + 0.01, 0.25)
    lag = 60.0 * fps / cands

    def at(l: np.ndarray) -> np.ndarray:
        l = np.clip(l, 0, ac.size - 2)
        i = l.astype(int)
        f = l - i
        return ac[i] * (1 - f) + ac[i + 1] * f

    score = at(lag) + 0.5 * at(2 * lag) + 0.33 * at(3 * lag) + 0.25 * at(4 * lag)
    score = np.maximum(score, 0)
    prior = np.exp(-0.5 * (np.log2(cands / 115.0) / 0.9) ** 2)
    weighted = score * prior
    inside = (cands >= BPM_MIN) & (cands < BPM_MAX)
    best = cands[inside][np.argmax(weighted[inside])]
    return float(best), float(score[inside].max() if inside.any() else 0.0)


def _fourier(env: np.ndarray, fps: float, bpms: np.ndarray) -> np.ndarray:
    """Coefficient de Fourier de l'enveloppe à chaque tempo candidat (complexe)."""
    n = np.arange(env.size, dtype=np.float64)
    out = np.empty(bpms.size, dtype=np.complex128)
    step = max(1, 400_000 // max(env.size, 1))           # blocs de ~6 Mo : mémoire basse sur un long mix
    for s in range(0, bpms.size, step):
        f = bpms[s:s + step, None] / 60.0 / fps          # cycles par image
        out[s:s + step] = (np.exp(-2j * np.pi * f * n[None, :]) * env[None, :]).sum(axis=1)
    return out


def _refine(env: np.ndarray, fps: float, bpm0: float) -> Tuple[float, float]:
    """Tempo exact autour de bpm0 ; renvoie (bpm, cohérence 0..1).

    1. Fourier (±3 %) : le pic n'est net que si la grille tient tout le morceau -> ±0,05 BPM ;
    2. alignement direct (±0,15 BPM par pas de 0,005) : force moyenne des attaques sous la grille,
       au meilleur calage. Une grille fausse de 0,07 BPM dérive de ~55 ms en une minute : le score
       chute nettement, d'où une précision de l'ordre de 0,01 BPM même sur un extrait court ;
    3. arrondi à l'entier s'il aligne (presque) aussi bien : productions à tempo entier, comme
       l'affiche Rekordbox ; un vrai 92,46 reste 92,46."""
    norm = float(np.abs(env).sum()) or 1.0
    coarse = np.arange(bpm0 * 0.97, bpm0 * 1.03, 0.02)
    c = _fourier(env, fps, coarse)
    b1 = coarse[int(np.argmax(np.abs(c)))]
    fine = np.arange(b1 - 0.03, b1 + 0.0301, 0.002)
    cf = _fourier(env, fps, fine)
    k = int(np.argmax(np.abs(cf)))
    bpm_f, coherence = float(fine[k]), abs(complex(cf[k])) / norm

    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    cands = np.arange(bpm_f - 0.15, bpm_f + 0.1501, 0.005)
    scores = np.array([_alignment(smooth, fps * 60.0 / b) for b in cands])
    j = int(np.argmax(scores))
    bpm = float(cands[j])
    if 0 < j < cands.size - 1:                       # sommet parabolique entre deux pas
        a, b, cc = scores[j - 1], scores[j], scores[j + 1]
        den = a - 2 * b + cc
        if den < 0:
            bpm += 0.005 * 0.5 * (a - cc) / den
    integer = float(round(bpm))
    if integer != bpm and abs(integer - bpm) <= 0.05:
        if _alignment(smooth, fps * 60.0 / integer) >= 0.99 * float(scores[j]):
            bpm = integer
    return round(bpm, 2), coherence


def _sample(env: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """Valeurs de l'enveloppe (interpolation linéaire) aux positions fractionnaires `pos`."""
    pos = np.clip(pos, 0, env.size - 1.000001)
    i = pos.astype(int)
    f = pos - i
    return env[i] * (1 - f) + env[i + 1] * f


def _best_phase(env: np.ndarray, period: float, step: float = 0.1) -> Tuple[float, float, float]:
    """Recherche directe de l'alignement de la grille : (phase en images, force aux temps, force aux
    demi-temps). Plus fiable que l'argument de Fourier, qui vise le « centre de gravité » des
    attaques (décalé quand une note tenue suit le coup) au lieu de leur début."""
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    k = np.arange(0, max(1, int((env.size - 1) // period)))
    phases = np.arange(0, period, step)
    pos = phases[:, None] + k[None, :] * period
    strength = _sample(smooth, pos).mean(axis=1)
    j = int(np.argmax(strength))
    half = float(_sample(smooth, pos[j] + period / 2).mean())
    return float(phases[j]), float(strength[j]), half


def _alignment(smooth: np.ndarray, period: float, step: float = 0.25) -> float:
    """Force moyenne de l'enveloppe (lissée) sous une grille de période `period`, au meilleur calage."""
    k = np.arange(0, max(1, int((smooth.size - 1) // period)))
    phases = np.arange(0, period, step)
    return float(_sample(smooth, phases[:, None] + k[None, :] * period).mean(axis=1).max())


def _resolve_ternary(env: np.ndarray, fps: float, bpm: float) -> float:
    """Garde-fou contre la confusion 2/3 – 3/2 (ex. 116 au lieu de 174) : la grille juste place ses
    temps sur les attaques ; une grille à 2/3 ou 3/2 tombe une fois sur deux ou trois entre elles."""
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    best, best_score = bpm, _alignment(smooth, fps * 60.0 / bpm)
    for ratio in (1.5, 2.0 / 3.0):
        alt = bpm * ratio
        if BPM_MIN <= alt < BPM_MAX:
            score = _alignment(smooth, fps * 60.0 / alt)
            if score > 1.15 * best_score:
                best, best_score = alt, score
    return best


def _choose_octave(env: np.ndarray, benv: np.ndarray, fps: float, bpm: float) -> float:
    """Entre un tempo et son double (tous deux dans la plage, ex. 75/150, 87/174), on garde le LENT
    si ses demi-temps sont nettement moins accentués que ses temps (kick/caisse claire sur les temps,
    charleston entre les deux : rap à 75), le RAPIDE si les demi-temps sont presque aussi forts (le
    « lent » ne serait qu'un temps sur deux : drum'n'bass à 174, techno à 140)."""
    slow, fast = (bpm / 2, bpm) if bpm / 2 >= BPM_MIN else (bpm, bpm * 2)
    if fast >= BPM_MAX or slow < BPM_MIN:
        return bpm
    period = fps * 60.0 / slow
    _, on, half = _best_phase(env, period)
    _, b_on, b_half = _best_phase(benv, period)
    full_ratio = half / on if on > 0 else 1.0
    # Les basses (kick) tranchent le mieux : sur des tests calibrés, ~0,06 pour un vrai tempo lent
    # (kick sur les temps seulement) contre ~0,8 pour un vrai tempo rapide ; le global (charleston
    # en croches partout) ne sépare qu'à peine (0,7 contre 0,8).
    ratio = 0.7 * (b_half / b_on) + 0.3 * full_ratio if b_on > 0.05 else full_ratio
    return fast if ratio >= 0.55 else slow


def analyze_tempo(x: np.ndarray, sr: int) -> BeatGrid:
    duration = x.size / float(sr)
    if duration < 4.0 or float(np.max(np.abs(x), initial=0.0)) < 1e-3:
        return BeatGrid()
    env, benv, fps = onset_envelopes(x, sr)
    if env.size < fps * 3 or not np.any(env):
        return BeatGrid()
    bpm0, strength = _coarse_tempo(env, fps)
    if strength < 0.05:
        return BeatGrid()
    bpm0 = _resolve_ternary(env, fps, bpm0)
    bpm0 = _choose_octave(env, benv, fps, bpm0)
    bpm, coherence = _refine(env, fps, bpm0)
    period = fps * 60.0 / bpm                                   # images par temps
    # position du 1er temps (en images) par recherche directe ; la différence spectrale place une
    # attaque entre deux images (-0.5 image) et l'image est centrée sur sa fenêtre (+N_FFT/2)
    phase_frames, _, _ = _best_phase(env, period)
    t_of = lambda f: ((f - 0.5) * HOP + N_FFT / 2) / sr + ONSET_LATENCY   # image -> secondes
    first = t_of(phase_frames)
    beat_len = 60.0 / bpm
    first %= beat_len
    # temps fort : décalage (0..3) qui concentre le plus d'attaques de basses (+ un peu de global)
    times = np.arange(first, duration, beat_len)
    frames = ((times - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5

    def sample(e: np.ndarray) -> np.ndarray:
        i = np.clip(np.round(frames).astype(int), 0, e.size - 1)
        lo, hi = np.clip(i - 1, 0, e.size - 1), np.clip(i + 1, 0, e.size - 1)
        return np.maximum.reduce([e[lo], e[i], e[hi]])

    strength_at = sample(benv) + 0.25 * sample(env)
    scores = [float(strength_at[j::4].mean()) if strength_at[j::4].size else 0.0 for j in range(4)]
    down = int(np.argmax(scores))
    beats = [(((k - down) % 4) + 1, float(t)) for k, t in enumerate(times)]
    return BeatGrid(bpm=bpm, first_beat=float(first), downbeat_offset=down,
                    confidence=float(min(1.0, coherence * 4)), beats=beats)
