"""1.4.4 (B131) : analyse d'un passage de la grille (Grille et cues ▸ Tempo ▸ « Analyser ce passage »).

Sur la plage du passage seulement (décodée à part pour un long son) :
* tempos locaux (`tempo_profile.local_tempi`) → palier (médiane) ou rampe (droite ajustée, gardée si l'écart
  début-fin atteint 3 % et que la droite colle mieux qu'un palier) ;
* phase calée sur les attaques (temps contre contretemps : les basses tranchent, comme pour la grille fixe) ;
* 1er temps de la mesure par la méthode de B125 (`tempo._downbeat_vote`) limitée à la plage ;
* garde-fous : passage trop court (< 8 mesures), temps trop flous (forme « libre »), rapport ×2, ×½, ×3/2, ×2/3
  avec un passage voisin (erreur d'octave probable : refusé), tempos hors 40-300.
Sans Qt : appelé dans un fil de fond par l'interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from . import tempo as T
from . import tempo_profile as TP

MIN_BARS = 8
RAMP_MIN = 0.03                 # écart début-fin d'une rampe
OCTAVES = (2.0, 0.5, 1.5, 2.0 / 3.0)
OCTAVE_TOL = 0.03
BPM_LO, BPM_HI = 40.0, 300.0


@dataclass
class SegmentResult:
    shape: str = "step"         # step | ramp | free
    bpm: float = 0.0            # tempo (de début pour une rampe)
    bpm_end: float = 0.0        # tempo de fin (rampe), sinon = bpm
    first_ms: int = 0           # 1er temps du passage (ms, depuis le début du son)
    number: int = 1             # numéro 1-4 de ce temps dans la mesure
    note: str = ""              # "" | "short" | "weak" | "octave" | "range"

    @property
    def ok(self) -> bool:
        return self.note in ("", "weak") and self.bpm > 0


def too_short(start_s: float, end_s: float, bpm: float) -> bool:
    return bpm <= 0 or (end_s - start_s) < MIN_BARS * 4 * 60.0 / bpm


def octave_of(bpm: float, neighbours: Sequence[float]) -> bool:
    """Rapport ×2, ×½, ×3/2, ×2/3 avec un passage voisin (à 3 % près)."""
    for nb in neighbours:
        if nb and bpm:
            r = bpm / nb
            if any(abs(r / o - 1.0) <= OCTAVE_TOL for o in OCTAVES):
                return True
    return False


def _beat_times(shape: str, phase: float, span: float, b0: float, b1: float) -> np.ndarray:
    if shape == "ramp":
        return np.array(TP.ramp_times(phase, span, b0 + (b1 - b0) * phase / max(1e-6, span), b1))
    return np.arange(phase, span, 60.0 / b0)


def _score(env: np.ndarray, times: np.ndarray, sr: int) -> float:
    if times.size == 0:
        return 0.0
    f = T._frame_of(times, sr)
    i = np.clip(np.round(f).astype(int), 0, env.size - 1)
    lo, hi = np.clip(i - 1, 0, env.size - 1), np.clip(i + 1, 0, env.size - 1)
    return float(np.mean(np.maximum.reduce([env[lo], env[i], env[hi]])))


def analyze(samples: np.ndarray, sr: int, start_s: float, end_s: float, ref_bpm: float,
            neighbours: Sequence[float] = (), allow_ramp: bool = True) -> SegmentResult:
    """Analyse de `samples` (le passage seul, qui commence à `start_s` dans le son)."""
    span = float(end_s - start_s)
    if too_short(start_s, end_s, ref_bpm):
        return SegmentResult(bpm=ref_bpm, bpm_end=ref_bpm, first_ms=int(round(start_s * 1000)), note="short")
    env, benv, fps = T.onset_envelopes(np.asarray(samples, dtype=np.float32), sr)
    win = float(min(12.0, max(4.0, span / 3.0)))
    tempi, strength = TP.local_tempi(env, fps, ref_bpm, win=win, hop=2.0)
    centres = np.arange(tempi.size) * 2.0 + win / 2.0
    ok = ~np.isnan(tempi)
    if ok.sum() < 2 or (strength.size and float(np.median(strength)) < TP.MIN_STRENGTH):
        return SegmentResult("free", ref_bpm, ref_bpm, int(round(start_s * 1000)), 1, "weak")
    v, c = tempi[ok], centres[ok]
    med = float(np.median(v))
    shape, b0, b1 = "step", med, med
    if allow_ramp and v.size >= 3:
        a, b = np.polyfit(c, v, 1)
        lin = a * c + b
        res_l = float(np.mean(np.abs(v - lin)))
        res_c = float(np.mean(np.abs(v - med)))
        s0, s1 = float(b), float(a * span + b)
        if abs(s1 - s0) / max(1e-6, s0) >= RAMP_MIN and res_l < 0.8 * res_c:
            shape, b0, b1 = "ramp", s0, s1
    if not all(BPM_LO <= x <= BPM_HI for x in (b0, b1)):
        return SegmentResult(shape, b0, b1, int(round(start_s * 1000)), 1, "range")
    # tempo d'un palier affiné : autocorrélation de toute la plage autour de la médiane
    if shape == "step":
        smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
        b0 = b1 = float(T._refine_align(smooth, fps, med)[0])
    if octave_of(b0, neighbours):
        return SegmentResult(shape, b0, b1, int(round(start_s * 1000)), 1, "octave")
    period = 60.0 / b0
    if shape == "step":       # même calage (temps / contretemps) que la grille d'un son entier
        best = float(T._passage_phase(np.asarray(samples, dtype=np.float32), sr, env, benv, fps, b0, 0, env.size))
        best %= period
        return _finish(samples, sr, benv, shape, best, span, start_s, b0, b1)
    # rampe : 1er temps entre 0 et une période, pas de 5 ms ; temps contre contretemps : les basses tranchent
    best, best_s = 0.0, -1.0
    for ph in np.arange(0.0, period, 0.005):
        sc = _score(env, _beat_times(shape, ph, span, b0, b1), sr)
        if sc > best_s:
            best, best_s = float(ph), sc
    off = (best + period / 2) % period
    if _score(benv, _beat_times(shape, off, span, b0, b1), sr) > 1.15 * _score(benv, _beat_times(shape, best, span,
                                                                                                    b0, b1), sr):
        best = off
    return _finish(samples, sr, benv, shape, best, span, start_s, b0, b1)


def _finish(samples: np.ndarray, sr: int, benv: np.ndarray, shape: str, best: float, span: float, start_s: float,
            b0: float, b1: float) -> SegmentResult:
    times = _beat_times(shape, best, span, b0, b1)
    if shape == "ramp" and times.size:              # tempo de début au 1er temps posé
        b0 = b0 + (b1 - b0) * best / max(1e-6, span)
    number = 1
    if times.size >= 8:
        try:
            shift = T._downbeat_vote(np.asarray(samples, dtype=np.float32), sr, benv, times)[0]
            number = ((0 - int(shift)) % 4) + 1
        except Exception:  # noqa: BLE001 - 1er temps : simple aide
            number = 1
    return SegmentResult(shape, round(b0, 2), round(b1, 2), int(round((start_s + best) * 1000)), number)


def decode_range(path: str, start_s: float, end_s: float, ffmpeg_location: Optional[str] = None,
                 sr: int = 22050) -> np.ndarray:
    """La plage [start_s, end_s] seule (A09 : un passage d'un long set sans décoder tout le son) ; repli : tout
    décoder puis couper."""
    import subprocess

    from . import decode as D

    ffmpeg = D.find_ffmpeg(ffmpeg_location)
    if ffmpeg:
        cmd = [ffmpeg, "-v", "error", "-nostdin", "-ss", f"{max(0.0, start_s):.3f}", "-t",
               f"{max(0.1, end_s - start_s):.3f}", "-i", str(path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar",
               str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
        try:
            out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                 creationflags=D._no_window(), timeout=300, check=False)
            if out.returncode == 0 and out.stdout:
                data = out.stdout[: len(out.stdout) - len(out.stdout) % 4]
                return np.frombuffer(data, dtype="<f4").copy()
        except (OSError, subprocess.SubprocessError):
            pass
    dec = D.decode(path, ffmpeg_location, sr)
    a, b = int(max(0.0, start_s) * dec.sr), int(max(0.0, end_s) * dec.sr)
    return np.asarray(dec.samples[a:b], dtype=np.float32)


def analyze_file(path: str, start_s: float, end_s: float, ref_bpm: float, neighbours: Sequence[float] = (),
                 ffmpeg_location: Optional[str] = None, allow_ramp: bool = True) -> SegmentResult:
    if too_short(start_s, end_s, ref_bpm):
        return SegmentResult(bpm=ref_bpm, bpm_end=ref_bpm, first_ms=int(round(start_s * 1000)), note="short")
    x = decode_range(path, start_s, end_s, ffmpeg_location)
    return analyze(x, 22050, start_s, end_s, ref_bpm, neighbours, allow_ramp)


__all__: List[str] = ["SegmentResult", "analyze", "analyze_file", "decode_range", "octave_of", "too_short"]
