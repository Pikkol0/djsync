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
  * .2EX (V0.3.0, formes d'onde « 3 bandes » de Rekordbox 6/7 et du CDJ-3000), mesuré sur 10 sons réels :
      PWV7 : 150/s, 3 octets = basses, médiums, aigus (0-127) ; ≈ a x 127 x (bande / crête p99)^0,6,
             a = 0,97 / 0,96 / 0,68 (erreur moyenne 8/127) ;
      PWV6 : 1200 colonnes x 3 octets = moyenne du PWV7 sur la colonne, chaque bande ramenée à la même
             moyenne (≈ 0,55 x moyenne des basses) ;
      PWVC : 3 entiers ≈ k / (bande au centile 99,9), k = 81 / 54 / 42 (erreur ±15 %).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DETAIL_RATE = 150            # points par seconde (PWV3 / PWV5)
PREVIEW_COLS = 400           # PWAV
TINY_COLS = 100              # PWV2
COLOR_PREVIEW_COLS = 1200    # PWV4
THREE_BAND_COLS = 1200       # PWV6
THREE_BAND_GAIN = (0.973, 0.964, 0.682)
THREE_BAND_NORM_K = (81.0, 54.0, 42.0)
LOW_CUT, HIGH_CUT = 250.0, 2500.0


@dataclass
class Waveforms:
    detail: bytes            # PWV3 : 150/s, 1 octet
    color_detail: bytes      # PWV5 : 150/s, 2 octets big-endian
    preview: bytes           # PWAV : 400 octets
    tiny_preview: bytes      # PWV2 : 100 octets
    color_preview: bytes     # PWV4 : 1200 x 6 octets
    band_detail: bytes = b""          # PWV7 : 150/s, 3 octets (basses, médiums, aigus)
    band_preview: bytes = b""         # PWV6 : 1200 x 3 octets
    band_norm: tuple = (0, 0, 0)      # PWVC

    @property
    def detail_count(self) -> int:
        return len(self.detail)


def _frame_features(x: np.ndarray, sr: int, n: int, rate: int = DETAIL_RATE):
    """(crête, RMS basses, RMS médiums, RMS aigus) par point de forme d'onde (150/s).

    Traitement par blocs recouvrants alignés sur les points : la mémoire reste de quelques Mo même
    pour un mix d'une heure (aucun signal de bande complet n'est conservé)."""
    hop = sr // rate
    if hop * rate != sr:
        raise ValueError(f"analysis rate is not a multiple of {rate} Hz")
    total = n * hop
    peak = np.zeros(n, dtype=np.float64)
    feats = np.zeros((3, n), dtype=np.float64)
    frames_per_block, pad = 12 * rate, 4096               # 12 s par bloc
    for f0 in range(0, n, frames_per_block):
        f1 = min(n, f0 + frames_per_block)
        a, b = max(0, f0 * hop - pad), min(total, f1 * hop + pad)
        seg = x[a:b].astype(np.float64)
        if seg.size < b - a:                                # fin du son : complétée par du silence
            seg = np.pad(seg, (0, b - a - seg.size))
        lo0 = f0 * hop - a
        peak[f0:f1] = np.abs(seg[lo0: lo0 + (f1 - f0) * hop]).reshape(f1 - f0, hop).max(axis=1)
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


# 1.3.0-rc.5 (B25) : recalage sur 7 m4a analysés à la fois par DJSync et par Rekordbox 7 (même clé,
# 27/10). Rekordbox ne ramène PAS chaque son à sa propre crête : la hauteur suit le niveau réel (un son
# masterisé moins fort a une forme d'onde plus basse). Avant, DJSync étirait chaque son jusqu'en haut
# (hauteur saturée à 31, deux fois trop haute) ; et ses formes d'onde étaient en avance d'un point (6,7 ms).
# Erreurs moyennes (validation croisée son par son) avant -> après : hauteur PWV5 3,1 -> 1,3 /31 ;
# rouge / vert / bleu 1,2 / 0,7 / 1,1 -> 0,9 / 0,5 / 0,8 /7 ; blancheur PWV3 0,9 -> 0,5 /7 ;
# PWAV 4,9 -> 3,5 /31 ; PWV2 3,2 -> 2,5 /15 ; PWV4 19 / 25 / 13 / 10 / 8 / 6 -> 6 / 15 / 6 / 5 / 5 / 4.
WAVE_DELAY_POINTS = 1
HEIGHT_POLY = (7.6775, -6.0407, 17.9981, -0.783)          # hauteur = a.p + b.p² + c.p³ + d, p = crête (0-1)
WHITE_MODEL = np.array([5.1308, 2.0682, 3.0625, -0.3532, 0.312])
RGB_MODEL = np.array([
    [-7.9505, 8.3224, 8.1548, 16.1174, -8.8904, -6.6716, -4.3061, -6.2998, -2.4848, 8.0229, 2.6309, 5.1654, -1.2391, -0.072],
    [4.8244, 3.7421, -16.6103, -6.754, -5.9802, 18.4555, 3.677, -7.4671, -0.6431, 17.7457, -4.6045, -2.3643, 0.0662, -3.3915],
    [1.5707, -0.0271, -1.749, -2.0053, -1.9634, 4.4823, 0.203, -5.6713, -12.1911, 8.8509, 19.3944, -0.3279, 0.6716, -4.1903],
])
PWAV_MODEL = (0.6973, 23.1411, -2.7322)                     # crête max, crête RMS, constante (par colonne)
PWV2_MODEL = (5.8137, 10.1704, -1.0829)
# Aperçu couleur PWV4 : 6 octets par colonne = modèle linéaire sur 12 mesures de la colonne (moyennes /
# crêtes / RMS des 3 bandes, crête globale, parts d'aigus…), sur les niveaux réels (rc.5).
PWV4_MODEL = np.array([
    [-0.6844, -0.2003, -0.2375, 0.3483, 0.2798, 0.302, 0.5878, 0.4595, 0.2567, 0.0682, 0.0499, -3.3241],
    [2.4148, 0.5946, 5.1747, -0.2383, -0.5325, -0.1543, 0.2476, -0.1208, -1.736, -1.4785, 1.0742, 126.187],
    [-0.1649, -0.1768, -0.4409, 0.8232, 0.3212, -0.1043, 0.1066, 0.1541, 0.0635, 0.0151, 0.005, 0.574],
    [0.2303, -0.065, -0.1993, 0.9726, 0.0842, -0.0348, -0.1242, -0.0398, 0.0243, 0.0619, 0.0013, -1.9501],
    [-0.348, 0.0695, -0.1247, 0.0128, 0.8728, -0.0728, 0.3984, 0.0356, -0.005, -0.006, 0.0178, -0.5738],
    [-0.2704, -0.1779, 0.6105, -0.0024, 0.0344, 0.6893, 0.2855, 0.0591, 0.0313, -0.027, -0.0133, 2.4321],
])


def _delay(a: np.ndarray, k: int) -> np.ndarray:
    return a if k <= 0 or a.size <= k else np.concatenate([np.zeros(k, dtype=a.dtype), a[:-k]])


def compute_waveforms(x: np.ndarray, sr: int, duration: float) -> Waveforms:
    """Formes d'onde Rekordbox (PWV3, PWV5, PWAV, PWV2, PWV4 et 3 bandes .2EX), calées sur les fichiers
    de Rekordbox (V1.1-A4.1, puis 1.3.0-rc.5 sur les niveaux réels : voir les constantes ci-dessus)."""
    n = max(1, int(math.ceil(duration * DETAIL_RATE)))
    peak, L, M, H = _frame_features(x, sr, n)
    peak, L, M, H = (_delay(v, WAVE_DELAY_POINTS) for v in (peak, L, M, H))

    p = np.clip(peak, 0, 1)
    a1, a2, a3, a0 = HEIGHT_POLY
    height = np.clip(np.round(a1 * p + a2 * p ** 2 + a3 * p ** 3 + a0), 0, 31).astype(np.int64)
    tot = L + M + H + 1e-12
    white = np.clip(np.round(np.vstack([(M + H) / tot, M / tot, H / tot, p, np.ones(n)]).T @ WHITE_MODEL),
                    0, 7).astype(np.int64)
    white[height == 0] = 0
    detail = (height | (white << 5)).astype(np.uint8)

    mx = np.maximum(np.maximum(L, M), H) + 1e-12
    feats = np.vstack([L, M, H, np.sqrt(L), np.sqrt(M), np.sqrt(H), L / mx, M / mx, H / mx, np.sqrt(M / mx),
                       np.sqrt(H / mx), (L / mx) ** 1.5, p, np.ones(n)]).T
    r, g, b = (np.clip(np.round(feats @ RGB_MODEL[j]), 0, 7).astype(np.int64) for j in range(3))
    silent = height == 0
    r[silent] = g[silent] = b[silent] = 0
    color_detail = ((r << 13) | (g << 10) | (b << 7) | (height << 2)).astype(">u2").tobytes()

    prev = bytearray()
    for a, z in _columns(n, PREVIEW_COLS):
        seg = p[a:z]
        h = int(round(PWAV_MODEL[0] * float(seg.max()) + PWAV_MODEL[1] * float(np.sqrt((seg ** 2).mean()))
                      + PWAV_MODEL[2])) if z > a else 0
        h = max(0, min(h, 31))
        w = int(round(float(white[a:z].mean()))) if z > a and h else 0
        prev.append(h | (min(w, 7) << 5))
    tiny = bytearray()
    for a, z in _columns(n, TINY_COLS):
        seg = p[a:z]
        h = (PWV2_MODEL[0] * float(seg.max()) + PWV2_MODEL[1] * float(np.sqrt((seg ** 2).mean()))
             + PWV2_MODEL[2]) if z > a else 0.0
        tiny.append(max(0, min(15, int(round(h)))))
    color_prev = bytearray()
    Lb, Mb, Hb, pk = L * 127, M * 127, H * 127, p * 127
    pk3 = p ** 3 * 127
    for a, z in _columns(n, COLOR_PREVIEW_COLS):
        lseg, mseg, hseg = Lb[a:z], Mb[a:z], Hb[a:z]
        lm, mm, hm = float(lseg.mean()), float(mseg.mean()), float(hseg.mean())
        s = lm + mm + hm
        f = np.array([lm, mm, hm, lseg.max(), mseg.max(), hseg.max(), float(np.sqrt((lseg ** 2).mean())),
                      float(pk[a:z].max()), float(pk3[a:z].mean()), hm / s * 127 if s > 0 else 0.0,
                      (mm + hm) / s * 127 if s > 0 else 0.0, 1.0])
        vals = PWV4_MODEL @ f if float(pk[a:z].max()) > 0.5 else np.zeros(6)
        lim = (127, 255, 127, 127, 127, 127)
        color_prev += bytes(int(min(lim[j], max(0, round(float(vals[j]))))) for j in range(6))
    band_detail, band_preview, band_norm = _three_band(peak, L, M, H, n)
    return Waveforms(detail=detail.tobytes(), color_detail=color_detail, preview=bytes(prev),
                     tiny_preview=bytes(tiny), color_preview=bytes(color_prev), band_detail=band_detail,
                     band_preview=band_preview, band_norm=band_norm)


def _three_band(peak: np.ndarray, L: np.ndarray, M: np.ndarray, H: np.ndarray, n: int):
    """Formes d'onde 3 bandes (.2EX) : PWV7, PWV6, PWVC (voir l'en-tête du module)."""
    ref = float(np.percentile(peak, 99)) if np.any(peak) else 0.0
    kernel = np.ones(3) / 3
    det = np.zeros((n, 3))
    norm = []
    for j, band in enumerate((L, M, H)):
        sm = np.convolve(band, kernel, "same") if n >= 3 else band
        if ref > 0:
            det[:, j] = np.clip(THREE_BAND_GAIN[j] * 127 * (np.maximum(sm, 0) / ref) ** 0.6, 0, 127)
        top = float(np.percentile(band, 99.9)) if np.any(band) else 0.0
        norm.append(int(min(65535, max(1, round(THREE_BAND_NORM_K[j] / top)))) if top > 0 else 0)
    det = np.round(det)
    cols = np.array([det[a:z].mean(axis=0) for a, z in _columns(n, THREE_BAND_COLS)])
    target = 0.55 * float(cols[:, 0].mean())
    for j in range(3):
        m = float(cols[:, j].mean())
        if m > 0:
            cols[:, j] *= target / m
    prev = np.clip(np.round(cols), 0, 127)
    return det.astype(np.uint8).tobytes(), prev.astype(np.uint8).tobytes(), tuple(norm)


# ------------------------------------------------- éditeur de grille (V1.0.0)
GRID_RATE = 450              # points par seconde (2,2 ms) : 3 fois plus fin que le PWV7 des platines


@dataclass
class BandWave:
    """Forme d'onde 3 bandes fine, pour placer les temps à l'œil comme dans Rekordbox."""
    rate: int
    low: np.ndarray          # uint8 0-127, une valeur par point
    mid: np.ndarray
    high: np.ndarray

    @property
    def duration_ms(self) -> float:
        return self.low.size * 1000.0 / self.rate


def band_wave(x: np.ndarray, sr: int, rate: int = GRID_RATE) -> BandWave:
    """Même échelle que le PWV7 calé sur Rekordbox (gain par bande, exposant 0,6 sur la crête p99),
    à `rate` points par seconde."""
    n = max(1, int(math.ceil(x.size / sr * rate)))
    peak, L, M, H = _frame_features(x, sr, n, rate)
    ref = float(np.percentile(peak, 99)) if np.any(peak) else 0.0
    kernel = np.ones(3) / 3
    out = []
    for j, band in enumerate((L, M, H)):
        sm = np.convolve(band, kernel, "same") if n >= 3 else band
        v = np.zeros(n) if ref <= 0 else np.clip(THREE_BAND_GAIN[j] * 127 * (np.maximum(sm, 0) / ref) ** 0.6, 0, 127)
        out.append(np.round(v).astype(np.uint8))
    return BandWave(rate, *out)


_WAVE_MEMORY: dict = {}
CACHE_FILES = 100          # formes d'onde de l'éditeur de grille gardées sur disque (~100-300 Ko chacune)


def cached_band_wave(path, ffmpeg_location=None, cache_dir=None) -> BandWave:
    """band_wave d'un fichier, en mémoire puis sur disque (clé : chemin, taille, date) : rouvrir la
    grille d'un son est immédiat."""
    import hashlib
    from pathlib import Path

    from .decode import decode, timeline_lead_seconds

    path = Path(path)
    st = path.stat()
    # Le décalage de base de temps fait partie de la clé : une correction (m4a, 1.2.0-rc.4) invalide
    # les formes d'onde déjà en cache.
    lead = round(timeline_lead_seconds(path) * 1000, 1)
    key = hashlib.sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{GRID_RATE}|{lead}".encode()).hexdigest()[:20]
    if key in _WAVE_MEMORY:
        return _WAVE_MEMORY[key]
    target = Path(cache_dir) / f"{key}.npz" if cache_dir else None
    wave = None
    if target is not None and target.is_file():
        try:
            with np.load(target) as z:
                wave = BandWave(int(z["rate"]), z["low"], z["mid"], z["high"])
        except Exception:                      # noqa: BLE001 - cache illisible : on recalcule
            wave = None
    if wave is None:
        audio = decode(path, ffmpeg_location)
        wave = band_wave(audio.samples, audio.sr)
        if target is not None:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".tmp.npz")
                np.savez_compressed(tmp, rate=wave.rate, low=wave.low, mid=wave.mid, high=wave.high)
                tmp.replace(target)
                olds = sorted(target.parent.glob("*.npz"), key=lambda f: f.stat().st_mtime)
                for old in olds[:-CACHE_FILES]:
                    old.unlink(missing_ok=True)
            except OSError:
                pass
    if len(_WAVE_MEMORY) > 20:
        _WAVE_MEMORY.pop(next(iter(_WAVE_MEMORY)))
    _WAVE_MEMORY[key] = wave
    return wave
