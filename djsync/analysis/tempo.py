"""BPM et grille de temps (beatgrid), en numpy pur.

Méthode (V1.1-A4.1, recalibrée sur 213 sons réels analysés par Rekordbox) :
  1. enveloppe d'attaques : flux spectral (log-magnitude, différence positive) à ~86 images/s,
     plus une enveloppe « basses » (< 150 Hz) pour repérer les temps forts ;
  2. CANDIDATS : pics de l'autocorrélation de l'enveloppe (renforcée par ses multiples), plus leurs
     rapports 3/2 et 2/3, ramenés dans une octave de référence [90, 180) ;
  3. chaque candidat est AFFINÉ (±2 %, puis 0,002 BPM) par alignement direct : force moyenne des
     attaques sous la grille, au meilleur calage. On compare ensuite les candidats affinés : une
     grille juste tombe sur les attaques du début à la fin, une grille aux 2/3 ou dérivant de 0,5
     BPM non. (Mesuré : la transformée de Fourier, utilisée avant, donnait parfois un pic plus haut
     au mauvais tempo : 129,5 au lieu de 128,99 ; et comparer des candidats NON affinés produisait
     des erreurs x1,375 comme 127 -> 174,6.) ;
  4. arrondi à l'entier si l'entier aligne (presque) aussi bien : 92,46 reste 92,46 ;
  5. OCTAVE : entre X (140-180) et X/2 (70-90), même règle que celle observée chez Rekordbox sur
     la bibliothèque de référence : il garde le plus souvent le tempo rapide sous 168 (31 sons sur
     44), et le lent au-dessus (8 sur 9). Aucune mesure du signal n'a mieux prédit son choix ;
  6. premier temps de la mesure : le décalage (0-3) qui concentre le plus d'énergie de basses.

Comme Rekordbox en mode « grille constante », on renvoie une grille à tempo unique.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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
    variable: bool = False                             # grille qui suit un tempo changeant (voir _warp)

    def beat_tempos(self) -> List[float]:
        """Tempo de chaque temps (BPM) : constant, ou mesuré d'un temps au suivant si la grille varie."""
        if not self.variable or len(self.beats) < 2:
            return [self.bpm] * len(self.beats)
        t = [b for _, b in self.beats]
        out = [60.0 / (t[i + 1] - t[i]) for i in range(len(t) - 1)]
        return out + out[-1:]

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


REF_LO, REF_HI = 90.0, 180.0         # octave de référence des candidats
OCTAVE_SLOW_FROM = 168.0             # au-delà, Rekordbox affiche presque toujours la moitié (84-90)


def _fold(bpm: float) -> float:
    while bpm < REF_LO:
        bpm *= 2
    while bpm >= REF_HI:
        bpm /= 2
    return bpm


def _candidates(env: np.ndarray, fps: float, n: int = 6) -> List[float]:
    """Tempos candidats (dans [90, 180)) : pics de l'autocorrélation + rapports 3/2 et 2/3."""
    ac = _autocorr(env)
    cands = np.arange(35.0, 360.0, 0.25)
    lag = 60.0 * fps / cands
    l = np.clip(lag[:, None] * np.array([1, 2, 3, 4])[None, :], 0, ac.size - 2)
    i = l.astype(int)
    f = l - i
    vals = ac[i] * (1 - f) + ac[i + 1] * f
    score = np.maximum(vals @ np.array([1.0, 0.5, 0.33, 0.25]), 0)
    peaks = [k for k in range(1, score.size - 1) if score[k] >= score[k - 1] and score[k] > score[k + 1]]
    peaks.sort(key=lambda k: -score[k])
    out: List[float] = []
    for k in peaks[:n]:
        for b in (cands[k], cands[k] * 1.5, cands[k] * 2 / 3):
            fb = _fold(float(b))
            if all(abs(fb - o) / o > 0.012 for o in out):
                out.append(fb)
    return out


