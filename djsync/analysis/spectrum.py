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

1.4.1 (C46, calé sur le banc A05 : 81 pistes de CD, 2 025 copies) : la coupure seule ne suffit pas (un
« faux sans perte » garde le bruit de fond plat du WAV au-dessus de la coupure du codec ; un MP3 V0 ou un
Opus coupent comme un vrai sans perte ou un MP3 320). `measure()` lit maintenant 3 tranches (25, 50, 75 %)
et décide sur plusieurs indices (`classify`) :
* le bord : premier point au-delà duquel le spectre reste 30 dB sous son niveau de 14-15 kHz, retenu
  seulement si la chute est raide (≥ 18 dB sur 750 Hz : un codec, pas l'atténuation douce d'un master) ;
* les « trous » : écart entre médiane et 10e centile des cases temps-fréquence (passages forts) entre 15 et
  20 kHz ; un MP3 met des bandes à zéro, un vrai sans perte, un AAC ou un Opus gardent un fond continu.
Résultat sur le banc (tiers de vérification compris) : vrai sans perte gardé 96 % (jamais 128 / 192) ; faux
sans perte détectés 83 % (90 % hors AAC 256, qui ne se distingue pas d'un vrai sans perte) au lieu de 22 % ;
MP3 128 / 192 / 256 / 320 exacts ≥ 80 % ; un Opus coupe comme un MP3 320 : classé 320 ici, plafonné à
≈ 192 par core.quality quand il vient d'une vidéo ou en a la signature (48 kHz).
Le registre garde un « équivalent de coupure » par classe (`REPRESENTATIVE`) : `estimate()` et tout le reste de
l'application n'ont pas changé ; les mesures d'avant (quality-2.json) sont refaites à la demande.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)

LOSSLESS = 9999                     # « débit » d'un vrai sans perte dans les comparaisons
SLICE = 20.0                        # secondes analysées
N_FFT = 4096
# (coupure minimale en Hz, débit équivalent), du meilleur au moins bon
_CLASSES = ((21000, LOSSLESS), (20000, 320), (19200, 256), (17800, 192), (0, 128))


# 1.4.1 (C46) : indices du banc A05 (mêmes calculs que tools/quality_bench.py)
POSITIONS = (0.25, 0.50, 0.75)
Q_FFT = 2048
BAND_LO, BAND_HI, BAND_STEP = 10000, 24000, 250
QBAND_LO, QBAND_HI = 12000, 22000
# « équivalent de coupure » enregistré pour chaque classe : estimate() le ramène à la même classe
REPRESENTATIVE = {LOSSLESS: 22050, 320: 20000, 256: 19500, 192: 18750, 128: 16500}
# seuils calés sur le banc (tools/quality_calibrate.py)
EDGE_LOSSLESS, EDGE_320, EDGE_256, EDGE_192 = 20750, 19750, 19000, 18000
DROP_DB, STEEP_DB = 30.0, 18.0
HOLES_V0 = 24.0


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
    wall = _brick_wall(smooth, freqs, ref)
    if wall is not None and wall < freqs[top]:
        return wall
    return int(min(freqs[top], sr / 2))


def _brick_wall(smooth: np.ndarray, freqs: np.ndarray, ref: float) -> Optional[int]:
    """1.4.0-rc.3 (B67) : coupure nette d'un codec (chute de plus de 30 dB en moins de 1 kHz) suivie d'un
    plancher plat (bruit, pas de musique) jusqu'en haut : ce plancher n'est pas du contenu. Ex. : flux
    YouTube (Opus) enregistré en WAV 48 kHz : mur à 20 kHz, bruit plat à ≈ −80 dB jusqu'à 24 kHz."""
    step = max(1, int(round(1000 / (freqs[1] - freqs[0]))))      # nombre de cases pour 1 kHz
    for i in range(len(freqs) - 2 * step - 1, 0, -1):
        if freqs[i] < 14000:
            break
        j = i + step
        if smooth[i] < ref - 60 or smooth[i] - smooth[j] < 30:
            continue
        floor = smooth[j:]
        if floor.size >= step and float(np.std(floor)) < 3.0 and float(np.mean(floor)) < ref - 60:
            # bord du mur : dernier point encore à moins de 20 dB sous le niveau d'avant la chute
            k = i
            while k + 1 < j and smooth[k + 1] > smooth[i] - 20:
                k += 1
            return int(freqs[k])
    return None


def slice_features(x: np.ndarray, sr: int) -> Optional[dict]:
    """Indices d'une tranche (mêmes calculs que le banc A05) : spectre moyen au-dessus de 10 kHz (dB sous le
    niveau 1-8 kHz, cases de 250 Hz) et, par bande de 1 kHz de 12 à 22 kHz, 10e / 50e / 90e centile des cases
    temps-fréquence dans la moitié forte des trames. None si trop court ou silencieux."""
    if x.size < Q_FFT * 8:
        return None
    hop = Q_FFT // 2
    n = 1 + (x.size - Q_FFT) // hop
    idx = np.arange(Q_FFT)[None, :] + hop * np.arange(n)[:, None]
    win = np.hanning(Q_FFT).astype(np.float32)
    power = np.abs(np.fft.rfft(x[idx] * win[None, :], axis=1)) ** 2
    power /= float((win ** 2).sum()) ** 2 / 4.0
    freqs = np.fft.rfftfreq(Q_FFT, 1.0 / sr)
    mid = (freqs >= 1000) & (freqs <= 8000)
    frame_level = 10 * np.log10(power[:, mid].mean(axis=1) + 1e-30)
    level = float(np.median(frame_level))
    if level < -90:
        return None
    loud = frame_level >= level
    mean_db = 10 * np.log10(power.mean(axis=0) + 1e-30)
    ref = float(np.median(mean_db[mid]))
    spec: list = []
    for lo in range(BAND_LO, BAND_HI, BAND_STEP):
        sel = (freqs >= lo) & (freqs < lo + BAND_STEP)
        spec.append(round(float(mean_db[sel].mean()) - ref, 1) if sel.any() else None)
    cells = 10 * np.log10(power[loud] + 1e-30)
    quant: list = []
    for lo in range(QBAND_LO, QBAND_HI, 1000):
        sel = (freqs >= lo) & (freqs < lo + 1000)
        if not sel.any():
            quant.append(None)
            continue
        quant.append([round(float(v), 1) for v in np.percentile(cells[:, sel], (10, 50, 90))])
    return {"level": round(level, 1), "ref": round(ref, 1), "spec": spec, "quant": quant}


def _slice_indices(f: dict) -> Optional[tuple]:
    """(bord en Hz, trous 15-19 kHz sous le bord, trous 17-20 kHz) d'une tranche ; None si inutilisable."""
    v = np.array([x for x in f.get("spec") or [] if x is not None], dtype=float)
    n = len(v)
    if n < 24:                                    # spectre qui ne monte pas à 16 kHz (fichier < 32 kHz)
        return None
    v15 = float(np.mean(v[16:20]))                # 14-15 kHz
    run = np.maximum.accumulate(v[::-1])[::-1]    # maximum de tout ce qui suit
    below = np.nonzero(run[20:] < v15 - DROP_DB)[0]
    edge = BAND_LO + BAND_STEP * n
    if below.size:
        j = 20 + int(below[0])
        lo = max(20, j - 4)
        steep = max((v[k] - v[k + 3] for k in range(lo, min(j + 1, n - 3))), default=0.0)
        if steep >= STEEP_DB:                     # chute nette : un codec, pas un master doux
            edge = BAND_LO + BAND_STEP * j
    q = f.get("quant") or []

    def holes(b: int) -> float:
        return float(q[b][1] - q[b][0]) if b < len(q) and q[b] else 0.0

    low = max(holes(b) for b in range(3, 7) if 12000 + 1000 * b + 1000 <= max(edge, 16000))
    high = max(holes(5), holes(6), holes(7))
    return float(edge), low, high


def classify(features: list) -> Tuple[int, int]:
    """(classe : LOSSLESS, 320, 256, 192, 128 ; 0 si inconnue, bord en Hz) d'après les indices de 1 à 3
    tranches (`slice_features`). Seuils calés sur le banc A05."""
    ind = [i for i in (_slice_indices(f) for f in features if f) if i is not None]
    if not ind:
        return 0, 0
    edge, low, high = (float(np.median([i[k] for i in ind])) for k in range(3))
    if edge >= EDGE_LOSSLESS:
        return (LOSSLESS if low < HOLES_V0 else 256), int(edge)      # MP3 V0 : plein spectre mais troué
    if edge >= EDGE_320:
        # MP3 320 ou Opus (mur à 20 kHz) : l'Opus n'y laisse pas de trous, mais un MP3 320 de musique dense
        # non plus (12 % du banc). Classé 320 ; l'Opus d'une vidéo est plafonné à ≈ 192 par
        # core.quality (source, ou 48 kHz + mur vers 20 kHz), jamais un vrai MP3 320 accusé à tort.
        return 320, int(edge)
    if edge >= EDGE_256:
        return 256, int(edge)
    if edge >= EDGE_192:
        return 192, int(edge)
    return 128, int(edge)


def measure(path: Union[str, Path], ffmpeg_location: Optional[str] = None,
            duration: float = 0.0, native_sr: int = 0) -> Optional[int]:
    """« Équivalent de coupure » (REPRESENTATIVE) de la classe mesurée sur 3 tranches de 20 s (25, 50,
    75 % du son) ; None si impossible. Fichier à moins de 40 kHz : ancienne mesure (coupure seule)."""
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
    starts = [max(0.0, duration * p - SLICE / 2) for p in POSITIONS] if duration > SLICE else [0.0]
    feats = []
    try:
        for start in starts:
            x = _decode_slice(path, ffmpeg, sr, start)
            if sr < 40000:                         # 1.4.1 : trop peu d'aigus pour les indices du banc
                return cutoff_of(x, sr)
            feats.append(slice_features(x, sr))
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("Spectrum not measured (%s): %s", path.name, exc)
        return None
    kbps, _edge = classify(feats)
    return REPRESENTATIVE.get(kbps) if kbps else None


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

    # 1.4.0-rc.3 (B67) : nouveau fichier : les mesures d'avant (mur + bruit pris pour du sans perte) sont refaites
    # 1.4.1 (C46) : de même pour les mesures de la 1.4.0 (une tranche, coupure seule) : refaites à la demande
    return settings_dir() / "quality-3.json"


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


def remember(path: Union[str, Path], cutoff: Optional[int], save: bool = True) -> None:
    """Retient une coupure mesurée ; `save=False` : écrite plus tard par `flush()` (1.4.0-rc.6, C180 :
    un recalcul de toute la bibliothèque n'écrit pas le fichier à chaque son)."""
    if not cutoff:
        return
    key = _key(Path(path))
    if key is None:
        return
    with _lock:
        _load()[key] = int(cutoff)
    if save:
        flush()


def flush() -> None:
    """Écrit le registre (fichier temporaire puis remplacement : jamais à moitié écrit)."""
    with _lock:
        data = _load()
        try:
            f = _file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".djsync-tmp")
            tmp.write_text(json.dumps(data), "utf-8")
            tmp.replace(f)
        except OSError as exc:
            log.info("Quality register not saved: %s", exc)


def measure_and_remember(path: Union[str, Path], ffmpeg_location: Optional[str] = None,
                         duration: float = 0.0, force: bool = False, save: bool = True) -> Optional[int]:
    """Coupure du fichier : celle déjà retenue, sinon mesurée et retenue. 1.4.0-rc.6 (C180) : `force` mesure
    de nouveau même si elle est connue (« Recalculer la qualité supposée ») ; une mesure ratée garde l'ancienne."""
    c = None if force else known(path)
    if c is None:
        c = measure(path, ffmpeg_location, duration)
        remember(path, c, save=save)
        if c is None and force:
            c = known(path)
    return c
