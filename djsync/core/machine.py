"""Mode léger pour les PC modestes (1.4.0, C65).

DJSync doit tourner sur la plupart des PC, même vieux (version portable sur une clé). Le mode léger
n'enlève aucune fonction : il rend seulement certaines choses plus économes.

* Choix : « auto » (défaut : actif si ≤ 4 Go de mémoire ou ≤ 2 cœurs), « on », « off ».
* Effets (voir `LightMode`) : lecture dans Grille et cues à 30 images/s au plus ; forme d'onde défilante du
  lecteur coupée (le lecteur garde sa forme d'onde fixe) ; analyse en arrière-plan un son à la fois et mise en
  pause pendant la lecture.
* Au démarrage, sur un PC repéré comme modeste et en « auto » : une fenêtre l'explique une fois, avec
  « Ne plus me le rappeler » (demande de l'auteur, 28/10).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger(__name__)

MODES = ("auto", "on", "off")
MODEST_MEMORY_GB = 4.0
MODEST_CORES = 2
LIGHT_FRAME_MS = 33             # 30 images/s
LIGHT_ANALYSIS_BATCH = 1


@dataclass(frozen=True)
class MachineInfo:
    cores: int
    memory_gb: Optional[float]          # None si inconnue

    @property
    def modest(self) -> bool:
        low_mem = self.memory_gb is not None and self.memory_gb <= MODEST_MEMORY_GB + 0.25
        return bool(low_mem or (self.cores and self.cores <= MODEST_CORES))

    def describe(self) -> str:
        mem = f"{self.memory_gb:.0f} GB" if self.memory_gb is not None else "? GB"
        return f"{self.cores} cores, {mem}"


_INFO: Optional[MachineInfo] = None


def machine_info(refresh: bool = False) -> MachineInfo:
    global _INFO
    if _INFO is None or refresh:
        mem = None
        try:
            import psutil

            mem = psutil.virtual_memory().total / 1024 ** 3
        except Exception:  # noqa: BLE001 - psutil absent : mémoire inconnue, seuls les cœurs comptent
            mem = None
        _INFO = MachineInfo(int(os.cpu_count() or 1), mem)
    return _INFO


def light_active(settings: Any, info: Optional[MachineInfo] = None) -> bool:
    mode = getattr(settings, "light_mode", "auto")
    if mode == "on":
        return True
    if mode == "off":
        return False
    return bool((info or machine_info()).modest)


def should_offer(settings: Any, info: Optional[MachineInfo] = None) -> bool:
    """La fenêtre du démarrage : PC modeste, mode « auto », pas encore refusée."""
    return getattr(settings, "light_mode", "auto") == "auto" and not getattr(settings, "light_prompt_off", False) \
        and bool((info or machine_info()).modest)