def _refine_align(smooth: np.ndarray, fps: float, bpm0: float, span: float = 0.02) -> Tuple[float, float]:
    """Tempo exact près de bpm0 par alignement direct ; renvoie (bpm arrondi au centième, score)."""
    c1 = np.arange(bpm0 * (1 - span), bpm0 * (1 + span), 0.04)
    s1 = np.array([_alignment(smooth, fps * 60.0 / b, 0.5) for b in c1])
    b1 = float(c1[int(np.argmax(s1))])
    c2 = np.arange(b1 - 0.06, b1 + 0.0601, 0.01)
    s2 = np.array([_alignment(smooth, fps * 60.0 / b, 0.25) for b in c2])
    b2 = float(c2[int(np.argmax(s2))])
    c3 = np.arange(b2 - 0.012, b2 + 0.0121, 0.002)
    s3 = np.array([_alignment(smooth, fps * 60.0 / b, 0.1) for b in c3])
    j = int(np.argmax(s3))
    bpm, best = float(c3[j]), float(s3[j])
    integer = float(round(bpm))
    if integer != bpm and abs(integer - bpm) <= 0.06:
        si = _alignment(smooth, fps * 60.0 / integer, 0.1)
        if si >= 0.985 * best:
            bpm, best = integer, si
    return round(bpm, 2), best


OFFBEAT_FLIP = 1.3     # basses du contretemps / basses du temps au-delà duquel la grille est décalée


