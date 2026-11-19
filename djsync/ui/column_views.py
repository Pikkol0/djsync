"""1.4.3 (C214) : vues de colonnes de la Bibliothèque (« Vue : Préparer un set ▾ »).

Une vue = les colonnes affichées (les largeurs et l'ordre restent ceux du tableau). Cinq vues d'origine, que
l'utilisateur peut modifier (« Enregistrer ») ou rétablir, et des vues personnelles qu'il crée et nomme. La vue
choisie est retenue par liste (playlist, « Tous les sons »…) et par bibliothèque.

Réglage `library_views` : {"current": id, "custom": {id: {"name", "shown"}}, "saved": {id d'origine: shown},
"by_list": {"<bibliothèque>|<liste>": id}}. Logique sans Qt (testable seule).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..i18n import t

BUILTIN = ("discover", "prepare", "mix", "quality", "all")
# colonnes affichées par vue d'origine ; « discover » = l'affichage par défaut d'avant la 1.4.3 ; None = toutes
SHOWN: Dict[str, Optional[Tuple[str, ...]]] = {
    "discover": ("pos", "key", "artist", "bpm", "duration", "source", "added", "playlists", "cues"),
    "prepare": ("pos", "key", "artist", "bpm", "duration", "cues", "analysis", "playlists", "rating", "color",
                "mytags"),
    "mix": ("pos", "key", "artist", "bpm", "duration", "cues", "color", "mytags", "last_played"),
    "quality": ("pos", "artist", "duration", "format", "bitrate", "real", "rate", "size", "source", "dup", "path"),
    "all": None,
}
DEFAULT = "discover"
MAX_LISTS = 500


class ColumnViews:
    """Vues sur les colonnes facultatives `optional` d'un tableau ; `data` = le réglage (modifié sur place)."""

    def __init__(self, data: Dict[str, Any], optional: Sequence[str]) -> None:
        self.data = data
        self.optional = list(optional)
        for k in ("custom", "saved", "by_list"):
            if not isinstance(data.get(k), dict):
                data[k] = {}
        if data.get("current") not in self.ids():
            data["current"] = ""

    # ------------------------------------------------------------------ lecture
    def ids(self) -> List[str]:
        return list(BUILTIN) + list(self.data["custom"])

    def name(self, view: str) -> str:
        if view in BUILTIN:
            return t(f"views.{view}")
        return str((self.data["custom"].get(view) or {}).get("name") or view)

    def shown(self, view: str) -> Set[str]:
        if view in self.data["custom"]:
            return set(self.data["custom"][view].get("shown") or []) & set(self.optional)
        if view in self.data["saved"]:
            return set(self.data["saved"][view]) & set(self.optional)
        cols = SHOWN.get(view, SHOWN[DEFAULT])
        return set(self.optional) if cols is None else set(cols) & set(self.optional)

    def hidden(self, view: str) -> Set[str]:
        return set(self.optional) - self.shown(view)

    @property
    def current(self) -> str:
        return self.data.get("current") or ""

    def is_custom(self, view: str) -> bool:
        return view in self.data["custom"]

    def is_changed_builtin(self, view: str) -> bool:
        return view in BUILTIN and view in self.data["saved"]

    def modified(self, hidden: Iterable[str]) -> bool:
        """Les colonnes affichées ne sont plus celles de la vue en cours."""
        if not self.current:
            return False
        return (set(hidden) & set(self.optional)) != self.hidden(self.current)

    def matching(self, hidden: Iterable[str]) -> str:
        want = set(hidden) & set(self.optional)
        return next((v for v in self.ids() if self.hidden(v) == want), "")

    # ------------------------------------------------------------------ choix
    def first_use(self, hidden: Iterable[str]) -> str:
        """Pas encore de vue choisie : celle qui correspond aux colonnes affichées, sinon une vue personnelle
        « Mes colonnes » qui les garde (rien ne change à l'écran)."""
        if self.current:
            return self.current
        view = self.matching(hidden) or self.create(t("views.mine"), hidden)
        self.data["current"] = view
        return view

    def select(self, view: str, list_key: str = "") -> None:
        if view not in self.ids():
            return
        self.data["current"] = view
        if list_key:
            lists = self.data["by_list"]
            lists.pop(list_key, None)
            lists[list_key] = view
            while len(lists) > MAX_LISTS:
                lists.pop(next(iter(lists)))

    def for_list(self, list_key: str) -> str:
        view = self.data["by_list"].get(list_key) or ""
        return view if view in self.ids() else ""

    # ------------------------------------------------------------------ changements
    def save(self, view: str, hidden: Iterable[str]) -> None:
        shown = sorted(set(self.optional) - set(hidden))
        if view in self.data["custom"]:
            self.data["custom"][view]["shown"] = shown
        elif view in BUILTIN:
            self.data["saved"][view] = shown

    def restore_builtin(self, view: str) -> None:
        self.data["saved"].pop(view, None)

    def create(self, name: str, hidden: Iterable[str]) -> str:
        n = 1
        while f"v{n}" in self.data["custom"]:
            n += 1
        view = f"v{n}"
        self.data["custom"][view] = {"name": (name or "").strip() or t("views.mine"),
                                     "shown": sorted(set(self.optional) - set(hidden))}
        return view

    def rename(self, view: str, name: str) -> None:
        if view in self.data["custom"] and (name or "").strip():
            self.data["custom"][view]["name"] = name.strip()

    def delete(self, view: str) -> None:
        if view not in self.data["custom"]:
            return
        del self.data["custom"][view]
        for key in [k for k, v in self.data["by_list"].items() if v == view]:
            del self.data["by_list"][key]
        if self.current == view:
            self.data["current"] = DEFAULT
