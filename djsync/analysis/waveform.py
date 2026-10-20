"""Formes d'onde au format Pioneer (contenu des balises ANLZ), calculées en numpy.

Tout part de 3 enveloppes par bande (basses < 250 Hz, médiums, aigus > 2,5 kHz) et d'une
enveloppe crête, à 150 points par seconde (résolution des formes d'onde « détail » Pioneer).
Les échelles et la répartition des octets ont été calées sur de VRAIS fichiers exportés par
Rekordbox (6 morceaux, jeux DAT/EXT/2EX) :
  * PWV3 / PWAV : 1 octet = hauteur (5 bits bas, 0-31) + « blancheur » (3 bits hauts) ;
  * PWV2        : hauteur sur 4 bits (0-15), 100 colonnes ;
  * PWV5        : 16 bits = rouge(3) vert(3) bleu(3) hauteur(5) 00 ; rouge = basses, vert =
                  médiums, bleu = aigus (couleurs « RGB » des platines) ;
  * PWV4        : 1200 colonnes de 6 octets. Mesuré sur les fichiers réels : d2 ≈ 1,12 x crête des
                  basses (R² = 0,98), d3 ≈ moyenne quadratique des basses, d4 ≈ 0,5 x crête des
                  médiums, d5 ≈ 1,6 x moyenne des aigus, d0 ≈ 0,8 x somme des moyennes, d1 ≈ 130-250.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DETAIL_RATE = 150            # points par seconde (PWV3 / PWV5)
PREVIEW_COLS = 400           # PWAV
TINY_COLS = 100              # PWV2
COLOR_PREVIEW_COLS = 1200    # PWV4
LOW_CUT, HIGH_CUT = 250.0, 2500.0


@dataclass
class Waveforms:
    detail: bytes            # PWV3 : 150/s, 1 octet
    color_detail: bytes      # PWV5 : 150/s, 2 octets big-endian
    preview: bytes           # PWAV : 400 octets
    tiny_preview: bytes      # PWV2 : 100 octets
    color_preview: bytes     # PWV4 : 1200 x 6 octets

    @property
    def detail_count(self) -> int:
        return len(self.detail)


def _frame_features(x: np.ndarray, sr: int, n: int):
    """(crête, RMS basses, RMS médiums, RMS aigus) par point de forme d'onde (150/s).

    Traitement par blocs recouvrants alignés sur les points : la mémoire reste de quelques Mo même
    pour un mix d'une heure (aucun signal de bande complet n'est conservé)."""
    hop = sr // DETAIL_RATE
    if hop * DETAIL_RATE != sr:
        raise ValueError("fréquence d'analyse non multiple de 150 Hz")
    total = n * hop
    if x.size < total:
        x = np.pad(x, (0, total - x.size))
    peak = np.abs(x[:total]).reshape(n, hop).max(axis=1).astype(np.float64)
    feats = np.zeros((3, n), dtype=np.float64)
    frames_per_block, pad = 1800, 4096                    # 12 s par bloc
    for f0 in range(0, n, frames_per_block):
        f1 = min(n, f0 + frames_per_block)
        a, b = max(0, f0 * hop - pad), min(total, f1 * hop + pad)
        seg = x[a:b].astype(np.float64)
        spec = np.fft.rfft(seg)
        f = np.fft.rfftfreq(seg.size, 1.0 / sr)
        # transitions douces (évite les oscillations d'un filtre « mur »)
        g_low = np.clip((LOW_CUT * 1.25 - f) / (LOW_CUT * 0.5), 0, 1)
        g_high = np.clip((f - HIGH_CUT * 0.8) / (HIGH_CUT * 0.4), 0, 1)
        g_mid = np.clip(1.0 - g_low - g_high, 0, 1)
        lo = f0 * hop - a
        for i, g in enumerate((g_low, g_mid, g_high)):
            band = np.fft.irfft(spec * g, seg.size)[lo: lo + (f1 - f0) * hop]
            feats[i, f0:f1] = np.sqrt((band.reshape(f1 - f0, hop) ** 2).mean(axis=1))
    return peak, feats[0], feats[1], feats[2]


def _columns(n: int, cols: int):
    for c in range(cols):
        a = (c * n) // cols
        b = max(a + 1, ((c + 1) * n) // cols)
        yield min(a, n - 1), min(b, n)


# Aperçu couleur PWV4 : 6 octets par colonne = modèle linéaire sur 12 mesures de la colonne
# (moyennes / crêtes / RMS des 3 bandes, crête globale, parts d'aigus…), ajusté sur 12 000 colonnes
# de 10 sons réels exportés par Rekordbox. Validation croisée par son : erreur moyenne par octet
# 28/42/23/13/15/9 -> 14/21/13/11/11/7.
PWV4_MODEL = np.array([
    [-1.3108, -0.6192, -1.1130, -0.2577, 0.1411, 0.5102, 1.0796, 0.5046, 0.8290, -0.0185, -0.1061, 20.8977],
    [1.1440, 0.5320, 3.0892, -0.0450, -0.2348, -0.4293, -0.6053, 0.0807, -1.1695, -1.2743, 0.1778, 198.5616],
    [-1.1208, -0.5370, -1.0379, 0.1671, 0.1892, 0.3705, 0.8986, 0.0951, 0.6828, -0.1219, -0.1499, 25.8843],
    [-0.8708, -0.7135, -1.0238, 0.3873, 0.0899, 0.4294, 0.9073, -0.0838, 0.5336, -0.0579, -0.0047, 9.3005],
    [-1.3914, -0.2419, -0.8584, -0.1403, 0.7037, 0.2973, 1.0284, -0.0532, 0.5051, -0.0605, -0.1225, 19.8417],
    [-0.5396, -0.2573, 0.1282, -0.1009, -0.0161, 0.8585, 0.5000, -0.0079, 0.2171, -0.0864, -0.0398, 9.7574],
])


def compute_waveforms(x: np.ndarray, sr: int, duration: float) -> Waveforms:
    """Calibré sur les fichiers .EXT de Rekordbox de 10 sons réels (V1.1-A4.1), erreurs moyennes
    avant -> après : hauteur 8,5 -> 3,5 (sur 31) ; rouge 1,2 -> 1,0, vert 1,4 -> 0,6, bleu 2,8 -> 0,9
    (sur 7) ; blancheur 0,75 -> 0,61. Alignement temporel : 0 ms (mp3 compris)."""
    n = max(1, int(math.ceil(duration * DETAIL_RATE)))
    peak, L, M, H = _frame_features(x, sr, n)

    ref_peak = float(np.percentile(peak, 99.5)) if np.any(peak) else 0.0
    rel = np.zeros(n) if ref_peak <= 0 else np.clip(peak / ref_peak, 0, 1)
    height = np.round(31 * rel ** 3).astype(np.int64)          # courbe de Rekordbox : ~ puissance 3
    bands = np.vstack([L, M, H])
    ref_band = float(np.percentile(bands.max(axis=0), 99.5)) if np.any(bands) else 0.0
    if ref_band > 0:
        bands = np.clip(bands * (127.0 / ref_band), 0, 127)
    Lb, Mb, Hb = bands
    mx = np.maximum(bands.max(axis=0), 1e-9)
    total = Lb + Mb + Hb + 1e-9

    # « blancheur » 0-7 : part des médiums + aigus
    white = np.clip(np.round(8 * (Mb + Hb) / total), 0, 7).astype(np.int64)
    white[height == 0] = 0
    detail = (height | (white << 5)).astype(np.uint8)

    r = np.clip(np.round(7 * (Lb / mx) ** 1.5), 0, 7).astype(np.int64)
    g = np.clip(np.round(5 * (Mb / mx) ** 0.5), 0, 7).astype(np.int64)
    b = np.clip(np.round(10 * (Hb / mx) ** 0.5), 0, 7).astype(np.int64)
    silent = height == 0
    r[silent] = g[silent] = b[silent] = 0
    color_detail = ((r << 13) | (g << 10) | (b << 7) | (height << 2)).astype(">u2").tobytes()

    # Aperçus calés sur Rekordbox : PWAV = 0,78 x hauteur moyenne de la colonne (erreur 9,6 -> 3,0 /31) ;
    # PWV2 = 0,93 x moyenne quadratique du niveau relatif (erreur 3,1 -> 1,9 /15).
    prev = bytearray()
    for a, z in _columns(n, PREVIEW_COLS):
        h = int(round(0.78 * float(height[a:z].mean()))) if z > a else 0
        w = int(round(float(white[a:z].mean()))) if z > a and h else 0
        prev.append(min(h, 31) | (min(w, 7) << 5))
    tiny = bytearray()
    for a, z in _columns(n, TINY_COLS):
        h = 0.93 * 15 * float(np.sqrt((rel[a:z] ** 2).mean())) if z > a else 0.0
        tiny.append(min(15, int(round(h))))
    color_prev = bytearray()
    pk = rel * 127
    pk3 = rel ** 3 * 127
    for a, z in _columns(n, COLOR_PREVIEW_COLS):
        lseg, mseg, hseg = Lb[a:z], Mb[a:z], Hb[a:z]
        lm, mm, hm = float(lseg.mean()), float(mseg.mean()), float(hseg.mean())
        s = lm + mm + hm
        f = np.array([lm, mm, hm, lseg.max(), mseg.max(), hseg.max(), float(np.sqrt((lseg ** 2).mean())),
                      float(pk[a:z].max()), float(pk3[a:z].mean()), hm / s * 127 if s > 0 else 0.0,
                      (mm + hm) / s * 127 if s > 0 else 0.0, 1.0])
        vals = PWV4_MODEL @ f if s > 0.5 else np.zeros(6)
        lim = (127, 255, 127, 127, 127, 127)
        color_prev += bytes(int(min(lim[j], max(0, round(float(vals[j]))))) for j in range(6))
    return Waveforms(detail=detail.tobytes(), color_detail=color_detail, preview=bytes(prev),
                     tiny_preview=bytes(tiny), color_preview=bytes(color_prev))
