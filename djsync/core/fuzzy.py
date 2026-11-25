"""1.4.3-rc.4 (B126) : quelle partie de rapidfuzz tourne (compilée ou Python pur), et pourquoi.

Module sans dépendance (ni numpy, ni le reste de DJSync) : l'autotest de l'exe l'appelle avant tout autre
import, dans l'état où l'app importe rapidfuzz. En 1.4.2 et 1.4.3-rc.3, l'exe Windows ne gardait la DLL
C++ de rapidfuzz (msvcp140-…, rangée par delvewheel dans `rapidfuzz.libs`) que dans `numpy.libs` :
l'autotest importait numpy d'abord et réussissait, l'app importait rapidfuzz d'abord et tournait en Python pur.
"""
from __future__ import annotations

import importlib

# modules compilés que rapidfuzz essaie avant de se rabattre sur `*_py` (rapidfuzz/_utils.fallback_import)
_COMPILED = ("rapidfuzz.fuzz_cpp", "rapidfuzz.process_cpp_impl", "rapidfuzz.distance.metrics_cpp")


def backend() -> str:
    """« compiled » si rapidfuzz utilise sa partie compilée, « python » s'il s'est rabattu sur son code Python
    pur (50 à 100 fois plus lent)."""
    from rapidfuzz import fuzz, process

    mods = (getattr(process.cdist, "__module__", "") or "", getattr(fuzz.ratio, "__module__", "") or "")
    return "python" if any(m.endswith("_py") for m in mods) else "compiled"


def fallback_reason() -> str:
    """Erreur d'import du premier module compilé qui ne se charge pas (rapidfuzz l'avale sans rien dire),
    « » si tous se chargent."""
    for name in _COMPILED:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - c'est l'information cherchée
            return f"{name}: {type(exc).__name__}: {exc}"
    return ""


def describe() -> str:
    """« compiled » ou « python (<raison>) », pour le journal et l'autotest."""
    kind = backend()
    if kind == "compiled":
        return kind
    reason = fallback_reason()
    return f"{kind} ({reason})" if reason else kind
