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


MP3_DECODER_DELAY = 529     # échantillons : délai fixe du décodeur MP3 (s'ajoute au délai d'encodeur LAME)


def mp3_priming_samples(path: Union[str, Path]) -> int:
    """Silence d'amorçage d'un MP3 (délai d'encodeur de l'en-tête LAME/Info + 529), en échantillons à
    la fréquence du fichier ; 0 sans en-tête LAME.

    Pourquoi : FFmpeg retire ce silence (lecture « sans blanc »), Rekordbox et les platines NON.
    Mesuré sur 213 sons d'une vraie clé : grilles DJSync à 0,1 ms de Rekordbox en WAV, mais 24,6 ms
    trop tôt en MP3 = 1 105 échantillons (576 + 529) à 44,1 kHz. On rajoute donc ce silence avant
    l'analyse : grille et formes d'onde sont dans la base de temps de la platine."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(256 * 1024)
    except OSError:
        return 0
    pos = 0
    if data[:3] == b"ID3" and len(data) > 10:
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        pos = 10 + size + (10 if data[5] & 0x10 else 0)
    while pos + 4 < len(data) and not (data[pos] == 0xFF and (data[pos + 1] & 0xE0) == 0xE0):
        pos += 1
    if pos + 4 >= len(data):
        return 0
    mpeg1 = ((data[pos + 1] >> 3) & 3) == 3
    mono = (data[pos + 3] >> 6) == 3
    x = pos + 4 + ((17 if mono else 32) if mpeg1 else (9 if mono else 17))
    if data[x:x + 4] not in (b"Xing", b"Info") or x + 8 > len(data):
        return 0
    flags = int.from_bytes(data[x + 4:x + 8], "big")
    y = x + 8 + (4 if flags & 1 else 0) + (4 if flags & 2 else 0) + (100 if flags & 4 else 0) + (4 if flags & 8 else 0)
    if y + 24 > len(data):
        return 0
    d = data[y + 21:y + 24]
    delay = (d[0] << 4) | (d[1] >> 4)
    return delay + MP3_DECODER_DELAY if 0 < delay < 4096 else 0


def peak_level(x: np.ndarray) -> float:
    """max |x| sans copie du signal (np.abs(x) en créerait une de la taille du son)."""
    if x.size == 0:
        return 0.0
    return float(max(x.max(), -x.min()))


def _native_rate(path: Path) -> int:
    try:
        import mutagen

        info = mutagen.File(str(path)).info
        return int(getattr(info, "sample_rate", 0) or 44100)
    except Exception:  # noqa: BLE001
        return 44100


class DecodeError(Exception):
    """Fichier illisible ou FFmpeg introuvable."""


@dataclass
class Decoded:
    samples: np.ndarray       # mono, float32, [-1, 1], à `sr`
    sr: int
    duration: float           # secondes

    @property
    def is_silent(self) -> bool:
        return self.samples.size == 0 or peak_level(self.samples) < 1e-4


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


def _duration_hint(path: Path) -> float:
    try:
        import mutagen

        info = mutagen.File(str(path)).info
        return float(getattr(info, "length", 0.0) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _decode_ffmpeg(path: Path, ffmpeg: str, sr: int) -> np.ndarray:
    """V0.5.0 : lecture en flux directement dans un tableau pré-alloué (durée connue d'avance) —
    plus de copie intégrale du tampon de sortie : le pic mémoire d'un mix d'1 h passe d'environ
    800 Mo à la taille du signal mono (≈ 320 Mo à 22 kHz)."""
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0", "-vn",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                creationflags=_no_window())
    except OSError as exc:
        raise DecodeError(f"FFmpeg could not decode the file: {exc}") from exc
    import threading

    errors: list = []
    reader = threading.Thread(target=lambda: errors.append(proc.stderr.read()), daemon=True)
    reader.start()
    capacity = max(int((_duration_hint(path) + 2.0) * sr), sr * 10)
    out = np.empty(capacity, dtype="<f4")
    filled = 0                                          # octets reçus
    pending = b""
    try:
        while True:
            chunk = proc.stdout.read(1 << 20)
            if not chunk:
                break
            data = pending + chunk
            usable = len(data) - len(data) % 4
            pending = data[usable:]
            n = usable // 4
            start = filled // 4
            if start + n > out.size:
                out = np.resize(out, max(out.size * 3 // 2, start + n))
            out[start:start + n] = np.frombuffer(data, dtype="<f4", count=n)
            filled += usable
        proc.wait(timeout=600)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise DecodeError(f"FFmpeg could not decode the file: {exc}") from exc
    finally:
        proc.stdout.close()
    reader.join(5)
    if proc.returncode != 0 and not filled:
        msg = (errors[0] if errors else b"").decode("utf-8", "replace").strip().splitlines()
        raise DecodeError(f"FFmpeg: {msg[-1] if msg else 'unknown error'}")
    count = filled // 4
    if count < out.size:
        out = out[:count].copy() if out.size - count > sr * 30 else out[:count]
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
        raise DecodeError(f"WAV unreadable without FFmpeg: {exc}") from exc
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
        raise DecodeError(f"{width * 8}-bit WAV not supported without FFmpeg")
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
        raise DecodeError("FFmpeg not found: required to analyse this format (Settings > FFmpeg).")
    samples = samples.astype(np.float32, copy=False)
    np.nan_to_num(samples, copy=False)
    np.clip(samples, -1.0, 1.0, out=samples)
    if ffmpeg and path.suffix.lower() == ".mp3":
        priming = mp3_priming_samples(path)
        if priming:
            pad = int(round(priming * sr / _native_rate(path)))
            samples = np.concatenate([np.zeros(pad, dtype=np.float32), samples])
    return Decoded(samples, sr, samples.size / float(sr))
