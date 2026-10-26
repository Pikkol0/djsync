"""Morceaux SYNTHÉTIQUES à BPM, premier temps, temps fort et tonalité connus (vérité terrain exacte).

Batterie (kick sur chaque temps, plus fort sur le 1, caisse claire sur 2 et 4, charleston en croches)
+ accords avec harmoniques et basse. Progressions choisies sans ambiguïté de tonique (V majeur en
mineur : Am-F-E-Am, et non Am-F-C-G qui est aussi vi-IV-I-V de Do majeur).
"""
from __future__ import annotations

import io
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

SR = 44100
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _tone(f: float, dur: float) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    y = sum((0.6 ** k) * np.sin(2 * np.pi * f * (k + 1) * t) for k in range(5))
    return y * np.minimum(1, t / 0.01) * np.exp(-t * 1.5)


def _chord(root: str, minor: bool, dur: float) -> np.ndarray:
    r = NOTE[root]
    notes = [r + i - 9 for i in ((0, 3, 7) if minor else (0, 4, 7))]
    return sum(_tone(440 * 2 ** (n / 12), dur) for n in notes) + 0.8 * _tone(440 * 2 ** ((r - 9 - 24) / 12), dur)


def song(bpm: float, first: float, duration: float, chords: Sequence[str], minors: Sequence[bool],
         bpm_end: Optional[float] = None, beats_out: Optional[list] = None) -> np.ndarray:
    """bpm_end : tempo final (accélération linéaire, comme un batteur live) ; beats_out reçoit les
    instants exacts des temps (vérité terrain)."""
    rng = np.random.default_rng(7)
    t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-t * 30)) / SR) * np.exp(-t * 12)
    ts = np.arange(int(0.15 * SR)) / SR
    snare = rng.normal(0, 0.5, ts.size) * np.exp(-ts * 25)
    th = np.arange(int(0.05 * SR)) / SR
    hat = 0.25 * np.diff(rng.normal(0, 1, th.size), prepend=0) * np.exp(-th * 80)
    y = np.zeros(int(duration * SR) + SR)

    def add(sig: np.ndarray, at: float) -> None:
        i = int(round(at * SR))
        if 0 <= i < y.size:
            e = min(y.size, i + sig.size)
            y[i:e] += sig[: e - i]

    beat, k, c, at = 60.0 / bpm, 0, 0, first
    while at < duration:
        if bpm_end is not None:
            beat = 60.0 / (bpm + (bpm_end - bpm) * at / duration)
        if beats_out is not None:
            beats_out.append(at)
        add(kick * (1.0 if k % 4 == 0 else 0.7), at)
        if k % 4 in (1, 3):
            add(snare, at)
        add(hat, at)
        add(hat, at + beat / 2)
        if k % 4 == 0:
            add(0.25 * _chord(chords[c % len(chords)], minors[c % len(minors)], beat * 4), at)
            c += 1
        k += 1
        at += beat
    y = y[: int(duration * SR)]
    return (y / np.max(np.abs(y)) * 0.9).astype(np.float32)


def write_wav(path: Path, y: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.repeat((np.clip(y, -1, 1) * 32767).astype("<i2"), 2).tobytes())
    return path


def cover_png(color=(200, 40, 120), size=(300, 200)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def write_m4a(path: Path, y: np.ndarray, cover: Optional[bytes] = None) -> Path:
    """AAC/m4a (comme les téléchargements DJSync), pochette intégrée facultative. Nécessite FFmpeg."""
    tmp = write_wav(path.with_suffix(".tmp.wav"), y)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-c:a", "aac", "-b:a", "160k", str(path)],
                   check=True)
    tmp.unlink()
    if cover:
        from mutagen.mp4 import MP4, MP4Cover

        mp4 = MP4(str(path))
        if mp4.tags is None:
            mp4.add_tags()
        mp4["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_PNG)]
        mp4.save()
    return path


def groove(bpm: float, first: float, duration: float, style: str, seed: int = 3) -> np.ndarray:
    """1.3.0 (B11) : batteries où l'attaque la plus forte n'est PAS sur le temps.
    house : kick sur chaque temps, clap 2 et 4, charleston OUVERT très fort sur les contretemps, basse
    sur les contretemps ; trap : kick syncopé (1, 2&, 3&), clap sur le 3, charlestons en doubles
    croches, 808 tenue ; hiphop : kick 1 et 3&, caisse claire 2 et 4, charleston en croches.
    Temps fort (1) = `first`."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-t * 30)) / SR) * np.exp(-t * 12)
    tc = np.arange(int(0.18 * SR)) / SR
    clap = rng.normal(0, 0.6, tc.size) * np.exp(-tc * 22)
    clap = np.convolve(clap, [1, -0.9], mode="same")                     # surtout des aigus/médiums
    to = np.arange(int(0.22 * SR)) / SR
    ohat = np.diff(rng.normal(0, 1, to.size), n=3, prepend=[0, 0, 0]) * 0.35 * np.exp(-to * 16)   # aigus
    th = np.arange(int(0.04 * SR)) / SR
    chat = 0.3 * np.diff(rng.normal(0, 1, th.size), prepend=0) * np.exp(-th * 90)
    y = np.zeros(int(duration * SR) + SR)

    def add(sig: np.ndarray, at: float, gain: float = 1.0) -> None:
        i = int(round(at * SR))
        if 0 <= i < y.size:
            e = min(y.size, i + sig.size)
            y[i:e] += gain * sig[: e - i]

    def bass(f: float, dur: float) -> np.ndarray:
        tb = np.arange(int(dur * SR)) / SR
        return np.sin(2 * np.pi * f * tb) * np.minimum(1, tb / 0.005) * np.exp(-tb * 6) * np.minimum(1, (dur - tb) / 0.02)

    beat = 60.0 / bpm
    k, at = 0, first
    while at < duration:
        n = k % 4
        if style == "house":
            add(kick, at)
            if n in (1, 3):
                add(clap, at, 0.6)
            add(ohat, at + beat / 2, 1.6)
            add(bass(55.0 * (1.5 if n == 2 else 1.0), beat * 0.45), at + beat / 2, 0.8)
            add(chat, at, 0.4)
        elif style == "trap":
            if n == 0:
                add(kick, at)
                add(bass(49.0, beat * 1.8), at, 0.9)
            if n == 1:
                add(kick, at + beat / 2, 0.9)
            if n == 2:
                add(clap, at, 1.0)
                add(kick, at + beat / 2, 0.8)
            for s in range(4):
                add(chat, at + s * beat / 4, 1.2 if s % 2 else 1.6)
        else:  # hiphop
            if n == 0:
                add(kick, at)
            if n == 2:
                add(kick, at + beat / 2, 0.9)
            if n in (1, 3):
                add(clap, at, 0.9)
            add(chat, at, 1.0)
            add(chat, at + beat / 2, 1.3)
        k += 1
        at += beat
    y = y[: int(duration * SR)]
    return (y / np.max(np.abs(y)) * 0.9).astype(np.float32)
