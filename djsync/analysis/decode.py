"""Décodage audio -> échantillons mono float32 à fréquence fixe.

FFmpeg (déjà requis par DJSync pour le téléchargement) fait tout le travail : il lit m4a/mp3/flac/
aiff/wav et rééchantillonne. Aucune bibliothèque audio lourde n'est embarquée. Les .wav PCM se
décodent aussi sans FFmpeg (module `wave` standard), ce qui sert aux tests et aux machines sans FFmpeg.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np

ANALYSIS_SR = 22050          # suffisant pour BPM/tonalité/formes d'onde (bande utile < 11 kHz)


class DecodeError(Exception):
    """Fichier illisible ou FFmpeg introuvable."""


@dataclass
class Decoded:
    samples: np.ndarray       # mono, float32, [-1, 1], à `sr`
    sr: int
    duration: float           # secondes

    @property
    def is_silent(self) -> bool:
        return self.samples.size == 0 or float(np.max(np.abs(self.samples))) < 1e-4


def find_ffmpeg(location: Optional[str] = None) -> Optional[str]:
    """Même règle que le reste de DJSync : dossier des Paramètres, sinon PATH (outils portables inclus)."""
    if location:
        for name in ("ffmpeg.exe", "ffmpeg"):
            cand = Path(location) / name
            if cand.is_file():
                return str(cand)
    return shutil.which("ffmpeg")


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _decode_ffmpeg(path: Path, ffmpeg: str, sr: int) -> np.ndarray:
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0", "-vn",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600,
                              creationflags=_no_window())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DecodeError(f"FFmpeg n'a pas pu décoder le fichier : {exc}") from exc
    if proc.returncode != 0 and not proc.stdout:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise DecodeError(f"FFmpeg : {msg[-1] if msg else 'erreur inconnue'}")
    raw = proc.stdout
    usable = len(raw) - len(raw) % 4
    out = np.frombuffer(raw, dtype="<f4", count=usable // 4).copy()   # une seule copie (tampon libéré ensuite)
    del raw, proc
    return out


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Rééchantillonnage simple (filtre passe-bas par moyenne glissante + interpolation linéaire) :
    largement suffisant pour l'analyse, inutile pour l'écoute."""
    if src == dst or x.size == 0:
        return x
    if src > dst:
        k = max(1, int(round(src / dst)))
        if k > 1:
            kernel = np.ones(k, dtype=np.float32) / k
            x = np.convolve(x, kernel, mode="same").astype(np.float32)
    n_out = int(round(x.size * dst / src))
    pos = np.arange(n_out, dtype=np.float64) * (src / dst)
    return np.interp(pos, np.arange(x.size), x).astype(np.float32)


def _decode_wav(path: Path, sr: int) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError, OSError) as exc:
        raise DecodeError(f"WAV illisible sans FFmpeg : {exc}") from exc
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        data = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise DecodeError(f"WAV {width * 8} bits non géré sans FFmpeg")
    if ch > 1:
        data = data[: data.size - data.size % ch].reshape(-1, ch).mean(axis=1)
    return _resample(data, rate, sr)


def decode(path: Union[str, Path], ffmpeg_location: Optional[str] = None, sr: int = ANALYSIS_SR) -> Decoded:
    """Décode tout le fichier en mono à `sr` Hz."""
    path = Path(path)
    ffmpeg = find_ffmpeg(ffmpeg_location)
    if ffmpeg:
        try:
            samples = _decode_ffmpeg(path, ffmpeg, sr)
        except DecodeError:
            if path.suffix.lower() != ".wav":
                raise
            samples = _decode_wav(path, sr)
    elif path.suffix.lower() == ".wav":
        samples = _decode_wav(path, sr)
    else:
        raise DecodeError("FFmpeg introuvable : nécessaire pour analyser ce format (Paramètres > FFmpeg).")
    samples = samples.astype(np.float32, copy=False)
    np.nan_to_num(samples, copy=False)
    np.clip(samples, -1.0, 1.0, out=samples)
    return Decoded(samples, sr, samples.size / float(sr))
