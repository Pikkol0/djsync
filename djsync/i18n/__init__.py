"""Internationalisation : anglais par défaut, français en option.

    from djsync.i18n import t, set_language
    set_language("fr")
    t("tab.search")                  # -> "Recherche"
    t("lib.tracks", n=12)            # -> "12 titres"

Règles :
  * clé absente de la langue active -> repli sur l'anglais -> sinon la clé elle-même
    (visible à l'écran, donc repérable, mais jamais d'exception) ;
  * les catalogues sont de simples dictionnaires Python (`en.py`, `fr.py`) : pas de fichier à
    embarquer dans l'.exe PyInstaller ;
  * `LazyLabels` : dictionnaire dont les valeurs sont traduites à la lecture, pour les anciennes
    tables de libellés (SEARCH_MODE_LABELS…) qui doivent suivre un changement de langue.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterator, Mapping

from . import en, fr

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
LANGUAGES: Dict[str, str] = {"en": "English", "fr": "Français"}  # code -> nom affiché (dans sa propre langue)
_CATALOGS: Dict[str, Dict[str, str]] = {"en": en.STRINGS, "fr": fr.STRINGS}

_current = DEFAULT_LANGUAGE


def normalize_language(code: str) -> str:
    """'fr', 'FR', 'fr_FR', 'fr-CA' -> 'fr' ; langue inconnue -> anglais."""
    base = (code or "").strip().lower().replace("_", "-").split("-")[0]
    return base if base in _CATALOGS else DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    global _current
    _current = normalize_language(code)
    return _current


def get_language() -> str:
    return _current


def t(key: str, **params: Any) -> str:
    """Texte traduit ; `params` remplace les {champs} (ex. t("lib.tracks", n=3))."""
    text = _CATALOGS[_current].get(key)
    if text is None:
        text = _CATALOGS[DEFAULT_LANGUAGE].get(key, key)
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            log.warning("Paramètres incorrects pour la clé i18n %r : %r", key, params)
    return text


def plural(key_one: str, key_many: str, n: int, **params: Any) -> str:
    """Choisit la forme singulier/pluriel (1 -> singulier ; 0 et 1 sont singuliers en français)."""
    singular = n == 1 or (_current == "fr" and n == 0)
    return t(key_one if singular else key_many, n=n, **params)


class LazyLabels(Mapping):
    """Mapping clé -> texte traduit À LA LECTURE (suit le changement de langue)."""

    def __init__(self, keys: Callable[[], Mapping[Any, str]]) -> None:
        self._keys = keys

    def __getitem__(self, item: Any) -> str:
        return t(self._keys()[item])

    def __iter__(self) -> Iterator[Any]:
        return iter(self._keys())

    def __len__(self) -> int:
        return len(self._keys())
