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
     1.4.4 (B125) : les entrées des basses (fin d'intro, drop) l'emportent ; en désaccord, le son est marqué
     « 1er temps à vérifier » (choix dans Grille et cues).

Comme Rekordbox en mode « grille constante », on renvoie une grille à tempo unique.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .decode import peak_level

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
    profile: Optional[object] = None                   # 1.4.3 (C69) : tempo_profile.TempoProfile
    # 1.4.3 (C16) : grille par passage (beatswitch) : (début s, BPM, 1er temps fort s) par passage
    sections: List[Tuple[float, float, float]] = field(default_factory=list)

    def beat_tempos(self) -> List[float]:
        """Tempo de chaque temps (BPM) : constant, celui de son passage (C16), ou mesuré d'un temps au suivant
        si la grille varie."""
        if len(self.sections) > 1 and self.beats:
            from .tempo_profile import section_at

            secs = sorted(self.sections, key=lambda s: s[0])
            return [secs[section_at(secs, t)][1] for _, t in self.beats]
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


# 1.4.1 (B11) : énergie des basses (60-150 Hz) dans les 100 ms qui suivent chaque temps, comparée à celle
# qui suit chaque contretemps. Le test par les ATTAQUES (_kick_phase) se trompe sur le hardstyle, la
# hypertechno, la house à basse décalée : la basse « off » y attaque plus net que le kick, long et saturé.
# Mesuré sur 83 sons de l'échantillon (grilles Rekordbox) : grille juste 2,30 au plus ; grille sur le
# contretemps jusqu'à 34 (8 sur 19 au-dessus de 3) -> seuil 3, aucun son juste qui bascule.
BASS_ENERGY_FLIP = 3.0


def _band_energy(x: np.ndarray, sr: int, lo: float, hi: float) -> Tuple[np.ndarray, float]:
    """(énergie de la bande lo-hi Hz par trame de 256 échantillons, trames par seconde)."""
    n, hop = 512, 256
    view = np.lib.stride_tricks.sliding_window_view(x, n)[::hop]
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    sel = (freqs >= lo) & (freqs <= hi)
    win = np.hanning(n).astype(np.float32)
    energy = np.concatenate([(np.abs(np.fft.rfft(view[i:i + 4096] * win, axis=1))[:, sel] ** 2).sum(axis=1)
                             for i in range(0, view.shape[0], 4096)])
    return energy, sr / hop


def _bass_energy_flip(x: np.ndarray, sr: int, times: np.ndarray, beat: float,
                      debug: Optional[Dict] = None) -> bool:
    """True si l'énergie des basses est nettement plus forte un demi-temps après chaque temps."""
    if x.size < 512 * 8 or times.size < 16:
        return False
    energy, fps = _band_energy(x, sr, 60, 150)
    k = max(1, int(0.1 * fps))
    starts = (times[4:-4] * fps).astype(int)

    def at(pos: np.ndarray) -> float:
        vals = [float(energy[a:a + k].mean()) for a in pos if 0 <= a and a + k < energy.size]
        return float(np.median(vals)) if vals else 0.0

    on = at(starts)
    off = at(((times[4:-4] + beat / 2) * fps).astype(int))
    ratio = off / on if on > 0 else (float("inf") if off > 0 else 0.0)
    if debug is not None:
        debug["bass_energy_offbeat_ratio"] = round(ratio, 3)
    return ratio > BASS_ENERGY_FLIP


# 1.4.1 (B11, 2e passe) : deux indices de plus, combinés (calés sur 74 grilles de l'échantillon dont 12 sur
# le contretemps ; vérifiés ensuite sur la mesure de la tour) : montée de l'énergie 60-150 Hz sur 60 ms et
# énergie 150-400 Hz sur 30 ms, contretemps moins temps, chacun divisé par son écart-type sur les grilles
# justes. Score > 1,15 -> grille décalée d'un demi-temps (grilles justes : 0,96 au plus).
OFFBEAT_SCORE_FLIP = 1.15
_SD_LOW_RISE, _SD_LOWMID = 1.64, 0.817


def _offbeat_score(x: np.ndarray, sr: int, times: np.ndarray, beat: float,
                   debug: Optional[Dict] = None) -> float:
    if x.size < 512 * 8 or times.size < 24:
        return 0.0
    tt = times[8:-8]

    def stat(lo: float, hi: float, win: float, rise: bool) -> float:
        energy, fps = _band_energy(x, sr, lo, hi)
        le = np.log(energy + 1e-9)
        k = max(1, int(win * fps))

        def at(ts: np.ndarray) -> float:
            vals = []
            for a in (ts * fps).astype(int):
                if a >= k and a + k < le.size:
                    v = float(le[a:a + k].mean())
                    vals.append(v - float(le[a - k:a].mean()) if rise else v)
            return float(np.median(vals)) if vals else 0.0

        return at(tt + beat / 2) - at(tt)

    score = stat(60, 150, 0.06, True) / _SD_LOW_RISE + stat(150, 400, 0.03, False) / _SD_LOWMID
    if debug is not None:
        debug["offbeat_score"] = round(score, 3)
    return score


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


def _frame_of(t: np.ndarray, sr: int) -> np.ndarray:
    """Secondes -> image de l'enveloppe (inverse de t_of dans analyze_tempo)."""
    return ((np.asarray(t, dtype=np.float64) - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5


def _time_of(f: float, sr: int) -> float:
    return ((f - 0.5) * HOP + N_FFT / 2) / sr + ONSET_LATENCY


def _downbeat(x: np.ndarray, sr: int, benv: np.ndarray, times: np.ndarray,
              debug: Optional[Dict] = None) -> int:
    """Décalage (0..3) du 1er temps de mesure : celui qui concentre changements harmoniques, attaques et énergie
    des basses (B12), sauf si des entrées des basses disent autre chose (B125). Moins de 8 temps : 0."""
    return _downbeat_vote(x, sr, benv, times, debug)[0]


# 1.4.4 (B125) : entrées des basses (fin d'intro, drop après un break) : indice prépondérant du 1er temps.
# Seuils posés sur des sons synthétiques, à caler avec la mesure de la tour (python -m djsync.analysis).
ENTRY_RISE = float(np.log(4.0))      # 2 mesures après / 2 mesures avant (médianes, énergie 40-120 Hz) : x4 (6 dB)
ENTRY_JUMP = float(np.log(2.0))      # saut d'un temps au suivant qui marque l'attaque de l'entrée
ENTRY_STEADY = float(np.log(2.5))    # temps plus fort que le régime établi : roulement, pas l'entrée
ENTRY_AGREE = 0.75                   # part des votes de la position gagnante en dessous de laquelle les entrées se contredisent
AVG_MARGIN = 1.0                     # avance du score moyen (B12) au-delà de laquelle il contredit les entrées
PHRASE_BEATS = 64                    # 16 mesures : entrées espacées d'un multiple de 16 mesures (phrases) renforcées


def _beat_means(cs: np.ndarray, n: int, efps: float, t0: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Énergie moyenne entre t0 et t1 (secondes), par sommes cumulées (aucun calcul de plus sur l'audio)."""
    a = np.clip((t0 * efps).astype(int), 0, n - 1)
    b = np.clip((t1 * efps).astype(int), a + 1, n)
    return (cs[b] - cs[a]) / (b - a)


def _entries(energy: np.ndarray, efps: float, times: np.ndarray, benv: np.ndarray,
             frames: np.ndarray) -> List[Tuple[int, float]]:
    """1.4.4 (B125) : entrées des basses : (indice du temps, force). Montée franche et durable de l'énergie
    40-120 Hz (déjà calculée pour B12) : les 2 mesures après nettement au-dessus des 2 mesures avant, chacune.
    Écartés : ce qui ne tient pas 2 mesures (kicks isolés avant le départ), l'entrée sur un demi-temps (pas de vote),
    le roulement de kicks collé au départ (temps hors du régime établi, ou trop d'attaques) ; kick étiré : seule son
    attaque est vue (l'énergie reste haute ensuite, pas de nouveau saut)."""
    n = times.size
    if n < 24 or energy.size < 16:
        return []
    beat = float(np.median(np.diff(times)))
    cs = np.concatenate([[0.0], np.cumsum(energy, dtype=np.float64)])
    m = lambda a, b: _beat_means(cs, energy.size, efps, a, b)          # noqa: E731
    lin = m(times, times + beat)
    floor = max(1e-12, 1e-4 * float(np.percentile(lin, 95)))           # silence : 40 dB sous le plus fort
    lg = lambda v: np.log(np.maximum(v, floor))                         # noqa: E731
    e, h1, h2 = lg(lin), lg(m(times, times + beat / 2)), lg(m(times + beat / 2, times + beat))
    fr = np.clip(np.round(frames).astype(int), 0, max(0, benv.size - 1))

    def attacks(j: int) -> int:
        a, b = fr[j], fr[j + 1] if j + 1 < n else fr[j] + int(round(beat * efps))
        seg = benv[a:max(a + 1, b)]
        if seg.size < 3:
            return 0
        peak = (seg[1:-1] > 2.0) & (seg[1:-1] >= seg[:-2]) & (seg[1:-1] > seg[2:])
        return int(peak.sum())

    out: List[Tuple[int, float]] = []
    for j in range(8, n - 8):
        if e[j] - e[j - 1] < ENTRY_JUMP:
            continue
        before = float(np.median(e[j - 8:j]))
        rise = min(float(np.median(e[j:j + 4])), float(np.median(e[j + 4:j + 8]))) - before
        if rise < ENTRY_RISE:
            continue                                         # ne tient pas 2 mesures
        if h2[j] - h1[j] > ENTRY_RISE:
            continue                                         # entrée sur un demi-temps : pas de vote
        c, steady = j, float(np.median(e[j + 4:min(n, j + 12)]))
        att = int(np.median([attacks(k) for k in range(j + 4, min(n - 1, j + 12))] or [1]))
        while c < min(j + 4, n - 8) and (e[c] - steady > ENTRY_STEADY or attacks(c) >= att + 2):
            c += 1                                           # roulement de kicks collé au départ
        if out and c - out[-1][0] < 8:
            continue                                         # même entrée (la basse après le kick) : la 1re attaque compte
        out.append((c, rise))
    return out


def _downbeat_vote(x: np.ndarray, sr: int, benv: np.ndarray, times: np.ndarray,
                   debug: Optional[Dict] = None) -> Tuple[int, bool, float]:
    """(décalage 0..3 du 1er temps, « 1er temps à vérifier », instant de l'entrée la plus nette en s ou -1)."""
    if times.size < 8:
        return 0, False, -1.0
    frames = _frame_of(times, sr)

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

    # 1.4.1 (B12) : + énergie des basses (40-120 Hz) dans les 80 ms après le temps : le kick et la basse
    # appuient le 1er temps. Mesuré sur 62 grilles justes de l'échantillon : 1er temps de Rekordbox
    # retrouvé 41 fois -> 47 (validation croisée par moitiés : 65 % -> 70 %).
    low = np.zeros(times.size)
    entries: List[Tuple[int, float]] = []
    if x.size >= 512 * 8:
        energy, efps = _band_energy(x, sr, 40, 120)
        k = max(1, int(0.08 * efps))
        starts = (times * efps).astype(int)
        low = np.array([np.log(float(energy[a:a + k].mean()) + 1e-9) if 0 <= a and a + k < energy.size else 0.0
                        for a in starts])
        entries = _entries(energy, efps, times, benv, frames)       # 1.4.4 (B125) : mêmes énergies, rien de décodé
    scores = list(z(harm) + 0.5 * z(bass) + z(low))
    avg = int(np.argmax(scores))
    down, check, ref = avg, False, -1.0
    if entries:
        # 1.4.4 (B125) : vote des entrées ; phrases de 16 / 32 mesures : entrées espacées d'un multiple de 16 mesures
        # renforcées (indice secondaire)
        votes = np.zeros(4)
        for i, (j, w) in enumerate(entries):
            partners = sum(1 for q, (jj, _w) in enumerate(entries) if q != i and abs(jj - j) % PHRASE_BEATS == 0)
            votes[j % 4] += w * (1.0 + 0.5 * min(2, partners))
        down = int(np.argmax(votes))
        split = votes[down] < ENTRY_AGREE * votes.sum()
        if split:                                   # entrées contradictoires : la moyenne départage (son à vérifier)
            down = max((q for q in range(4) if votes[q] >= 0.5 * votes[down]), key=lambda q: scores[q])
        against = down != avg and scores[avg] - scores[down] > AVG_MARGIN
        check = bool(split or against)
        ref = float(times[max(entries, key=lambda e: e[1])[0]])
        if debug is not None:
            debug["downbeat_entries"] = " ".join(f"{times[j]:.1f}s:{j % 4}:{w:.2f}" for j, w in entries)
            debug["downbeat_check"] = int(check)
    if debug is not None:
        debug["downbeat_scores"] = " ".join(f"{v:.2f}" for v in scores)
    return down, check, ref


SPLIT_MIN_S = 16.0        # un passage plus court n'a pas sa propre grille (fusionné avec son voisin)
SPLIT_SEARCH_S = 6.0      # recherche du raccord : de part et d'autre de l'écart entre deux paliers


def _passage_phase(x: np.ndarray, sr: int, env: np.ndarray, benv: np.ndarray, fps: float, bpm: float,
                   a: int, b: int) -> float:
    """1er temps (secondes, absolu) d'une grille à `bpm` calée sur les images a..b, avec les mêmes contrôles
    temps / contretemps que la grille du son (B11)."""
    period = fps * 60.0 / bpm
    ph, _, _ = _best_phase(env[a:b], period)
    ph = _kick_phase(benv[a:b], period, ph)
    beat = 60.0 / bpm
    t0 = _time_of(a + ph, sr)
    lo_t, hi_t = _time_of(a, sr), _time_of(b, sr)
    times = np.arange(t0, hi_t, beat)
    seg = x[max(0, int(lo_t * sr)): int(hi_t * sr)]
    rel = times - max(0.0, lo_t)
    if _bass_energy_flip(seg, sr, rel, beat) or _offbeat_score(seg, sr, rel, beat) > OFFBEAT_SCORE_FLIP:
        t0 += beat / 2
    return float(t0)


def _passage_tempo(env: np.ndarray, benv: np.ndarray, smooth: np.ndarray, fps: float, hint: float) -> float:
    """Tempo d'un passage, choisi comme celui d'un son entier (candidats, alignement, règle d'octave) : le
    tempo local de tempo_profile est cherché près du tempo du son et peut lire x4/3 ou x2/3 un passage
    très différent (140 -> 100 lu 133)."""
    refined = {_refine_align(smooth, fps, c) for c in _candidates(env, fps)}
    refined.add(_refine_align(smooth, fps, _fold(hint)))
    best = max(refined, key=lambda r: r[1])[0]
    return _choose_octave(env, benv, fps, best)


def _split_grid(x: np.ndarray, sr: int, env: np.ndarray, benv: np.ndarray, fps: float, duration: float,
                profile: Any, debug: Optional[Dict] = None) -> Optional[List[Tuple[float, float, float]]]:
    """1.4.3 (C16) : beatswitch : une grille par passage (paliers de tempo_profile._plateaus séparés par un vrai
    changement), chacune avec son tempo exact et son calage ; raccord à l'endroit où la grille du passage
    suivant colle mieux aux attaques que celle du précédent. Renvoie les passages (début = 1er temps, BPM,
    un 1er temps de mesure), ou None si un passage manque d'appui."""
    plat, cuts = list(getattr(profile, "plateaus", []) or []), set(getattr(profile, "cuts", []) or [])
    if len(plat) < 2 or not cuts:
        return None
    groups: List[List[Tuple[float, float, float]]] = [[plat[0]]]
    for k in range(1, len(plat)):
        if k - 1 in cuts:
            groups.append([])
        groups[-1].append(plat[k])
    passages = []                    # (cœur début s, cœur fin s, tempo du plus long palier)
    for g in groups:
        main = max(g, key=lambda p: p[1] - p[0])
        passages.append([g[0][0], g[-1][1], main[2]])
    # un passage trop court rejoint le précédent (motif bref, pas un changement)
    merged = [passages[0]]
    for p in passages[1:]:
        if p[1] - p[0] + 12.0 < SPLIT_MIN_S:
            merged[-1][1] = p[1]
        else:
            merged.append(p)
    if len(merged) < 2:
        return None
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    n_frames = env.size
    fr = lambda t: int(np.clip(float(_frame_of(t, sr)), 0, n_frames - 1))   # noqa: E731
    grids = []                       # (BPM exact, 1er temps s)
    for c0, c1, tempo in merged:
        a, b = fr(c0 - 4.0), fr(c1 + 4.0)
        if b - a < fps * 8:
            return None
        bpm = _passage_tempo(env[a:b], benv[a:b], smooth[a:b], fps, tempo)
        grids.append((bpm, _passage_phase(x, sr, env, benv, fps, bpm, a, b)))
    # raccords
    starts = [0.0]
    for i in range(len(merged) - 1):
        (bpm_a, t_a), (bpm_b, t_b) = grids[i], grids[i + 1]
        lo_t = max(starts[-1] + 1.0, merged[i][1] - SPLIT_SEARCH_S)
        hi_t = min(duration, merged[i + 1][0] + SPLIT_SEARCH_S)
        if hi_t - lo_t < 1.0:
            return None
        beat_a, beat_b = 60.0 / bpm_a, 60.0 / bpm_b
        ta = t_a + beat_a * np.arange(np.ceil((lo_t - t_a) / beat_a), np.floor((hi_t - t_a) / beat_a) + 1)
        tb = t_b + beat_b * np.arange(np.ceil((lo_t - t_b) / beat_b), np.floor((hi_t - t_b) / beat_b) + 1)
        if ta.size < 2 or tb.size < 2:
            return None
        mu = float(smooth[fr(lo_t):fr(hi_t) + 1].mean())
        sa = _sample(smooth, _frame_of(ta, sr)) - mu
        sb = _sample(smooth, _frame_of(tb, sr)) - mu
        cands = np.sort(np.concatenate([tb, [lo_t, hi_t]]))
        score = [float(sa[ta < c].sum() + sb[tb >= c].sum()) for c in cands]
        cut = float(cands[int(np.argmax(score))])
        first_b = float(tb[tb >= cut][0]) if np.any(tb >= cut) else float(tb[-1])
        starts.append(first_b)
    sections = []
    for i, (bpm, t0) in enumerate(grids):
        beat = 60.0 / bpm
        start = starts[i] if i else float(t0 % beat)
        if i:
            start = float(t0 + beat * np.round((start - t0) / beat))       # 1er temps exactement sur la grille
        end = starts[i + 1] if i + 1 < len(starts) else duration
        times = np.arange(start, end - 1e-6, beat)
        down = _downbeat(x, sr, benv, times) if times.size >= 8 else 0
        if times.size >= 8:
            down_t = float(times[down])
        elif times.size:                                  # passage trop court : la mesure continue
            down_t = float(times[0])
        else:
            return None
        sections.append((float(start), float(bpm), down_t))
    if debug is not None:
        debug["split"] = " ".join(f"{s:.1f}s:{b:.2f}" for s, b, _ in sections)
    return sections


def analyze_tempo(x: np.ndarray, sr: int, debug: Optional[Dict] = None, grid_mode: str = "auto") -> BeatGrid:
    """`debug` (facultatif) reçoit les mesures intermédiaires : sert à calibrer sur une vraie bibliothèque.
    1.4.3 (C16) : `grid_mode` « never » : toujours une grille fixe (choix de l'utilisateur pour ce son) ;
    1.4.4 (C221) : « classic » (réglage) : grille fixe et aucune détection du tempo qui change."""
    duration = x.size / float(sr)
    if duration < 4.0 or peak_level(x) < 1e-3:
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
    if _bass_energy_flip(x, sr, np.arange(first, duration, beat_len), beat_len, debug):   # 1.4.1 (B11)
        first = (first + beat_len / 2) % beat_len
    elif _offbeat_score(x, sr, np.arange(first, duration, beat_len), beat_len, debug) > OFFBEAT_SCORE_FLIP:
        first = (first + beat_len / 2) % beat_len
    times = np.arange(first, duration, beat_len)
    # 1.4.3 (C69) : profil de tempo (beatswitch, accélération, set, live). La grille variable n'est essayée
    # que pour un tempo qui bouge PEU À PEU (live, accélération, set) : sur l'échantillon du PC fixe, elle se
    # déclenchait sur 30 sons sur 337 à tempo fixe, souvent calée sur le contretemps (écart médian 120 ms
    # avec Rekordbox) ; un beatswitch garde une grille fixe (C16 : une grille par passage).
    from .tempo_profile import TempoProfile, classify

    try:
        # 1.4.4 (C221) : analyse « Classique » : ni détection du tempo qui change, ni grille par passage
        profile = TempoProfile() if grid_mode == "classic" else classify(env, fps, bpm, duration, debug)
    except Exception:  # noqa: BLE001 - le profil n'est qu'une information en plus
        profile = TempoProfile()
    warped = None
    if grid_mode != "never" and profile.kind == "switch":           # 1.4.3 (C16) : une grille par passage
        try:
            sections = _split_grid(x, sr, env, benv, fps, duration, profile, debug)
        except Exception:  # noqa: BLE001 - repli : la grille fixe
            sections = None
        if sections:
            from .tempo_profile import section_beats

            beats = section_beats(sections, duration)
            # BPM affiché (liste, export.pdb) : celui qui couvre le plus de temps, passages au même tempo cumulés
            span: Dict[float, float] = {}
            for i, (st, b, _d) in enumerate(sections):
                end = sections[i + 1][0] if i + 1 < len(sections) else duration
                span[round(b, 2)] = span.get(round(b, 2), 0.0) + end - st
            profile.split, profile.sections = True, sections
            profile.lo, profile.hi = min(b for _, b, _ in sections), max(b for _, b, _ in sections)
            return BeatGrid(bpm=max(span, key=span.get), first_beat=beats[0][1] if beats else 0.0,
                            downbeat_offset=0, confidence=float(min(1.0, coherence * 4)), beats=beats,
                            variable=False, profile=profile, sections=sections)
    if grid_mode != "never" and profile.kind in ("live", "ramp", "set"):
        warped = _warp(env, fps, bpm, ((first - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5, debug)
    variable = warped is not None
    profile.variable = variable
    if variable:
        times = t_of(warped)
        times = times[(times >= 0) & (times < duration)]
        # 1.4.3 (C69) : même contrôle temps / contretemps que la grille fixe (B11) : la grille suivie se cale
        # sur les attaques les plus fortes, parfois celles du contretemps
        step = float(np.median(np.diff(times)))
        if times.size > 2 and (_bass_energy_flip(x, sr, times, step)
                               or _offbeat_score(x, sr, times, step) > OFFBEAT_SCORE_FLIP):
            mids = (times[:-1] + times[1:]) / 2
            times = np.concatenate([[mids[0] - step] if mids[0] - step >= 0 else [], mids])
        first = float(times[0])
        bpm = round(float(np.median(60.0 / np.diff(times))), 2)        # tempo affiché : tempo médian
    # temps fort : décalage (0..3) qui concentre le plus d'attaques de basses (+ un peu de global)
    down, check, ref = _downbeat_vote(x, sr, benv, times, debug)
    # 1.4.4 (B125) : « 1er temps à vérifier » gardé avec le profil (registre tempo.json, comme les sons à valider de C16)
    profile.downbeat_check, profile.downbeat_at = check, (ref if check else -1.0)
    beats = [(((k - down) % 4) + 1, float(t)) for k, t in enumerate(times)]
    return BeatGrid(bpm=bpm, first_beat=float(first), downbeat_offset=down,
                    confidence=float(min(1.0, coherence * 4)), beats=beats, variable=variable, profile=profile)
