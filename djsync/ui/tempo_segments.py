"""1.4.4 (C221) : tempo variable dans « Grille et cues » : passages (segments) et repères éditables.

* bande des passages sous la forme d'onde, chacun avec son BPM ; BPM sous la souris et BPM au curseur (mis à
  jour pendant la lecture) : une recherche dichotomique dans la grille, rien n'est recalculé en bougeant ;
* repères « changement de tempo » et « nouveau son », posés sur un temps : ajouter, déplacer (glisser la
  poignée en bas de la forme d'onde), supprimer ; BPM d'un passage corrigé ; la grille est recalculée depuis
  les passages (un tempo par temps, PQTZ, comme la grille par passage de C16) seulement quand le tempo change ;
* un repère « nouveau son » est aussi une mémoire nommée (visible sur les platines) ;
* type détecté corrigé à la main ; repères et type gardés à la réanalyse (registre tempo.json, tempo_profile).

Un passage : (début ms, BPM, numéro 1-4 de son premier temps, genre "" | "tempo" | "sound").
"""
from __future__ import annotations

import logging
from bisect import bisect_left, bisect_right
from typing import Any, List, Optional, Sequence, Tuple

from ..analysis import grid as G
from .tempo_grids import changes, is_constant, split_beats

log = logging.getLogger(__name__)

Beat = Tuple[int, int, int]            # (numéro 1-4, tempo x100, ms)
Seg = Tuple[int, float, int, str]      # (début ms, BPM, numéro du 1er temps, genre)
KIND_CHOICES = ("", "none", "switch", "ramp", "set", "live")


# ------------------------------------------------------------------------------- calculs (sans Qt)
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


def to_sections(segs: Sequence[Seg]) -> List[Tuple[float, float, float]]:
    """Passages au format de tempo_profile.section_beats : (début s, BPM, un 1er temps de mesure s)."""
    out = []
    for st, bpm, n, _k in segs:
        out.append((st / 1000.0, float(bpm), st / 1000.0 - (n - 1) * 60.0 / bpm))
    return out


def to_marks(segs: Sequence[Seg]) -> List[Tuple[float, float, float, str]]:
    """Ce qui est gardé dans tempo.json (passages + genre de chaque repère)."""
    return [(a, b, c, s[3]) for (a, b, c), s in zip(to_sections(segs), segs)]


def build(segs: Sequence[Seg], duration_ms: int) -> List[Beat]:
    """Grille recalculée depuis les passages : un tempo par temps (PQTZ)."""
    return split_beats(to_sections(segs), duration_ms)


def layout(segs: Sequence[Seg]) -> List[Tuple[int, float]]:
    """Changements de tempo seulement (passages voisins au même BPM réunis) : si rien ne change ici, la grille
    reste telle quelle (un repère « nouveau son » ne touche pas une grille de live)."""
    out: List[Tuple[int, float]] = []
    for st, bpm, _n, _k in segs:
        if not out or abs(out[-1][1] - bpm) > 0.004:
            out.append((st, round(bpm, 2)))
    return out


def segment_at(segs: Sequence[Seg], ms: float) -> int:
    k = 0
    for i, s in enumerate(segs):
        if ms + 0.5 >= s[0]:
            k = i
    return k


def add_mark(segs: Sequence[Seg], beats: Sequence[Beat], ms: float, kind: str) -> Tuple[List[Seg], Optional[int]]:
    """Repère sur le temps le plus proche de `ms` ; un repère déjà là change de genre. (passages, indice)."""
    segs = list(segs)
    i = G.nearest(beats, ms)
    if i <= 0 or not segs:
        return segs, None
    st, n = int(beats[i][2]), int(beats[i][0])
    for k, s in enumerate(segs):
        if s[0] == st:
            if k == 0:
                return segs, None
            segs[k] = (st, s[1], s[2], kind)
            return segs, k
    k = segment_at(segs, st)
    segs.insert(k + 1, (st, segs[k][1], n, kind))
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
    st, bpm, n, _kind = segs[k]
    if abs(segs[k - 1][1] - bpm) <= 0.004:
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
        _st, bpm, _n, kind = segs[k]
        segs[k] = (int(target[0]), bpm, int(target[1]), kind)
    return segs


