"""1.4.3 (C69) : sons dont le tempo change, et de quelle façon (« profil de tempo »).

Mesuré pendant l'analyse, à partir de l'enveloppe d'attaques déjà calculée par tempo.py (aucun décodage en
plus, ~0,1 s pour un son de 4 min) :

* tempo LOCAL, fenêtres de 12 s tous les 3 s (autocorrélation, entre 0,78 et 1,28 fois le tempo du son :
  au-delà, les erreurs x4/3 et x3/2 l'emportent sur les vrais changements) :
  repère les changements nets (beatswitch), les accélérations et les sets ;
* écart d'une grille CONSTANTE au fil du son : calage de la grille, fenêtres de 16 s tous les 4 s, replié sur
  le demi-temps (un calage qui hésite entre temps et contretemps n'est pas un écart) ; c'est ce qui compte
  pour la platine : au-delà de ~60 ms, une grille fixe décroche.

Types (jamais affirmés : l'interface dit « détecté », la liste « Tempo qui change » les regroupe) :
  « switch » : au moins deux passages stables (20 s et plus) à des tempos différents de 4 % ou plus ;
  « ramp »   : le tempo monte (ou descend) de 3 % ou plus, peu à peu ;
  « set »    : mix ou set de 10 min et plus dont le tempo bouge ;
  « live »   : tempo qui flotte (batteur, version live) : une grille fixe décroche, sans palier net.

1.4.3 (C16) : un beatswitch reçoit une grille par passage (tempo.py, _split_grid) : un tempo et un calage par
passage, raccordés au changement ; réglage « grille variable : auto / jamais » (set_policy) et choix « grille
fixe » par son (set_choice), gardé à la réanalyse.

Mesuré sur l'échantillon du PC fixe (19 lives, sets et beatswitchs ; 337 sons de référence) : voir
claude/mesures-1.4.3.md dans les docs du projet.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)

KINDS = ("switch", "ramp", "set", "live")

SET_SECONDS = 600.0          # au-delà : un mix ou un set
SWITCH_RATIO = 0.04          # écart entre deux paliers pour un beatswitch
RAMP_RATIO = 0.03            # montée (ou descente) totale pour une accélération
LIVE_DRIFT_MS = 120.0        # décrochage d'une grille fixe pour un tempo « humain »
SET_DRIFT_MS = 60.0
MIN_STRENGTH = 0.18          # en dessous (médiane), les temps sont trop flous : rien n'est affirmé
# rapports qui trahissent une erreur d'octave ou de mesure (x2, x3/2, x4/3) plutôt qu'un vrai changement
_SUSPECT = (2.0, 0.5, 1.5, 2 / 3, 4 / 3, 0.75)
# x5/4 : souvent un motif rythmique (intro, pont, rap en triolets) ; gardé seulement pour UN changement entre
# deux longs passages (un quart du son chacun au moins) : sur l'échantillon, 6 faux beatswitchs sur 337 sinon
_FIVE_FOUR = (1.25, 0.8)
DOMINANT = 0.6               # un palier qui couvre 60 % du son : pas une accélération


@dataclass
class TempoProfile:
    kind: str = ""            # "" : tempo stable, ou rien de sûr
    lo: float = 0.0           # tempo le plus lent / le plus rapide des passages stables (BPM)
    hi: float = 0.0
    drift_ms: float = 0.0     # décrochage d'une grille constante (10e-90e centile, ms)
    variable: bool = False    # la grille écrite suit le tempo (tempo.py, _warp)
    # 1.4.3 (C16) : beatswitch : une grille par passage, écrite telle quelle dans PQTZ
    split: bool = False       # la grille écrite change de tempo à chaque passage
    sections: List[Tuple[float, float, float]] = field(default_factory=list)   # (début s, BPM, 1er temps fort s)
    choice: str = ""          # choix de l'utilisateur gardé à la réanalyse : "" (auto) | "fixed"
    # mesures de classify() pour la grille par passage (jamais enregistrées) : paliers (début s, fin s, BPM),
    # et indices des paliers suivis d'un vrai changement
    plateaus: List[Tuple[float, float, float]] = field(default_factory=list, repr=False, compare=False)
    cuts: List[int] = field(default_factory=list, repr=False, compare=False)

    @property
    def changes(self) -> bool:
        return bool(self.kind)

    def to_list(self) -> list:
        return [self.kind, round(self.lo, 1), round(self.hi, 1), round(self.drift_ms), int(self.variable),
                int(self.split), [[round(a, 3), round(b, 3), round(c, 3)] for a, b, c in self.sections], self.choice]

    @classmethod
    def from_list(cls, v: Optional[list]) -> Optional["TempoProfile"]:
        if not v:
            return None
        try:
            secs = [(float(a), float(b), float(c)) for a, b, c in (v[6] if len(v) > 6 and v[6] else [])]
            return cls(str(v[0]), float(v[1]), float(v[2]), float(v[3]) if len(v) > 3 else 0.0,
                       bool(v[4]) if len(v) > 4 else False, bool(v[5]) if len(v) > 5 else False, secs,
                       str(v[7]) if len(v) > 7 and v[7] else "")
        except (TypeError, ValueError, IndexError):
            return None


def _autocorr(x: np.ndarray) -> np.ndarray:
    n = x.size
    f = np.fft.rfft(x - x.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    return ac / ac[0] if ac[0] > 0 else ac


def local_tempi(env: np.ndarray, fps: float, ref: float, win: float = 12.0,
                hop: float = 3.0) -> Tuple[np.ndarray, np.ndarray]:
    """(tempo local en BPM, NaN quand le choix touche le bord de la plage ; force) par fenêtre."""
    n, h = int(win * fps), max(1, int(hop * fps))
    cands = np.arange(ref * 0.78, ref * 1.28, 0.05)
    lag = 60.0 * fps / cands
    bpm, strength = [], []
    for a in range(0, max(1, env.size - n), h):
        seg = env[a:a + n]
        if seg.size < n // 2 or not np.any(seg):
            bpm.append(np.nan)
            strength.append(0.0)
            continue
        ac = _autocorr(seg)

        def at(l: np.ndarray) -> np.ndarray:
            l = np.clip(l, 0, ac.size - 2)
            i = l.astype(int)
            f = l - i
            return ac[i] * (1 - f) + ac[i + 1] * f

        sc = at(lag) + 0.5 * at(2 * lag) + 0.5 * at(4 * lag)
        j = int(np.argmax(sc))
        bpm.append(np.nan if j < 3 or j > cands.size - 4 else float(cands[j]))
        strength.append(float(sc[j]))
    return np.array(bpm), np.array(strength)


def grid_drift_ms(env: np.ndarray, fps: float, bpm: float, win: float = 16.0, hop: float = 4.0) -> float:
    """Décrochage d'une grille constante à `bpm` au fil du son (ms, 10e-90e centile du calage local,
    replié sur le demi-temps). ~5 ms pour un son produit sur ordinateur, 100 ms et plus pour un live."""
    if bpm <= 0:
        return 0.0
    smooth = np.convolve(env, [0.25, 0.5, 0.25], mode="same")
    half = fps * 30.0 / bpm
    n, h = int(win * fps), max(1, int(hop * fps))
    if smooth.size < n or half < 2:
        return 0.0
    phases = np.arange(0, half, 0.25)
    k = np.arange(0, int(n // half))
    pos_rel = phases[:, None] + k[None, :] * half
    found, contrast = [], []
    for a in range(0, smooth.size - n + 1, h):
        pos = np.clip(a + pos_rel, 0, smooth.size - 1.000001)
        i = pos.astype(int)
        f = pos - i
        st = (smooth[i] * (1 - f) + smooth[i + 1] * f).mean(axis=1)
        j = int(np.argmax(st))
        found.append((a + phases[j]) % half)
        contrast.append((st[j] - st.mean()) / (st.std() + 1e-9))
    if len(found) < 5:
        return 0.0
    ph = np.unwrap(np.array(found) / half * 2 * np.pi) / (2 * np.pi) * half
    ph = ph[np.array(contrast) > 1.5]
    if ph.size < 5:
        return 0.0
    lo, hi = np.percentile(ph, [10, 90])
    return float((hi - lo) / fps * 1000.0)


def _plateaus(v: np.ndarray, min_len: int = 7, tol: float = 0.02) -> List[Tuple[int, int, float]]:
    """Passages stables : (début, fin exclue, tempo médian), au moins `min_len` fenêtres à ±tol."""
    out: List[Tuple[int, int, float]] = []
    i = 0
    while i < v.size:
        if np.isnan(v[i]):
            i += 1
            continue
        j, vals, miss = i + 1, [v[i]], 0
        while j < v.size:
            if np.isnan(v[j]) or abs(v[j] / np.median(vals) - 1) > tol:
                miss += 1                       # une fenêtre isolée hors palier est tolérée
                if miss > 1:
                    break
            else:
                vals.append(v[j])
                miss = 0
            j += 1
        end = j - miss
        if len(vals) >= min_len:
            out.append((i, end, float(np.median(vals))))
            i = end
        else:
            i += 1
    merged: List[Tuple[int, int, float]] = []
    for p in out:                               # paliers voisins au même tempo : un seul
        if merged and abs(p[2] / merged[-1][2] - 1) < tol * 1.25:
            a, _, m = merged[-1]
            merged[-1] = (a, p[1], (m + p[2]) / 2)
        else:
            merged.append(p)
    return merged


def _suspect(r: float) -> bool:
    return any(abs(r / s - 1) < 0.015 for s in _SUSPECT)


def classify(env: np.ndarray, fps: float, bpm: float, duration: float,
             debug: Optional[Dict] = None) -> TempoProfile:
    """Profil de tempo d'un son (voir l'en-tête du module)."""
    if bpm <= 0 or env.size < fps * 30:
        return TempoProfile()
    v, s = local_tempi(env, fps, bpm)
    drift = grid_drift_ms(env, fps, bpm)
    strength = float(np.median(s)) if s.size else 0.0
    plat = _plateaus(v)
    if debug is not None:
        debug.update(tp_strength=round(strength, 3), tp_drift_ms=round(drift, 1),
                     tp_plateaus=" ".join(f"{p[2]:.1f}x{p[1] - p[0]}" for p in plat))
    if strength < MIN_STRENGTH or v.size < 8:
        return TempoProfile(drift_ms=drift)
    tempos = [p[2] for p in plat] or [bpm]
    lo, hi = min(tempos), max(tempos)
    # beatswitch : deux paliers qui se suivent, assez différents, rapport qui n'est pas une erreur d'octave
    steps = [plat[k + 1][2] / plat[k][2] for k in range(len(plat) - 1)]
    total = max(1, v.size)

    def real_step(k: int) -> bool:
        r = steps[k]
        if abs(r - 1) < SWITCH_RATIO or _suspect(r):
            return False
        if any(abs(r / f - 1) < 0.02 for f in _FIVE_FOUR):
            a, b = plat[k], plat[k + 1]
            return len(plat) == 2 and min(a[1] - a[0], b[1] - b[0]) >= 0.25 * total
        return True

    cuts = [k for k in range(len(steps)) if real_step(k)]
    big = [steps[k] for k in cuts]
    dominant = max((p[1] - p[0] for p in _plateaus(v, tol=0.01)), default=0) >= DOMINANT * total
    # accélération : le tempo monte (ou descend) peu à peu ; mesurée sur les fenêtres fiables
    ok = ~np.isnan(v)
    ramp = 0.0
    if ok.sum() >= 10:
        vv = v[ok]
        q = max(3, vv.size // 5)
        a, b = float(np.median(vv[:q])), float(np.median(vv[-q:]))
        rank = np.argsort(np.argsort(vv))
        rho = float(np.corrcoef(np.arange(vv.size), rank)[0, 1]) if vv.size > 2 else 0.0
        if abs(b / a - 1) >= RAMP_RATIO and abs(rho) >= 0.6 and not _suspect(b / a) and not dominant \
                and not any(abs(b / a / f - 1) < 0.02 for f in _FIVE_FOUR):
            ramp = b / a - 1
            lo, hi = min(lo, a, b), max(hi, a, b)
    gradual = bool(steps) and all(abs(r - 1) < 0.07 for r in steps) and \
        (all(r > 1 for r in steps) or all(r < 1 for r in steps)) and len(steps) >= 2
    if duration >= SET_SECONDS and (drift >= SET_DRIFT_MS or hi / lo - 1 >= 0.01 or big):
        kind = "set"
    elif ramp and (not big or gradual):
        kind = "ramp"
    elif big:
        kind = "switch"
    elif drift >= LIVE_DRIFT_MS and float(np.nanpercentile(v, 75) / np.nanpercentile(v, 25) - 1) >= 0.008:
        kind = "live"
    else:
        kind = ""
    if not kind:
        lo = hi = bpm
    if debug is not None:
        debug.update(tp_kind=kind, tp_ramp=round(ramp, 3))
    out = TempoProfile(kind, lo, hi, drift)
    # centre de la première et de la dernière fenêtre de chaque palier (fenêtres de 12 s tous les 3 s)
    out.plateaus = [(a * 3.0 + 6.0, (b - 1) * 3.0 + 6.0, m) for a, b, m in plat]
    out.cuts = cuts
    return out


# ------------------------------------------------------------------------------- grille par passage (C16)
def section_beats(sections: List[Tuple[float, float, float]], duration: float) -> List[Tuple[int, float]]:
    """Temps (numéro 1-4, secondes) d'une grille par passage. Chaque passage : (début = son 1er temps, BPM,
    un 1er temps de mesure) ; il s'arrête au début du suivant. Raccord : un dernier temps trop proche du
    passage suivant (moins d'un demi-temps) est retiré, pour qu'aucun temps ne soit plus court que la moitié
    d'un temps des deux passages."""
    out: List[Tuple[int, float]] = []
    secs = sorted((s for s in sections if s[1] > 0), key=lambda s: s[0])
    for i, (start, bpm, down) in enumerate(secs):
        beat = 60.0 / bpm
        end = secs[i + 1][0] if i + 1 < len(secs) else duration
        nxt_beat = 60.0 / secs[i + 1][1] if i + 1 < len(secs) else beat
        times = np.arange(start, end - 1e-6, beat)
        if i + 1 < len(secs) and times.size and end - times[-1] < 0.5 * min(beat, nxt_beat):
            times = times[:-1]
        for tt in times:
            k = int(round((tt - down) / beat))
            out.append(((k % 4) + 1, float(tt)))
    return out


def section_at(sections: List[Tuple[float, float, float]], t: float) -> int:
    """Indice du passage qui contient l'instant `t` (secondes)."""
    idx = 0
    for i, s in enumerate(sorted(sections, key=lambda s: s[0])):
        if t + 1e-6 >= s[0]:
            idx = i
    return idx


# ------------------------------------------------------------------------------- réglage (Réglages ▸ Analyse)
GRID_MODES = ("auto", "never")
_policy = "auto"


def set_policy(mode: str) -> None:
    """« auto » : grille variable (live, accélération, set) ou par passage (beatswitch) quand l'analyse le
    juge utile ; « never » : toujours une grille fixe (comme le mode « grille constante » de Rekordbox)."""
    global _policy
    _policy = mode if mode in GRID_MODES else "auto"


def policy() -> str:
    return _policy


def grid_mode_for(path: Union[str, Path, None]) -> str:
    """Mode de grille pour l'analyse de `path` : le réglage, ou « never » si l'utilisateur a choisi la grille
    fixe pour ce son (bouton de Grille et cues)."""
    if _policy == "never":
        return "never"
    if path is not None:
        try:
            p = known(path)
        except Exception:  # noqa: BLE001
            p = None
        if p is not None and p.choice == "fixed":
            return "never"
    return "auto"


# ------------------------------------------------------------------------------- registre
# Comme gain.json (C109) et la qualité réelle (C46) : un petit fichier dans le dossier des réglages, clé
# « nom du fichier|taille », lu par la Bibliothèque (pastille sur le BPM, liste « Tempo qui change »).
_lock = threading.Lock()
_cache: Optional[Dict[str, list]] = None
_store_path: Optional[Path] = None


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "tempo.json"


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


def _key(path: Path) -> Optional[str]:
    try:
        return f"{path.name.casefold()}|{path.stat().st_size}"
    except OSError:
        return None


def lookup(name: str, size: int) -> Optional[TempoProfile]:
    """Profil déjà mesuré (nom du fichier et taille connus par la bibliothèque), sinon None."""
    if not name or not size:
        return None
    with _lock:
        return TempoProfile.from_list(_load().get(f"{name.casefold()}|{int(size)}"))


def known(path: Union[str, Path]) -> Optional[TempoProfile]:
    key = _key(Path(path))
    if key is None:
        return None
    with _lock:
        return TempoProfile.from_list(_load().get(key))


def set_choice(name: str, size: int, choice: str) -> bool:
    """1.4.3 (C16) : « fixed » (grille fixe gardée à la réanalyse) ou "" ; False si le son n'est pas connu."""
    if not name or not size:
        return False
    key = f"{name.casefold()}|{int(size)}"
    with _lock:
        data = _load()
        p = TempoProfile.from_list(data.get(key))
        if p is None:
            return False
        p.choice = "fixed" if choice == "fixed" else ""
        data[key] = p.to_list()
        _save(data)
    return True


def _save(data: Dict[str, list]) -> None:
    try:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".djsync-tmp")
        tmp.write_text(json.dumps(data), "utf-8")
        tmp.replace(f)
    except OSError as exc:
        log.info("Tempo register not saved: %s", exc)


def remember(path: Union[str, Path], profile: Optional[TempoProfile]) -> None:
    """Retient le profil ; un tempo stable est retenu aussi (le son a été analysé : rien à signaler)."""
    if profile is None:
        return
    key = _key(Path(path))
    if key is None:
        return
    with _lock:
        data = _load()
        old = TempoProfile.from_list(data.get(key))
        if old is not None and old.choice and not profile.choice:     # C16 : le choix de l'utilisateur reste
            profile.choice = old.choice
        if data.get(key) == profile.to_list():
            return
        data[key] = profile.to_list()
        _save(data)
