"""Gain automatique (1.4.3, C109) : volume égalisé entre les sons, comme le « Auto Gain » de Rekordbox.

* `measure(x, sr)` : sonie intégrée (LUFS, méthode ITU-R BS.1770 : pondération K, blocs de 400 ms recouverts
  à 75 %, portes absolue −70 LUFS et relative −10 LU) et crête (dBFS), sur le signal mono de l'analyse ;
* `gain_db(lufs, peak_db)` : gain qui amène le son à la sonie de référence (TARGET_LUFS), borné à ±12 dB ;
* registre `gain.json` (dossier des réglages) : gain par fichier (nom et taille), écrit par l'analyse, lu par le
  lecteur de DJSync (préécoute et Bibliothèque) quand « Volume égalisé » est actif ; sur l'ordinateur, le gain
  est aussi écrit dans master.db (djmdMixerParam), là où Rekordbox garde le sien.

TARGET_LUFS calé le 19/11/2026 sur les gains « Auto Gain » de Rekordbox (147 sons de l'échantillon du PC fixe,
djmdMixerParam) : Rekordbox amène chaque son à −10,7 LUFS (écart-type 0,5 dB ; même crête mesurée, à 0,0 dB
près). Avec −10,7 : écart moyen 0,35 dB, 96 % des sons à 1 dB près (avec −9 : 1,8 dB, 2 %).
"""
from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)

TARGET_LUFS = -10.7
MAX_GAIN_DB = 12.0


def _k_weight(freqs: np.ndarray) -> np.ndarray:
    """|H(f)|² de la pondération K (étage en plateau +4 dB vers 1,68 kHz, puis passe-haut 38 Hz), réponse
    analogique des filtres de BS.1770."""
    s = 1j * 2 * np.pi * freqs
    w0 = 2 * np.pi * 1681.974450955533
    q = 0.7071752369554196
    g = 10 ** (3.999843853973347 / 20)
    shelf = (g * s ** 2 + math.sqrt(g) * w0 / q * s + w0 ** 2) / (s ** 2 + w0 / q * s + w0 ** 2)
    w1 = 2 * np.pi * 38.13547087602444
    q1 = 0.5003270373238773
    hp = s ** 2 / (s ** 2 + w1 / q1 * s + w1 ** 2)
    return np.abs(shelf * hp) ** 2


def measure(x: np.ndarray, sr: int) -> Tuple[Optional[float], Optional[float]]:
    """(sonie intégrée en LUFS, crête en dBFS) ; (None, None) pour un son trop court ou silencieux."""
    block, hop = int(0.4 * sr), int(0.1 * sr)
    if x.size < block:
        return None, None
    peak = float(max(x.max(), -x.min())) if x.size else 0.0
    n = 1 + (x.size - block) // hop
    weight = _k_weight(np.fft.rfftfreq(block, 1.0 / sr))
    powers = np.empty(n)
    step = 512                                          # blocs traités par paquets (mémoire bornée)
    for a in range(0, n, step):
        b = min(n, a + step)
        idx = np.arange(block)[None, :] + hop * np.arange(a, b)[:, None]
        spec = np.abs(np.fft.rfft(x[idx], axis=1)) ** 2
        spec[:, 1:-1] *= 2.0                            # spectre d'un seul côté
        powers[a:b] = (spec * weight[None, :]).sum(axis=1) / (block * block)
    loud = -0.691 + 10 * np.log10(np.maximum(powers, 1e-20))
    gated = powers[loud > -70.0]
    if gated.size == 0:
        return None, (20 * math.log10(peak) if peak > 0 else None)
    rel = -0.691 + 10 * math.log10(float(gated.mean())) - 10.0
    final = powers[(loud > -70.0) & (loud > rel)]
    lufs = -0.691 + 10 * math.log10(float(final.mean())) if final.size else None
    return lufs, (20 * math.log10(peak) if peak > 0 else None)


def gain_db(lufs: Optional[float], peak_db: Optional[float] = None) -> float:
    if lufs is None:
        return 0.0
    return float(max(-MAX_GAIN_DB, min(MAX_GAIN_DB, TARGET_LUFS - lufs)))


def playback_factor(gain: float, peak_db: Optional[float]) -> float:
    """Facteur appliqué à la lecture : le gain, sans jamais faire saturer la crête du son."""
    factor = 10 ** (gain / 20.0)
    if peak_db is not None:
        factor = min(factor, 10 ** (-peak_db / 20.0) * 0.98)
    return max(0.0, factor)


# ------------------------------------------------------------------------------- registre
_lock = threading.Lock()
_cache: Optional[Dict[str, list]] = None
_store_path: Optional[Path] = None


def _key(path: Path) -> Optional[str]:
    try:
        return f"{path.name.casefold()}|{path.stat().st_size}"
    except OSError:
        return None


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "gain.json"


def use_store(path: Optional[Path]) -> None:
    """Tests : registre dans un autre fichier (None = celui des réglages)."""
    global _store_path, _cache
    with _lock:
        _store_path, _cache = (Path(path) if path else None), None


def _load() -> Dict[str, list]:
    global _cache
    if _cache is None:
        try:
            _cache = {k: list(v) for k, v in json.loads(_file().read_text("utf-8")).items()}
        except (OSError, ValueError, AttributeError, TypeError):
            _cache = {}
    return _cache


def known(path: Union[str, Path]) -> Optional[Tuple[float, Optional[float]]]:
    """(gain dB, crête dBFS) déjà mesurés pour ce fichier, sinon None."""
    key = _key(Path(path))
    if key is None:
        return None
    with _lock:
        v = _load().get(key)
    if not v:
        return None
    return float(v[0]), (None if v[1] is None else float(v[1]))


def remember(path: Union[str, Path], gain: float, peak_db: Optional[float]) -> None:
    key = _key(Path(path))
    if key is None:
        return
    with _lock:
        data = _load()
        data[key] = [round(float(gain), 2), None if peak_db is None else round(float(peak_db), 2)]
        try:
            f = _file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".djsync-tmp")
            tmp.write_text(json.dumps(data), "utf-8")
            tmp.replace(f)
        except OSError as exc:
            log.info("Gain register not saved: %s", exc)
