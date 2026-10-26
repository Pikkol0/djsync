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


# 1.3.0 (B11) : bandes qui distinguent le temps du contretemps. Kick : fondamentale 40-100 Hz ;
# clap / caisse claire : bruit 1,5-5 kHz (toujours SUR un temps, 2 et 4 ou 3) ; charleston : 7-11 kHz
# (souvent ouvert sur le contretemps en house, ce qui attire la grille dessus).
BANDS = {"full": (30, 8000), "bass": (30, 150), "kick": (40, 100), "clap": (1500, 5000), "hat": (7000, 11000)}


def onset_bands(x: np.ndarray, sr: int) -> Tuple[Dict[str, np.ndarray], float]:
    """Enveloppes d'attaques par bande (flux spectral log, normalisé) et images par seconde."""
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    masks = {k: (freqs >= lo) & (freqs <= hi) for k, (lo, hi) in BANDS.items()}
    prev = None
    acc: Dict[str, list] = {k: [] for k in BANDS}
    for mag in _frames(x, N_FFT, HOP):
        lm = np.log1p(100.0 * mag)
        if prev is None:
            prev = lm[:1]
        d = np.diff(np.concatenate([prev, lm], axis=0), axis=0)
        d = np.maximum(d, 0.0)
        for k, m in masks.items():
            acc[k].append(d[:, m].sum(axis=1))
        prev = lm[-1:]
    fps = sr / HOP

    def clean(e: np.ndarray) -> np.ndarray:
        w = max(1, int(fps * 0.4))
        local = np.convolve(e, np.ones(w) / w, mode="same")
        e = np.maximum(e - local, 0.0)
        s = e.std()
        return (e / s).astype(np.float64) if s > 0 else e.astype(np.float64)

    return {k: clean(np.concatenate(v)) for k, v in acc.items()}, fps


def onset_envelopes(x: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray, float]:
    """(enveloppe globale, enveloppe des basses, images par seconde)."""
    bands, fps = onset_bands(x, sr)
    return bands["full"], bands["bass"], fps


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


THREE_HALVES_SCORE = 0.95     # A02 : voir analyze_tempo
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


OFFBEAT_FLIP = 1.3     # (avant 1.3.0) basses du contretemps / basses du temps : gardé pour le diagnostic
BACKBEAT_MIN = 0.20    # motif clap / caisse claire net (contraste sur 4 temps) …
BACKBEAT_GAIN = 2.5    # … et nettement plus marqué un demi-temps plus loin


