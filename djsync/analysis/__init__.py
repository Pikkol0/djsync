"""Analyse audio locale (V1.1-A4) : BPM + grille, tonalité (Camelot), formes d'onde Pioneer (ANLZ).

Dépendances : numpy + FFmpeg (déjà requis). Pas de librosa/scipy/numba : l'exécutable portable
reste léger. Usage :

    result = analyze_file("son.m4a")                       # ~1 à 3 s pour un morceau de 4 min
    rel = write_anlz(drive_root, "/Contents/A/B/son.m4a", result, file_type=4, native_sr=44100)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .anlz import write_files
from .decode import ANALYSIS_SR, DecodeError, find_ffmpeg
from .decode import decode as decode_audio      # (le nom « decode » reste celui du sous-module)
from .decode import decode_with_native
from .key import KeyResult, analyze_key
from .tempo import BeatGrid, analyze_tempo
from .waveform import Waveforms, compute_waveforms, compute_waveforms_rekordbox, rekordbox_rate

log = logging.getLogger(__name__)

__all__ = ["AnalysisResult", "analyze_file", "write_anlz", "DecodeError", "find_ffmpeg", "BeatGrid", "KeyResult"]

MP3_FILE_TYPE = 1


@dataclass
class AnalysisResult:
    duration: float
    grid: BeatGrid
    key: KeyResult
    waveforms: Waveforms
    seconds: float = 0.0          # temps de calcul
    cutoff: Optional[int] = None  # 1.4.0 (C46) : coupure du spectre (Hz), vraie qualité du fichier
    lufs: Optional[float] = None  # 1.4.3 (C109) : sonie intégrée
    peak_db: Optional[float] = None
    encoder: Optional[object] = None  # 1.4.3 (A04) : encoder.EncoderInfo (en-tête LAME / Xing, encodeur AAC)

    @property
    def gain_db(self) -> float:
        """1.4.3 (C109) : gain automatique (dB), comme le « Auto Gain » de Rekordbox."""
        from .loudness import gain_db

        return gain_db(self.lufs, self.peak_db)

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


def analyze_file(path: Union[str, Path], ffmpeg_location: Optional[str] = None, *, _in_worker: bool = False,
                 _skip_spectrum: bool = False, grid_mode: Optional[str] = None) -> AnalysisResult:
    """Un seul décodage (1.4.3, A1-7) : mono 22 050 Hz pour le tempo et la tonalité, et le même son à sa
    fréquence d'origine pour les formes d'onde (calculées comme Rekordbox, A7-3) et le spectre.
    1.4.3 (A1-6) : résultat déjà calculé par un processus d'analyse s'il y en a un (analysis/pool.py).
    1.4.3 (C16) : `grid_mode` (« auto » | « never ») : par défaut le réglage et le choix fait pour ce son."""
    if not _in_worker:
        from .pool import current

        pre = current()
        if pre is not None:
            ready = pre.take(path, ffmpeg_location)
            if ready is not None:
                return ready
    if grid_mode is None:
        from .tempo_profile import grid_mode_for

        grid_mode = grid_mode_for(path)
    started = time.perf_counter()
    audio, native = decode_with_native(path, ffmpeg_location, ANALYSIS_SR)
    try:
        x, sr = audio.samples, audio.sr
        grid = analyze_tempo(x, sr, grid_mode=grid_mode)
        key = analyze_key(x, sr)
        try:                                              # 1.4.3 (C109) : gain automatique
            from .loudness import measure as measure_loudness

            lufs, peak_db = measure_loudness(x, sr)
        except Exception:  # noqa: BLE001
            log.debug("Ignored error in analyze_file (loudness)", exc_info=True)
            lufs = peak_db = None
        wf = None
        if native is not None and rekordbox_rate(native.rate):
            try:
                wf = compute_waveforms_rekordbox(native)
            except Exception:  # noqa: BLE001 - repli : l'ancien calcul
                log.warning("Rekordbox waveforms failed for %s, previous method used", Path(path).name, exc_info=True)
        if wf is None:
            wf = compute_waveforms(x, sr, audio.duration)
        cutoff = None
        try:                                              # 1.4.0 (C46) : gardé dans le registre
            from .spectrum import known, measure_and_remember, measure_native, remember

            cutoff = None if _skip_spectrum else known(path)
            if cutoff is None and not _skip_spectrum:
                if native is not None:
                    cutoff = measure_native(native, audio.duration)
                    if not _in_worker:                 # le registre est écrit par le processus principal
                        remember(path, cutoff)
                elif _in_worker:
                    from .spectrum import measure

                    cutoff = measure(path, ffmpeg_location, audio.duration)
                else:
                    cutoff = measure_and_remember(path, ffmpeg_location, audio.duration)
        except Exception:  # noqa: BLE001 - la vraie qualité n'est qu'une information en plus
            log.debug("Ignored error in analyze_file", exc_info=True)  # 1.4.3 (A3-4)
    finally:
        if native is not None:
            native.close()
    try:                                                  # 1.4.3 (A04) : ce que dit l'en-tête du fichier
        from .encoder import read as read_encoder

        enc = read_encoder(path)
    except Exception:  # noqa: BLE001
        enc = None
    result = AnalysisResult(audio.duration, grid, key, wf, time.perf_counter() - started, cutoff, lufs, peak_db, enc)
    if not _in_worker and enc is not None:
        from .encoder import remember as remember_encoder

        remember_encoder(path, enc)
    if not _in_worker and lufs is not None:
        from .loudness import remember as remember_gain

        remember_gain(path, result.gain_db, peak_db)
    if not _in_worker:                                           # 1.4.4 (C221) : passages posés à la main
        _manual_grid(path, result)
    if not _in_worker and grid.profile is not None:              # 1.4.3 (C69) : tempo qui change
        try:
            from .tempo_profile import remember as remember_tempo

            remember_tempo(path, grid.profile)
        except Exception:  # noqa: BLE001
            log.debug("Ignored error in analyze_file (tempo profile)", exc_info=True)
    return result


def _manual_grid(path: Union[str, Path], result: AnalysisResult) -> None:
    """1.4.4 (C221) : réanalyse d'un son aux passages posés dans Grille et cues : ils sont gardés."""
    try:
        from .tempo_profile import apply_manual

        apply_manual(path, result.grid, result.duration)
    except Exception:  # noqa: BLE001
        log.debug("Ignored error in analyze_file (manual tempo marks)", exc_info=True)


def write_anlz(drive_root: Union[str, Path], track_path: str, result: AnalysisResult, file_type: int = 0,
               native_sr: int = 44100, rel_dir: Optional[str] = None, auto_cue: bool = False,
               previous: Optional[str] = None) -> str:
    """Écrit les fichiers d'analyse sur la clé (ou dans le dossier « share » de Rekordbox sur
    l'ordinateur : `rel_dir` imposé) ; renvoie « /PIONEER/USBANLZ/…/ANLZ0000.DAT »."""
    total = int(round(result.duration * native_sr)) if file_type == MP3_FILE_TYPE else 0
    cue = result.first_downbeat_ms if auto_cue else None
    return write_files(Path(drive_root), track_path, result.pqtz_beats(), result.waveforms, total, rel_dir=rel_dir,
                       memory_cues=[cue] if cue is not None else (), previous=previous)
