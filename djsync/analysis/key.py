"""Tonalité (24 clés majeures/mineures) en numpy pur, convertie en Camelot.

Méthode (Krumhansl-Schmuckler ; profils = moitié Sha'ath / KeyFinder, moitié profil appris sur 206
sons analysés par Rekordbox — V1.1-A4.1, validation croisée : 67,5 % -> 71,8 % de tonalités
identiques à Rekordbox, 83,5 % -> 90,3 % de tonalités compatibles pour le mix) :
  1. spectre (FFT 8192 points à 22 050 Hz : ~2,7 Hz de résolution) sur tout le morceau ;
  2. accordage : écart moyen (en centièmes de demi-ton) des pics spectraux au tempérament égal,
     pour ne pas se tromper de demi-ton sur une vidéo YouTube légèrement accélérée ;
  3. chromagramme : énergie de chaque bin attribuée à sa classe de hauteur (C2 à C7), poids
     triangulaire selon la distance au demi-ton ; les pics seuls comptent (fond de bruit retiré) ;
     On moyenne le chromagramme accordé et celui à 440 Hz : aucun des deux ne gagne seul (un son
     désaccordé d'un quart de ton est ambigu, Rekordbox tranche parfois dans l'autre sens) ;
  4. corrélation avec les 24 profils tournés ; meilleure corrélation = tonalité.

Les noms suivent la convention de Rekordbox relevée dans un vrai export.pdb :
C, Db, D, Eb, E, F, F#, G, Ab, A, Bb, B et la même chose suivie de « m » pour les mineures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from .decode import peak_level

from ..core.camelot import to_camelot

NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
# Profils de Sha'ath (libKeyFinder), indice 0 = tonique
SHAATH_MAJOR = np.array([7.23900502618145, 3.50351166725158, 3.58430582939911, 2.84870053049922, 5.81856655665853,
                  4.55891174314763, 2.44831611651744, 6.99258598309745, 3.39126408185928, 4.55767847298431,
                  4.07849452350154, 4.45073808813262])
SHAATH_MINOR = np.array([7.00255045759871, 3.14360061770071, 4.35908323706906, 5.40104234087157, 3.67498728785599,
                  4.08766432493939, 3.90972451219255, 6.20271651004128, 3.63478133929837, 2.86817271296547,
                  5.35435930648155, 3.83423117440823])
# Profils utilisés : 50 % Sha'ath + 50 % moyenne des chromas (tournés sur la tonique Rekordbox) de
# 206 sons réels (29 majeurs, 177 mineurs : rap/club FR surtout), normalisés à 100.
MAJOR = np.array([12.4558, 6.3104, 8.1697, 5.5927, 10.769, 8.0643, 5.6778, 12.2947, 6.219, 8.8315, 6.9589, 8.6563])
MINOR = np.array([12.9, 6.0059, 8.6862, 9.8416, 6.5706, 8.4704, 6.5798, 11.8502, 7.0887, 5.9945, 9.3565, 6.6555])
N_FFT = 8192
HOP = 4096
MIDI_LO, MIDI_HI = 36, 96            # C2 .. C7


@dataclass
class KeyResult:
    name: Optional[str] = None       # « Am », « F#m », « Eb »… (None = indéterminée)
    camelot: Optional[str] = None    # « 8A »…
    confidence: float = 0.0          # écart relatif entre la 1re et la 2e clé (0..1)
    tuning_cents: float = 0.0


def _spectra(x: np.ndarray):
    if x.size < N_FFT:
        return
    win = np.hanning(N_FFT).astype(np.float32)
    view = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP]    # aucune copie
    for start in range(0, view.shape[0], 64):
        yield np.abs(np.fft.rfft(view[start:start + 64] * win, axis=1)).astype(np.float32)


def analyze_key(x: np.ndarray, sr: int, debug: Optional[Dict] = None) -> KeyResult:
    if x.size < N_FFT * 4 or peak_level(x) < 1e-3:
        return KeyResult()
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    lo_f = 440.0 * 2 ** ((MIDI_LO - 0.5 - 69) / 12)
    hi_f = 440.0 * 2 ** ((MIDI_HI + 0.5 - 69) / 12)
    sel = np.where((freqs >= lo_f) & (freqs <= hi_f))[0]
    midi = 69 + 12 * np.log2(freqs[sel] / 440.0)

    # moyenne des spectres (racine de la magnitude : atténue la domination des basses)
    acc = np.zeros(sel.size, dtype=np.float64)
    frames = 0
    for mag in _spectra(x):
        m = np.sqrt(mag[:, sel])
        # pics locaux seulement (harmoniques), fond de bruit retiré
        peak = (m[:, 1:-1] > m[:, :-2]) & (m[:, 1:-1] >= m[:, 2:])
        keep = np.zeros_like(m, dtype=bool)
        keep[:, 1:-1] = peak
        floor = np.median(m, axis=1, keepdims=True)
        acc += np.where(keep, np.maximum(m - floor, 0), 0).sum(axis=0)
        frames += m.shape[0]
    if frames == 0 or not np.any(acc):
        return KeyResult()

    # accordage : moyenne circulaire de l'écart au demi-ton, pondérée par l'énergie
    dev = midi - np.round(midi)
    ang = np.angle(np.sum(acc * np.exp(2j * np.pi * dev)))
    tuning = ang / (2 * np.pi)                               # en demi-tons, dans [-0.5, 0.5]
    m_t = midi - tuning
    pc_float = m_t - np.round(m_t)
    weight = np.clip(1.0 - np.abs(pc_float) * 2.0, 0.0, 1.0)  # 1 au centre du demi-ton, 0 à ±50 cents
    pcs = (np.round(m_t).astype(int)) % 12
    tuned = np.bincount(pcs, weights=acc * weight, minlength=12)
    w0 = np.clip(1.0 - np.abs(midi - np.round(midi)) * 2.0, 0.0, 1.0)
    c440 = np.bincount(np.round(midi).astype(int) % 12, weights=acc * w0, minlength=12)
    if debug is not None:                       # chromas bruts (avec / sans accordage) pour calibrage
        debug.update(tuning_cents=round(float(tuning * 100), 1),
                     chroma=" ".join(f"{v / max(tuned.sum(), 1e-9):.4f}" for v in tuned),
                     chroma_440=" ".join(f"{v / max(c440.sum(), 1e-9):.4f}" for v in c440))
    if tuned.sum() <= 0 or c440.sum() <= 0:
        return KeyResult()
    chroma = tuned / tuned.sum() + c440 / c440.sum()
    if chroma.sum() <= 0:
        return KeyResult()

    scores = np.empty(24)
    for tonic in range(12):
        rolled = np.roll(chroma, -tonic)
        scores[tonic] = np.corrcoef(rolled, MAJOR)[0, 1]
        scores[12 + tonic] = np.corrcoef(rolled, MINOR)[0, 1]
    order = np.argsort(scores)[::-1]
    best, second = scores[order[0]], scores[order[1]]
    if not np.isfinite(best) or best < 0.1:
        return KeyResult(tuning_cents=float(tuning * 100))
    k = int(order[0])
    name = NAMES[k % 12] + ("m" if k >= 12 else "")
    if debug is not None:
        debug["key_top3"] = " ".join(f"{to_camelot(NAMES[int(i) % 12] + ('m' if i >= 12 else ''))}:{scores[i]:.3f}"
                                     for i in order[:3])
    conf = float(np.clip((best - second) / max(abs(best), 1e-9) * 5, 0.0, 1.0))
    return KeyResult(name=name, camelot=to_camelot(name), confidence=conf, tuning_cents=float(tuning * 100))