def set_segment_bpm(segs: Sequence[Seg], k: int, bpm: float, anchor: Optional[Tuple[float, int]] = None) -> List[Seg]:
    """BPM du passage `k`. Le passage garde son début (le repère) ; le premier passage reste calé sur le temps
    sélectionné `anchor` (ms, numéro) s'il est dedans, et repart du début du son."""
    segs = list(segs)
    if not 0 <= k < len(segs) or bpm <= 0:
        return segs
    st, _old, n, kind = segs[k]
    if k == 0 and anchor is not None and (len(segs) == 1 or anchor[0] < segs[1][0]):
        step = 60000.0 / bpm
        m = int(anchor[0] // step)
        st, n = int(round(anchor[0] - m * step)), ((anchor[1] - 1 - m) % 4) + 1
    segs[k] = (st, float(bpm), n, kind)
    return segs


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
    """Bande des passages, sur toute la longueur du son, sous la forme d'onde."""
    QtCore, QtGui, QtWidgets = _qt()
    from . import theme

    class SegmentBand(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.tools = tools
            self.setFixedHeight(theme.px(22))
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
            fm = QtGui.QFontMetrics(p.font())
            for k, (st, bpm, _n, kind) in enumerate(segs):
                x0 = 0.0 if k == 0 else self._x(st)
                x1 = self._x(segs[k + 1][0]) if k + 1 < len(segs) else float(w)
                tone = 0.34 if k == cur else (0.14 if k % 2 == 0 else 0.22)
                p.fillRect(QtCore.QRectF(x0, 1, max(1.0, x1 - x0), h - 2),
                           QtGui.QColor(theme.mix(theme.SURFACE, theme.ACCENT, tone)))
                text = f"{bpm:.2f}".rstrip("0").rstrip(".")
                if x1 - x0 > fm.horizontalAdvance(text) + 8:
                    p.setPen(QtGui.QColor(theme.TEXT))
                    p.drawText(QtCore.QRectF(x0, 0, x1 - x0, h), QtCore.Qt.AlignCenter, text)
                if k:
                    p.setPen(QtGui.QPen(QtGui.QColor(SegmentTools.colour(kind)), theme.px(2)))
                    p.drawLine(QtCore.QPointF(x0, 0), QtCore.QPointF(x0, h))
            span = ed.view_s * 1000.0                     # zone affichée en grand
            p.setPen(QtGui.QPen(QtGui.QColor(theme.FAINT), 1))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(QtCore.QRectF(self._x(max(0.0, ed.start_ms)), 0.5, max(2.0, self._x(span)), h - 1))
            from .cursor import draw_cursor

            draw_cursor(p, self._x(ed.cursor_ms), 0, h, glow=False)
            p.end()

        def mouseMoveEvent(self, e: Any) -> None:  # noqa: N802
            self.tools.hover(self._ms(e.position().x()))

        def leaveEvent(self, _e: Any) -> None:  # noqa: N802
            self.tools.hover(None)

        def mousePressEvent(self, e: Any) -> None:  # noqa: N802
            """Clic : au début de ce passage (pour corriger son BPM, l'écouter)."""
            segs = self.tools.segs
            if segs:
                k = segment_at(segs, self._ms(e.position().x()))
                self.tools.ed.go_to(float(segs[k][0]))
                self.tools.ed._move_cursor(float(segs[k][0]))

    return SegmentBand()


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
        self._stored = list(self._initial_keep)
        self.edited = False                    # repères posés, déplacés, supprimés, BPM d'un passage
        self._drag: Optional[int] = None
        self._targets: List[Tuple[int, int]] = []
        self._target_ms: List[int] = []
        self._drag_to: Optional[Tuple[int, int]] = None
        self._hover: Optional[float] = None
        self._live_text = ""
        self._band_tick = 0.0
        self._build()

    # ------------------------------------------------------------------ registre
    def _profile(self) -> Any:
        from .tempo_grids import profile_of

        return profile_of(self.ed.track)

    def _stored_keep(self) -> List[Tuple[float, str]]:
        p = self._profile()
        return [(a * 1000.0, k) for a, _b, _c, k in (getattr(p, "marks", None) or [])[1:]]

    # ------------------------------------------------------------------ interface
    @staticmethod
    def colour(kind: str) -> str:
        from . import theme

        return theme.SKY if kind == "sound" else theme.WARN

    def _build(self) -> None:
        _c, _g, QtWidgets = _qt()
        from ..i18n import t
        from . import theme
        from .widgets import FlowLayout, ShrinkCombo, button, label, panel, vbox

        self.band = make_band(self)
        self.live_lbl = label("", "dim")
        self.live_lbl.setToolTip(t("grid.seg_live_tip"))
        card = panel()
        v = vbox(card, margins=theme.px(10), spacing=theme.px(6))
        v.addWidget(label(t("grid.seg_zone"), "section"))
        box = QtWidgets.QWidget()
        row = FlowLayout(box, spacing=theme.px(6))
        self.add_tempo_btn = button(t("grid.seg_add_tempo"), lambda: self.add("tempo"), icon="plus",
                                    tooltip=t("grid.seg_add_tempo_tip"))
        self.add_sound_btn = button(t("grid.seg_add_sound"), lambda: self.add("sound"), icon="plus",
                                    tooltip=t("grid.seg_add_sound_tip"))
        self.remove_btn = button(t("grid.seg_remove"), self.remove, kind="flat", tooltip=t("grid.seg_remove_tip"))
        for b in (self.add_tempo_btn, self.add_sound_btn, self.remove_btn):
            row.addWidget(b)
        v.addWidget(box)
        box2 = QtWidgets.QWidget()
        row2 = FlowLayout(box2, spacing=theme.px(6))
        self.seg_lbl = label("", "dim")
        self.bpm_entry = QtWidgets.QLineEdit()
        self.bpm_entry.setFixedWidth(theme.px(78))
        self.bpm_entry.setToolTip(t("grid.seg_bpm_tip"))
        self.bpm_entry.returnPressed.connect(self.apply_bpm)
        self.bpm_btn = button(t("grid.seg_apply"), self.apply_bpm, icon="check", tooltip=t("grid.seg_bpm_tip"))
        for wdg in (self.seg_lbl, self.bpm_entry, self.bpm_btn):
            row2.addWidget(wdg)
        v.addWidget(box2)
        box3 = QtWidgets.QWidget()
        row3 = FlowLayout(box3, spacing=theme.px(6))
        row3.addWidget(label(t("grid.seg_kind"), "dim"))
        self.kind_menu = ShrinkCombo()
        self.kind_menu.setToolTip(t("grid.seg_kind_tip"))
        for key in KIND_CHOICES:
            self.kind_menu.addItem(t(f"grid.seg_kind_{key or 'auto'}"), key)
        self.kind_menu.currentIndexChanged.connect(self._kind_picked)
        row3.addWidget(self.kind_menu)
        v.addWidget(box3)
        self.card = card

    # ------------------------------------------------------------------ état
    def sync(self, cues: bool = True) -> None:
        """Grille changée par un autre outil (décalage, BPM, deux kicks…) : passages relus, repères gardés."""
        beats = self.ed.beats
        if beats is self._of:
            return
        first = self._of is None
        keep = self._keep if first else [(float(s[0]), s[3]) for s in self.segs[1:] if s[3] == "sound"]
        self.segs = segments_of(beats, keep)
        self._of = beats
        if cues and not first:
            self._sync_cues()

    def reset(self) -> None:
        """« Annuler les modifications » : repères d'origine."""
        self._keep = list(self._initial_keep)
        self._of = None
        self.edited = False

    def dirty(self) -> bool:
        if not self.edited:
            return False
        now = [(round(s[0]), s[3]) for s in self.segs[1:]]
        return now != [(round(a), k) for a, k in self._stored]

    def _times_cache(self) -> List[int]:
        if self._times_of is not self.ed.beats:
            self._times = [b[2] for b in self.ed.beats]
            self._times_of = self.ed.beats
        return self._times

    def _commit(self, segs: List[Seg]) -> None:
        """Nouveaux passages : la grille n'est recalculée que si le tempo change quelque part."""
        ed = self.ed
        anchor = ed.beats[ed.selected][2] if ed.beats else 0
        if layout(segs) != layout(self.segs):
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
        self._commit(segs)

    def remove(self) -> None:
        self.sync()
        if len(self.segs) < 2:
            return
        k = min(range(1, len(self.segs)), key=lambda i: abs(self.segs[i][0] - self.ed.cursor_ms))
        self._commit(remove_mark(self.segs, k))

    def apply_bpm(self) -> None:
        ed = self.ed
        try:
            bpm = float(self.bpm_entry.text().replace(",", "."))
        except ValueError:
            return
        if not 40 <= bpm <= 300 or not ed.beats:
            ed.ctrl.message("warn", self._t("grid.bpm_range"))
            return
        self.sync()
        k = segment_at(self.segs, ed.cursor_ms)
        sel = ed.beats[ed.selected]
        self._commit(set_segment_bpm(self.segs, k, bpm, (float(sel[2]), int(sel[0]))))

    def _kind_picked(self, _i: int) -> None:
        if getattr(self, "_filling", False):
            return
        from .tempo_grids import TempoGridService

        if TempoGridService.set_kind(self.ed.track, self.kind_menu.currentData() or ""):
            self.ed._refresh_info()

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
            self._commit(move_mark(self.segs, k, to))
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
            st, bpm, _n, kind = self.segs[k]
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
        if not tick or now - self._band_tick > 0.1:        # la bande suit la lecture, 10 fois par seconde
            self._band_tick = now
            self.band.update()

    def refresh(self) -> None:
        """Après chaque changement (appelé par GridEditor._refresh_info)."""
        from ..i18n import t

        self.sync()
        ed = self.ed
        if not self.segs:
            return
        k = segment_at(self.segs, ed.cursor_ms)
        self.seg_lbl.setText(t("grid.seg_current", n=k + 1, total=len(self.segs)))
        if not self.bpm_entry.hasFocus():
            self.bpm_entry.setText(f"{self.segs[k][1]:.2f}")
        self.remove_btn.setEnabled(len(self.segs) > 1)
        p = self._profile()
        user = getattr(p, "user_kind", "") if p is not None else ""
        detected = getattr(p, "detected", "") if p is not None else ""
        self._filling = True
        try:
            auto = t("grid.seg_kind_auto_is", kind=t(f"grid.seg_kind_{detected or 'none'}"))
            self.kind_menu.setItemText(0, auto)
            self.kind_menu.setCurrentIndex(max(0, self.kind_menu.findData(user)))
            self.kind_menu.setEnabled(p is not None)
        finally:
            self._filling = False
        self.live()

    def remember(self) -> None:
        """À l'enregistrement : repères gardés à la réanalyse (aucun : plus rien à garder)."""
        if not self.edited and not self._stored:
            return
        from .tempo_grids import TempoGridService

        self.sync(cues=False)
        marks = to_marks(self.segs) if len(self.segs) > 1 else []
        if TempoGridService.remember_marks(self.ed.track, marks):
            self._stored = [(float(s[0]), s[3]) for s in self.segs[1:]]
