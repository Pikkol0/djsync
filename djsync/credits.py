"""1.3.1 (C55) : remerciements. Un seul endroit pour les noms (pseudonymes, acceptés par chacun pour
être publiés) : README, Paramètres ▸ DJSync, onglet Retours et notes de release les reprennent."""
from __future__ import annotations

from typing import List

THANKS: List[str] = ["Tazyh", "Vogue", "Paf", "Kuss"]


def names(lang: str = "en") -> str:
    """« A, B, C and D » / « A, B, C et D »."""
    sep = " et " if lang == "fr" else " and "
    return ", ".join(THANKS[:-1]) + sep + THANKS[-1] if len(THANKS) > 1 else "".join(THANKS)


def thanks_text(lang: str = "en") -> str:
    if lang == "fr":
        return (f"Un grand merci à {names('fr')} pour la mise à disposition de leurs ressources, leurs tests et "
                "leur aide pour mener ce projet à bien.")
    return (f"A huge thank you to {names('en')} for sharing their resources and testing, and for helping make "
            "this project happen.")
