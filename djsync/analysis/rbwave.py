"""Formes d'onde calculées comme Rekordbox (1.4.3, A7-3).

Portage en numpy des formules de Sleeve (github.com/alii/sleeve, GPL-2.0-or-later, contributeurs de Sleeve), `crates/rbl-analysis/src/wave_creator.rs` et `blue_overview.rs`, elles-mêmes tirées d'une
lecture de Rekordbox 7.2 (`analyzer::WaveCreator`, `BeatAnalyzer`, `LoudViewMaker`). Crédit dans
THIRD_PARTY_NOTICES.md.

Différences avec Sleeve, voulues pour rester en Python sans scipy :
* les filtres (biquads en cascade) sont appliqués par convolution FFT avec leur réponse impulsionnelle
  tronquée à 4 096 échantillons (erreur < 1e-9 de la pleine échelle : les filtres les plus lents, 100 et
  150 Hz, s'éteignent en ≈ 50 ms) ;
* le signal est le mono de FFmpeg ramené à (G + D) / 2 : seuls deux canaux exactement opposés (cas
  « inverted » de Sleeve) diffèrent ;
* le détecteur de crêtes des aperçus bleus (PWAV, PWV2) est rejoué par blocs (mêmes règles : fenêtre de
  0,32 s, décroissance après 1,714 s, une fois par bloc de 1/75 s) au lieu d'échantillon par échantillon.

Le signal arrive par morceaux (`WaveFeed.push`) : un mix d'une heure n'est jamais gardé entier.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import List, Optional, Tuple

import numpy as np

OVERVIEW_COLUMNS = 1200
DETAIL_PER_SECOND = 150
GAIN_FLOOR = 0.8
GAIN_CAP = (3.0, 3.0, 5.0)
ENVELOPE_BACK_MS = (300, 200, 100)
ENVELOPE_DECAY = (0.99, 0.98, 0.97)
WHITENESS = (0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125)
HEIGHTS = np.array([50790.4, 39321.6, 30801.92, 25886.72, 23265.28, 21299.2, 19398.4, 17367.04, 15892.48,
                    14909.44, 13926.4, 12943.36, 11960.32, 10977.28, 9994.24, 9011.2, 8028.16, 7045.12, 6062.08,
                    5079.04, 4096.0, 3112.96, 2195.2], dtype=np.float32)
DOT_HEIGHTS = (20675, 16422, 13045, 10362, 8230, 6538, 5193, 4125, 3276, 2602, 2067, 1642, 1304)
MID_HIGH_CROSSOVER = 7900.0
KERNEL = 4096                  # longueur des réponses impulsionnelles
FFT_SIZE = 32768
SUPPORTED_RATES = (44100, 48000, 88200, 96000)


def supported(rate: int) -> bool:
    return rate in SUPPORTED_RATES


# ------------------------------------------------------------------------------------------- filtres
def _rbj(hz: float, rate: float, low: bool):
    w0 = 2.0 * math.pi * hz / rate
    cos = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * math.sqrt(0.5))
    a0 = 1.0 + alpha
    b = [(1.0 - cos) / 2.0, 1.0 - cos, (1.0 - cos) / 2.0] if low else [(1.0 + cos) / 2.0, -(1.0 + cos), (1.0 + cos) / 2.0]
    return [v / a0 for v in b], [-2.0 * cos / a0, (1.0 - alpha) / a0]


def _butterworth_low(hz: float, rate: float):
    k = math.tan(math.pi * hz / rate)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    return [k * k * norm, 2.0 * k * k * norm, k * k * norm], [2.0 * (k * k - 1.0) * norm, (1.0 - math.sqrt(2.0) * k + k * k) * norm]


def _iir_pass(hz: float, rate: float, q: float, kind: int):
    """`IirPassFilter` de Rekordbox (blue_overview.rs) : 0 passe-bande, 1 passe-haut, 2 passe-bas."""
    angle = hz * 6.28318530717958 / rate
    sin, cos = math.sin(angle), math.cos(angle)
    alpha = sin / (q + q)
    norm = 1.0 / (alpha + 1.0)
    if kind == 0:
        b = [alpha * norm, 0.0, -alpha * norm]
    elif kind == 1:
        b = [(cos * 0.5 + 0.5) * norm, -(cos + 1.0) * norm, (cos * 0.5 + 0.5) * norm]
    else:
        b = [(0.5 - cos * 0.5) * norm, (1.0 - cos) * norm, (0.5 - cos * 0.5) * norm]
    return b, [-2.0 * cos * norm, norm - norm * alpha]


def _impulse(stages, n: int) -> np.ndarray:
    x = [0.0] * n
    x[0] = 1.0
    for b, a in stages:
        y = [0.0] * n
        x1 = x2 = y1 = y2 = 0.0
        b0, b1, b2 = b
        a1, a2 = a
        for i, v in enumerate(x):
            out = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1, y2, y1 = x1, v, y1, out
            y[i] = out
        x = y
    return np.array(x)


@lru_cache(maxsize=4)
def _kernels(rate: int):
    """Spectres (FFT_SIZE) des 14 chaînes de filtres, dans l'ordre :
    0-2 trois bandes (≤ 300, 250-1200, 3000-9000 Hz) ; 3 basses ≤ 400 ; 4-6 détail couleur (≤ 100,
    300-3000, ≥ 1500) ; 7-9 aperçu couleur (≤ 200, 200-2000, ≥ 2000, filtres doublés) ; 10 PWV3 ≤ 150 Hz
    (Butterworth) ; 11-13 aperçus bleus (150 Hz Q 0,9 ; 283-7900 ; ≥ 7900)."""
    r = float(rate)
    lp = lambda hz: _rbj(hz, r, True)          # noqa: E731
    hp = lambda hz: _rbj(hz, r, False)         # noqa: E731
    q = float(np.float32(math.sqrt(0.5)))
    q9 = float(np.float32(0.9))
    chains = [
        [lp(300.0)], [hp(250.0), lp(1200.0)], [hp(3000.0), lp(9000.0)],
        [lp(400.0)],
        [lp(100.0)], [hp(300.0), lp(3000.0)], [hp(1500.0)],
        [lp(200.0), lp(200.0)], [hp(200.0), hp(200.0), lp(2000.0), lp(2000.0)], [hp(2000.0), hp(2000.0)],
        [_butterworth_low(150.0, r)],
        [_iir_pass(150.0, r, q9, 0)] * 2,
        [_iir_pass(283.0, r, q, 1), _iir_pass(MID_HIGH_CROSSOVER, r, q, 2), _iir_pass(283.0, r, q, 1),
         _iir_pass(MID_HIGH_CROSSOVER, r, q, 2)],
        [_iir_pass(MID_HIGH_CROSSOVER, r, q, 1)] * 2,
    ]
    spectra = np.empty((len(chains), FFT_SIZE // 2 + 1), dtype=np.complex64)
    for i, chain in enumerate(chains):
        spectra[i] = np.fft.rfft(_impulse(chain, KERNEL), FFT_SIZE).astype(np.complex64)
    return spectra


# ------------------------------------------------------------------- détecteur de crêtes (aperçus bleus)
class _Peaks:
    """`Peaks::block` de blue_overview.rs, rejoué par segments. `w` = 4 pour les points (PWV2), qui ne
    regardent qu'un échantillon sur 4 (le plus fort des 4)."""

    def __init__(self, rate: int, per_block: int, ratio: float, tiny: bool):
        self.w = 4 if tiny else 1
        self.tiny = tiny
        self.floor = np.float32(327.68 if tiny else 0.01)
        self.ratio = np.float32(ratio)
        self.bu = per_block // self.w                         # bloc, en unités du flux
        self.dw = -(-int(rate * 0.011609977324263039) // self.w)   # unités avant une décroissance
        self.w_end = math.ceil(rate * 0.32 / self.w)            # fin de la fenêtre (exclue), après l'évènement
        self.d_start = int(math.floor(rate * 1.714 / self.w)) + 1
        self.values: List[float] = [0.01]
        self.count = 0
        self.started = False
        self.e = 0                                             # unité du dernier évènement
        self.p = np.float32(0.0)
        self.p_block_end: Optional[np.float32] = None          # P à la dernière fin de bloc depuis le dernier compte
        self.increments: List[int] = []                       # unités où le compte augmente
        self.events: List[int] = []                           # unités des départs / évènements

    def _set(self, at: int, value) -> None:
        if len(self.values) <= at:
            self.values.extend([0.0] * (at + 1 - len(self.values)))
        self.values[at] = float(value)

    def _thr(self, p):
        return p * self.ratio if p > self.floor else self.floor

    def _event(self, g: int, u) -> None:
        if self.p_block_end is not None:
            self._set(self.count, self.p_block_end)
        self._set(self.count - (0 if self.tiny else 1), self.p)
        self.count += 1
        self.increments.append(g)
        self.events.append(g)
        self.e = g
        self.p = np.float32(u)
        self.p_block_end = None

    def _block_end_seen(self, value) -> None:
        self.p_block_end = np.float32(value)

    def feed(self, u: np.ndarray, j0: int) -> None:
        """Unités u (float32), la première à l'indice global j0 ; j0 et len(u) sont des multiples du bloc."""
        n = u.size
        pos = 0
        bu = self.bu
        while pos < n:
            if not self.started:
                hit = np.flatnonzero(u[pos:] > self.floor)
                if hit.size == 0:
                    return
                k = pos + int(hit[0])
                self._set(0, u[k])
                self.count = 1
                self.started = True
                self.increments.append(j0 + k)
                self.events.append(j0 + k)
                self.e, self.p, self.p_block_end = j0 + k, np.float32(u[k]), None
                pos = k + 1
                continue
            g = j0 + pos
            if g < self.e + self.w_end:                         # fenêtre : le pic monte
                stop = min(n, self.e + self.w_end - j0)
                seg = u[pos:stop]
                if self.p > self.floor:
                    run = np.maximum.accumulate(np.maximum(seg, self.p))
                else:
                    run = np.maximum.accumulate(np.where(seg >= self.floor, seg, np.float32(0)))
                    run = np.maximum(run, self.p)
                ends = np.arange(((pos // bu) + 1) * bu, stop + 1, bu)   # fins de bloc (exclues) dans le segment
                if ends.size:
                    self._block_end_seen(run[ends[-1] - pos - 1])
                self.p = np.float32(run[-1])
                pos = stop
                continue
            if g < self.e + self.d_start:                       # entre les deux : seulement un évènement
                stop = min(n, self.e + self.d_start - j0)
                hit = np.flatnonzero(u[pos:stop] >= self._thr(self.p))
                if hit.size:
                    k = pos + int(hit[0])
                    if (k // bu) * bu > pos:                    # une fin de bloc avant l'évènement
                        self._block_end_seen(self.p)
                    self._event(j0 + k, u[k])
                    pos = k + 1
                    continue
                if (stop // bu) * bu > pos:
                    self._block_end_seen(self.p)
                pos = stop
                continue
            pos = self._decay(u, j0, pos)

    def _decay(self, u: np.ndarray, j0: int, pos: int) -> int:
        """Phase de décroissance jusqu'au prochain évènement ou la fin du morceau ; renvoie la position."""
        n, bu, dw = u.size, self.bu, self.dw
        r = np.float32(0.9938303)
        if pos % bu:                                           # début de la phase au milieu d'un bloc
            be = min(n, (pos // bu + 1) * bu)
            for a, b in ((pos, min(be, pos + dw)), (pos + dw, be)):
                if a >= b:
                    continue
                hit = np.flatnonzero(u[a:b] >= self._thr(self.p))
                if hit.size:
                    k = a + int(hit[0])
                    self._event(j0 + k, u[k])
                    return k + 1
                if b == pos + dw:
                    self.p = max(np.float32(self.p * r), self.floor)
            self._block_end_seen(self.p)
            pos = be
        nb = (n - pos) // bu
        if nb <= 0:
            return n
        blocks = u[pos: pos + nb * bu].reshape(nb, bu)
        m1 = blocks[:, :dw].max(axis=1)
        m2 = blocks[:, dw:].max(axis=1) if bu > dw else np.zeros(nb, dtype=np.float32)
        seq = np.empty(nb + 1, dtype=np.float32)
        seq[0] = self.p
        if self.p > self.floor:
            seq[1:] = r
            seq = np.cumprod(seq, dtype=np.float32)
        seq = np.maximum(seq, self.floor)
        thr = np.where(seq > self.floor, seq * self.ratio, self.floor).astype(np.float32)
        hits = np.flatnonzero((m1 >= thr[:-1]) | (m2 >= thr[1:]))
        if hits.size == 0:
            self.p = seq[nb]
            self._block_end_seen(self.p)
            return pos + nb * bu
        k = int(hits[0])
        if k > 0:
            self._block_end_seen(seq[k])
        self.p = seq[k]
        a = pos + k * bu
        hit = np.flatnonzero(u[a: a + dw] >= thr[k])
        if hit.size:
            i = a + int(hit[0])
        else:
            self.p = seq[k + 1]
            i = a + dw + int(np.flatnonzero(u[a + dw: a + bu] >= thr[k + 1])[0])
        self._event(j0 + i, u[i])
        return i + 1

    def finish(self, last_unit: int) -> None:
        """Dernier échantillon (`end`) puis fin du dernier bloc."""
        if self.p_block_end is not None:
            self._set(self.count, self.p_block_end)
        self._set(self.count, self.p)
        self.count += 1
        self.increments.append(last_unit)
        self._set(self.count, self.p)

    def counts(self, blocks: int) -> np.ndarray:
        """Compte à la fin de chaque bloc."""
        ends = (np.arange(blocks) + 1) * self.bu
        return np.searchsorted(np.array(self.increments, dtype=np.int64), ends, side="left").astype(np.int64)

    def started_blocks(self, blocks: int) -> np.ndarray:
        out = np.zeros(blocks, dtype=bool)
        if self.events:
            idx = np.array(self.events, dtype=np.int64) // self.bu
            out[idx[idx < blocks]] = True
        return out


class _Columns:
    def __init__(self):
        self.values = [0.0] * 400
        self.column = 0
        self.consumed = 0
        self.tick = 0
        self.elapsed = np.float32(0.0)
        self.sum = np.float32(0.0)

    def update(self, tick, peaks, count, last, width, inv):
        if self.column >= 400:
            return
        stop = count if last else max(0, count - 1)
        if not last and self.consumed >= stop:
            return
        self.values[self.column] = self.sum
        self.elapsed = np.float32(self.elapsed + np.float32(tick - self.tick))
        for p in range(self.consumed, stop):
            if self.elapsed >= width:
                self.values[self.column] = np.float32(self.sum * np.float32(7500.0) * inv)
                if self.column + 1 < 400:
                    self.values[self.column + 1] = self.values[self.column]
                self.column += 2
                self.elapsed = np.float32(self.elapsed - width)
                while self.elapsed >= width and self.column < 400:
                    self.column += 2
                    self.elapsed = np.float32(self.elapsed - width)
                self.sum = np.float32(0.0)
            if self.column >= 400:
                break
            peak = peaks[p] if p < len(peaks) else 0.0
            self.sum = np.float32(self.sum + (np.float32(0.0) if (p == stop - 1 and last) else np.float32(int(peak))))
            self.values[self.column] = self.sum
        self.tick = tick
        self.consumed = stop


class _DotColumns:
    def __init__(self):
        self.values = [0] * 100
        self.column = 0
        self.consumed = 0
        self.sum = 0

    def update(self, tick, peaks, count, last, width):
        if self.column >= 100:
            return
        nxt = 100 if last else min(tick // width, 99)
        self.values[self.column] = self.sum
        if self.column < nxt:
            self.values[self.column] = self.sum * 75 // (width * 2)      # entiers positifs : // = division de Rust
            self.column = nxt
            self.sum = 0
        if count > self.consumed and tick >= 51 and self.column < 100:
            self.sum += int(peaks[self.consumed]) if self.consumed < len(peaks) else 0
            self.values[self.column] = self.sum
        self.consumed = count


# --------------------------------------------------------------------------------- calcul en flux
class WaveFeed:
    """Reçoit le mono (float32, [-1, 1], (G + D) / 2) à `rate`, par morceaux dans l'ordre ; `finish()`
    donne les sections ANLZ."""

    def __init__(self, rate: int):
        if not supported(rate):
            raise ValueError(f"unsupported rate {rate}")
        self.rate = rate
        self.spectra = _kernels(rate)
        self.pb3 = rate // DETAIL_PER_SECOND                        # PWV3 : 294 à 44,1 kHz
        self.pb = int(rate / 75.0)                                   # aperçus bleus : 588
        ms_base = rate // math.gcd(rate, 1000)
        base = math.lcm(ms_base, self.pb3, self.pb)
        self.hop = ((FFT_SIZE - KERNEL + 1) // base) * base
        self.tail = np.zeros(KERNEL - 1, dtype=np.float32)
        self.pending = np.zeros(0, dtype=np.float32)
        self.frames = 0                                              # échantillons traités
        self.ms_done = 0
        # valeurs par milliseconde
        self.ms: dict = {k: [] for k in ("three0", "three1", "three2", "top", "bottom", "bass", "c0", "c1", "c2",
                                         "d0", "d1", "d2")}
        self.blue_blocks: List[np.ndarray] = []                      # (pic, pic < 150 Hz) par bloc PWV3
        self.raw_sums: List[np.ndarray] = []                         # somme |x| par bloc bleu
        self.block_frames: List[int] = []
        self.peaks = [_Peaks(rate, self.pb, 0.75, False), _Peaks(rate, self.pb, 0.75, False),
                      _Peaks(rate, self.pb, 0.66, False)]
        self.dots = [_Peaks(rate, self.pb, 0.75, True), _Peaks(rate, self.pb, 0.75, True)]

    def push(self, x: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float32)
        if self.pending.size:
            x = np.concatenate([self.pending, x])
        n = (x.size // self.hop) * self.hop
        for a in range(0, n, self.hop):
            self._chunk(x[a:a + self.hop], last=False)
        self.pending = x[n:].copy()

    def _ms_starts(self, s: int, e: int) -> Tuple[np.ndarray, int]:
        """Débuts (relatifs à s) des millisecondes qui commencent dans [s, e)."""
        r = self.rate
        m0 = self.ms_done
        m1 = (e * 1000 + r - 1) // r                       # ms dont le début < e
        i = np.arange(m0, m1, dtype=np.int64)
        starts = (i * r + 999) // 1000 - s
        return starts, m1

    def _chunk(self, x: np.ndarray, last: bool) -> None:
        n = x.size
        if n == 0:
            return
        s = self.frames
        ext = np.concatenate([self.tail, x])
        spec = np.fft.rfft(ext, FFT_SIZE)
        k1 = KERNEL - 1
        ys = [np.fft.irfft(spec * self.spectra[i], FFT_SIZE)[k1:k1 + n] for i in range(14)]
        self.tail = ext[-k1:].copy()
        rb = np.float32(32768.0 / 32767.0)                 # Rekordbox divise par 32 767
        starts, m1 = self._ms_starts(s, s + n)
        self.ms_done = m1

        def peak_ms(y, scale=rb):
            v = np.maximum.reduceat(np.abs(y), starts) * (scale * np.float32(32768.0))
            return np.minimum(np.trunc(v), 32767.0).astype(np.int16)

        for j in range(3):
            self.ms[f"three{j}"].append(peak_ms(ys[j]))
            self.ms[f"d{j}"].append(peak_ms(ys[4 + j]))
        self.ms["bass"].append(peak_ms(ys[3]))
        sx = np.clip(np.trunc(x * (rb * np.float32(32768.0))), -32768, 32767)
        self.ms["top"].append(np.maximum(np.maximum.reduceat(sx, starts), 0).astype(np.int16))
        self.ms["bottom"].append(np.minimum(np.minimum.reduceat(sx, starts), 0).astype(np.int16))
        col = np.vstack([ys[7], ys[8], ys[9]])
        lead = np.argmax(col, axis=0)
        counts = [np.add.reduceat((lead == b).astype(np.int32), starts) for b in range(3)]
        sizes = np.diff(np.append(starts, n))
        for b in range(3):
            pk = np.minimum(np.trunc(np.maximum.reduceat(np.abs(col[b]), starts) * (rb * np.float32(32768.0))), 32767.0)
            val = np.where(pk >= 32767.0, 32767.0, np.trunc(pk.astype(np.float64) * counts[b] / sizes))
            self.ms[f"c{b}"].append(val.astype(np.int16))
        # PWV3 : blocs de rate/150 sur le mix entier
        xi = np.trunc(x.astype(np.float64) * 32768.0)
        y10 = np.minimum(np.abs(np.trunc(ys[10].astype(np.float64) * 32768.0)), 32767.0)
        nb3 = -(-n // self.pb3)
        pad3 = nb3 * self.pb3 - n
        ax = np.pad(np.minimum(np.abs(xi), 32767.0), (0, pad3)).reshape(nb3, self.pb3).max(axis=1)
        al = np.pad(y10, (0, pad3)).reshape(nb3, self.pb3).max(axis=1)
        self.blue_blocks.append(np.vstack([ax, al]).T)
        # aperçus bleus : blocs de rate/75
        mono = (xi / 32768.0).astype(np.float32)
        nb = -(-n // self.pb)
        pad = nb * self.pb - n
        self.raw_sums.append(np.pad(np.abs(mono.astype(np.float64) * 32768.0), (0, pad)).reshape(nb, self.pb).sum(axis=1))
        self.block_frames.extend([self.pb] * (nb - 1) + [self.pb - pad])
        bands = [np.abs(y.astype(np.float32)) * np.float32(32768.0) for y in (ys[11], ys[12], ys[13])]
        j0 = s
        for p, band in zip(self.peaks, bands):
            p.feed(np.pad(band, (0, pad)), j0)
        for p, band in zip(self.dots, bands[:2]):
            b = np.pad(band, (0, pad))
            p.feed(b.reshape(-1, 4).max(axis=1), j0 // 4)
        self.frames += n

    # ----------------------------------------------------------------------------------- sections
    def finish(self):
        if self.pending.size or self.frames == 0:
            self._chunk(self.pending, last=True)
            self.pending = np.zeros(0, dtype=np.float32)
        frames = self.frames
        if frames == 0:
            return None
        ms = -(-frames * 1000 // self.rate)
        per = {}
        for k, parts in self.ms.items():
            arr = np.concatenate(parts).astype(np.int64) if parts else np.zeros(0, dtype=np.int64)
            per[k] = np.pad(arr, (0, max(0, ms - arr.size)))[:ms]
        columns = _grid(ms, OVERVIEW_COLUMNS)
        means, raw, held = _gains(per, columns, ms)
        pwvc = tuple(80 if held[b] < GAIN_FLOOR else int(100.0 * min(held[b], GAIN_CAP[b])) for b in range(3))
        points = _grid(ms, -(-frames * DETAIL_PER_SECOND // self.rate))
        scale = [min(max(raw[b], GAIN_FLOOR), GAIN_CAP[b]) / 256.0 for b in range(3)]
        pwv6 = (np.trunc(means * np.array(scale)).astype(np.int64) & 0xFF).astype(np.uint8).tobytes()
        pwv7 = _detail(per, points, pwvc)
        pwv4 = _colour_preview(per, columns)
        pwv5 = _colour_detail(per, points)
        pwv3 = self._pwv3()
        pwav, pwv2 = self._blue_overview()
        return pwv3, pwv5, pwav, pwv2, pwv4, pwv7, pwv6, pwvc

    def _pwv3(self) -> bytes:
        blocks = np.concatenate(self.blue_blocks)
        total = -(-self.frames // self.pb3)
        blocks = blocks[:total]
        peak, low = blocks[:, 0], blocks[:, 1]
        loudest = max(1.0, float(peak.max()) if peak.size else 1.0)
        share = np.divide(low, peak, out=np.zeros_like(low), where=peak > 0)
        white = np.full(peak.size, 7, dtype=np.int64)
        for i, t in reversed(list(enumerate(WHITENESS))):
            white = np.where(share >= t, i, white)
        white[peak == 0] = 7
        height = np.minimum(_height_of(peak, loudest), 31)
        return ((white << 5) | height).astype(np.uint8).tobytes()

    def _blue_overview(self) -> Tuple[bytes, bytes]:
        nblocks = -(-self.frames // self.pb)
        last_unit = self.frames - 1
        for p in self.peaks:
            p.finish(last_unit)
        for p in self.dots:
            p.finish(last_unit // 4)
        counts = [p.counts(nblocks) for p in self.peaks]
        dcounts = [p.counts(nblocks) for p in self.dots]
        for c, p in zip(counts + dcounts, self.peaks + self.dots):     # le dernier bloc compte l'incrément de fin
            c[-1] = p.count
        low_started = self.peaks[0].started_blocks(nblocks)
        sums = np.concatenate(self.raw_sums)[:nblocks]
        fr = self.block_frames[:nblocks]
        means: List[Optional[float]] = []
        raw_sum, raw_blocks = np.float32(0.0), 0
        for b in range(nblocks):
            raw_sum = np.float32(raw_sum + np.float32(sums[b]))
            raw_blocks += 1
            if raw_blocks >= 9 or low_started[b]:
                means.append(float(np.float32(raw_sum / np.float32(self.pb * raw_blocks))))
                raw_sum, raw_blocks = np.float32(0.0), 0
            else:
                means.append(None)
        frames = self.frames
        total = math.ceil(frames / self.pb)
        inv = np.float32(1.0 / max(total, 1))
        width = np.float32(total * 0.005)
        dot_width = max(frames // self.pb // 100, 1)
        bc = [_Columns() for _ in range(3)]
        dc = [_DotColumns() for _ in range(2)]
        raw_columns = [np.float32(0.0)] * 400
        raw_at, previous, first, started_before = 0, np.float32(0.0), 0, False
        pvals = [p.values for p in self.peaks]
        dvals = [p.values for p in self.dots]
        for at in range(nblocks):
            last = at + 1 == nblocks
            tick = at + 1
            ready = means[at] is not None
            mean = np.float32(means[at] or 0.0)
            nxt = 400 if last else min(int(np.float32(tick) * np.float32(400.0) * inv), 399)
            raw_columns[min(raw_at, 399)] = previous
            if raw_at < nxt:
                raw_columns[raw_at] = np.float32(previous * np.float32(15000.0) * inv)
                for i in range(raw_at + 1, nxt):
                    raw_columns[i] = np.float32(0.0)
                raw_at = nxt
            if ready and raw_at < 400:
                if started_before:
                    raw_columns[first] = np.float32(raw_columns[first] + (mean if raw_at == first else mean * np.float32(15000.0) * inv))
                else:
                    raw_columns[raw_at] = np.float32(raw_columns[raw_at] + mean)
                    first = raw_at
            if raw_at < 400:
                previous = raw_columns[raw_at]
            if low_started[at]:
                started_before = True
            if ready:
                started_before = bool(low_started[at])
            for i in range(3):
                bc[i].update(tick, pvals[i], int(counts[i][at]), last, width, inv)
            for i in range(2):
                dc[i].update(tick, dvals[i], int(dcounts[i][at]), last, dot_width)
        low = np.array(bc[0].values, dtype=np.float32)
        mid = np.array(bc[1].values, dtype=np.float32)
        high = np.array(bc[2].values, dtype=np.float32)

        def db(v):
            with np.errstate(divide="ignore"):
                out = (np.log10(np.maximum(v.astype(np.float64), 1e-30) / 32768.0) * 20.0).astype(np.float32) + np.float32(30.5)
            return np.where(v > 0, out, np.float32(0.0))

        lq, mq, hq = (np.clip(db(v), 0.0, 30.0).astype(np.int64) for v in (low * np.float32(0.5), mid * np.float32(0.25), high))
        colour = np.where(lq < 14, np.where(mq - hq < 4, 5, 4),
                          np.where(mq < hq, np.where(lq <= hq, 3, 2), (lq <= mq).astype(np.int64)))
        level = np.minimum(np.float32(1.0 / 32768.0) * low * np.float32(0.75) + np.float32(0.25), np.float32(1.0)) \
            * np.array(raw_columns, dtype=np.float32)
        ge = level[:, None] >= HEIGHTS[None, :]
        height = np.where(ge.any(axis=1), 25 - np.argmax(ge, axis=1), 2)
        pwav = ((colour << 5) | height).astype(np.uint8).tobytes()
        pwv2 = bytearray()
        for lo, mi in zip(dc[0].values, dc[1].values):
            if lo == 0 and mi == 0:
                pwv2.append(1)
            else:
                pos = next((i for i, t in enumerate(DOT_HEIGHTS) if lo >= t), None)
                pwv2.append(2 if pos is None else 15 - pos)
        return pwav, bytes(pwv2)


# ------------------------------------------------------------------------------- sections, suite
def _grid(ms: int, points: int) -> np.ndarray:
    """(premier, dernier) ms de chaque point : un accumulateur gagne `points` par ms et ferme un point
    chaque fois qu'il atteint `ms` ; plusieurs points fermés sur la même ms répètent sa plage."""
    if ms <= 0 or points <= 0:
        return np.zeros((0, 2), dtype=np.int64)
    k = np.arange(points, dtype=np.int64)
    at = ((k + 1) * ms + points - 1) // points - 1
    prev = np.concatenate([[-1], at[:-1]])
    first = np.where(at != prev, prev + 1, -1)
    first = np.maximum.accumulate(first)
    return np.vstack([first, at]).T


def _range_max(values: np.ndarray, rng: np.ndarray, pad: int, minimum: bool = False) -> np.ndarray:
    """max (ou min) de values sur [premier - pad, dernier + pad] pour chaque plage, pli commencé à 0."""
    v = values
    if pad:
        n = v.size
        acc = v.copy()
        for d in range(1, pad + 1):
            if minimum:
                acc[d:] = np.minimum(acc[d:], v[:n - d])
                acc[:n - d] = np.minimum(acc[:n - d], v[d:])
            else:
                acc[d:] = np.maximum(acc[d:], v[:n - d])
                acc[:n - d] = np.maximum(acc[:n - d], v[d:])
        v = acc
    firsts, lasts = rng[:, 0], rng[:, 1]
    starts, inverse = np.unique(firsts, return_inverse=True)
    red = (np.minimum if minimum else np.maximum).reduceat(v, starts)
    out = red[inverse]
    # plages distinctes = partition des ms : la réduction s'arrête au début de la plage suivante,
    # la dernière va jusqu'au bout ; on la borne à `dernier`
    tail = lasts[-1] + 1
    if tail < v.size and starts.size:
        red_last = (np.minimum if minimum else np.maximum).reduce(v[starts[-1]:tail])
        out = np.where(firsts == starts[-1], red_last, out)
    return np.minimum(out, 0) if minimum else np.maximum(out, 0)


def _gains(per: dict, columns: np.ndarray, ms: int):
    lead = (ms // 1000, (2 * (ms // 1000)) // 3, ms // 3000)
    means = np.zeros((columns.shape[0], 3))
    for b in range(3):
        v = per[f"three{b}"].astype(np.float64)
        cs = np.concatenate([[0.0], np.cumsum(v)])
        frm = columns[:, 0] - lead[b]
        s = cs[columns[:, 1] + 1] - cs[np.maximum(frm, 0)]
        means[:, b] = s / (columns[:, 1] - frm + 1)
    sums = means.sum(axis=0)
    largest = float(sums.max()) if sums.size else 0.0
    equal = np.array([1.0 if sums[b] == 0.0 else largest / sums[b] for b in range(3)])
    tallest = max(float((means * equal).sum(axis=1).max()) if means.size else 0.0, np.finfo(np.float64).tiny)
    with np.errstate(over="ignore", divide="ignore"):
        raw = 32768.0 * equal / tallest
    peak = [float(per[f"three{b}"].max()) if per[f"three{b}"].size else 0.0 for b in range(3)]
    treble = 16384.0 * (1.0 - math.cos(math.pi * peak[2] / 32768.0))
    held = (min(raw[0], 32768.0 / max(peak[0], 1.0)), min(raw[1], 32768.0 / max(peak[1], 1.0)),
            min(raw[2], 32768.0 / max(treble, 1.0)))
    return means, raw, held


def _detail(per: dict, points: np.ndarray, pwvc) -> bytes:
    at = points[:, 1]
    gain = [np.float32(c) * np.float32(0.01) for c in pwvc]
    lv = []
    for b in range(3):
        v = per[f"three{b}"].astype(np.float32)
        back = ENVELOPE_BACK_MS[b]
        dec = np.float32(ENVELOPE_DECAY[b])
        frm = np.maximum(at - back, 0)
        held = v[frm].copy()
        for k in range(1, back + 1):
            idx = frm + k
            ok = idx <= at
            if not ok.any():
                break
            val = v[np.minimum(idx, v.size - 1)]
            new = np.where(val > held, val, val + (held - val) * dec).astype(np.float32)
            held = np.where(ok, new, held)
        lv.append(held)
    out = np.empty((at.size, 3), dtype=np.int64)
    out[:, 0] = np.trunc(lv[0] * gain[0] / np.float32(256.0))
    out[:, 1] = np.trunc(lv[1] * gain[1] / np.float32(256.0))
    out[:, 2] = np.trunc(gain[2] * np.float32(64.0) * (np.float32(1.0) - np.cos(lv[2] * np.float32(math.pi) / np.float32(32768.0))))
    return (out & 0xFF).astype(np.uint8).tobytes()


def _byte(v: np.ndarray) -> np.ndarray:
    return (np.trunc(v / 256.0).astype(np.int64) & 0xFF).astype(np.uint8)


def _colour_preview(per: dict, columns: np.ndarray) -> bytes:
    out = np.empty((columns.shape[0], 6), dtype=np.uint8)
    out[:, 0] = _byte(_range_max(per["top"], columns, 0))
    out[:, 1] = _byte(_range_max(per["bottom"], columns, 0, minimum=True))
    out[:, 2] = _byte(_range_max(per["bass"], columns, 0))
    out[:, 3] = _byte(_range_max(per["c0"], columns, 12))
    out[:, 4] = _byte(_range_max(per["c1"], columns, 1))
    out[:, 5] = _byte(_range_max(per["c2"], columns, 0))
    return out.tobytes()


def _height_of(peak: np.ndarray, loudest: float) -> np.ndarray:
    return np.trunc(np.trunc(peak * 32767.0 / loudest) ** 2 * 2.9327451233027466e-8).astype(np.int64)


def _colour_detail(per: dict, points: np.ndarray) -> bytes:
    top, bottom = per["top"].astype(np.float64), per["bottom"].astype(np.float64)
    mag = np.minimum(np.maximum(np.abs(top), np.abs(bottom)), 32767.0)
    loudest = float(mag.max()) if mag.size else 0.0
    low = _range_max(per["d0"], points, 12).astype(np.float32)
    mid = _range_max(per["d1"], points, 1).astype(np.float32)
    high = _range_max(per["d2"], points, 0).astype(np.float32)
    pt = _range_max(per["top"], points, 0).astype(np.float64)
    pb = _range_max(per["bottom"], points, 0, minimum=True).astype(np.float64)
    peak = np.minimum(np.maximum(np.abs(pt), np.abs(pb)), 32767.0)
    height = np.zeros(peak.size, dtype=np.int64) if loudest < 1.0 else (_height_of(peak, loudest) & 31)
    r, g, b = _detail_colour(low, mid, high)
    return ((r << 13) | (g << 10) | (b << 7) | (height << 2)).astype(">u2").tobytes()


def _detail_colour(low, mid, high):
    f = np.float32
    loudest = np.maximum(np.maximum(low, mid), high)
    zero = loudest == 0
    safe = np.where(zero, f(1.0), loudest)
    blue = np.clip(high * f(255.0) / safe, 0.0, 255.0).astype(np.float32)
    red = (low * f(255.0) / safe).astype(np.float32)
    green = (mid * f(255.0) / safe).astype(np.float32)
    shared = (green * red / f(765.0) * (f(1.0) - blue / f(64.0))).astype(np.float32)
    dark_blue = blue < f(64.0)
    red = np.where(dark_blue, red - shared, red).astype(np.float32)
    green = np.where(dark_blue, green - shared, green).astype(np.float32)
    green = (green + green * f(-0.00234375) * np.minimum(np.maximum(red, blue), f(128.0))).astype(np.float32)
    blue = (f(1.3) * blue).astype(np.float32)
    red = np.where(zero, f(255.0), red)
    green = np.where(zero, f(255.0), green)
    blue = np.where(zero, f(255.0), blue)
    r, g, b = (np.trunc(np.clip(c, 0.0, 255.0)).astype(np.int64) for c in (red, green, blue))
    led = np.maximum(np.maximum(r, g), b)
    dark = (r < 32) & (g < 32) & (b < 32)
    return (np.where(dark, (r == led).astype(np.int64), r >> 5), np.where(dark, (g == led).astype(np.int64), g >> 5),
            np.where(dark, (b == led).astype(np.int64), b >> 5))
