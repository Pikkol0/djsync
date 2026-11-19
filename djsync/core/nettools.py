"""1.4.3 (A1-13) : connexions HTTPS gardées ouvertes (une session `requests` par service, jamais partagée entre
services pour ne pas mélanger leurs cookies) et recherche des programmes (`shutil.which`) gardée en mémoire.

Mesure du 19/11 (portable Windows, 10 téléchargements) : ≈ 19 % du calcul en poignées de main HTTPS et
chargement des certificats, ≈ 1,2 s par téléchargement à relancer `shutil.which` pour deno, node, qjs, ffmpeg.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Any, Dict, Optional, Tuple

_sessions: Dict[str, Any] = {}
_sessions_lock = threading.Lock()

_which: Dict[Tuple[str, str], Tuple[Optional[str], float]] = {}
_which_lock = threading.Lock()
WHICH_MISS_TTL = 300.0          # un programme absent est recherché de nouveau après 5 min (installé entre-temps)


def session(service: str) -> Any:
    """Session `requests` propre au service (`"covers"`, `"archive"`…), créée au premier appel."""
    with _sessions_lock:
        s = _sessions.get(service)
        if s is None:
            import requests          # import tardif : démarrage plus rapide

            s = _sessions[service] = requests.Session()
        return s


def which(name: str) -> Optional[str]:
    """`shutil.which` gardé en mémoire (trouvé : jusqu'à la fin ; absent : 5 min), par valeur de PATH."""
    key = (name, os.environ.get("PATH", ""))
    now = time.monotonic()
    with _which_lock:
        hit = _which.get(key)
        if hit is not None and (hit[0] is not None and os.path.isfile(hit[0]) or
                                hit[0] is None and now - hit[1] < WHICH_MISS_TTL):
            return hit[0]
    found = shutil.which(name)
    with _which_lock:
        _which[key] = (found, now)
    return found


def clear() -> None:
    """Oublie tout (tests, changement de dossier des outils)."""
    with _which_lock:
        _which.clear()


# 1.4.3 (A3-3) : venu de ui.controller
_OFFLINE = ("max retries exceeded", "failed to establish a new connection", "getaddrinfo failed",
            "name or service not known", "temporary failure in name resolution", "nodename nor servname",
            "network is unreachable", "no route to host", "unable to connect to proxy", "connecttimeout",
            "connection refused", "urlopen error", "errno 11001")


def is_offline_error(exc: Any) -> bool:
    """Pas d'Internet (ou serveur injoignable) : message clair plutôt que la trace technique."""
    try:
        import requests

        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
    except ImportError:                 # pragma: no cover
        pass
    text = str(exc).lower()
    return any(k in text for k in _OFFLINE)
