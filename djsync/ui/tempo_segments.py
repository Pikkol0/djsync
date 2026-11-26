"""1.4.4 (C221) : tempo variable dans « Grille et cues » : passages (segments) et repères éditables.

* bande des passages sous la forme d'onde, chacun avec son BPM ; BPM sous la souris et BPM au curseur (mis à
  jour pendant la lecture) : une recherche dichotomique dans la grille, rien n'est recalculé en bougeant ;
* repères « changement de tempo » et « nouveau son », posés sur un temps : ajouter, déplacer (glisser la
  poignée en bas de la forme d'onde), supprimer ; BPM d'un passage corrigé ; la grille est recalculée depuis
  les passages (un tempo par temps, PQTZ, comme la grille par passage de C16) seulement quand le tempo change ;
* un repère « nouveau son » est aussi une mémoire nommée (visible sur les platines) ;
* type détecté corrigé à la main ; repères et type gardés à la réanalyse (registre tempo.json, tempo_profile).

Un passage : (début ms, BPM, numéro 1-4 de son premier temps, genre "" | "tempo" | "sound") ; 1.4.4 (B131) :
plus forme (palier, rampe, libre), BPM de fin et origine (analyse, main). B131 / C237 : outils de grille appliqués au
passage sous le curseur (ou à tout le son), type du son qui change vraiment la grille, analyse d'un passage ou de
tous, bande fine des passages seulement si le tempo change, tableau des passages (onglet Tempo).
"""
from __future__ import annotations

import logging
from bisect import bisect_left, bisect_right
from typing import Any, List, Optional, Sequence, Tuple

from ..analysis import grid as G
from .tempo_grids import changes, is_constant, split_beats

log = logging.getLogger(__name__)

Beat = Tuple[int, int, int]            # (numéro 1-4, tempo x100, ms)
Seg = tuple                             # (début ms, BPM, numéro du 1er temps, genre[, forme, BPM de fin, origine])
KIND_CHOICES = ("", "none", "switch", "ramp", "set", "live")


# ------------------------------------------------------------------------------- calculs (sans Qt)
# 1.4.4 (B131) : un passage peut porter 3 valeurs de plus : forme ("step" palier, "ramp" rampe, "free" libre), BPM de
# fin (rampe) et origine ("auto" analyse, "main" retouché à la main). Un palier de l'analyse reste un 4-uplet (format
# de C221) ; un repère posé (genre non vide) en 4-uplet est « main ».
def seg(st: float, bpm: float, n: int, kind: str = "", shape: str = "step", end: Optional[float] = None,
        origin: str = "auto") -> tuple:
    if shape == "step" and origin == ("main" if kind else "auto"):
        return (int(st), float(bpm), int(n), kind)
    return (int(st), float(bpm), int(n), kind, shape, float(bpm if end is None else end), origin)


def shape_of(s: Sequence[Any]) -> str:
    return s[4] if len(s) > 4 else "step"


def end_of(s: Sequence[Any]) -> float:
    return float(s[5]) if len(s) > 4 else float(s[1])


def origin_of(s: Sequence[Any]) -> str:
    return s[6] if len(s) > 4 else ("main" if s[3] else "auto")


def replace(s: Sequence[Any], **kw: Any) -> tuple:
    """Copie d'un passage avec des champs changés (st, bpm, n, kind, shape, end, origin)."""
    d = {"st": s[0], "bpm": s[1], "n": s[2], "kind": s[3], "shape": shape_of(s), "end": end_of(s),
         "origin": origin_of(s)}
    d.update(kw)
    if d["shape"] == "step" and "end" not in kw:
        d["end"] = d["bpm"]
    return seg(d["st"], d["bpm"], d["n"], d["kind"], d["shape"], d["end"], d["origin"])


