"""Analyse audio locale (V1.1-A4) : BPM + grille, tonalité (Camelot), formes d'onde Pioneer (ANLZ).

Dépendances : numpy + FFmpeg (déjà requis). Pas de librosa/scipy/numba : l'exécutable portable
reste léger. Usage :

    result = analyze_file("son.m4a")                       # ~1 à 3 s pour un morceau de 4 min
    rel = write_anlz(drive_root, "/Contents/A/B/son.m4a", result, file_type=4, native_sr=44100)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .anlz import write_files
from .decode import ANALYSIS_SR, DecodeError, find_ffmpeg
from .decode import decode as decode_audio      # (le nom « decode » reste celui du sous-module)
from .key import KeyResult, analyze_key
from .tempo import BeatGrid, analyze_tempo
from .waveform import Waveforms, compute_waveforms

__all__ = ["AnalysisResult", "analyze_file", "write_anlz", "configure", "OPTIONS", "RESULT_HOOKS", "BPM_RANGES", "DecodeError", "find_ffmpeg", "BeatGrid", "KeyResult"]

MP3_FILE_TYPE = 1

# 1.3.0 (C16) : options d'analyse choisies dans les Réglages (appliquées à toutes les analyses).
#   tempo_mode : "auto" (une grille qui suit le tempo quand il change nettement, à vérifier) ou
#                "constant" (toujours un tempo unique, comme le réglage par défaut de Rekordbox) ;
#   bpm_range  : plage d'affichage du BPM (le tempo est ramené à l'octave qui tombe dedans).
OPTIONS: Dict[str, Any] = {"tempo_mode": "auto", "bpm_range": (70, 180)}
BPM_RANGES = ((70, 180), (58, 115), (68, 135), (78, 155), (88, 175), (98, 195))
# Appelées après chaque analyse : hook(chemin du fichier, AnalysisResult). Ne doivent pas lever.
RESULT_HOOKS: List[Callable[[Path, "AnalysisResult"], None]] = []


def configure(tempo_mode: str = "auto", bpm_range: Tuple[int, int] = (70, 180)) -> None:
    OPTIONS["tempo_mode"] = tempo_mode if tempo_mode in ("auto", "constant") else "auto"
    lo, hi = (int(v) for v in bpm_range)
    OPTIONS["bpm_range"] = (lo, hi) if (lo, hi) in BPM_RANGES else (70, 180)


@dataclass
class AnalysisResult:
    duration: float
    grid: BeatGrid
    key: KeyResult
    waveforms: Waveforms
    seconds: float = 0.0          # temps de calcul

    @property
    def bpm(self) -> float:
        return self.grid.bpm

    @property
    def bpmx100(self) -> int:
        return self.grid.bpmx100

    @property
    def first_downbeat_ms(self) -> Optional[int]:
        """Premier temps fort (temps 1 d'une mesure), en ms : position de la mémoire automatique."""
        for n, t in self.grid.beats:
            if n == 1:
                return int(round(t * 1000))
        return None

    def pqtz_beats(self) -> List[Tuple[int, int, int]]:
        """(numéro dans la mesure 1-4, tempo x100, temps en ms) pour la balise PQTZ."""
        tempos = self.grid.beat_tempos()
        return [(n, int(round(bpm * 100)), int(round(t * 1000))) for (n, t), bpm in zip(self.grid.beats, tempos)]


def analyze_file(path: Union[str, Path], ffmpeg_location: Optional[str] = None) -> AnalysisResult:
    started = time.perf_counter()
    audio = decode_audio(path, ffmpeg_location, ANALYSIS_SR)
    x, sr = audio.samples, audio.sr
    grid = analyze_tempo(x, sr, constant=OPTIONS["tempo_mode"] == "constant", bpm_range=OPTIONS["bpm_range"])
    key = analyze_key(x, sr)
    wf = compute_waveforms(x, sr, audio.duration)
    result = AnalysisResult(audio.duration, grid, key, wf, time.perf_counter() - started)
    for hook in list(RESULT_HOOKS):
        try:
            hook(Path(path), result)
        except Exception:  # noqa: BLE001 - un suivi (sons à tempo variable) ne doit jamais casser l'analyse
            import logging

            logging.getLogger(__name__).exception("analysis hook")
    return result


def write_anlz(drive_root: Union[str, Path], track_path: str, result: AnalysisResult, file_type: int = 0,
               native_sr: int = 44100, rel_dir: Optional[str] = None, auto_cue: bool = False) -> str:
    """Écrit les fichiers d'analyse sur la clé (ou dans le dossier « share » de Rekordbox sur
    l'ordinateur : `rel_dir` imposé) ; renvoie « /PIONEER/USBANLZ/…/ANLZ0000.DAT »."""
    total = int(round(result.duration * native_sr)) if file_type == MP3_FILE_TYPE else 0
    cue = result.first_downbeat_ms if auto_cue else None
    return write_files(Path(drive_root), track_path, result.pqtz_beats(), result.waveforms, total, rel_dir=rel_dir,
                       memory_cues=[cue] if cue is not None else ())
