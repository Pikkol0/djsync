"""1.4.1 (C60) : marqueur « cues placés » des listes de sons.

Pour chaque son : ses hot cues (pad et couleur), son nombre de boucles et de mémoires. Clé USB : lus dans les
fichiers d'analyse (Rekordbox n'écrit pas les cues dans exportLibrary.db), gardés en mémoire tant que ces
fichiers ne changent pas (date et taille) : une liste de 2 000 sons n'est lue qu'une fois. Bibliothèque de
l'ordinateur : table djmdCue de master.db, en une requête par lot.
Rien n'est écrit : lecture seule.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

SLOT_LETTERS = "ABCDEFGH"
CACHE_MAX = 30000


@dataclass(frozen=True)
class CueMark:
    hot: Tuple[Tuple[int, str], ...] = ()     # (pad 1..8, couleur « #rrggbb »), dans l'ordre des pads
    loops: int = 0                            # boucles (hot cues ou mémoires)
    memories: int = 0                         # mémoires (boucles comprises)

    @property
    def empty(self) -> bool:
        return not self.hot and not self.memories

    @property
    def letters(self) -> str:
        """« ABD » : pads posés (texte de la cellule, pour le tri et la recherche)."""
        return "".join(SLOT_LETTERS[s - 1] for s, _c in self.hot if 1 <= s <= 8)

    @property
    def colors(self) -> List[str]:
        return [c for _s, c in self.hot]


NONE = CueMark()


def _hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(v))) for v in rgb))


def summarize(cues: Iterable[Any]) -> CueMark:
    """Résumé d'une liste de `analysis.cues.Cue`."""
    hot: Dict[int, str] = {}
    loops = memories = 0
    for c in cues:
        if c.is_hot:
            hot.setdefault(int(c.slot), _hex(c.colour()))
        else:
            memories += 1
        if c.is_loop:
            loops += 1
    return CueMark(tuple(sorted(hot.items())), loops, memories)


# ------------------------------------------------------------------------------------------ lecture
_lock = threading.Lock()
_cache: Dict[Tuple[Any, ...], CueMark] = {}


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _stat(p: Path) -> Tuple[int, int]:
    try:
        st = p.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return 0, 0


def _usb_mark(lib: Any, track: Any) -> CueMark:
    from ..analysis.cues import read_cues

    rel = getattr(track, "analysis_path", None)
    if not rel:
        return NONE
    root = getattr(getattr(lib, "drive", None), "root", None)
    dat = Path(root) / str(rel).lstrip("/\\") if root is not None else Path(rel)
    ext = dat.with_suffix(".EXT")
    key = (str(dat).casefold(), _stat(dat), _stat(ext))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    try:
        data = dat.read_bytes()
    except OSError:
        return NONE
    try:
        mark = summarize(read_cues(data, ext.read_bytes() if ext.is_file() else None))
    except (OSError, ValueError) as exc:
        log.debug("Cues not read (%s): %s", dat, exc)
        mark = NONE
    with _lock:
        if len(_cache) > CACHE_MAX:
            _cache.clear()
        _cache[key] = mark
    return mark


def read_marks(lib: Any, tracks: Sequence[Any], should_stop: Optional[Any] = None) -> Dict[int, CueMark]:
    """content_id -> CueMark pour les sons donnés (hors du fil de l'interface)."""
    out: Dict[int, CueMark] = {}
    if lib is None or not tracks:
        return out
    many = getattr(lib, "track_cues_many", None)
    if many is not None:                                   # master.db : par lots, en une requête
        ids = [int(x.content_id) for x in tracks]
        for k in range(0, len(ids), 800):
            found = many(ids[k:k + 800])
            for cid in ids[k:k + 800]:
                out[cid] = summarize(found.get(cid, ()))
        return out
    usb = getattr(lib, "drive", None) is not None
    for x in tracks:
        if should_stop is not None and should_stop():
            break
        if usb:
            out[int(x.content_id)] = _usb_mark(lib, x)
            continue
        try:
            out[int(x.content_id)] = summarize(lib.track_cues(x.content_id))
        except Exception:  # noqa: BLE001 - un son illisible n'arrête pas la liste
            out[int(x.content_id)] = NONE
    return out
