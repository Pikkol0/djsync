"""Empreinte audio légère (1.3.0, B02 / C13) : comparer deux sons par le son, pas par le titre.

Principe (proche de Haitsma & Kalker, sans dépendance) : le son est décodé en mono 11 025 Hz, découpé
en trames de ~93 ms ; pour chaque trame, l'énergie de 33 bandes logarithmiques entre 300 et 2 000 Hz
donne 32 bits (signe de la variation d'énergie entre bandes voisines, d'une trame à l'autre). Deux
encodages du même enregistrement (m4a / mp3, débit différent) donnent presque les mêmes bits ; deux
morceaux différents en ont ~50 % de différents.

Comparer = chercher le décalage qui aligne le mieux les deux empreintes (± 40 s), puis mesurer, fenêtre
par fenêtre de 20 s, la part des bits identiques. Le décalage sert aussi à reporter les cues d'une
version à l'autre (C13). Positions dans la base de temps de Rekordbox (silence d'amorçage compris,
comme les cues), grâce à `decode`.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

log = logging.getLogger(__name__)

SR = 11025
N_FFT = 4096
HOP = 128
HOP_MS = HOP * 1000.0 / SR                  # ≈ 92,9 ms par trame
BANDS = 33
MAX_SHIFT_S = 40.0
WINDOW_S = 20.0
# Verdicts (à calibrer sur de vraies paires : voir tools/dup_audio_report.py)
SAME_BER = 0.35                             # fenêtre « identique » : distance < 0,35
SAME_SHARE = 0.85                           # même son : ≥ 85 % des fenêtres identiques
VARIANT_SHARE = 0.25                        # variante : au moins un quart du son en commun
SAME_DURATION_GAP_S = 8.0


@dataclass
class Match:
    shift_ms: float          # position dans b = position dans a + shift_ms
    ber: float               # distance sur tout le recouvrement (0 = identique, ~0,75 sans rapport)
    share: float             # part des fenêtres de 20 s quasi identiques (sur le plus court des deux)
    verdict: str             # "same" | "variant" | "different"


def fingerprint(samples: np.ndarray, sr: int = SR) -> np.ndarray:
    """Empreinte (uint32 par trame) d'un signal mono à `sr` Hz."""
    x = np.asarray(samples, dtype=np.float32)
    if sr != SR:
        from .decode import _resample

        x = _resample(x, sr, SR).astype(np.float32)
    if x.size < N_FFT * 4:
        return np.zeros(0, dtype=np.uint32)
    n = 1 + (x.size - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(N_FFT).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    edges = np.geomspace(300.0, 2000.0, BANDS + 1)
    band = np.stack([spec[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) for lo, hi in zip(edges[:-1], edges[1:])],
                    axis=1)
    # plancher : les bandes presque vides (bruit, silence) donnent des bits stables au lieu d'aléatoires
    floor = max(1e-9, float(np.percentile(band.max(axis=1), 75)) * 5e-2)
    band = np.log10(band + floor)
    diff = band[:, :-1] - band[:, 1:]                     # 32 différences entre bandes voisines
    bits = (diff[1:] - diff[:-1]) > 0.01                  # variation d'une trame à l'autre (hors bruit de fond)
    weights = (1 << np.arange(32, dtype=np.uint64)).astype(np.uint64)
    return (bits.astype(np.uint64) * weights).sum(axis=1).astype(np.uint32)


_BITS = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _popcount(v: np.ndarray) -> np.ndarray:
    return _BITS[np.ascontiguousarray(v).view(np.uint8)].reshape(-1, 4).sum(axis=1, dtype=np.int64)


def _pop_total(v: np.ndarray) -> int:
    return int(_BITS[np.ascontiguousarray(v).view(np.uint8)].sum(dtype=np.int64))


def _distance(x: np.ndarray, y: np.ndarray) -> float:
    """Part des bits « actifs » (à 1 dans l'une ou l'autre empreinte) qui diffèrent : 0 = identique,
    ~0,7-0,8 pour deux morceaux sans rapport. Les trames calmes (bits à 0 partout) ne comptent pas."""
    union = _pop_total(x | y)
    return _pop_total(x ^ y) / union if union else 1.0


def is_usable(fp: Any) -> bool:
    """Assez de son pour comparer : au moins 10 s, et pas du silence (bits presque tous à 0)."""
    if fp is None or len(fp) < int(10_000 / HOP_MS):
        return False
    return _pop_total(fp) > 0.02 * 32 * len(fp)


def compare(a: np.ndarray, b: np.ndarray, duration_a: float = 0.0, duration_b: float = 0.0,
            max_shift_s: float = MAX_SHIFT_S) -> Match:
    """Meilleur alignement de deux empreintes et verdict."""
    if a.size < 20 or b.size < 20:
        return Match(0.0, 1.0, 0.0, "different")
    max_shift = int(max_shift_s * 1000.0 / HOP_MS)
    min_overlap = min(a.size, b.size, int(15_000 / HOP_MS))

    def dist_at(x: np.ndarray, y: np.ndarray, off: int, need: int) -> float:
        """Distance pénalisée par un recouvrement partiel : dans une musique en boucles, un décalage
        d'une boucle entière ressemble presque autant, mais recouvre moins."""
        lo, hi = max(0, -off), min(x.size, y.size - off)
        if hi - lo < need:
            return 2.0
        cover = (hi - lo) / float(min(x.size, y.size))
        return _distance(x[lo:hi], y[lo + off:hi + off]) * (1.0 + 2.0 * (1.0 - cover))

    # recherche grossière une trame sur deux (deux phases), puis affinage à la trame près des meilleurs
    # candidats (dans une musique en boucles, plusieurs décalages se ressemblent)
    a2 = a[::2]
    coarse = []
    for phase in (0, 1):
        b2 = b[phase::2]
        for off2 in range(-max_shift // 2, max_shift // 2 + 1):
            d = dist_at(a2, b2, off2, min_overlap // 2)
            if d < 2.0:
                coarse.append((d, off2 * 2 + phase))
    if not coarse:
        return Match(0.0, 1.0, 0.0, "different")
    coarse.sort()
    centres: list = []
    for _d, off in coarse:
        if all(abs(off - c) > 4 for c in centres):
            centres.append(off)
        if len(centres) >= 6:
            break
    best = min((dist_at(a, b, off, min_overlap), off) for c in centres for off in range(c - 2, c + 3))
    _score, off = best
    lo, hi = max(0, -off), min(a.size, b.size - off)
    ber = _distance(a[lo:hi], b[lo + off:hi + off]) if hi > lo else 1.0
    win = max(1, int(WINDOW_S * 1000.0 / HOP_MS))
    shorter = min(a.size, b.size)
    good = 0
    if hi > lo:
        xa, xb = a[lo:hi], b[lo + off:hi + off]
        for s in range(0, xa.size, win):
            n = min(win, xa.size - s)
            if n >= win // 2 and _distance(xa[s:s + n], xb[s:s + n]) < SAME_BER:
                good += n
    share = good / float(shorter)
    gap = abs(duration_a - duration_b) if duration_a and duration_b else 0.0
    if share >= SAME_SHARE and gap <= SAME_DURATION_GAP_S:
        verdict = "same"
    elif share >= VARIANT_SHARE:
        verdict = "variant"
    else:
        verdict = "different"
    return Match(off * HOP_MS, ber, min(1.0, share), verdict)


def matches_at(a: np.ndarray, b: np.ndarray, shift_ms: float, ms: float, radius_s: float = 5.0) -> bool:
    """Le passage autour de `ms` (dans a) se retrouve-t-il à `ms + shift_ms` dans b ? (C13 : un cue
    n'est reporté que là où les deux versions sont identiques.)"""
    off = int(round(shift_ms / HOP_MS))
    c = int(ms / HOP_MS)
    r = int(radius_s * 1000.0 / HOP_MS)
    lo, hi = max(0, c - r, -off), min(a.size, c + r, b.size - off)
    if hi - lo < r // 2:
        return False
    return _distance(a[lo:hi], b[lo + off:hi + off]) < SAME_BER


def file_key(path: Union[str, Path]) -> str:
    p = Path(path)
    st = p.stat()
    return hashlib.sha1(f"{p.name}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")).hexdigest()[:20]


def file_fingerprint(path: Union[str, Path], ffmpeg_location: Optional[str] = None,
                     cache_dir: Optional[Path] = None) -> np.ndarray:
    """Empreinte d'un fichier audio (lue dans le cache si possible). Lève DecodeError si illisible."""
    from .decode import decode

    key = file_key(path)
    cached = Path(cache_dir) / f"{key}.npy" if cache_dir else None
    if cached is not None and cached.is_file():
        try:
            return np.load(cached)
        except (OSError, ValueError):
            pass
    d = decode(path, ffmpeg_location, sr=SR)
    fp = fingerprint(d.samples, d.sr)
    if cached is not None:
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            np.save(cached, fp)
        except OSError as exc:
            log.debug("Fingerprint not cached: %s", exc)
    return fp
