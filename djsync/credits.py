"""1.3.1 (C55) : remerciements. Un seul endroit pour les noms (pseudonymes, acceptés par chacun pour
être publiés) : README, Paramètres ▸ DJSync, onglet Retours et notes de release les reprennent. Les
phrases sont dans les catalogues (clé « about.thanks »)."""
from __future__ import annotations

from typing import List

THANKS: List[str] = ["Tazyh", "Vogue", "Paf", "Kuss"]


def names(lang: str = "en") -> str:
    """« A, B, C and D » / « A, B, C et D »."""
    from .i18n import en, fr

    word = (fr if lang == "fr" else en).STRINGS["about.thanks_and"]
    return ", ".join(THANKS[:-1]) + f" {word} " + THANKS[-1] if len(THANKS) > 1 else "".join(THANKS)


def thanks_text(lang: str = "en") -> str:
    from .i18n import en, fr

    return (fr if lang == "fr" else en).STRINGS["about.thanks"].format(names=names(lang))