def _median_bpm(beats: Sequence[Beat], i: int, j: int) -> float:
    tempos = sorted(b[1] for b in beats[i:j]) or [beats[i][1]]
    return tempos[len(tempos) // 2] / 100.0


def segments_of(beats: Sequence[Beat], keep: Sequence[Tuple[float, str]] = ()) -> List[Seg]:
    """Passages d'une grille : un par changement de tempo (grille par passage), un seul pour une grille fixe ou
    qui suit un live ; plus les repères `keep` (ms, genre) recalés sur le temps le plus proche."""
    if not beats:
        return []
    kinds = {}
    if not is_constant(beats):
        found = changes(beats)
        if len(found) <= max(2, len(beats) // 16):          # grille variable de live : pas de passages
            kinds = {i: "tempo" for i, _a, _b in found}
    for ms, kind in keep:
        i = G.nearest(beats, ms)
        if i > 0 and (kind == "sound" or i not in kinds):
            kinds[i] = kind or "tempo"
    idx = [0] + sorted(kinds)
    out: List[Seg] = []
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < len(idx) else len(beats)
        out.append((int(beats[i][2]), _median_bpm(beats, i, j), int(beats[i][0]), "" if k == 0 else kinds[i]))
    return out


def segments_of_marks(marks: Sequence[Sequence[Any]]) -> List[Seg]:
    """1.4.4 (B131) : passages enregistrés (tempo.json) : formes et origines comprises."""
    from ..analysis import tempo_profile as TP

    out: List[Seg] = []
    for m in sorted(marks, key=lambda m: float(m[0])):
        st, bpm, down = float(m[0]) * 1000.0, float(m[1]), float(m[2])
        n = (int(round((float(m[0]) - down) * bpm / 60.0)) % 4) + 1
        out.append(seg(st, bpm, n, m[3] if out else "", TP.mark_shape(m), TP.mark_end(m), TP.mark_origin(m)))
    return out


def to_sections(segs: Sequence[Seg]) -> List[Tuple[float, float, float]]:
    """Passages au format de tempo_profile.section_beats : (début s, BPM, un 1er temps de mesure s)."""
    out = []
    for s in segs:
        st, bpm, n = s[0], float(s[1]), s[2]
        out.append((st / 1000.0, bpm, st / 1000.0 - (n - 1) * 60.0 / bpm))
    return out


def to_marks(segs: Sequence[Seg]) -> List[tuple]:
    """Ce qui est gardé dans tempo.json (passages, genre de chaque repère ; 1.4.4 (B131) : forme, BPM de fin et
    origine quand ils comptent)."""
    out = []
    for (a, b, c), s in zip(to_sections(segs), segs):
        if len(s) > 4:
            out.append((a, b, c, s[3], shape_of(s), end_of(s), origin_of(s)))
        else:
            out.append((a, b, c, s[3]))
    return out


def build(segs: Sequence[Seg], duration_ms: int) -> List[Beat]:
    """Grille recalculée depuis les passages : un tempo par temps (PQTZ). Que des paliers : grille de C221."""
    if all(shape_of(s) == "step" for s in segs):
        return split_beats(to_sections(segs), duration_ms)
    from ..analysis import tempo_profile as TP

    return [(n, int(round(bpm * 100)), int(round(tt * 1000)))
            for n, tt, bpm in TP.marks_beats(to_marks(segs), duration_ms / 1000.0)]


def layout(segs: Sequence[Seg]) -> List[tuple]:
    """Changements de tempo seulement (passages voisins au même BPM réunis) : si rien ne change ici, la grille
    reste telle quelle (un repère « nouveau son » ne touche pas une grille de live). 1.4.4 (B131) : une rampe ou
    un passage libre compte toujours."""
    out: List[tuple] = []
    for s in segs:
        st, bpm, shape = s[0], s[1], shape_of(s)
        if shape != "step":
            out.append((st, round(bpm, 2), shape, round(end_of(s), 2)))
        elif not out or len(out[-1]) > 2 or abs(out[-1][1] - bpm) > 0.004:
            out.append((st, round(bpm, 2)))
    return out


def segment_at(segs: Sequence[Seg], ms: float) -> int:
    k = 0
    for i, s in enumerate(segs):
        if ms + 0.5 >= s[0]:
            k = i
    return k


def bounds(segs: Sequence[Seg], k: int, duration_ms: int) -> Tuple[int, int]:
    """Début et fin (ms) du passage `k` (le 1er commence au début du son)."""
    lo = 0 if k == 0 else int(segs[k][0])
    hi = int(segs[k + 1][0]) if k + 1 < len(segs) else int(duration_ms)
    return lo, hi


def add_mark(segs: Sequence[Seg], beats: Sequence[Beat], ms: float, kind: str) -> Tuple[List[Seg], Optional[int]]:
    """Repère sur le temps le plus proche de `ms` ; un repère déjà là change de genre. (passages, indice).
    1.4.4 (B131) : une rampe coupée en deux reste continue (tempo du temps coupé au bout de l'une, au début de
    l'autre)."""
    segs = list(segs)
    i = G.nearest(beats, ms)
    if i <= 0 or not segs:
        return segs, None
    st, n = int(beats[i][2]), int(beats[i][0])
    for k, s in enumerate(segs):
        if s[0] == st:
            if k == 0:
                return segs, None
            segs[k] = replace(s, kind=kind)
            return segs, k
    k = segment_at(segs, st)
    parent = segs[k]
    if shape_of(parent) == "ramp":
        here = beats[i][1] / 100.0
        segs[k] = replace(parent, end=here)
        segs.insert(k + 1, seg(st, here, n, kind, "ramp", end_of(parent), "main"))
    else:
        segs.insert(k + 1, (st, parent[1], n, kind))
    return segs, k + 1


def remove_mark(segs: Sequence[Seg], k: int) -> List[Seg]:
    segs = list(segs)
    if 1 <= k < len(segs):
        del segs[k]
    return segs


def move_targets(segs: Sequence[Seg], beats: Sequence[Beat], k: int, duration_ms: int) -> List[Tuple[int, int]]:
    """Temps (ms, numéro) où le repère `k` peut aller, entre ses voisins. Sans changement de tempo, ceux de la
    grille ; sinon, avant : les temps du passage `k` prolongés vers l'arrière ; après : ceux du passage
    précédent prolongé (calculé une fois, à la prise du repère)."""
    if not 1 <= k < len(segs):
        return []
    lo = segs[k - 1][0]
    hi = segs[k + 1][0] if k + 1 < len(segs) else duration_ms
    st, bpm, n = segs[k][0], segs[k][1], segs[k][2]
    if abs(segs[k - 1][1] - bpm) <= 0.004 and shape_of(segs[k]) == shape_of(segs[k - 1]) == "step":
        return [(b[2], b[0]) for b in beats if lo < b[2] < hi]
    out = []
    step = 60000.0 / bpm
    m = 1
    while st - m * step > lo + 1:
        out.append((int(round(st - m * step)), ((n - 1 - m) % 4) + 1))
        m += 1
    out.reverse()
    out.append((st, n))
    after = build(remove_mark(segs, k), duration_ms)
    out += [(b[2], b[0]) for b in after if st < b[2] < hi]
    return out


def move_mark(segs: Sequence[Seg], k: int, target: Tuple[int, int]) -> List[Seg]:
    segs = list(segs)
    if 1 <= k < len(segs):
        segs[k] = replace(segs[k], st=int(target[0]), n=int(target[1]))
    return segs


def set_segment_bpm(segs: Sequence[Seg], k: int, bpm: float, anchor: Optional[Tuple[float, int]] = None) -> List[Seg]:
    """BPM du passage `k`. Le passage garde son début (le repère) ; le premier passage reste calé sur le temps
    sélectionné `anchor` (ms, numéro) s'il est dedans, et repart du début du son. 1.4.4 (B131) : une rampe
    devient un palier ; le passage est marqué retouché à la main."""
    segs = list(segs)
    if not 0 <= k < len(segs) or bpm <= 0:
        return segs
    st, n = segs[k][0], segs[k][2]
    if k == 0 and anchor is not None and (len(segs) == 1 or anchor[0] < segs[1][0]):
        step = 60000.0 / bpm
        m = int(anchor[0] // step)
        st, n = int(round(anchor[0] - m * step)), ((anchor[1] - 1 - m) % 4) + 1
    was_step_auto = len(segs[k]) <= 4
    if was_step_auto:
        segs[k] = (st, float(bpm), n, segs[k][3])
    else:
        segs[k] = replace(segs[k], st=st, bpm=float(bpm), n=n, shape="step", end=float(bpm), origin="main")
    return segs


def set_shape(segs: Sequence[Seg], k: int, shape: str, bpm: float, end: Optional[float] = None) -> List[Seg]:
    """1.4.4 (B131) : forme d'un passage choisie à la main (palier, rampe de `bpm` à `end`, libre)."""
    segs = list(segs)
    if 0 <= k < len(segs) and bpm > 0:
        segs[k] = replace(segs[k], bpm=float(bpm), shape=shape, end=float(end if end else bpm), origin="main")
    return segs


def apply_result(segs: Sequence[Seg], k: int, res: Any, duration_ms: int) -> List[Seg]:
    """1.4.4 (B131) : résultat de l'analyse d'un passage (segment_tempo.SegmentResult) : forme, tempos, 1er temps et
    son numéro ; la borne est recalée sur ce 1er temps (jamais au-delà des bornes voisines)."""
    segs = list(segs)
    if not 0 <= k < len(segs):
        return segs
    lo, hi = bounds(segs, k, duration_ms)
    st = int(res.first_ms) if k else int(res.first_ms)
    if k and not (segs[k - 1][0] < st < hi):
        st = segs[k][0]
    segs[k] = replace(segs[k], st=st, bpm=float(res.bpm), n=int(res.number), shape=res.shape,
                      end=float(res.bpm_end or res.bpm), origin="auto")
    if k == 0:
        segs[0] = replace(segs[0], st=st)
    return segs


def splice(old: Sequence[Beat], new: Sequence[Beat], lo_ms: float, hi_ms: float) -> List[Beat]:
    """1.4.4 (B131) : « ce passage » : temps de `new` entre les bornes (à un demi-temps près, pour garder le temps
    de la borne), ceux de `old` ailleurs."""
    def half(beats: Sequence[Beat], ms: float) -> float:
        if len(beats) < 2:
            return 0.0
        i = max(1, min(len(beats) - 1, G.nearest(beats, ms)))
        return abs(beats[i][2] - beats[i - 1][2]) / 2.0

    a = lo_ms - half(old, lo_ms) if lo_ms > 0 else -1e9
    b = hi_ms - half(old, hi_ms)
    before = [x for x in old if x[2] < a]
    after = [x for x in old if x[2] >= b]
    mid = [x for x in new if a <= x[2] < b]
    if before and mid and mid[0][2] - before[-1][2] < 0.5 * (60000.0 / max(1, mid[0][1] / 100.0)):
        mid = mid[1:]
    if after and mid and after[0][2] - mid[-1][2] < 0.5 * (60000.0 / max(1, mid[-1][1] / 100.0)):
        mid = mid[:-1]
    return list(before) + list(mid) + list(after)


def resegment(segs: Sequence[Seg], beats: Sequence[Beat], k: Optional[int] = None) -> List[Seg]:
    """1.4.4 (B131) : bornes recalées sur le temps le plus proche de la nouvelle grille ; le passage `k` (outil
    appliqué à « ce passage ») prend le BPM médian de ses temps et devient un palier retouché à la main."""
    if not beats:
        return list(segs)
    out: List[Seg] = []
    for i, s in enumerate(segs):
        j = 0 if i == 0 else G.nearest(beats, s[0])
        if i and out and beats[j][2] <= out[-1][0]:
            continue                                      # deux bornes sur le même temps : fusion
        out.append(replace(s, st=int(beats[j][2]), n=int(beats[j][0])) if i else replace(s, st=int(beats[0][2]),
                                                                                         n=int(beats[0][0])))
    if k is not None and 0 <= k < len(out):
        lo = out[k][0]
        hi = out[k + 1][0] if k + 1 < len(out) else float("inf")
        idx = [i for i, b in enumerate(beats) if lo <= b[2] < hi]
        if idx:
            bpm = _median_bpm(beats, idx[0], idx[-1] + 1)
            out[k] = replace(out[k], bpm=bpm, shape="step", end=bpm, origin="main")
    return out


def tempo_at(times: Sequence[int], beats: Sequence[Beat], ms: float) -> float:
    """BPM du temps qui contient `ms` (celui écrit dans PQTZ). `times` : positions des temps (en cache)."""
    if not beats:
        return 0.0
    i = max(0, min(len(beats) - 1, bisect_right(times, ms) - 1))
    return beats[i][1] / 100.0


# ------------------------------------------------------------------------------- interface
def _qt() -> Any:
    from PySide6 import QtCore, QtGui, QtWidgets

    return QtCore, QtGui, QtWidgets


def make_band(tools: "SegmentTools") -> Any:
    """Bande des passages, sur toute la longueur du son, sous la forme d'onde d'ensemble. 1.4.4 (B131) : 10 px,
    affichée seulement s'il y a plus d'un passage ; clic = curseur à l'endroit cliqué ; survol = passage et BPM."""
    QtCore, QtGui, QtWidgets = _qt()
    from . import theme

    class SegmentBand(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.tools = tools
            self.setFixedHeight(theme.px(10))
            self.setMouseTracking(True)
            self.setCursor(QtCore.Qt.PointingHandCursor)

        def _ms(self, x: float) -> float:
            return max(0.0, x) / max(1, self.width()) * max(1, self.tools.ed.duration_ms)

        def _x(self, ms: float) -> float:
            return ms / max(1, self.tools.ed.duration_ms) * self.width()

        def paintEvent(self, _e: Any) -> None:  # noqa: N802
            ed, segs = self.tools.ed, self.tools.segs
            p = QtGui.QPainter(self)
            w, h = self.width(), self.height()
            p.fillRect(self.rect(), QtGui.QColor(theme.SURFACE))
            cur = segment_at(segs, ed.cursor_ms) if segs else -1
            for k, sg in enumerate(segs):
                x0 = 0.0 if k == 0 else self._x(sg[0])
                x1 = self._x(segs[k + 1][0]) if k + 1 < len(segs) else float(w)
                tone = 0.40 if k == cur else (0.14 if k % 2 == 0 else 0.24)
                col = QtGui.QColor(theme.mix(theme.SURFACE, SegmentTools.shape_colour(shape_of(sg)), tone))
                p.fillRect(QtCore.QRectF(x0, 0, max(1.0, x1 - x0), h), col)
                if k:
                    p.setPen(QtGui.QPen(QtGui.QColor(SegmentTools.colour(sg[3])), theme.px(2)))
                    p.drawLine(QtCore.QPointF(x0, 0), QtCore.QPointF(x0, h))
            from .cursor import draw_cursor

            draw_cursor(p, self._x(ed.cursor_ms), 0, h, glow=False)
            p.end()

        def mouseMoveEvent(self, e: Any) -> None:  # noqa: N802
            ms = self._ms(e.position().x())
            self.tools.hover(ms)
            self.setToolTip(self.tools.band_tip(ms))

        def leaveEvent(self, _e: Any) -> None:  # noqa: N802
            self.tools.hover(None)

        def mousePressEvent(self, e: Any) -> None:  # noqa: N802
            """1.4.4 (B131) : curseur à l'endroit exact cliqué (plus au début du passage)."""
            ms = self._ms(e.position().x())
            self.tools.ed.go_to(ms)
            self.tools.ed._move_cursor(ms)
            self.tools.refresh()

    return SegmentBand()


SHAPES = ("step", "ramp", "free")


class SegmentTools:
    """Passages et repères de la page Grille et cues (tenu par `GridEditor.seg_tools`)."""

    HANDLE = 9                 # poignée d'un repère (px logiques), en bas de la forme d'onde

    def __init__(self, editor: Any) -> None:
        self.ed = editor
        self.segs: List[Seg] = []
        self._of: Any = None                   # grille dont les passages sont tirés
        self._times: List[int] = []
        self._times_of: Any = None
        self._keep: List[Tuple[float, str]] = self._stored_keep()
        self._initial_keep = list(self._keep)
        self._from_marks = self._stored_marks()          # 1.4.4 (B131) : passages enregistrés (rampes…)
        self._base_sig: Optional[list] = None
        self.edited = False                    # repères posés, déplacés, supprimés, BPM d'un passage
        self.scope = "passage"                 # 1.4.4 (B131) : « ce passage » | « all » (tout le son)
        self._drag: Optional[int] = None
        self._targets: List[Tuple[int, int]] = []
        self._target_ms: List[int] = []
        self._drag_to: Optional[Tuple[int, int]] = None
        self._hover: Optional[float] = None
        self._live_text = ""
        self._band_tick = 0.0
        self.proposal: Optional[Tuple[List[Seg], str]] = None   # analyse proposée (passages, texte), à appliquer
        self._analysing = 0
        self._build()

    # ------------------------------------------------------------------ registre
    def _profile(self) -> Any:
        from .tempo_grids import profile_of

        return profile_of(self.ed.track)

    def _stored_keep(self) -> List[Tuple[float, str]]:
        p = self._profile()
        return [(m[0] * 1000.0, m[3]) for m in (getattr(p, "marks", None) or [])[1:]]

    def _stored_marks(self) -> List[tuple]:
        """Passages enregistrés avec une forme autre que palier (sinon : relus depuis la grille, comme en C221)."""
        from ..analysis import tempo_profile as TP

        marks = list(getattr(self._profile(), "marks", None) or [])
        if marks and any(TP.mark_shape(m) != "step" for m in marks):
            return marks
        return []

    @staticmethod
    def _sig(segs: Sequence[Seg]) -> list:
        return [(round(s[0]), round(s[1], 2), s[3], shape_of(s), round(end_of(s), 2)) for s in segs[1:]] + \
            [(shape_of(segs[0]), round(end_of(segs[0]), 2))] if segs else []

    # ------------------------------------------------------------------ interface
    @staticmethod
    def colour(kind: str) -> str:
        from . import theme

        return theme.SKY if kind == "sound" else theme.WARN

    @staticmethod
    def shape_colour(shape: str) -> str:
        from . import theme

        return {"ramp": theme.WARN, "free": theme.FAINT}.get(shape, theme.ACCENT)

    def _build(self) -> None:
        _c, _g, QtWidgets = _qt()
        from ..i18n import t
        from . import theme
        from .widgets import FlowLayout, ShrinkCombo, button, label, panel, vbox

        self.band = make_band(self)
        self.band.hide()
        self.live_lbl = label("", "dim")
        self.live_lbl.setToolTip(t("grid.seg_live_tip"))
        # 1.4.4 (B131) : portée des outils de grille quand le son a plusieurs passages
        self.scope_box = QtWidgets.QWidget()
        sr = FlowLayout(self.scope_box, spacing=theme.px(6))
        sr.addWidget(label(t("grid.scope"), "dim"))
        self.scope_passage = button(t("grid.scope_passage"), lambda: self.set_scope("passage"),
                                    tooltip=t("grid.scope_passage_tip"))
        self.scope_all = button(t("grid.scope_all"), lambda: self.set_scope("all"), tooltip=t("grid.scope_all_tip"))
        for b in (self.scope_passage, self.scope_all):
            b.setCheckable(True)
            sr.addWidget(b)
        self.scope_passage.setChecked(True)
        self.scope_box.hide()
        # tableau des passages (son au tempo variable)
        self.table = QtWidgets.QTreeWidget()
        self.table.setObjectName("passages")
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setHeaderLabels([t("grid.col_n"), t("grid.col_start"), t("grid.col_end"), t("grid.col_shape"),
                                    t("grid.col_bpm"), t("grid.col_origin")])
        self.table.setMinimumHeight(theme.px(110))
        self.table.itemClicked.connect(self._row_clicked)
        card = panel()
        v = vbox(card, margins=theme.px(10), spacing=theme.px(6))
        self.seg_lbl = label("", "section")
        v.addWidget(self.seg_lbl)
        box = QtWidgets.QWidget()
        row = FlowLayout(box, spacing=theme.px(6))
        self.add_tempo_btn = button(t("grid.seg_add_tempo"), lambda: self.add("tempo"), icon="plus",
                                    tooltip=t("grid.seg_add_tempo_tip"))
        self.add_sound_btn = button(t("grid.seg_add_sound"), lambda: self.add("sound"), icon="plus",
                                    tooltip=t("grid.seg_add_sound_tip"))
        self.remove_btn = button(t("grid.seg_remove"), self.remove, kind="danger", icon="trash",
                                 tooltip=t("grid.seg_remove_tip"))
        for b in (self.add_tempo_btn, self.add_sound_btn, self.remove_btn):
            row.addWidget(b)
        v.addWidget(box)
        box2 = QtWidgets.QWidget()
        row2 = FlowLayout(box2, spacing=theme.px(6))
        row2.addWidget(label(t("grid.col_shape"), "dim"))
        self.shape_menu = ShrinkCombo()
        for key in SHAPES:
            self.shape_menu.addItem(t(f"grid.shape_{key}"), key)
        self.shape_menu.setToolTip(t("grid.shape_tip"))
        self.shape_menu.currentIndexChanged.connect(self._shape_picked)
        row2.addWidget(self.shape_menu)
        self.bpm_entry = QtWidgets.QLineEdit()
        self.bpm_entry.setFixedWidth(theme.px(78))
        self.bpm_entry.setToolTip(t("grid.seg_bpm_tip"))
        self.bpm_entry.returnPressed.connect(self.apply_bpm)
        self.end_lbl = label("→", "dim")
        self.end_entry = QtWidgets.QLineEdit()
        self.end_entry.setFixedWidth(theme.px(78))
        self.end_entry.setToolTip(t("grid.seg_end_tip"))
        self.end_entry.returnPressed.connect(self.apply_bpm)
        self.bpm_btn = button(t("grid.seg_apply"), self.apply_bpm, icon="check", tooltip=t("grid.seg_bpm_tip"))
        for wdg in (self.bpm_entry, self.end_lbl, self.end_entry, self.bpm_btn):
            row2.addWidget(wdg)
        v.addWidget(box2)
        box3 = QtWidgets.QWidget()
        row3 = FlowLayout(box3, spacing=theme.px(6))
        self.analyse_btn = button(t("grid.analyse_passage"), lambda: self.analyse(False), icon="wave",
                                  tooltip=t("grid.analyse_passage_tip"))
        self.analyse_all_btn = button(t("grid.analyse_all"), lambda: self.analyse(True), icon="wave",
                                      tooltip=t("grid.analyse_all_tip"))
        self.apply_btn = button(t("grid.analyse_apply"), self.apply_proposal, kind="primary", icon="check")
        self.apply_btn.hide()
        for b in (self.analyse_btn, self.analyse_all_btn, self.apply_btn):
            row3.addWidget(b)
        v.addWidget(box3)
        self.proposal_lbl = label("", "dim", wrap=True)
        self.proposal_lbl.hide()
        v.addWidget(self.proposal_lbl)
        box4 = QtWidgets.QWidget()
        row4 = FlowLayout(box4, spacing=theme.px(6))
        row4.addWidget(label(t("grid.seg_kind"), "dim"))
        self.kind_menu = ShrinkCombo()
        self.kind_menu.setToolTip(t("grid.seg_kind_tip"))
        for key in KIND_CHOICES:
            self.kind_menu.addItem(t(f"grid.seg_kind_{key or 'auto'}"), key)
        self.kind_menu.currentIndexChanged.connect(self._kind_picked)
        row4.addWidget(self.kind_menu)
        v.addWidget(box4)
        self.card = card

    def set_scope(self, scope: str) -> None:
        self.scope = scope if scope in ("passage", "all") else "passage"
        self.scope_passage.setChecked(self.scope == "passage")
        self.scope_all.setChecked(self.scope == "all")

    def multi(self) -> bool:
        return len(self.segs) > 1

    # ------------------------------------------------------------------ état
    def sync(self, cues: bool = True) -> None:
        """Grille changée par un autre outil (décalage, BPM, deux kicks…) : passages relus, repères gardés."""
        beats = self.ed.beats
        if beats is self._of:
            return
        first = self._of is None
        if first and self._from_marks:
            self.segs = segments_of_marks(self._from_marks)
        else:
            keep = self._keep if first else [(float(s[0]), s[3]) for s in self.segs[1:] if s[3] == "sound"]
            self.segs = segments_of(beats, keep)
        self._of = beats
        if self._base_sig is None:
            self._base_sig = self._sig(self.segs)
        if cues and not first:
            self._sync_cues()

    def reset(self) -> None:
        """« Annuler les modifications » : repères d'origine."""
        self._keep = list(self._initial_keep)
        self._of = None
        self.edited = False
        self._clear_proposal()

    def dirty(self) -> bool:
        if not self.edited:
            return False
        return self._sig(self.segs) != self._base_sig

    def _times_cache(self) -> List[int]:
        if self._times_of is not self.ed.beats:
            self._times = [b[2] for b in self.ed.beats]
            self._times_of = self.ed.beats
        return self._times

    def _commit(self, segs: List[Seg], force: bool = False) -> None:
        """Nouveaux passages : la grille n'est recalculée que si le tempo change quelque part."""
        ed = self.ed
        anchor = ed.beats[ed.selected][2] if ed.beats else 0
        if force or layout(segs) != layout(self.segs):
            beats = build(segs, ed.duration_ms)
            if beats:
                ed.beats = beats
        self.segs = segs
        self._of = ed.beats
        self.edited = True
        if ed.beats:
            ed.selected = G.nearest(ed.beats, anchor)
        self._sync_cues()
        ed._refresh_info()
        ed.draw()

    def _sync_cues(self) -> None:
        """Repères « nouveau son » = mémoires nommées (les platines les montrent) ; les autres mémoires restent."""
        from ..analysis.cues import Cue
        from ..i18n import t

        name = t("grid.seg_sound_cue")
        want = sorted(s[0] for s in self.segs[1:] if s[3] == "sound")
        ours = [c for c in self.ed.cues if not c.slot and not c.is_loop and c.name == name]
        if sorted(int(c.ms) for c in ours) == want:
            return
        self.ed.cues = [c for c in self.ed.cues if c not in ours or int(c.ms) in want]
        have = {int(c.ms) for c in self.ed.cues if not c.slot and not c.is_loop and c.name == name}
        self.ed.cues += [Cue(slot=0, ms=ms, name=name) for ms in want if ms not in have]
        panel_ = getattr(self.ed, "cue_panel", None)
        if panel_ is not None:
            panel_.refresh()

    # ------------------------------------------------------------------ 1.4.4 (B131) : portée des outils
    def apply_scoped(self, new_full: Optional[List[Beat]], at_ms: Optional[float] = None) -> Optional[List[Beat]]:
        """Outil de grille (1er / 2e kick, décalage, ½ temps, début de mesure, BPM) : grille calculée pour tout le
        son (`new_full`) puis, si le son a plusieurs passages et que la portée est « ce passage », gardée seulement
        dans le passage sous le curseur (ou sous `at_ms`). Les bornes suivent, calées sur le temps le plus proche ;
        les cues posés pile sur un temps près d'une borne déplacée suivent aussi. Renvoie la grille à garder."""
        ed = self.ed
        if not new_full:
            return new_full
        self.sync(cues=False)
        if not self.multi():
            return new_full
        old_segs = list(self.segs)
        if self.scope == "all":
            beats = list(new_full)
            segs = resegment(old_segs, beats)
        else:
            k = segment_at(old_segs, ed.cursor_ms if at_ms is None else at_ms)
            lo, hi = bounds(old_segs, k, ed.duration_ms)
            beats = splice(ed.beats, new_full, lo, hi)
            segs = resegment(old_segs, beats, k)
        self._snap_cues(old_segs, segs)
        self.segs = segs
        self._of = beats
        self.edited = True
        self._sync_cues()
        return beats

    def _snap_cues(self, old: Sequence[Seg], new: Sequence[Seg]) -> None:
        """Cues, mémoires et boucles pile sur une borne déplacée (±5 ms) : la suivent."""
        moved = {int(a[0]): int(b[0]) for a, b in zip(old, new) if int(a[0]) != int(b[0])}
        if not moved:
            return
        for c in getattr(self.ed, "cues", []):
            for frm, to in moved.items():
                if abs(int(c.ms) - frm) <= 5:
                    try:
                        c.ms = to
                    except AttributeError:
                        pass
                    break

    # ------------------------------------------------------------------ actions
    def add(self, kind: str) -> None:
        ed = self.ed
        if not ed.beats:
            return
        self.sync()
        segs, k = add_mark(self.segs, ed.beats, ed.cursor_ms, kind)
        if k is None:
            ed.ctrl.message("warn", self._t("grid.seg_first_beat"))
            return
        lo, hi = bounds(segs, k, ed.duration_ms)
        prev_lo, _p = bounds(segs, k - 1, ed.duration_ms)
        if (hi - lo) < 4 * 60000.0 / max(1.0, segs[k][1]) or (lo - prev_lo) < 4 * 60000.0 / max(1.0, segs[k][1]):
            ed.ctrl.message("info", self._t("grid.seg_close"))       # bornes à moins de 4 temps : fusion proposée
        self._commit(segs)

    def remove(self) -> None:
        self.sync()
        if len(self.segs) < 2:
            return
        k = min(range(1, len(self.segs)), key=lambda i: abs(self.segs[i][0] - self.ed.cursor_ms))
        self._commit(remove_mark(self.segs, k))

    def _numbers(self) -> Tuple[Optional[float], Optional[float]]:
        def num(w: Any) -> Optional[float]:
            try:
                return float(w.text().replace(",", "."))
            except ValueError:
                return None
        return num(self.bpm_entry), num(self.end_entry)

    def apply_bpm(self) -> None:
        ed = self.ed
        bpm, end = self._numbers()
        if bpm is None:
            return
        if not 40 <= bpm <= 300 or not ed.beats:
            ed.ctrl.message("warn", self._t("grid.bpm_range"))
            return
        self.sync()
        k = segment_at(self.segs, ed.cursor_ms)
        if shape_of(self.segs[k]) == "ramp" and end is not None:
            if not 40 <= end <= 300:
                ed.ctrl.message("warn", self._t("grid.bpm_range"))
                return
            self._commit(set_shape(self.segs, k, "ramp", bpm, end), force=True)
            return
        sel = ed.beats[ed.selected]
        self._commit(set_segment_bpm(self.segs, k, bpm, (float(sel[2]), int(sel[0]))))

    def _shape_picked(self, _i: int) -> None:
        """Forme du passage choisie à la main : palier, rampe (du BPM du passage à celui du suivant), libre."""
        if getattr(self, "_filling", False):
            return
        ed = self.ed
        self.sync()
        if not self.segs or not ed.beats:
            return
        k = segment_at(self.segs, ed.cursor_ms)
        shape = self.shape_menu.currentData() or "step"
        cur = self.segs[k]
        if shape == shape_of(cur):
            return
        nxt = self.segs[k + 1][1] if k + 1 < len(self.segs) else cur[1]
        end = (nxt if abs(nxt - cur[1]) > 0.01 else cur[1] * 1.03) if shape == "ramp" else cur[1]
        self._commit(set_shape(self.segs, k, shape, cur[1], end), force=True)

    def _kind_picked(self, _i: int) -> None:
        """Type du son corrigé à la main (gardé à la réanalyse) ; 1.4.4 (B131) : il change vraiment la grille.
        Accélération / ralentissement : le passage sous le curseur devient une rampe analysée ; tempo stable :
        grille fixe ; beatswitch : paliers ; live / set : grille variable de l'analyse."""
        if getattr(self, "_filling", False):
            return
        from .tempo_grids import TempoGridService

        kind = self.kind_menu.currentData() or ""
        if TempoGridService.set_kind(self.ed.track, kind):
            self.ed._refresh_info()
        ed = self.ed
        if not ed.beats:
            return
        self.sync()
        if kind == "none":
            fixed = getattr(ed, "_fixed_grid", None)
            if fixed is not None and len({b[1] for b in ed.beats}) > 1:
                fixed()
        elif kind == "ramp":
            self.analyse(False, ramp=True, auto_apply=True)
        elif kind == "switch":
            if any(shape_of(s) != "step" for s in self.segs):
                segs = [replace(s, shape="step", end=s[1], origin="main") if shape_of(s) != "step" else s
                        for s in self.segs]
                self._commit(segs, force=True)
        elif kind in ("live", "set"):
            orig = getattr(ed, "original", None)
            if orig and len({b[1] for b in orig}) > 1 and ed.beats != orig:
                ed.beats = list(orig)
                self._of = None
                self.edited = True
                ed._refresh_info()
                ed.draw()

    # ------------------------------------------------------------------ 1.4.4 (B131) : analyse par passage
    def analyse(self, every: bool, ramp: bool = False, auto_apply: bool = False) -> None:
        """« Analyser ce passage / tous les passages » : décodage de la plage en fond (pool d'analyse), résultat
        proposé (« Appliquer », annulable) ; un passage trop court, sans temps nets ou à un rapport ×2 / ×3/2 de son
        voisin n'est pas changé (message)."""
        from pathlib import Path

        from ..analysis import segment_tempo as ST

        ed = self.ed
        self.sync()
        if not self.segs or not ed.beats:
            return
        path = getattr(ed.track, "path", "")
        if not path or not Path(path).is_file():
            ed.ctrl.message("warn", self._t("grid.analyse_no_file"))
            return
        ks = list(range(len(self.segs))) if every else [segment_at(self.segs, ed.cursor_ms)]
        segs0 = list(self.segs)
        dur = ed.duration_ms
        ffmpeg = getattr(ed.ctrl.settings, "ffmpeg_location", "") or None

        def work() -> list:
            out = []
            for k in ks:
                lo, hi = bounds(segs0, k, dur)
                nb = [segs0[j][1] for j in (k - 1, k + 1) if 0 <= j < len(segs0)]
                res = ST.analyze_file(path, lo / 1000.0, hi / 1000.0, float(segs0[k][1]), nb, ffmpeg,
                                      allow_ramp=True)
                if ramp and res.shape == "step" and res.ok:
                    res.shape, res.bpm_end = "ramp", res.bpm
                out.append((k, res))
            return out

        def done(results: list) -> None:
            self._analysing = max(0, self._analysing - 1)
            self.analyse_btn.setEnabled(True)
            self.analyse_all_btn.setEnabled(True)
            if getattr(ed, "_closed", False):
                return
            self._propose(segs0, results, auto_apply)

        def failed(exc: BaseException) -> None:
            self._analysing = max(0, self._analysing - 1)
            self.analyse_btn.setEnabled(True)
            self.analyse_all_btn.setEnabled(True)
            log.info("Passage analysis failed: %s", exc)
            ed.ctrl.message("warn", self._t("grid.analyse_failed"))

        self._analysing += 1
        self.analyse_btn.setEnabled(False)
        self.analyse_all_btn.setEnabled(False)
        self.proposal_lbl.setText(self._t("grid.analysing"))
        self.proposal_lbl.show()
        ed.ctrl.dispatcher.submit(work, done, failed, pool="analysis")

    def _propose(self, segs0: List[Seg], results: list, auto_apply: bool) -> None:
        from ..i18n import t

        segs = list(segs0)
        lines, changed = [], False
        for k, res in results:
            if res.note == "short":
                nb = segs0[k - 1][1] if k else (segs0[1][1] if len(segs0) > 1 else segs0[0][1])
                lines.append(t("grid.analyse_short", n=k + 1, bpm=f"{nb:.2f}"))
                continue
            if res.note in ("octave", "range"):
                lines.append(t("grid.analyse_octave", n=k + 1, bpm=f"{res.bpm:.2f}"))
                continue
            if res.note == "weak" and res.shape == "free":
                if k == 0:
                    lines.append(t("grid.analyse_weak", n=k + 1))
                    continue
                segs[k] = replace(segs[k], shape="free", end=segs[k - 1][1], origin="auto")
                lines.append(t("grid.analyse_free", n=k + 1))
                changed = True
                continue
            segs = apply_result(segs, k, res, self.ed.duration_ms)
            if res.shape == "ramp":
                lines.append(t("grid.analyse_ramp", n=k + 1, a=f"{res.bpm:.2f}", b=f"{res.bpm_end:.2f}"))
            else:
                lines.append(t("grid.analyse_step", n=k + 1, bpm=f"{res.bpm:.2f}"))
            changed = True
        text = "\n".join(lines)
        self.proposal = (segs, text) if changed else None
        self.proposal_lbl.setText(text)
        self.proposal_lbl.setVisible(bool(text))
        self.apply_btn.setVisible(changed and not auto_apply)
        if changed and auto_apply:
            self.apply_proposal()

    def apply_proposal(self) -> None:
        if self.proposal is None:
            return
        segs, _text = self.proposal
        self._clear_proposal()
        self._commit(segs, force=True)

    def _clear_proposal(self) -> None:
        self.proposal = None
        if hasattr(self, "apply_btn"):
            self.apply_btn.hide()
            self.proposal_lbl.hide()

    @staticmethod
    def _t(key: str) -> str:
        from ..i18n import t

        return t(key)

    # ------------------------------------------------------------------ glisser un repère
    def _handle_y(self, h: int) -> float:
        from . import theme

        return h - theme.px(self.HANDLE) - 2

    def grab(self, x: float, y: float, h: int) -> bool:
        from . import theme

        if y < self._handle_y(h) - theme.px(4) or len(self.segs) < 2:
            return False
        self.sync()
        near = [k for k in range(1, len(self.segs)) if abs(self.ed._x(self.segs[k][0]) - x) <= theme.px(self.HANDLE)]
        if not near:
            return False
        self._drag = min(near, key=lambda k: abs(self.ed._x(self.segs[k][0]) - x))
        self._targets = move_targets(self.segs, self.ed.beats, self._drag, self.ed.duration_ms)
        self._target_ms = [a for a, _n in self._targets]
        self._drag_to = None
        return True

    def dragging(self) -> bool:
        return self._drag is not None

    def drag(self, x: float) -> None:
        if self._drag is None or not self._targets:
            return
        ms = self.ed._ms(x)
        i = bisect_left(self._target_ms, ms)
        cand = [j for j in (i - 1, i) if 0 <= j < len(self._targets)]
        j = min(cand, key=lambda j: abs(self._target_ms[j] - ms))
        self._drag_to = self._targets[j]
        self.ed.draw()

    def drop(self) -> None:
        k, to = self._drag, self._drag_to
        self._drag, self._drag_to, self._targets, self._target_ms = None, None, [], []
        if k is not None and to is not None and to[0] != self.segs[k][0]:
            old = list(self.segs)
            segs = move_mark(self.segs, k, to)
            self._snap_cues(old, segs)
            self._commit(segs)
        else:
            self.ed.draw()

    # ------------------------------------------------------------------ dessin et BPM en direct
    def paint(self, p: Any, w: int, h: int, top: float) -> None:
        """Repères sur la forme d'onde : trait (orange : tempo, bleu : nouveau son) et poignée en bas."""
        QtCore, QtGui, _w = _qt()
        from . import theme
        from ..i18n import t

        self.sync()
        if len(self.segs) < 2:
            return
        lo, hi = self.ed._ms(-20), self.ed._ms(w + 20)
        fm = QtGui.QFontMetrics(p.font())
        for k in range(1, len(self.segs)):
            st, kind = self.segs[k][0], self.segs[k][3]
            if self._drag == k and self._drag_to is not None:
                st = self._drag_to[0]
            if not lo <= st <= hi:
                continue
            x = self.ed._x(st)
            col = QtGui.QColor(self.colour(kind))
            if kind == "sound" or self._drag == k:
                p.setPen(QtGui.QPen(col, theme.px(2), QtCore.Qt.DashLine))
                p.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, h))
            if kind == "sound":
                p.drawText(QtCore.QPointF(x + 4, top + 2 * fm.ascent() + 2), t("grid.seg_sound_cue"))
            s = theme.px(self.HANDLE) / 2
            y = self._handle_y(h) + s
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(col)
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y - s), QtCore.QPointF(x + s, y),
                                           QtCore.QPointF(x, y + s), QtCore.QPointF(x - s, y)]))
            p.setBrush(QtCore.Qt.NoBrush)

    def hover(self, ms: Optional[float]) -> None:
        self._hover = ms
        self.live()

    def band_tip(self, ms: float) -> str:
        """Survol de la bande : passage et BPM."""
        from ..i18n import t

        if not self.segs:
            return ""
        k = segment_at(self.segs, ms)
        sg = self.segs[k]
        bpm = f"{sg[1]:.2f}" if shape_of(sg) != "ramp" else f"{sg[1]:.2f} → {end_of(sg):.2f}"
        return t("grid.band_tip", n=k + 1, total=len(self.segs), bpm=bpm, shape=t(f"grid.shape_{shape_of(sg)}"))

    def live(self, tick: bool = False) -> None:
        """BPM au curseur (lecture) et sous la souris ; texte changé seulement s'il change."""
        from ..i18n import t
        import time

        ed = self.ed
        if not ed.beats:
            return
        times = self._times_cache()
        parts = [t("grid.seg_bpm_here", bpm=f"{tempo_at(times, ed.beats, ed.cursor_ms):.2f}")]
        if self._hover is not None:
            parts.append(t("grid.seg_bpm_mouse", bpm=f"{tempo_at(times, ed.beats, self._hover):.2f}"))
        text = "  ·  ".join(parts)
        if text != self._live_text:
            self._live_text = text
            self.live_lbl.setText(text)
        now = time.monotonic()
        if self.band.isVisible() and (not tick or now - self._band_tick > 0.1):   # la bande suit la lecture
            self._band_tick = now
            self.band.update()

    def _fill_table(self) -> None:
        from ..i18n import t
        _c, QtGui, QtWidgets = _qt()

        def clock(ms: float) -> str:
            s_ = max(0.0, ms) / 1000.0
            return f"{int(s_ // 60)}:{s_ % 60:06.3f}"

        rows = []
        for k, sg in enumerate(self.segs):
            lo, hi = bounds(self.segs, k, self.ed.duration_ms)
            bpm = f"{sg[1]:.2f}" if shape_of(sg) != "ramp" else f"{sg[1]:.2f} → {end_of(sg):.2f}"
            rows.append((str(k + 1), clock(lo), clock(hi), t(f"grid.shape_{shape_of(sg)}"), bpm,
                         t(f"grid.origin_{origin_of(sg)}")))
        if rows == getattr(self, "_rows", None):
            return
        self._rows = rows
        self.table.clear()
        for k, r in enumerate(rows):
            it = QtWidgets.QTreeWidgetItem(list(r))
            it.setData(0, 256, k)
            it.setForeground(0, QtGui.QBrush(QtGui.QColor(self.shape_colour(shape_of(self.segs[k])))))
            self.table.addTopLevelItem(it)

    def _row_clicked(self, item: Any, _col: int = 0) -> None:
        k = item.data(0, 256)
        if k is None or not 0 <= k < len(self.segs):
            return
        lo, _hi = bounds(self.segs, k, self.ed.duration_ms)
        self.ed.go_to(float(lo))
        self.ed._move_cursor(float(lo))
        self.refresh()

    def refresh(self) -> None:
        """Après chaque changement (appelé par GridEditor._refresh_info)."""
        from ..i18n import t

        self.sync()
        ed = self.ed
        if not self.segs:
            return
        multi = self.multi()
        self.band.setVisible(multi)
        self.scope_box.setVisible(multi)
        self.table.setVisible(multi)
        k = segment_at(self.segs, ed.cursor_ms)
        cur = self.segs[k]
        self.seg_lbl.setText(t("grid.seg_current", n=k + 1, total=len(self.segs)))
        ramp = shape_of(cur) == "ramp"
        if not self.bpm_entry.hasFocus():
            self.bpm_entry.setText(f"{cur[1]:.2f}")
        if not self.end_entry.hasFocus():
            self.end_entry.setText(f"{end_of(cur):.2f}")
        self.end_lbl.setVisible(ramp)
        self.end_entry.setVisible(ramp)
        self.remove_btn.setEnabled(multi)
        if multi:
            self._fill_table()
            sel = self.table.topLevelItem(k)
            if sel is not None and self.table.currentItem() is not sel:
                self.table.setCurrentItem(sel)
        p = self._profile()
        user = getattr(p, "user_kind", "") if p is not None else ""
        detected = getattr(p, "detected", "") if p is not None else ""
        self._filling = True
        try:
            auto = t("grid.seg_kind_auto_is", kind=t(f"grid.seg_kind_{detected or 'none'}"))
            self.kind_menu.setItemText(0, auto)
            self.kind_menu.setCurrentIndex(max(0, self.kind_menu.findData(user)))
            self.kind_menu.setEnabled(p is not None)
            self.shape_menu.setCurrentIndex(max(0, self.shape_menu.findData(shape_of(cur))))
        finally:
            self._filling = False
        self.live()

    def remember(self) -> None:
        """À l'enregistrement : passages gardés à la réanalyse (aucun : plus rien à garder)."""
        if not self.edited and not self._initial_keep and not self._from_marks:
            return
        from .tempo_grids import TempoGridService

        self.sync(cues=False)
        keep = len(self.segs) > 1 or any(shape_of(s) != "step" for s in self.segs)
        marks = to_marks(self.segs) if keep else []
        if TempoGridService.remember_marks(self.ed.track, marks):
            self._base_sig = self._sig(self.segs)
            self._initial_keep = [(float(s[0]), s[3]) for s in self.segs[1:]]
