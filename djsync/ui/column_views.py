"""1.4.3 (C214) : vues de colonnes de la Bibliothèque (« Préparer un set ▾ », à côté de « Colonnes »).

Une vue = les colonnes affichées et leur ordre (les largeurs restent celles du tableau). Quatre vues d'origine
(1.4.3-rc.2, C218 : « Découvrir / ranger » et « Mixer » retirées), que l'utilisateur peut modifier
(« Enregistrer ») ou rétablir, et des vues personnelles qu'il crée et nomme. La vue choisie est retenue par liste
(playlist, « Tous les sons »…) et par bibliothèque.

Réglage `library_views` : {"current": id, "custom": {id: {"name", "shown", "order"}}, "saved": {id d'origine:
shown}, "saved_order": {id d'origine: ordre}, "by_list": {"<bibliothèque>|<liste>": id}}. Logique sans Qt.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..i18n import t

BUILTIN = ("essential", "prepare", "quality", "all")
# 1.4.3-rc.2 (C218) : colonnes de chaque vue d'origine, dans l'ordre : # (dans une playlist), titre (avec la
# pochette) puis artiste, puis ce que la vue sert à juger, le rangement, et les colonnes techniques à la fin
ORDER: Dict[str, Tuple[str, ...]] = {
    "essential": ("pos", "title", "artist", "bpm", "key", "duration", "playlists", "added"),
    "prepare": ("pos", "title", "artist", "bpm", "key", "duration", "analysis", "cues", "rating", "color",
                "mytags", "last_played", "playlists"),
    "quality": ("pos", "title", "artist", "real", "format", "bitrate", "rate", "source", "dup", "size", "path"),
}
ORDER["all"] = tuple(dict.fromkeys(ORDER["essential"] + ORDER["prepare"] + ORDER["quality"]))
# colonnes affichées par vue d'origine (None = toutes)
SHOWN: Dict[str, Optional[Tuple[str, ...]]] = {k: ORDER[k] for k in ("essential", "prepare", "quality")}
SHOWN["all"] = None
DEFAULT = "essential"
RETIRED = {"discover": "essential", "mix": "prepare"}     # 1.4.3-rc.2 (C218) : vues d'origine retirées
# affichage par défaut d'avant la 1.4.3-rc.2 (« Découvrir / ranger ») : devient « Essentiel » à la première ouverture
LEGACY_DEFAULT = ("pos", "key", "artist", "bpm", "duration", "source", "added", "playlists", "cues")
MAX_LISTS = 500


class ColumnViews:
    """Vues sur les colonnes facultatives `optional` d'un tableau ; `data` = le réglage (modifié sur place)."""

    def __init__(self, data: Dict[str, Any], optional: Sequence[str]) -> None:
        self.data = data
        self.optional = list(optional)
        for k in ("custom", "saved", "saved_order", "by_list"):
            if not isinstance(data.get(k), dict):
                data[k] = {}
        self.migrated = self._retire_old_views()
        if data.get("current") not in self.ids():
            data["current"] = ""

    def _retire_old_views(self) -> bool:
        """1.4.3-rc.2 (C218) : « Découvrir / ranger » et « Mixer » retirées. Modifiée par l'utilisateur, une vue
        est gardée telle quelle comme vue personnelle sous son ancien nom ; sinon elle devient « Essentiel »
        (« Découvrir / ranger ») ou « Préparer un set » (« Mixer »). Vrai si la vue en cours a changé."""
        data = self.data
        mapping: Dict[str, str] = {}
        for old, new in RETIRED.items():
            if old in data["saved"]:
                mapping[old] = self.create(t(f"views.{old}"), (), shown=data["saved"].pop(old))
            else:
                mapping[old] = new
            data["saved_order"].pop(old, None)
        changed = data.get("current") in mapping
        if changed:
            data["current"] = mapping[data["current"]]
        for key, view in list(data["by_list"].items()):
            if view in mapping:
                data["by_list"][key] = mapping[view]
        return changed

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

    def order(self, view: str) -> List[str]:
        """1.4.3-rc.2 (C218) : ordre des colonnes de la vue (les colonnes absentes gardent leur place)."""
        if view in self.data["custom"]:
            return list(self.data["custom"][view].get("order") or [])
        if view in self.data["saved_order"]:
            return list(self.data["saved_order"][view])
        return list(ORDER.get(view, ()))

    @property
    def current(self) -> str:
        return self.data.get("current") or ""

    def is_custom(self, view: str) -> bool:
        return view in self.data["custom"]

    def is_changed_builtin(self, view: str) -> bool:
        return view in BUILTIN and view in self.data["saved"]

    def modified(self, hidden: Iterable[str], order: Optional[Sequence[str]] = None) -> bool:
        """Les colonnes affichées (ou, 1.4.3-rc.2, leur ordre) ne sont plus celles de la vue en cours."""
        if not self.current:
            return False
        if (set(hidden) & set(self.optional)) != self.hidden(self.current):
            return True
        return order is not None and not self.same_order(self.current, order, hidden)

    def same_order(self, view: str, order: Sequence[str], hidden: Iterable[str] = ()) -> bool:
        """Les colonnes affichées que la vue range sont-elles dans l'ordre de la vue ?"""
        wanted = [k for k in self.order(view) if k not in set(hidden)]
        if not wanted:
            return True
        keep = set(wanted)
        return [k for k in order if k in keep] == [k for k in wanted if k in set(order)]

    def matching(self, hidden: Iterable[str]) -> str:
        want = set(hidden) & set(self.optional)
        return next((v for v in self.ids() if self.hidden(v) == want), "")

    # ------------------------------------------------------------------ choix
    def first_use(self, hidden: Iterable[str]) -> str:
        """Pas encore de vue choisie : celle qui correspond aux colonnes affichées, sinon une vue personnelle
        « Mes colonnes » qui les garde (rien ne change à l'écran)."""
        if self.current:
            return self.current
        view = self.matching(hidden)
        if not view and set(self.optional) - set(hidden) == set(LEGACY_DEFAULT) & set(self.optional):
            view = DEFAULT                               # 1.4.3-rc.2 (C218) : colonnes par défaut d'avant
        view = view or self.create(t("views.mine"), hidden)
        self.data["current"] = view
        self.migrated = True                              # ordre de la vue appliqué à la première ouverture
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
    def save(self, view: str, hidden: Iterable[str], order: Optional[Sequence[str]] = None) -> None:
        shown = sorted(set(self.optional) - set(hidden))
        if view in self.data["custom"]:
            self.data["custom"][view]["shown"] = shown
            if order is not None:
                self.data["custom"][view]["order"] = list(order)
        elif view in BUILTIN:
            self.data["saved"][view] = shown
            if order is not None:
                self.data["saved_order"][view] = list(order)

    def restore_builtin(self, view: str) -> None:
        self.data["saved"].pop(view, None)
        self.data["saved_order"].pop(view, None)

    def create(self, name: str, hidden: Iterable[str], order: Optional[Sequence[str]] = None,
               shown: Optional[Iterable[str]] = None) -> str:
        n = 1
        while f"v{n}" in self.data["custom"]:
            n += 1
        view = f"v{n}"
        cols = sorted(set(shown)) if shown is not None else sorted(set(self.optional) - set(hidden))
        self.data["custom"][view] = {"name": (name or "").strip() or t("views.mine"), "shown": cols}
        if order:
            self.data["custom"][view]["order"] = list(order)
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
