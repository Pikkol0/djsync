"""1.4.3 (C199, option A) : aperçu d'une fusion, « style GitHub » : ce qui reste (=), ce qui est ajouté (+) et ce qui
est retiré (−), par playlist et par cue, avant de confirmer.

Niveau de détail retenu : une ligne par playlist (pas par son des playlists) et une ligne par cue (hot cues A à H,
mémoires) ; les versions supprimées et le titre corrigé ont aussi leur ligne. Fonction pure : la fenêtre lui
passe ce qu'elle a déjà lu (playlists et cues de chaque version).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

KEEP, ADD, REMOVE = "=", "+", "−"


@dataclass(frozen=True)
class Line:
    sign: str           # KEEP, ADD, REMOVE
    section: str        # "info", "tracks", "playlists", "cues"
    text: str


def cue_text(c: Any) -> str:
    """« A 1:02 », « A 1:02 → 1:10 » (boucle), « Mémoire 0:32 » ; le nom du cue à la suite s'il en a un."""
    from ..i18n import t

    def mmss(ms: int) -> str:
        s = max(0, int(ms)) // 1000
        return f"{s // 60}:{s % 60:02d}"

    slot = int(getattr(c, "slot", 0) or 0)
    head = "ABCDEFGH"[slot - 1] if 1 <= slot <= 8 else t("merge.memory")
    out = f"{head} {mmss(c.ms)}"
    loop = getattr(c, "loop_ms", None)
    if loop and loop > c.ms:
        out += f" → {mmss(loop)}"
    name = (getattr(c, "name", "") or "").strip()
    return t("merge.cue_named", cue=out, name=name) if name else out


def _cue_key(c: Any) -> tuple:
    return int(getattr(c, "slot", 0) or 0), int(c.ms), int(getattr(c, "loop_ms", 0) or 0)


def build(keep: Any, others: Sequence[Any], playlists: Dict[int, List[str]], cues: Dict[int, List[Any]],
          cues_from: Optional[int] = None, new_title: Optional[str] = None, new_artist: Optional[str] = None,
          files_deleted: bool = True, cues_if_none: bool = False) -> List[Line]:
    """Lignes de l'aperçu. `cues_from` : version dont les cues sont repris (None = ceux de la version gardée).
    `cues_if_none` (fichier introuvable) : les cues de l'autre version ne passent que si la version gardée n'a
    aucun hot cue."""
    from ..i18n import t

    out: List[Line] = []
    if new_title is not None or new_artist is not None:
        old = f"{keep.artist or '—'} — {keep.title}"
        new = f"{new_artist if new_artist is not None else keep.artist or '—'} — " \
              f"{new_title if new_title is not None else keep.title}"
        out += [Line(REMOVE, "info", old), Line(ADD, "info", new)]
    out.append(Line(KEEP, "tracks", t("merge.kept", name=f"{keep.artist or '—'} — {keep.title}")))
    for o in others:
        key = "merge.removed_file" if files_deleted else "merge.removed_entry"
        out.append(Line(REMOVE, "tracks", t(key, name=f"{o.artist or '—'} — {o.title}")))
    mine = set(playlists.get(keep.content_id) or [])
    theirs: Dict[str, None] = {}
    for o in others:
        for name in playlists.get(o.content_id) or []:
            theirs.setdefault(name, None)
    for name in sorted(mine | set(theirs), key=str.lower):
        if name in mine:
            out.append(Line(KEEP, "playlists", name))
        else:
            out.append(Line(ADD, "playlists", t("merge.playlist_added", name=name)))
    if not mine and not theirs:
        out.append(Line(KEEP, "playlists", t("merge.no_playlist")))
    kept = list(cues.get(keep.content_id) or [])
    src = None if cues_from is None or int(cues_from) == int(keep.content_id) else int(cues_from)
    if src is not None and cues_if_none and any(getattr(c, "slot", 0) for c in kept):
        src = None                                        # la version gardée a déjà des hot cues : rien ne passe
    if src is None:
        for c in sorted(kept, key=_cue_key):
            out.append(Line(KEEP, "cues", cue_text(c)))
    else:
        new = list(cues.get(src) or [])
        old_k, new_k = {_cue_key(c) for c in kept}, {_cue_key(c) for c in new}
        for c in sorted(kept, key=_cue_key):
            out.append(Line(KEEP if _cue_key(c) in new_k else REMOVE, "cues", cue_text(c)))
        for c in sorted(new, key=_cue_key):
            if _cue_key(c) not in old_k:
                out.append(Line(ADD, "cues", cue_text(c)))
    if not any(line.section == "cues" for line in out):
        out.append(Line(KEEP, "cues", t("merge.no_cue")))
    return out


def counts(lines: Sequence[Line]) -> Dict[str, int]:
    return {s: sum(1 for x in lines if x.sign == s) for s in (KEEP, ADD, REMOVE)}


def to_html(lines: Sequence[Line], ok: str, err: str, dim: str) -> str:
    """Texte riche : une section par sujet, « + » en vert, « − » en rouge, « = » en gris."""
    from html import escape

    from ..i18n import t

    color = {ADD: ok, REMOVE: err, KEEP: dim}
    parts: List[str] = []
    for section in ("info", "tracks", "playlists", "cues"):
        rows = [x for x in lines if x.section == section]
        if not rows:
            continue
        parts.append(f"<b>{escape(t('merge.section_' + section))}</b>")
        for x in rows:
            parts.append(f"<span style='color:{color[x.sign]}; font-family: monospace;'>{escape(x.sign)}</span>"
                         f"&nbsp;<span style='color:{color[x.sign] if x.sign != KEEP else 'inherit'};'>"
                         f"{escape(x.text)}</span>")
    return "<br>".join(parts)
