"""Vraie qualité d'un fichier (1.4.0, C46) : fréquence de coupure du spectre.

Un encodeur avec perte coupe les aigus : un MP3 ou un AAC à 128 kbps s'arrête vers 16-17 kHz, un 192
vers 18,5 kHz, un 256 vers 19,5 kHz, un 320 vers 20-20,5 kHz ; un vrai fichier sans perte monte
jusqu'à 21-22 kHz. Un « FLAC » tiré d'un MP3 garde la coupure du MP3 : c'est ce qui le trahit.

* `measure(path)` : décode 20 s au milieu du son (fréquence d'origine, mono), moyenne le spectre,
  cherche la dernière fréquence encore nettement au-dessus du silence (≈ 0,2 s par son) ;
* `estimate(cutoff, sr)` : débit équivalent (128, 192, 256, 320) ou LOSSLESS ;
* un petit registre (`quality.json` dans le dossier des réglages, hors des caches vidables) garde les
  mesures par fichier (nom et taille : lus sans toucher au disque pour la Bibliothèque) : elles sont faites pendant l'analyse ou depuis l'onglet
  Mauvaise qualité, jamais au moment d'afficher.

Limite connue : un son pauvre en aigus (vieil enregistrement, lo-fi) peut sembler « ≈ 128 » ; c'est
toujours affiché comme une estimation (« ≈ »).
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np

log = logging.getLogger(__name__)

LOSSLESS = 9999                     # « débit » d'un vrai sans perte dans les comparaisons
SLICE = 20.0                        # secondes analysées
N_FFT = 4096
# (coupure minimale en Hz, débit équivalent), du meilleur au moins bon
_CLASSES = ((21000, LOSSLESS), (20000, 320), (19200, 256), (17800, 192), (0, 128))


def _decode_slice(path: Path, ffmpeg: str, sr: int, start: float) -> np.ndarray:
    from .decode import _no_window

    cmd = [ffmpeg, "-nostdin", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{SLICE:.0f}", "-i", str(path),
           "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         timeout=60, creationflags=_no_window(), check=False)
    return np.frombuffer(out.stdout, dtype=np.float32)


def cutoff_of(x: np.ndarray, sr: int) -> Optional[int]:
    """Fréquence de coupure (Hz) d'un signal mono, None si trop court ou silencieux."""
    if x.size < N_FFT * 4:
        return None
    hop = N_FFT // 2
    n = 1 + (x.size - N_FFT) // hop
    idx = np.arange(N_FFT)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(N_FFT)[None, :].astype(np.float32)
    power = (np.abs(np.fft.rfft(frames, axis=1)) ** 2).mean(axis=0)
    db = 10 * np.log10(power + 1e-20)
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    band = (freqs >= 1000) & (freqs <= 8000)
    ref = float(np.median(db[band]))
    if ref < -100:                                     # silence
        return None
    k = max(1, int(round(300 / (sr / N_FFT))))           # lissage sur ~300 Hz
    padded = np.pad(db, (k // 2, k - 1 - k // 2), mode="edge")   # bords : pas de zéros (0 dB) ajoutés
    smooth = np.convolve(padded, np.ones(k) / k, mode="valid")
    above = np.nonzero((smooth > ref - 75) & (freqs >= 2000))[0]
    if above.size == 0:
        return None
    top = int(above[-1])
    return int(min(freqs[top], sr / 2))


def measure(path: Union[str, Path], ffmpeg_location: Optional[str] = None,
            duration: float = 0.0, native_sr: int = 0) -> Optional[int]:
    """Coupure mesurée sur 20 s au milieu du son (None si impossible)."""
    from .decode import _native_rate, find_ffmpeg

    ffmpeg = find_ffmpeg(ffmpeg_location)
    if not ffmpeg:
        return None
    path = Path(path)
    sr = native_sr or _native_rate(path) or 44100
    sr = min(sr, 96000)
    if not duration:
        try:
            import mutagen

            duration = float(mutagen.File(str(path)).info.length or 0)
        except Exception:  # noqa: BLE001
            duration = 0.0
    start = max(0.0, duration / 2 - SLICE / 2) if duration > SLICE else 0.0
    try:
        x = _decode_slice(path, ffmpeg, sr, start)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("Spectrum not measured (%s): %s", path.name, exc)
        return None
    return cutoff_of(x, sr)


def estimate(cutoff: Optional[int], sr: int = 44100) -> int:
    """Débit équivalent d'après la coupure : 128, 192, 256, 320 ou LOSSLESS ; 0 si inconnu. Un fichier à
    moins de 44,1 kHz ne peut pas monter à 21 kHz : on compare à sa fréquence de Nyquist."""
    if not cutoff:
        return 0
    if sr and sr < 44100 and cutoff >= 0.95 * sr / 2:
        return LOSSLESS
    return next(kbps for limit, kbps in _CLASSES if cutoff >= limit)


# ------------------------------------------------------------- registre des mesures
_lock = threading.Lock()
_cache: Optional[Dict[str, int]] = None
_store_path: Optional[Path] = None


def _key(path: Path) -> Optional[str]:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return f"{path.name.casefold()}|{size}"


def lookup(name: str, size: int) -> Optional[int]:
    """Comme `known`, sans accès au disque : nom du fichier et taille connus (base de la bibliothèque)."""
    if not name or not size:
        return None
    with _lock:
        return _load().get(f"{name.casefold()}|{int(size)}")


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "quality.json"


def use_store(path: Optional[Path]) -> None:
    """Tests : registre dans un autre fichier (None = celui des réglages)."""
    global _store_path, _cache
    with _lock:
        _store_path, _cache = (Path(path) if path else None), None


def _load() -> Dict[str, int]:
    global _cache
    if _cache is None:
        try:
            _cache = {k: int(v) for k, v in json.loads(_file().read_text("utf-8")).items()}
        except (OSError, ValueError, AttributeError):
            _cache = {}
    return _cache


def known(path: Union[str, Path]) -> Optional[int]:
    """Coupure déjà mesurée pour ce fichier (None sinon) ; ne décode rien."""
    key = _key(Path(path))
    if key is None:
        return None
    with _lock:
        return _load().get(key)


def remember(path: Union[str, Path], cutoff: Optional[int]) -> None:
    if not cutoff:
        return
    key = _key(Path(path))
    if key is None:
        return
    with _lock:
        data = _load()
        data[key] = int(cutoff)
        try:
            f = _file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".djsync-tmp")
            tmp.write_text(json.dumps(data), "utf-8")
            tmp.replace(f)
        except OSError as exc:
            log.info("Quality register not saved: %s", exc)


def measure_and_remember(path: Union[str, Path], ffmpeg_location: Optional[str] = None,
                         duration: float = 0.0) -> Optional[int]:
    c = known(path)
    if c is None:
        c = measure(path, ffmpeg_location, duration)
        remember(path, c)
    return c
