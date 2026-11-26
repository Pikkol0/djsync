"""1.4.4 (C108) : énergie des sons (service tenu par le contrôleur, `controller.energy`, règle A3-10).

* valeur affichée (colonne « Énergie » de la Bibliothèque, lecteur) : celle choisie à la main, sinon celle de
  l'analyse (registre energy.json, analysis/energy.py) ;
* clic droit ▸ Énergie : 1 à 10, ou « Automatique » ;
* option « énergie dans le commentaire » (Paramètres ▸ Analyse, non par défaut) : « E7 » devant le commentaire
  du son, pour la voir sur les platines (le reste du commentaire est gardé).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from ..analysis import energy as E
from ..i18n import t

log = logging.getLogger(__name__)


def energy_of(track: Any) -> Tuple[int, bool]:
    """(énergie 1-10 ou 0 si inconnue, choisie à la main ?)."""
    try:
        v = E.lookup(Path(track.path).name, track.file_size)
    except Exception:  # noqa: BLE001
        return 0, False
    if not v:
        return 0, False
    return (v[1], True) if v[1] else (v[0], False)


def energy_values(track: Any) -> Dict[str, Any]:
    """Colonne « Énergie » : texte, valeur de tri, bulle et couleur (calme -> explosif)."""
    value, manual = energy_of(track)
    if not value:
        return {"energy": "", "energy__n": 0}
    from . import theme

    out: Dict[str, Any] = {"energy": str(value), "energy__n": value,
                           "energy__tip": t("energy.tip_manual" if manual else "energy.tip_auto", n=value)}
    if value >= 8:
        out["energy__color"] = theme.WARN
    return out


class EnergyService:
    """Tenu par le contrôleur (`controller.energy`)."""

    def __init__(self, controller: Any) -> None:
        self.ctrl = controller

    # ------------------------------------------------------------------ choix à la main
    def set_manual(self, tracks: Sequence[Any], value: int) -> int:
        """Énergie choisie (1-10) ou 0 (« Automatique ») ; renvoie le nombre de sons changés."""
        n = 0
        for x in tracks:
            try:
                if E.set_manual(Path(x.path).name, x.file_size, value):
                    n += 1
            except Exception:  # noqa: BLE001
                log.debug("Handled error in set_manual", exc_info=True)
        if n:
            self.write_comments(tracks)
            self.ctrl._emit("energy_changed")
        return n

    def menu_entries(self, tracks: Sequence[Any]) -> List[Any]:
        """Sous-menu « Énergie » : Automatique (valeur de l'analyse), puis 1 à 10 (✓ devant le choix fait)."""
        tracks = list(tracks)
        one = tracks[0] if len(tracks) == 1 else None
        value, manual = energy_of(one) if one is not None else (0, False)
        auto = 0
        if one is not None:
            v = E.lookup(Path(one.path).name, one.file_size)
            auto = v[0] if v else 0
        mark = "✓ "
        head = t("energy.auto_is", n=auto) if auto else t("energy.auto")
        out: List[Any] = [((mark if one is not None and not manual else "") + head,
                           lambda: self.set_manual(tracks, 0))]
        out.append(None)
        for n in range(1, 11):
            text = (mark if manual and value == n else "") + t(f"energy.level_{n}")
            out.append((text, lambda n=n: self.set_manual(tracks, n)))
        return out

    # ------------------------------------------------------------------ commentaire (option)
    def write_comments(self, tracks: Sequence[Any]) -> None:
        """Option « énergie dans le commentaire » : « E7 » devant le commentaire des sons (bibliothèque ouverte)."""
        if not getattr(self.ctrl.settings, "energy_comment", False):
            return
        lib = getattr(self.ctrl, "library", None)
        fn = getattr(lib, "set_energy_comments", None)
        if fn is None:
            return
        wanted = {}
        for x in tracks:
            value, _manual = energy_of(x)
            new = E.with_prefix(getattr(x, "comment", "") or "", value)
            if value and new != (getattr(x, "comment", "") or ""):
                wanted[x.content_id] = value
        if not wanted:
            return
        write = getattr(self.ctrl, "_write", None)
        if write is not None:
            write(lambda lib_: lib_.set_energy_comments(wanted), None, t("energy.comment_saved"))
        else:
            fn(wanted)
