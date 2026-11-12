"""1.4.1 (C60) : colonne « Cues » commune aux listes de sons (Bibliothèque, Analyser, Doublons, Uniformiser,
Diagnostic) : une pastille par hot cue posé, à sa couleur, « — » si aucun ; bulle « 3 hot cues, 1 boucle,
2 mémoires » ; triable (nombre de hot cues). Les cues sont lus hors du fil de l'interface
(`controller.cue_marks`) puis posés sur les lignes déjà affichées."""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

from ...i18n import plural, t
from ..table import Column, Row

KEY = "cues"


def cue_column(width: int = 84) -> Column:
    return Column(KEY, t("track.cues"), width, "center", min_width=48, tip=t("track.cues_tip"),
                  sort=lambda r: r.values.get("cues__n", -1))


def cue_values(mark: Any) -> Dict[str, Any]:
    """Valeurs d'une ligne pour un `core.cue_marks.CueMark` (None : pas encore lu)."""
    if mark is None:
        return {KEY: "", "cues__dots": [], "cues__n": -1, "cues__tip": ""}
    parts = []
    if mark.hot:
        parts.append(plural("cues.hot_one", "cues.hot_many", len(mark.hot)))
    if mark.loops:
        parts.append(plural("cues.loop_one", "cues.loop_many", mark.loops))
    if mark.memories:
        parts.append(plural("cues.memory_one", "cues.memory_many", mark.memories))
    tip = ", ".join(parts) if parts else t("cues.none")
    text = mark.letters or ("·" if mark.memories else "—")
    return {KEY: text, "cues__dots": mark.colors, "cues__n": len(mark.hot) + (0.5 if mark.memories else 0),
            "cues__tip": tip}


def column_shown(table: Any) -> bool:
    try:
        i = table.column_index(KEY)
    except (KeyError, ValueError):
        return False
    return i >= 0 and not table.isColumnHidden(i)


def fill(table: Any, ctrl: Any, rows: Optional[Iterable[Row]] = None, track_of: Optional[Callable[[Row], Any]] = None,
         force: bool = False, done: Optional[Callable[[Dict[int, Any]], None]] = None) -> None:
    """Lit les cues des sons des lignes (toutes par défaut) et les pose sur le tableau. Rien si la colonne est
    masquée (sauf `force`). `track_of(row)` : le LibraryTrack d'une ligne (par défaut row.data)."""
    if not force and not column_shown(table):
        return
    get = track_of or (lambda r: r.data)
    pairs = []
    for r in list(rows if rows is not None else table.all_rows()):
        x = get(r)
        if x is not None and getattr(x, "content_id", None) is not None:
            pairs.append((r.iid, x))
    if not pairs:
        return

    def ok(marks: Dict[int, Any]) -> None:
        try:
            table.update_many({iid: cue_values(marks.get(int(x.content_id))) for iid, x in pairs})
        except RuntimeError:                                      # tableau fermé entre-temps
            return
        if done is not None:
            done(marks)

    ctrl.cue_marks([x for _iid, x in pairs], ok)