def _pattern(env: np.ndarray, period: float, phase: float) -> float:
    """Contraste du motif sur 4 temps : (temps le plus fort du cycle − moyenne) / moyenne, mesuré aux
    positions phase + k·période. Une caisse claire / un clap sur 2 et 4 (ou sur le 3 en trap) donne un
    motif net SUR les temps ; des charlestons réguliers sur les contretemps n'en donnent aucun."""
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    n = int((smooth.size - 1 - phase - period) // period)
    if n < 16:
        return 0.0
    v = _sample(smooth, phase + np.arange(n) * period)
    m = np.array([v[j::4].mean() for j in range(4)])
    mean = float(m.mean())
    return float((m.max() - mean) / mean) if mean > 0 else 0.0


def _kick_phase(bands: Dict[str, np.ndarray], period: float, phase: float, debug: Optional[Dict] = None) -> float:
    """Temps ou contretemps ? (B11, 1.3.0) Le calage sur toutes les attaques tombe parfois sur le
    contretemps quand les charlestons ouverts y dominent. La règle 1.2 (basses du contretemps plus
    fortes) ne séparait pas les sons fautifs des bons sur 52 m4a comparés à Rekordbox (0,39 à 2,46
    contre jusqu'à 2,07) : les lignes de basse jouent souvent sur le contretemps. Nouvelle règle :
    le CLAP / la caisse claire (1,5-5 kHz) dessine un motif net sur 4 temps, toujours sur les temps.
    Si ce motif est net un demi-temps plus loin et quasi absent sous la grille, la grille est décalée.
    Synthétique : house à charleston ouvert dominant 0,25-0,51 contre 0,02-0,04 ; sons justes :
    0,11 au plus un demi-temps plus loin. À revalider sur la clé avec --compare (colonnes b11_*)."""
    here = _pattern(bands["clap"], period, phase)
    there = _pattern(bands["clap"], period, phase + period / 2)
    if debug is not None:
        smooth = np.convolve(bands["bass"], [0.25, 0.5, 0.25], mode="same")
        k = np.arange(0, max(1, int((smooth.size - 1 - phase) // period)))
        on = float(_sample(smooth, phase + k * period).mean())
        off = float(_sample(smooth, phase + period / 2 + k * period).mean())
        debug["kick_offbeat_ratio"] = round(off / on, 3) if on > 0 else -1
        for name in ("kick", "hat", "full"):
            debug[f"b11_{name}"] = f"{_pattern(bands[name], period, phase):.3f}/{_pattern(bands[name], period, phase + period / 2):.3f}"
        debug["b11_clap"] = f"{here:.3f}/{there:.3f}"
    if there >= BACKBEAT_MIN and there >= BACKBEAT_GAIN * here:
        if debug is not None:
            debug["b11_flip"] = True
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
    # écart de chaque temps suivi à la grille constante, mesuré comme un angle (repliement circulaire),
    # puis recentré sur l'écart moyen. 1.3.0 : un décalage CONSTANT (grille suivie calée un demi-temps
    # plus loin, sur les charlestons) n'est pas un tempo qui varie ; seule compte la variation de
    # l'écart au fil du morceau.
    ang = 2 * np.pi * (inside - phase0) / period
    centre = np.angle(np.mean(np.exp(1j * ang)))
    dev = np.angle(np.exp(1j * (ang - centre))) / (2 * np.pi) * period
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


def _fit_range(bpm: float, bpm_range: Tuple[float, float]) -> float:
    """C16 : ramène le tempo dans la plage choisie (octave : ×2 / ÷2), comme le réglage de Rekordbox."""
    lo, hi = bpm_range
    if bpm <= 0 or (lo, hi) == (BPM_MIN, BPM_MAX):
        return bpm
    while bpm >= hi and bpm / 2 >= lo:
        bpm /= 2
    while bpm < lo and bpm * 2 < hi:
        bpm *= 2
    return round(bpm, 2)


def analyze_tempo(x: np.ndarray, sr: int, debug: Optional[Dict] = None, constant: bool = False,
                  bpm_range: Tuple[float, float] = (BPM_MIN, BPM_MAX)) -> BeatGrid:
    """`debug` (facultatif) reçoit les mesures intermédiaires : sert à calibrer sur une vraie bibliothèque.
    `constant` (C16) : jamais de grille variable ; `bpm_range` : plage d'affichage du BPM."""
    duration = x.size / float(sr)
    if duration < 4.0 or peak_level(x) < 1e-3:
        return BeatGrid()
    bands, fps = onset_bands(x, sr)
    env, benv = bands["full"], bands["bass"]
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
    # A02 (1.3.0) : rapport 3:2. Quand le tempo 3/2 fois plus rapide aligne presque aussi bien (≥ 95 %),
    # Rekordbox le retient. Mesuré sur 52 m4a : corrige Alicante (90 -> 135) et ЗАВОД (106,67 -> 160),
    # aucun son juste ne bascule.
    for b, sc in refined[1:]:
        if abs(b / rep - 1.5) < 0.015 and sc >= THREE_HALVES_SCORE * rep_score:
            if debug is not None:
                debug["a02_three_halves"] = f"{rep:.2f}->{b:.2f}"
            rep, rep_score = b, sc
            break
    if debug is not None:
        debug["candidats"] = " ".join(f"{b:.2f}:{sc:.2f}" for b, sc in refined[:5])
    bpm = _fit_range(_choose_octave(env, benv, fps, rep, debug), bpm_range)
    coherence = abs(complex(_fourier(env, fps, np.array([bpm]))[0])) / (float(np.abs(env).sum()) or 1.0)
    if debug is not None:
        debug.update(before_refine=round(rep, 2), coherence=round(coherence, 4))
    period = fps * 60.0 / bpm                                   # images par temps
    # position du 1er temps (en images) par recherche directe ; la différence spectrale place une
    # attaque entre deux images (-0.5 image) et l'image est centrée sur sa fenêtre (+N_FFT/2)
    phase_frames, _, _ = _best_phase(env, period)
    phase_frames = _kick_phase(bands, period, phase_frames, debug)
    t_of = lambda f: ((f - 0.5) * HOP + N_FFT / 2) / sr + ONSET_LATENCY   # image -> secondes
    first = t_of(phase_frames)
    beat_len = 60.0 / bpm
    first %= beat_len
    times = np.arange(first, duration, beat_len)
    warped = None if constant else _warp(env, fps, bpm, ((first - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5, debug)
    variable = warped is not None
    if variable:
        times = t_of(warped)
        times = times[(times >= 0) & (times < duration)]
        first = float(times[0])
        bpm = round(float(np.median(60.0 / np.diff(times))), 2)        # tempo affiché : tempo médian
    # temps fort (B12, 1.3.0) : décalage (0..3) choisi par plusieurs indices, chacun mesuré en
    # CONTRASTE relatif (écart à la moyenne / moyenne) et non plus normalisé (z) : un indice sans
    # motif (pas d'accords, kick sur chaque temps) reste proche de 0 au lieu de peser autant que les
    # autres. Indices : kick (40-100 Hz : le 1 porte souvent le kick le plus fort ou le seul),
    # changement harmonique (accords en début de mesure), basses, et clap / caisse claire (presque
    # jamais sur le 1). Synthétique : 1 retrouvé en hip-hop / trap (0 sur 6 avec l'ancien calcul).
    frames = ((times - ONSET_LATENCY) * sr - N_FFT / 2) / HOP + 0.5

    def sample(e: np.ndarray) -> np.ndarray:
        i = np.clip(np.round(frames).astype(int), 0, e.size - 1)
        lo, hi = np.clip(i - 1, 0, e.size - 1), np.clip(i + 1, 0, e.size - 1)
        return np.maximum.reduce([e[lo], e[i], e[hi]])

    nums = np.arange(times.size) % 4
    harm = _harmonic_change(x, sr, times)

    def rel(v: np.ndarray) -> np.ndarray:
        per = np.array([float(v[nums == j].mean()) if np.any(nums == j) else 0.0 for j in range(4)])
        mean = float(per.mean())
        return (per - mean) / mean if mean > 0 else np.zeros(4)

    if times.size >= 8:
        parts = {"kick": rel(sample(bands["kick"])), "harm": rel(harm), "bass": rel(sample(benv)),
                 "clap": rel(sample(bands["clap"]))}
        scores = list(parts["kick"] + parts["harm"] + 0.5 * parts["bass"] - 0.5 * parts["clap"])
        if debug is not None:
            for k, v in parts.items():
                debug[f"b12_{k}"] = " ".join(f"{a:+.2f}" for a in v)
    else:
        scores = [0.0, 0.0, 0.0, 0.0]
    if debug is not None:
        debug["downbeat_scores"] = " ".join(f"{v:.2f}" for v in scores)
    down = int(np.argmax(scores))
    beats = [(((k - down) % 4) + 1, float(t)) for k, t in enumerate(times)]
    return BeatGrid(bpm=bpm, first_beat=float(first), downbeat_offset=down,
                    confidence=float(min(1.0, coherence * 4)), beats=beats, variable=variable)