def _kick_phase(benv: np.ndarray, period: float, phase: float, debug: Optional[Dict] = None) -> float:
    """Temps ou contretemps ? Le calage sur toutes les attaques peut tomber sur le contretemps quand
    les charlestons ouverts y dominent (house). Le KICK tranche : si les attaques graves sont
    nettement plus fortes un demi-temps plus loin, la grille est décalée d'un demi-temps.
    Mesuré sur 10 sons réels comparés aux grilles Rekordbox : 1,78 pour le seul son décalé (Pump It
    Up), 1,03 au plus pour les 9 autres -> seuil 1,3."""
    smooth = np.convolve(benv, [0.25, 0.5, 0.25], mode="same")
    k = np.arange(0, max(1, int((smooth.size - 1 - phase) // period)))
    on = float(_sample(smooth, phase + k * period).mean())
    off = float(_sample(smooth, phase + period / 2 + k * period).mean())
    if debug is not None:
        debug["kick_offbeat_ratio"] = round(off / on, 3) if on > 0 else -1
    if on > 0 and off > OFFBEAT_FLIP * on:
        return (phase + period / 2) % period
    return phase


def _choose_octave(env: np.ndarray, benv: np.ndarray, fps: float, bpm: float, debug: Optional[Dict] = None) -> float:
    """`bpm` est dans [90, 180). S'il est >= 140, sa moitié (70-90) est aussi dans la plage :
    règle calée sur Rekordbox (213 sons de référence) : rapide sous 168 BPM, lent au-dessus."""
    slow = bpm / 2
    if slow < BPM_MIN:
        return bpm
    period = fps * 60.0 / slow
    _, b_on, b_half = _best_phase(benv, period)
    bass_ratio = b_half / b_on if b_on > 0 else 0.0
    if debug is not None:
        debug.update(oct_slow=round(slow, 2), oct_bass_ratio=round(bass_ratio, 3))
    # (Une exception « basses rapides » pour la drum'n'bass a été essayée : sur les 9 sons concernés
    # de la référence, elle ne séparait pas Rekordbox ; la mesure reste dans le diagnostic.)
    return bpm if bpm < OCTAVE_SLOW_FROM else slow


DRIFT_LIMIT = 0.030       # s : en deçà, la grille constante est gardée (imperceptible, comme Rekordbox)
# Gain d'alignement exigé pour passer en grille variable. Mesuré : tempo qui accélère (120 -> 126,
# 126 -> 121) : x4,2 à x4,4 ; 10 sons réels à tempo fixe : x0,83 à x1,23 (le suivi colle aux
# micro-décalages humains sans être plus juste). 1,5 laisse une marge nette des deux côtés.
VARIABLE_GAIN = 1.5


def _warp(env: np.ndarray, fps: float, bpm: float, phase0: float, debug: Optional[Dict] = None) -> Optional[np.ndarray]:
    """Grille VARIABLE, seulement si elle est nettement meilleure. On calcule la grille constante et
    une grille suivie (_track_beats) ; on garde la suivie si (1) elle s'écarte de la constante de plus
    de 30 ms de façon durable (médiane glissante sur 9 temps) ET (2) elle colle au moins 1,5 fois
    mieux aux attaques. Une grille constante juste n'est jamais remplacée : sur 10 sons réels testés,
    aucun n'a basculé ; sur des tempos qui accélèrent (120 -> 126), la grille suit à < 5 ms."""
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    period = fps * 60.0 / bpm
    n_beats = int((env.size - 1 - phase0) // period) + 1
    if n_beats < 40:
        return None
    base = phase0 + np.arange(n_beats) * period
    tracked = _track_beats(smooth, period)
    if tracked is None or tracked.size < 40:
        return None
    inside = tracked[(tracked >= 0) & (tracked <= env.size - 1)]
    score_c = float(_sample(smooth, base).mean())
    score_t = float(_sample(smooth, inside).mean())
    # écart de chaque temps suivi au temps constant le plus proche (repliement sur ±1/2 temps)
    dev = (inside - phase0) / period
    dev = (dev - np.round(dev)) * period
    dev = np.array([np.median(dev[max(0, i - 4): i + 5]) for i in range(dev.size)])
    drift = float(np.max(np.abs(dev))) / fps
    if debug is not None:
        debug.update(drift_ms=round(drift * 1000, 1), grid_gain=round(score_t / max(score_c, 1e-9), 3))
    if drift <= DRIFT_LIMIT or score_t < VARIABLE_GAIN * score_c:
        return None
    return tracked


def _track_beats(smooth: np.ndarray, period: float, tightness: float = 60.0) -> Optional[np.ndarray]:
    """Suivi de temps par programmation dynamique (Ellis, 2007) : chaque temps vient 0,8 à 1,25
    période après le précédent, pénalisé selon log(écart/période)² ; on maximise la force des
    attaques sous les temps. Le tempo peut donc évoluer (accélération, live). Les positions (images)
    sont ensuite lissées par régression locale sur 8 temps : pas d'à-coups sur la platine."""
    n = smooth.size
    lo, hi = int(np.floor(period * 0.8)), int(np.ceil(period * 1.25))
    if n < hi * 8:
        return None
    taus = np.arange(lo, hi + 1)
    penalty = -tightness * np.log(taus / period) ** 2
    norm = smooth / (smooth.std() or 1.0)
    score = norm.copy()
    back = np.full(n, -1, dtype=np.int64)
    for t in range(lo, n):
        prev = t - taus
        ok = prev >= 0
        cand = score[prev[ok]] + penalty[ok]
        j = int(np.argmax(cand))
        if cand[j] > 0:
            score[t] = norm[t] + cand[j]
            back[t] = prev[ok][j]
    # fin : meilleur score dans la dernière période
    t = int(n - hi + np.argmax(score[n - hi:]))
    beats = [t]
    while back[t] >= 0:
        t = int(back[t])
        beats.append(t)
    b = np.array(beats[::-1], dtype=np.float64)
    if b.size < 16:
        return None
    # lissage : chaque temps = valeur d'une droite ajustée sur ses 8 voisins (garde la dérive, ôte le grain)
    out = b.copy()
    idx = np.arange(b.size)
    for i in range(b.size):
        a, z = max(0, i - 4), min(b.size, i + 5)
        coef = np.polyfit(idx[a:z], b[a:z], 1)
        out[i] = coef[0] * i + coef[1]
    # temps manquants avant le premier détecté (intro) : on prolonge à la période locale
    step = out[1] - out[0]
    head = []
    first = out[0] - step
    while first >= 0:
        head.append(first)
        first -= step
    return np.concatenate([np.array(head[::-1]), out])


def _harmonic_change(x: np.ndarray, sr: int, times: np.ndarray) -> np.ndarray:
    """Changement harmonique à chaque temps : distance entre le spectre (log, 50 Hz - 2 kHz) moyen
    du temps et celui du temps précédent. Les accords changent surtout en début de mesure.
    Mesuré contre les grilles Rekordbox de 8 sons réels : 1er temps de mesure retrouvé 6 fois sur 8
    (contre 3 sur 8 avec les seules attaques de basses)."""
    n_fft, hop = 4096, 1024
    if x.size < n_fft or times.size < 2:
        return np.zeros(times.size)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    band = (freqs >= 50) & (freqs <= 2000)
    view = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    win = np.hanning(n_fft).astype(np.float32)
    spec = np.concatenate([np.log1p(np.abs(np.fft.rfft(view[i:i + 256] * win, axis=1))[:, band]).astype(np.float32)
                           for i in range(0, view.shape[0], 256)])
    idx = np.clip(((times - n_fft / 2 / sr) * sr / hop).round().astype(int), 0, spec.shape[0] - 1)
    seg = [spec[idx[j]:idx[j + 1]].mean(axis=0) if idx[j + 1] > idx[j] else spec[idx[j]]
           for j in range(idx.size - 1)] + [spec[idx[-1]]]
    out = np.zeros(times.size)
    for j in range(1, len(seg)):
        out[j] = float(np.linalg.norm(seg[j] - seg[j - 1]))
    return out


def analyze_tempo(x: np.ndarray, sr: int, debug: Optional[Dict] = None) -> BeatGrid:
    """`debug` (facultatif) reçoit les mesures intermédiaires : sert à calibrer sur une vraie bibliothèque."""
    duration = x.size / float(sr)
    if duration < 4.0 or float(np.max(np.abs(x), initial=0.0)) < 1e-3:
        return BeatGrid()
    env, benv, fps = onset_envelopes(x, sr)
    if env.size < fps * 3 or not np.any(env):
        return BeatGrid()
    bpm0, strength = _coarse_tempo(env, fps)
    if debug is not None:
        debug.update(coarse=bpm0, coarse_strength=round(strength, 3))
    if strength < 0.05:
        return BeatGrid()
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    refined = sorted({_refine_align(smooth, fps, c) for c in _candidates(env, fps)}, key=lambda r: -r[1])
    if not refined:
        return BeatGrid()
    rep, rep_score = refined[0]
    if debug is not None:
        debug["candidats"] = " ".join(f"{b:.2f}:{sc:.2f}" for b, sc in refined[:5])
    bpm = _choose_octave(env, benv, fps, rep, debug)
    coherence = abs(complex(_fourier(env, fps, np.array([bpm]))[0])) / (float(np.abs(env).sum()) or 1.0)
    if debug is not None:
        debug.update(before_refine=round(rep, 2), coherence=round(coherence, 4))
    period = fps * 60.0 / bpm                                   # images par temps
    # position du 1er temps (en images) par recherche directe ; la différence spectrale place une
    # attaque entre deux images (-0.5 image) et l'image est centrée sur sa fenêtre (+N_FFT/2)
    phase_frames, _, _ = _best_phase(env, period)
    phase_frames = _kick_phase(benv, period, phase_frames, debug)
    t_of = lambda f: ((f - 0.5) * HOP + N_FFT / 2) / sr + ONSET_LATENCY   # image -> secondes
    first = t_of(phase_frames)
    beat_len = 60.0 / bpm
    first %= beat_len
    times = np.arange(first, duration, beat_len)
    warped = _warp(env, fps, bpm, ((first - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5, debug)
    variable = warped is not None
    if variable:
        times = t_of(warped)
        times = times[(times >= 0) & (times < duration)]
        first = float(times[0])
        bpm = round(float(np.median(60.0 / np.diff(times))), 2)        # tempo affiché : tempo médian
    # temps fort : décalage (0..3) qui concentre le plus d'attaques de basses (+ un peu de global)
    frames = ((times - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5

    def sample(e: np.ndarray) -> np.ndarray:
        i = np.clip(np.round(frames).astype(int), 0, e.size - 1)
        lo, hi = np.clip(i - 1, 0, e.size - 1), np.clip(i + 1, 0, e.size - 1)
        return np.maximum.reduce([e[lo], e[i], e[hi]])

    nums = np.arange(times.size) % 4
    bass = sample(benv)
    harm = _harmonic_change(x, sr, times)

    def z(v: np.ndarray) -> np.ndarray:
        per = np.array([float(v[nums == j].mean()) if np.any(nums == j) else 0.0 for j in range(4)])
        return (per - per.mean()) / (per.std() + 1e-9)

    scores = list(z(harm) + 0.5 * z(bass)) if times.size >= 8 else [0.0, 0.0, 0.0, 0.0]
    if debug is not None:
        debug["downbeat_scores"] = " ".join(f"{v:.2f}" for v in scores)
    down = int(np.argmax(scores))
    beats = [(((k - down) % 4) + 1, float(t)) for k, t in enumerate(times)]
    return BeatGrid(bpm=bpm, first_beat=float(first), downbeat_offset=down,
                    confidence=float(min(1.0, coherence * 4)), beats=beats, variable=variable)
