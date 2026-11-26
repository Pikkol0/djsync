"""1.4.4 (C108) : énergie d'un son, de 1 (calme) à 10 (explosif), comme le niveau d'énergie de Mixed In Key.

Calculée à l'analyse à partir de ce qu'elle mesure déjà : forme d'onde 3 bandes (PWV7, 150 points par seconde :
basses, médiums, aigus), sonie (C109) et tempo. Aucun décodage ni dépendance en plus : quelques opérations numpy
sur ~36 000 points pour un son de 4 min (moins d'une milliseconde par minute de son).

Cinq mesures entre 0 et 1, pondérées :
  * sonie (LUFS intégrés : -22 -> 0, -6 -> 1) ;
  * densité d'attaques (montées nettes de la forme d'onde par seconde : 0,5 -> 0, 7 -> 1) ;
  * tempo (70 -> 0, 170 BPM -> 1) ;
  * percussivité (variation moyenne de la forme d'onde rapportée à son niveau : une nappe tenue reste basse) ;
  * part des basses et des aigus (kick, charleston) face aux médiums.

Registre « energy.json » (comme gain.json, C109) : clé « nom du fichier|taille » -> [énergie calculée, énergie
choisie à la main (0 : automatique)]. Rekordbox n'a pas de champ énergie : rien n'est écrit dans ses bases, sauf
l'option « énergie dans le commentaire » (Paramètres ▸ Analyse).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)

RATE = 150.0                        # points par seconde de PWV7
WEIGHTS = (0.25, 0.25, 0.20, 0.15, 0.15)   # sonie, attaques, tempo, percussivité, basses + aigus


def _ramp(v: float, lo: float, hi: float) -> float:
    return float(min(1.0, max(0.0, (v - lo) / (hi - lo))))


def features(band_detail: bytes, bpm: float, lufs: Optional[float]) -> Optional[Dict[str, float]]:
    """Mesures (0-1) tirées de la forme d'onde 3 bandes, du tempo et de la sonie ; None sans forme d'onde."""
    if not band_detail or len(band_detail) < 3 * int(RATE * 5):
        return None
    w = np.frombuffer(band_detail[:len(band_detail) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.float32) / 127.0
    full = w.sum(axis=1)
    top = float(np.percentile(full, 95))
    if top <= 0.02:
        return None
    active = full > 0.1 * top                              # silences du début et de la fin écartés
    if active.sum() < RATE * 5:
        return None
    env = full / top
    rise = np.diff(env, prepend=env[:1])
    # attaque : montée nette (au moins 12 % du niveau haut en un point) qui est un maximum local de la montée
    peaks = (rise[1:-1] > 0.12) & (rise[1:-1] >= rise[:-2]) & (rise[1:-1] > rise[2:])
    seconds = float(active.sum()) / RATE
    rate = float(peaks.sum()) / max(1.0, seconds)
    level = float(env[active].mean())
    perc = float(np.abs(rise)[active].mean()) / max(0.05, level)
    tot = w[active].sum(axis=0)
    share = float((tot[0] + tot[2]) / max(1e-6, float(tot.sum())))
    return {"loud": _ramp(lufs, -22.0, -6.0) if lufs is not None else 0.5,
            "attacks": _ramp(rate, 0.5, 7.0),
            "tempo": _ramp(bpm, 70.0, 170.0) if bpm and bpm > 0 else 0.3,
            "perc": _ramp(perc, 0.02, 0.30),
            "share": _ramp(share, 0.35, 0.75)}


def compute(band_detail: bytes, bpm: float, lufs: Optional[float]) -> Optional[int]:
    """Énergie de 1 à 10, None si la forme d'onde manque (son trop court ou silencieux)."""
    f = features(band_detail, bpm, lufs)
    if f is None:
        return None
    score = sum(wt * f[k] for wt, k in zip(WEIGHTS, ("loud", "attacks", "tempo", "perc", "share")))
    return int(min(10, max(1, round(1 + 9 * score))))


# ------------------------------------------------------------------------------- commentaire (option)
_PREFIX = re.compile(r"^E(10|[1-9])(?: |$)")


def strip_prefix(comment: str) -> str:
    """Commentaire sans le préfixe « E7 » écrit par l'option."""
    return _PREFIX.sub("", comment or "", count=1)


def with_prefix(comment: str, energy: int) -> str:
    """« E7 » devant le commentaire, sans rien en effacer (ancien préfixe remplacé) ; energy 0 : préfixe retiré."""
    rest = strip_prefix(comment or "")
    if not energy:
        return rest
    return f"E{int(energy)} {rest}".rstrip() if rest else f"E{int(energy)}"


# ------------------------------------------------------------------------------- registre
_lock = threading.Lock()
_cache: Optional[Dict[str, list]] = None
_store_path: Optional[Path] = None


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "energy.json"


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


def _save(data: Dict[str, list]) -> None:
    try:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".djsync-tmp")
        tmp.write_text(json.dumps(data), "utf-8")
        tmp.replace(f)
    except OSError as exc:
        log.info("Energy register not saved: %s", exc)


def _path_key(path: Path) -> Optional[str]:
    try:
        return f"{path.name.casefold()}|{path.stat().st_size}"
    except OSError:
        return None


def lookup(name: str, size: int) -> Optional[Tuple[int, int]]:
    """(énergie calculée, énergie choisie à la main) ; 0 : inconnue / automatique ; None : rien de gardé."""
    if not name or not size:
        return None
    with _lock:
        v = _load().get(f"{name.casefold()}|{int(size)}")
    if not v:
        return None
    try:
        return int(v[0] or 0), int(v[1] or 0) if len(v) > 1 else 0
    except (TypeError, ValueError):
        return None


def value(name: str, size: int) -> int:
    """Énergie affichée : celle choisie à la main, sinon celle de l'analyse ; 0 si inconnue."""
    v = lookup(name, size)
    return (v[1] or v[0]) if v else 0


def remember(path: Union[str, Path], energy: Optional[int]) -> None:
    """Énergie calculée à l'analyse ; celle choisie à la main reste."""
    if not energy:
        return
    key = _path_key(Path(path))
    if key is None:
        return
    with _lock:
        data = _load()
        old = data.get(key) or [0, 0]
        new = [int(energy), int(old[1] if len(old) > 1 else 0)]
        if old != new:
            data[key] = new
            _save(data)


def set_manual(name: str, size: int, energy: int) -> bool:
    """Énergie choisie à la main (1-10), 0 : de nouveau celle de l'analyse."""
    if not name or not size:
        return False
    energy = int(energy) if 1 <= int(energy) <= 10 else 0
    key = f"{name.casefold()}|{int(size)}"
    with _lock:
        data = _load()
        old = data.get(key) or [0, 0]
        new = [int(old[0] or 0), energy]
        if new == [0, 0]:
            data.pop(key, None)
        else:
            data[key] = new
        _save(data)
    return True
