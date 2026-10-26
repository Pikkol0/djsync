"""Sons dont le tempo change (1.3.0, C16) : à faire vérifier par l'utilisateur.

À chaque analyse qui pose une grille VARIABLE, le son est noté ici avec son tempo le plus lent et le
plus rapide. La page « Tempos à vérifier » les liste ; pour chacun, l'utilisateur garde la grille qui
suit le tempo ou passe en tempo constant. Une nouvelle analyse à tempo constant retire le son.

Clé d'un son : les trois derniers éléments de son chemin, en minuscules (« artiste/album/fichier.m4a ») :
la même clé portable reste valable quand la lettre de lecteur change d'un ordinateur à l'autre.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

TODO, KEPT, CONSTANT = "todo", "kept", "constant"


def key_for(path: Any) -> str:
    parts = PurePath(str(path).replace("\\", "/")).parts
    return "/".join(parts[-3:]).lower()


class TempoReview:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.items: Dict[str, Dict[str, Any]] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.items = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def record(self, path: Any, tempos: List[float]) -> None:
        """Résultat d'une analyse : tempo variable -> à vérifier ; constant -> retiré."""
        key = key_for(path)
        with self._lock:
            if tempos and max(tempos) - min(tempos) >= 0.5:
                self.items[key] = {"min": round(min(tempos), 2), "max": round(max(tempos), 2), "status": TODO}
            elif key in self.items:
                del self.items[key]
            else:
                return
            self._save()

    def set_status(self, path: Any, status: str) -> None:
        key = key_for(path)
        with self._lock:
            if key in self.items:
                self.items[key]["status"] = status
                self._save()

    def get(self, path: Any) -> Optional[Dict[str, Any]]:
        return self.items.get(key_for(path))

    def pending_keys(self) -> List[str]:
        return [k for k, v in self.items.items() if v.get("status") == TODO]
