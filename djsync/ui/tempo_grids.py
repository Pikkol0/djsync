"""1.4.3 (C16) : grilles des sons dont le tempo change (service tenu par le contrôleur, règle A3-10).

* réglage « grille variable : auto / jamais » (Réglages ▸ Analyse) transmis à l'analyse ;
* grille par passage d'un beatswitch reconstruite depuis le registre des tempos (tempo.json), pour le bouton
  « Grille par passage » de Grille et cues ;
* grille fixe (un seul tempo) calée sur un temps, pour le bouton « Grille fixe » ; le choix est gardé pour la
  réanalyse (tempo_profile.set_choice) ;
* sons à valider : tempo qui change et grille pas encore marquée vérifiée (« Grille juste », C204) ;
* 1.4.4 (B125) : 1er temps de la mesure à vérifier (entrées des basses en désaccord à l'analyse).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from ..analysis import grid as G
from ..analysis import tempo_profile

log = logging.getLogger(__name__)

Beat = Tuple[int, int, int]           # (numéro 1-4, tempo x100, ms), comme la balise PQTZ


def profile_of(track: Any) -> Optional[tempo_profile.TempoProfile]:
    try:
        return tempo_profile.lookup(Path(track.path).name, track.file_size)
    except Exception:  # noqa: BLE001
        return None


def split_beats(sections: Sequence[Tuple[float, float, float]], duration_ms: int) -> List[Beat]:
    """Grille par passage, au format de Grille et cues."""
    secs = sorted(sections, key=lambda s: s[0])
    out: List[Beat] = []
    for n, t in tempo_profile.section_beats(list(secs), duration_ms / 1000.0):
        bpm = secs[tempo_profile.section_at(secs, t)][1]
        out.append((n, int(round(bpm * 100)), int(round(t * 1000))))
    return out


def main_tempo(beats: Sequence[Beat]) -> float:
    """Tempo (BPM) qui couvre le plus de temps : celui d'une grille fixe qui remplace une grille qui change."""
    if not beats:
        return 0.0
    span: dict = {}
    for a, b in zip(beats, beats[1:]):
        key = round(a[1] / 100.0, 1)
        span[key] = span.get(key, 0) + (b[2] - a[2])
    if not span:
        return beats[0][1] / 100.0
    best = max(span, key=span.get)
    # tempo exact (x100) le plus fréquent dans ce groupe
    exact = [b[1] for b in beats if round(b[1] / 100.0, 1) == best]
    return max(set(exact), key=exact.count) / 100.0


def changes(beats: Sequence[Beat], ratio: float = 0.03) -> List[Tuple[int, float, float]]:
    """Changements de tempo d'une grille : (indice du 1er temps du nouveau tempo, avant, après), au-delà de 3 %
    d'un temps au suivant (une grille variable de live bouge moins vite : pas de trait à chaque temps)."""
    out = []
    ref = beats[0][1] if beats else 0
    for i in range(1, len(beats)):
        cur = beats[i][1]
        if ref and abs(cur / ref - 1) >= ratio:
            out.append((i, ref / 100.0, cur / 100.0))
            ref = cur
    return out


def is_constant(beats: Sequence[Beat]) -> bool:
    return len({b[1] for b in beats}) <= 1


class TempoGridService:
    """Tenu par le contrôleur (`controller.tempo_grids`)."""

    def __init__(self, controller: Any) -> None:
        self.ctrl = controller
        self.apply_settings()

    def apply_settings(self) -> None:
        tempo_profile.set_policy(getattr(self.ctrl.settings, "tempo_grid", "auto") or "auto")

    # ------------------------------------------------------------------ Grille et cues
    def split_grid(self, track: Any, duration_ms: int) -> Optional[List[Beat]]:
        """Grille par passage trouvée par l'analyse, None si le son n'en a pas."""
        p = profile_of(track)
        if p is None or len(p.sections) < 2:
            return None
        return split_beats(p.sections, duration_ms)

    @staticmethod
    def fixed_grid(beats: Sequence[Beat], selected: int, duration_ms: int) -> Tuple[List[Beat], float]:
        """Un seul tempo (celui qui couvre le plus de temps), calé sur le temps sélectionné."""
        bpm = main_tempo(beats)
        return G.set_bpm(list(beats), bpm, selected, duration_ms), bpm

    def remember_choice(self, track: Any, beats: Optional[Sequence[Beat]]) -> None:
        """À l'enregistrement : grille fixe sur un son au tempo qui change -> gardée à la réanalyse ; grille qui
        change de nouveau -> l'analyse redécide."""
        p = profile_of(track)
        if p is None or not p.kind or beats is None:
            return
        choice = "fixed" if is_constant(beats) else ""
        if choice != p.choice:
            tempo_profile.set_choice(Path(track.path).name, track.file_size, choice)

    # ------------------------------------------------------------------ à valider
    @staticmethod
    def pending(track: Any, checked: Optional[bool]) -> bool:
        """Son au tempo qui change dont la grille n'a pas encore été marquée vérifiée."""
        p = profile_of(track) if getattr(track, "is_analysed", True) else None
        return p is not None and p.changes and checked is False

    # ------------------------------------------------------------------ 1er temps à vérifier (1.4.4, B125)
    @staticmethod
    def downbeat_pending(track: Any) -> bool:
        """Son dont l'analyse n'est pas sûre du 1er temps de la mesure (choix pas encore fait)."""
        p = profile_of(track) if getattr(track, "is_analysed", True) else None
        return p is not None and bool(getattr(p, "downbeat_check", False))

    @staticmethod
    def downbeat_at(track: Any) -> float:
        """Instant (s) de l'entrée des basses la plus nette, pour l'écoute ; -1 si inconnu."""
        p = profile_of(track)
        return float(getattr(p, "downbeat_at", -1.0)) if p is not None else -1.0

    @staticmethod
    def downbeat_done(track: Any) -> bool:
        """Choix fait (ou grille validée) : le son n'est plus « à vérifier »."""
        try:
            return tempo_profile.set_downbeat_checked(Path(track.path).name, track.file_size)
        except Exception:  # noqa: BLE001 - simple marque
            log.debug("Handled error in downbeat_done", exc_info=True)
            return False
