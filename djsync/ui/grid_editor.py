"""Éditeur « Grille et cues » : grille de temps (comme le mode GRID de Rekordbox) et, depuis la 1.3.0
(C22), hot cues A à H, boucles et mémoires (voir `cue_pads.py`).

Pour corriger un décalage observé sur les platines : la forme d'onde détaillée du son (ANLZ) avec
ses temps (1ers temps de mesure plus épais, à la couleur d'accent). On peut :
  * décaler toute la grille (±1, ±10, ±100 ms) ;
  * placer un début de mesure exactement sur le curseur, ou faire du temps sélectionné le 1 ;
  * imposer un BPM, le doubler ou le diviser par 2 (grille constante ancrée sur le temps sélectionné) ;
  * écouter à partir d'un endroit (clic ou glisser sur la forme d'onde : le curseur suit ; en lecture,
    la lecture saute à cet endroit) ;
puis Enregistrer : le .DAT est réécrit (copie d'origine dans DJSync_Backups/anlz), le BPM mis à
jour dans exportLibrary.db et export.pdb.

C'est une PAGE de la fenêtre principale (comme un onglet), ouverte par `DJSyncApp.open_grid_editor` :
changer d'onglet la cache sans perdre les modifications ; « Retour » ou Échap la ferme.
"""
from __future__ import annotations

import copy
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF, QShortcut, QKeySequence
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QScrollBar, QWidget

from ..analysis import grid as G
from ..analysis.cues import Cue, nearest_beat_ms
from ..audio.player import PAUSED, PLAYING
from ..i18n import plural, t
from ..models import LibraryTrack, format_duration
from . import theme
from .dialogs import ConfirmDialog
from .icons import qicon
from .widgets import button, hbox, icon_button, label, restyle, vbox

COLS_PER_S = 150.0          # forme d'onde détaillée ANLZ : 150 colonnes par seconde
VIEW_CHOICES = (2, 4, 8, 16, 32)
# Couleurs de la forme d'onde 3 bandes de Rekordbox (basses, médiums, aigus), quel que soit le thème
BAND_COLORS = ("#1f6fe5", "#f0982c", "#f6ead2")
SCROLL_STEPS = 1000


class GridCanvas(QWidget):
    def __init__(self, editor: "GridEditor") -> None:
        super().__init__()
        self.ed = editor
        self.setMinimumHeight(theme.px(110))        # 1.3.0-rc.3 (B16) : rétrécit avant les pads
        self.setCursor(Qt.CrossCursor)
        self._drag_x: Optional[float] = None
        self._drag_start = 0.0

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.SURFACE))
        self.ed.paint(p, self.width(), self.height())
        p.end()

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        """Clic gauche : curseur d'écoute ; clic droit / milieu : faire défiler en glissant."""
        self.setFocus()
        x = e.position().x()
        if e.button() == Qt.LeftButton:
            if not self.ed.grab_cue(x, e.position().y()):
                if self.ed.fixed_cursor:              # 1.3.0-rc.3 (B17) : on fait glisser le son sous le curseur
                    self.ed.begin_scrub(x)
                else:
                    self.ed.press(x)
        elif self.ed.fixed_cursor:
            self.ed.begin_scrub(x)
        else:
            self._drag_x, self._drag_start = x, self.ed.start_ms

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        x = e.position().x()
        if e.buttons() & Qt.LeftButton and self.ed.dragging_cue():
            self.ed.drag_cue(x, bool(e.modifiers() & Qt.ShiftModifier))
        elif self.ed.scrubbing_fixed():
            self.ed.scrub_to(x)
        elif e.buttons() & Qt.LeftButton:
            self.ed.press(x, dragging=True)
        elif self._drag_x is not None and e.buttons() & (Qt.RightButton | Qt.MiddleButton):
            self.ed.start_ms = self._drag_start - (x - self._drag_x) / self.ed.px_per_ms
            self.ed.draw()

    def mouseReleaseEvent(self, e: Any) -> None:    # noqa: N802
        if self.ed.scrubbing_fixed():
            self.ed.end_scrub(e.position().x())
        elif e.button() == Qt.LeftButton:
            if self.ed.dragging_cue():
                self.ed.drop_cue()
            else:
                self.ed.release()
        self._drag_x = None

    def contextMenuEvent(self, e: Any) -> None:     # noqa: N802
        e.accept()                                  # clic droit = défilement, pas de menu

    def wheelEvent(self, e: Any) -> None:           # noqa: N802
        """Molette : défiler. 1.2.1 (C03) : Ctrl / ⌘ + molette (ou pincement du pavé tactile) : zoomer."""
        if e.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
            self.ed.zoom(-1 if e.angleDelta().y() > 0 else 1)
            return
        dy = e.angleDelta().y() or e.angleDelta().x()
        if dy:
            self.ed.pan(-0.15 if dy > 0 else 0.15)

    def event(self, e: Any) -> bool:                 # noqa: D401
        from PySide6.QtCore import QEvent

        if e.type() == QEvent.NativeGesture:         # pincement (Mac, pavés tactiles)
            from PySide6.QtCore import Qt as _Qt

            if e.gestureType() == _Qt.ZoomNativeGesture and abs(e.value()) > 0.02:
                self.ed.zoom(-1 if e.value() > 0 else 1)
                return True
        return super().event(e)


class GridEditor(QWidget):
    """Page « Grille de temps » (dans la zone de contenu de la fenêtre principale)."""

    def __init__(self, parent: Any, controller: Any, track: LibraryTrack, on_close: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.ctrl, self.track = controller, track
        self._on_close = on_close
        self._closed = False
        self.original: List[Tuple[int, int, int]] = []
        self.beats: List[Tuple[int, int, int]] = []
        self.detail: List[Tuple[float, str]] = []
        self.wave: Any = None                  # BandWave fine (calculée depuis l'audio), sinon ANLZ
        self._wave_state = "loading"           # loading | ready | failed (ANLZ affichée seulement si échec)
        self.duration_ms = max(1, track.duration_seconds * 1000)
        self.view_s = 8
        self.start_ms = 0.0
        self.cursor_ms = 0.0
        self.selected = 0
        self.cues: List[Cue] = []              # 1.3.0 (C22) : hot cues, boucles, mémoires
        self.original_cues: List[Cue] = []
        self.active_loop: Optional[Tuple[int, int]] = None
        self._drag_cue: Optional[Cue] = None
        self._native = False
        self._scrubbing = False
        self._scrub: Optional[Tuple[float, float, bool]] = None    # (x de départ, curseur de départ, a bougé)
        # 1.3.0-rc.3 (B17) : curseur volant par défaut (il suit la souris sur une vue fixe) ; case « Curseur
        # fixe au centre » : le son défile sous un curseur immobile, comme Rekordbox. Choix gardé.
        self.fixed_cursor = bool(getattr(controller.settings, "grid_fixed_cursor", False))
        self._label_top, self._label_bottom = 14, 32               # bande des étiquettes (B16, recalculée au dessin)
        self._lead_ms = self._timeline_lead(track)
        self.body = vbox(self, margins=theme.px(18), spacing=theme.px(8))

        head = hbox()
        head.addWidget(button(t("grid.back"), self.close, kind="flat", icon="back"))
        titles = vbox(spacing=0)
        titles.addWidget(label(track.display_name, "title"))
        self.info = label(t("grid.loading"), "dim")
        titles.addWidget(self.info)
        head.addLayout(titles, 1)
        head.addWidget(label(t("grid.view"), "dim"))
        self.view_menu = QComboBox()
        self.view_menu.addItems([f"{v} s" for v in VIEW_CHOICES])
        self.view_menu.setCurrentText(f"{self.view_s} s")
        self.view_menu.currentTextChanged.connect(self._view_changed)
        head.addWidget(self.view_menu)
        head.addWidget(icon_button("minus", lambda: self.zoom(1), t("grid.zoom_out")))
        head.addWidget(icon_button("plus", lambda: self.zoom(-1), t("grid.zoom_in")))
        self.body.addLayout(head)

        # 1.3.0-rc.3 (B20) : son dont le fichier audio est introuvable
        self.missing = label(t("grid.file_missing"), "err", wrap=True)
        self.missing.setVisible(bool(controller.file_missing(track)))
        self.missing.setProperty("role", "err")
        self.body.addWidget(self.missing)
        self.canvas = GridCanvas(self)
        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.canvas.setToolTip(t("grid.hint"))
        self.body.addWidget(self.canvas, 1)
        self.scroll = QScrollBar(Qt.Horizontal)
        self.scroll.setRange(0, SCROLL_STEPS)
        self.scroll.valueChanged.connect(self._scrolled)
        self.body.addWidget(self.scroll)

        from .cue_pads import CuePanel

        self.cue_panel = CuePanel(self)
        self.body.addWidget(self.cue_panel)

        tools = hbox()
        self.play_btn = icon_button("play", self._play, t("grid.play_tip"), color=theme.ON_ACCENT)
        self.play_btn.setProperty("kind", "primary")
        tools.addWidget(self.play_btn)
        # 1.3.0-rc.3 (C40) : sortir de la boucle sans coupure (« Loop Exit » des platines)
        self.exit_btn = button(t("grid.loop_exit"), self.exit_loop, kind="primary", icon="next",
                               tooltip=t("grid.loop_exit_tip"))
        self.exit_btn.hide()
        tools.addWidget(self.exit_btn)
        self.time_lbl = label("0:00.000", "dim")
        self.time_lbl.setMinimumWidth(theme.px(64))
        tools.addWidget(self.time_lbl)
        tools.addSpacing(theme.px(8))
        tools.addWidget(label(t("grid.shift"), "dim"))
        for ms in (-100, -10, -1, 1, 10, 100):
            b = button(f"{ms:+d}".replace("-", "−"), lambda m=ms: self._shift(m), tooltip=t("grid.shift_tip", ms=ms))
            b.setMinimumWidth(theme.px(40))
            tools.addWidget(b)
        tools.addSpacing(theme.px(8))
        tools.addWidget(button(t("grid.half_beat"), self._shift_half, tooltip=t("grid.half_beat_tip")))
        tools.addStretch(1)
        self.fixed_box = QCheckBox(t("grid.fixed_cursor"))
        self.fixed_box.setToolTip(t("grid.fixed_cursor_tip"))
        self.fixed_box.setChecked(self.fixed_cursor)
        self.fixed_box.toggled.connect(self._set_fixed)
        tools.addWidget(self.fixed_box)
        self.body.addLayout(tools)

        tools2 = hbox()
        tools2.addWidget(button(t("grid.bar_here"), self._bar_here, kind="primary", icon="grid",
                                tooltip=t("grid.bar_here_tip")))
        tools2.addWidget(button(t("grid.downbeat"), self._downbeat, tooltip=t("grid.downbeat_tip")))
        tools2.addStretch(1)
        tools2.addWidget(button(t("grid.half"), lambda: self._scale(0.5), tooltip=t("grid.half_tip")))
        tools2.addWidget(button(t("grid.double"), lambda: self._scale(2.0), tooltip=t("grid.double_tip")))
        tools2.addSpacing(theme.px(8))
        tools2.addWidget(label("BPM", "dim"))
        self.bpm_entry = QLineEdit()
        self.bpm_entry.setFixedWidth(theme.px(70))
        self.bpm_entry.returnPressed.connect(self._apply_bpm)
        tools2.addWidget(self.bpm_entry)
        tools2.addWidget(button(t("grid.apply_bpm"), self._apply_bpm, icon="check", tooltip=t("grid.apply_bpm_tip")))
        self.body.addLayout(tools2)

        bar = hbox()
        self.reset_btn = button(t("grid.reset"), self._reset, icon="refresh")
        bar.addWidget(self.reset_btn)
        self.state_lbl = label("", "dim")
        bar.addWidget(self.state_lbl, 1)
        self.save_btn = button(t("action.save"), self._save, kind="primary", icon="check")
        self.save_btn.setEnabled(False)
        bar.addWidget(self.save_btn)
        bar.addWidget(button(t("grid.back"), self.close, icon="back"))
        self.body.addLayout(bar)

        for seq, fn in ((Qt.Key_Left, lambda: self._shift(-1)), (Qt.Key_Right, lambda: self._shift(1)),
                        (Qt.Key_Escape, self.close)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda f=fn: f() if not self.bpm_entry.hasFocus() else None)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)
        controller.load_grid(track.content_id, self._loaded, self._load_failed)
        controller._emit("grid_page", self)          # 1.3.0-rc.3 (B17) : le lecteur passe en forme d'onde 3 bandes

    def _timeline_lead(self, track: LibraryTrack) -> float:
        """La grille est dans la base de temps de Rekordbox (silence d'amorçage MP3, décalage m4a), le
        lecteur joue le fichier sans ce silence : on en tient compte pour le curseur et la lecture."""
        try:
            from ..analysis.decode import timeline_lead_seconds

            return timeline_lead_seconds(self.ctrl.library.absolute_path(track)) * 1000.0
        except Exception:  # noqa: BLE001
            return 0.0

    def _player_seek(self, ms: float) -> None:
        self.ctrl.player.seek(max(0.0, (ms - self._lead_ms) / 1000.0))

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return not self._closed and isValid(self)

    # ------------------------------------------------------------------ chargement
    def _loaded(self, data: Any) -> None:
        if not self.winfo_exists():
            return
        g = data["grid"]
        self.original = list(g.beats)
        self.beats = list(g.beats)
        self.detail = data["detail"]
        self._band_fallback = data.get("band")      # B21 : 3 bandes de Rekordbox si le fichier est introuvable
        self.duration_ms = max(g.duration_ms, g.beats[-1][2] + 1000, int(len(self.detail) / COLS_PER_S * 1000))
        self._native = g.native
        self.cues = copy.deepcopy(list(data.get("cues") or []))
        self.original_cues = copy.deepcopy(self.cues)
        self.cue_panel.refresh()
        self.selected = next((i for i, b in enumerate(self.beats) if b[0] == 1), 0)
        self.cursor_ms = self.beats[self.selected][2]
        self.start_ms = max(0.0, self.cursor_ms - 1000)
        self._center()
        self._refresh_info()
        self.draw()
        self.ctrl.load_grid_wave(self.track, self._wave_loaded)

    def _wave_loaded(self, wave: Any) -> None:
        if not self.winfo_exists():
            return
        if wave is None:                             # B21 : fichier introuvable ou illisible
            from ..analysis.anlz import band_from_detail

            wave = getattr(self, "_band_fallback", None) or band_from_detail(self.detail)
        self.wave = wave
        self._wave_state = "ready" if wave is not None else "failed"
        self.draw()

    def _load_failed(self, exc: BaseException) -> None:
        if self.winfo_exists():
            self.info.setText(self.ctrl.error_text(exc))
            self.info.setProperty("role", "err")
            restyle(self.info)

    # ---------------------------------------------------------------- géométrie
    @property
    def px_per_ms(self) -> float:
        return max(1, self.canvas.width()) / (self.view_s * 1000.0)

    def _x(self, ms: float) -> float:
        return (ms - self.start_ms) * self.px_per_ms

    def _ms(self, x: float) -> float:
        return self.start_ms + x / self.px_per_ms

    def _clamp_view(self) -> None:
        span = self.view_s * 1000.0
        if self.fixed_cursor:                # le curseur reste au centre, même au début et à la fin du son
            self.cursor_ms = max(0.0, min(float(self.duration_ms), self.cursor_ms))
            self.start_ms = self.cursor_ms - span / 2
            value = self.cursor_ms / max(1.0, float(self.duration_ms))
        else:
            self.start_ms = max(0.0, min(self.start_ms, max(0.0, self.duration_ms - span)))
            value = self.start_ms / max(1.0, self.duration_ms - span)
        self.scroll.blockSignals(True)
        self.scroll.setValue(int(SCROLL_STEPS * value))
        self.scroll.blockSignals(False)

    def _center(self) -> None:
        if self.fixed_cursor:
            self.start_ms = self.cursor_ms - self.view_s * 500.0

    def _set_fixed(self, on: bool) -> None:
        self.fixed_cursor = bool(on)
        try:
            self.ctrl.settings.grid_fixed_cursor = bool(on)
            self.ctrl.settings.save()
        except Exception:  # noqa: BLE001 - réglage de confort
            pass
        self._center()
        self.draw()

    # -------------------------------------------- curseur fixe : faire glisser le son (B17)
    def begin_scrub(self, x: float) -> None:
        self.active_loop = None
        self._scrub = (x, self.cursor_ms, False)
        self._scrubbing = True

    def scrubbing_fixed(self) -> bool:
        return self._scrub is not None

    def scrub_to(self, x: float) -> None:
        if self._scrub is None:
            return
        x0, c0, moved = self._scrub
        moved = moved or abs(x - x0) > 3
        self._scrub = (x0, c0, moved)
        if moved:
            self._move_cursor(c0 - (x - x0) / self.px_per_ms)

    def end_scrub(self, x: float) -> None:
        if self._scrub is None:
            return
        _x0, _c0, moved = self._scrub
        self._scrub = None
        if not moved:                        # simple clic : ce point vient sous le curseur
            self._move_cursor(self._ms(x))
        self.release()

    def _move_cursor(self, ms: float) -> None:
        self.cursor_ms = min(max(0.0, ms), float(self.duration_ms))
        if self.beats:
            self.selected = G.nearest(self.beats, self.cursor_ms)
            self._refresh_info()
        self._center()
        self._show_time()
        self.draw()

    # ------------------------------------------------------------------- dessin
    def draw(self) -> None:
        self.canvas.update()

    def paint(self, p: QPainter, w: int, h: int) -> None:
        if w < 10 or not self.beats:
            return
        self._clamp_view()
        mid = h * 0.55
        if self.wave is not None:
            self._paint_bands(p, w, h, mid)
        elif self._wave_state == "loading":         # pas d'ancienne forme d'onde le temps du calcul
            p.setPen(QColor(theme.FAINT))
            p.drawText(self.canvas.rect(), Qt.AlignCenter, t("grid.wave_loading"))
        elif self.detail:            # une colonne par pixel, max des colonnes ANLZ couvertes
            n = len(self.detail)
            for x in range(w):
                a = int(self._ms(x) / 1000.0 * COLS_PER_S)
                b = max(a + 1, int(self._ms(x + 1) / 1000.0 * COLS_PER_S))
                if a >= n or b <= 0:
                    continue
                seg = self.detail[max(0, a):min(n, b)]
                if not seg:
                    continue
                v, color = max(seg, key=lambda s: s[0])
                half = max(1.0, v * (h * 0.42))
                p.setPen(QColor(theme.DIM if color in ("#000000", "#000") else color))
                p.drawLine(QPointF(x, mid - half), QPointF(x, mid + half))
        lo, hi = self._ms(-2), self._ms(w + 2)
        font = QFont(p.font())
        font.setBold(True)
        p.setFont(font)
        # 1.3.0-rc.3 (B16) : bande du haut à l'échelle de la police, sur deux niveaux : numéros de mesure,
        # puis étiquettes des cues (plus de « B73 ») ; temps de la vue à droite, jamais recouvert
        fm = QFontMetrics(font)
        row = fm.height() + theme.px(2)
        self._label_top, self._label_bottom = row, row + fm.height() + theme.px(4)
        time_text = format_duration(int(max(0.0, self.start_ms) / 1000))
        time_left = w - theme.px(6) - fm.horizontalAdvance(time_text) - theme.px(6)
        bar_no = 0
        for i, (n, _tempo, ms) in enumerate(self.beats):
            if n == 1:
                bar_no += 1
            if ms < lo or ms > hi:
                continue
            x = self._x(ms)
            down = n == 1
            color = QColor(theme.ACCENT if down else theme.mix(theme.SURFACE, theme.TEXT, 0.55))
            p.setPen(QPen(color, theme.px(2.5) if down else 1))
            p.drawLine(QPointF(x, row), QPointF(x, h))
            if down and x + 4 + fm.horizontalAdvance(str(bar_no)) < time_left:
                p.drawText(QPointF(x + 4, fm.ascent() + 1), str(bar_no))
            if i == self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.WARN))
                p.drawPolygon(QPolygonF([QPointF(x - 6, h), QPointF(x + 6, h), QPointF(x, h - 10)]))
                p.setBrush(Qt.NoBrush)
        self._paint_cues(p, w, h)
        xc = self._x(self.cursor_ms)
        if 0 <= xc <= w:
            p.setPen(QPen(QColor(theme.TEXT), 1, Qt.DashLine))
            p.drawLine(QPointF(xc, 0), QPointF(xc, h))
        p.setPen(QColor(theme.FAINT))
        p.drawText(self.canvas.rect().adjusted(0, 1, -theme.px(6), 0), Qt.AlignRight | Qt.AlignTop, time_text)

    def _paint_cues(self, p: QPainter, w: int, h: int) -> None:
        """Boucles (bande colorée), hot cues (trait + étiquette de la lettre en haut), mémoires (▼ rouge)."""
        from .cue_pads import rgb_hex

        lo, hi = self._ms(-40), self._ms(w + 2)
        font = QFont(p.font())
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        top, bottom = self._label_top, self._label_bottom
        tag_w = fm.horizontalAdvance("W") + theme.px(6)
        for c in self.cues:
            if c.is_loop and c.loop_ms >= lo and c.ms <= hi:
                col = QColor(rgb_hex(c.colour()))
                col.setAlpha(70 if self.active_loop != (c.ms, c.loop_ms) else 120)
                x0, x1 = max(0.0, self._x(c.ms)), min(float(w), self._x(c.loop_ms))
                p.fillRect(int(x0), bottom, max(1, int(x1 - x0)), h - bottom, col)
        for c in self.cues:
            if c.ms < lo or c.ms > hi:
                continue
            x = self._x(c.ms)
            col = QColor(rgb_hex(c.colour()))
            if c.slot:
                p.setPen(QPen(col, theme.px(2)))
                p.drawLine(QPointF(x, bottom), QPointF(x, h))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRect(int(x), top, tag_w, bottom - top)
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor("#101010"))
                p.drawText(int(x), top, tag_w, bottom - top, Qt.AlignCenter, c.label)
            else:
                k = theme.px(6)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.ERR))
                p.drawPolygon(QPolygonF([QPointF(x - k, top), QPointF(x + k, top), QPointF(x, top + 1.6 * k)]))
                p.setBrush(Qt.NoBrush)

    # ------------------------------------------------------------ cues : glisser
    def grab_cue(self, x: float, y: float) -> bool:
        """Clic sur l'étiquette d'une hot cue (bande du haut) : on la déplace en glissant."""
        if y > self._label_bottom:
            return False
        tag_w = QFontMetrics(self.canvas.font()).horizontalAdvance("W") + theme.px(6)
        near = [c for c in self.cues if c.slot and -3 <= x - self._x(c.ms) <= tag_w + 3]
        if not near:
            return False
        self._drag_cue = near[0]
        return True

    def dragging_cue(self) -> bool:
        return self._drag_cue is not None

    def drag_cue(self, x: float, exact: bool = False) -> None:
        c = self._drag_cue
        if c is None:
            return
        ms = max(0.0, min(float(self.duration_ms), self._ms(x)))
        ms = int(round(ms)) if exact or not self.beats else nearest_beat_ms(self.beats, ms)
        if c.is_loop:
            c.loop_ms = ms + (c.loop_ms - c.ms)
        c.ms = ms
        self.cue_panel.refresh()
        self.draw()

    def drop_cue(self) -> None:
        self._drag_cue = None
        self.cues_changed()

    def cues_changed(self) -> None:
        self._refresh_info()
        self.draw()

    def cues_dirty(self) -> bool:
        def sig(cs: List[Cue]) -> List[Any]:
            return sorted((c.slot, c.ms, c.loop_ms if c.is_loop else None, c.loop_beats, c.name, c.color_code)
                          for c in cs)
        return sig(self.cues) != sig(self.original_cues)

    def go_to(self, ms: float) -> None:
        """Curseur sur ce point (vue recentrée) ; en lecture, la lecture y saute."""
        self.active_loop = None
        self.cursor_ms = float(ms)
        span = self.view_s * 1000.0
        if self.fixed_cursor:
            self._center()
        elif not (self.start_ms <= ms <= self.start_ms + span * 0.85):
            self.start_ms = ms - span * 0.15
        self._show_time()
        if self._is_playing_this() and self.ctrl.player.state in (PLAYING, PAUSED):
            self._player_seek(ms)
        self.draw()

    def play_from(self, ms: float, loop: Optional[Tuple[int, int]] = None) -> None:
        """Pad posé : écouter depuis ce point ; une boucle tourne jusqu'au prochain clic sur la forme d'onde."""
        self.go_to(ms)
        self.active_loop = (int(loop[0]), int(loop[1])) if loop else None
        if self._is_playing_this() and self.ctrl.player.state == PLAYING:
            return
        if self._is_playing_this() and self.ctrl.player.state == PAUSED:
            self.ctrl.player.toggle_pause()
            return
        self._play()

    def exit_loop(self) -> None:
        """C40 : la boucle s'arrête de revenir au début ; la lecture continue sans coupure."""
        if self.active_loop is None:
            return
        self.active_loop = None
        self.exit_btn.hide()
        self.draw()

    def keyPressEvent(self, e: Any) -> None:         # noqa: N802
        """Touches 1 à 8 (ou la même rangée sur un clavier AZERTY) : pads A à H ; 0 (« à ») : sortir de la boucle."""
        keys = "12345678"
        azerty = "".join(map(chr, (38, 233, 34, 39, 40, 45, 232, 95)))     # même rangée en AZERTY, sans Maj
        text = e.text()
        if text in ("0", chr(224)) and self.active_loop is not None and not self.bpm_entry.hasFocus():
            self.exit_loop()
            return
        if text and not self.bpm_entry.hasFocus():
            slot = keys.find(text) + 1 or azerty.find(text) + 1
            if slot:
                self.cue_panel.pad_clicked(slot)
                return
        super().keyPressEvent(e)

    def _paint_bands(self, p: QPainter, w: int, h: int, mid: float) -> None:
        """Forme d'onde 3 bandes façon Rekordbox : basses (bleu) derrière, médiums (orange), aigus
        (blanc) devant, symétrique ; chaque pixel = maximum des points qu'il couvre."""
        import numpy as np

        wave = self.wave
        n = wave.low.size
        xs = np.arange(w + 1, dtype=np.float64)
        pos = (self.start_ms + xs / self.px_per_ms) / 1000.0 * wave.rate
        a = np.clip(np.floor(pos[:-1]).astype(np.int64), 0, n - 1)
        b = np.clip(np.maximum(a + 1, np.floor(pos[1:]).astype(np.int64)), 1, n)
        inside = (pos[:-1] < n) & (pos[1:] > 0)
        scale = h * 0.27 / 127.0                 # amplitude réduite : temps plus lisibles
        p.setPen(Qt.NoPen)
        for band, color in zip((wave.low, wave.mid, wave.high), BAND_COLORS):
            # maximum sur [a_i, a_i+1) (bornes croissantes) ; un 0 ajouté en fin sert de borne finale
            vals = np.maximum.reduceat(np.append(band, 0), np.append(a, b[-1]))[:-1]
            vals = np.where(inside, vals, 0).astype(np.float64) * scale
            top = [QPointF(float(x) + 0.5, mid - v) for x, v in enumerate(vals)]
            bottom = [QPointF(float(x) + 0.5, mid + v) for x, v in reversed(list(enumerate(vals)))]
            p.setBrush(QColor(color))
            p.drawPolygon(QPolygonF(top + bottom))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(theme.mix(theme.SURFACE, theme.TEXT, 0.25)), 1))
        p.drawLine(QPointF(0, mid), QPointF(w, mid))

    def _refresh_info(self) -> None:
        if not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        bpm = tempos[len(tempos) // 2] / 100.0
        kind = t("grid.constant") if len(set(tempos)) <= 1 else t("grid.variable")
        delta = self.beats[self.selected][2] - self._original_at(self.selected)
        parts = [f"{bpm:.2f} BPM", kind, plural("grid.beats_one", "grid.beats_many", len(self.beats))]
        if self._native:
            parts.append(t("grid.native"))
        self.info.setText("  ·  ".join(parts))
        self.bpm_entry.setText(f"{bpm:.2f}")
        grid_changed = self.beats != self.original
        cues_changed = self.cues_dirty()
        self.save_btn.setEnabled(grid_changed or cues_changed)
        parts = [t("grid.modified", ms=f"{delta:+d}")] if grid_changed else []
        if cues_changed:
            parts.append(t("cue.modified"))
        self.state_lbl.setText("  ·  ".join(parts))

    def _original_at(self, index: int) -> int:
        """Position d'origine du temps le plus proche (pour afficher le décalage appliqué)."""
        if not self.original:
            return 0
        j = G.nearest(self.original, self.beats[index][2])
        return self.original[j][2]

    # ---------------------------------------------------------------- édition
    def _shift(self, ms: int) -> None:
        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.shift(self.beats, ms, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor + ms)
        self._refresh_info()
        self.draw()

    def _shift_half(self) -> None:
        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.shift_half_beat(self.beats, self.selected, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _downbeat(self) -> None:
        if self.beats:
            self.beats = G.set_downbeat(self.beats, self.selected)
            self._refresh_info()
            self.draw()

    def _bar_here(self) -> None:
        """Un temps exactement sur le curseur, qui devient le 1er temps d'une mesure."""
        if self.beats:
            self.beats, self.selected = G.bar_at(self.beats, self.cursor_ms, self.duration_ms)
            self._refresh_info()
            self.draw()

    def _scale(self, factor: float) -> None:
        if not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        if not 40 <= tempos[len(tempos) // 2] / 100.0 * factor <= 300:
            self.ctrl.message("warn", t("grid.bpm_range"))
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.scale_tempo(self.beats, factor, self.selected, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _apply_bpm(self) -> None:
        try:
            bpm = float(self.bpm_entry.text().replace(",", "."))
        except ValueError:
            return
        if not 40 <= bpm <= 300 or not self.beats:
            self.ctrl.message("warn", t("grid.bpm_range"))
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.set_bpm(self.beats, bpm, self.selected, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _reset(self) -> None:
        self.beats = list(self.original)
        self.cues = copy.deepcopy(self.original_cues)
        self.active_loop = None
        self.cue_panel.refresh()
        self.selected = min(self.selected, len(self.beats) - 1)
        self._refresh_info()
        self.draw()

    # --------------------------------------------------------------- navigation
    def _view_changed(self, text: str) -> None:
        center = self.cursor_ms if self.fixed_cursor else self.start_ms + self.view_s * 500
        self.view_s = int(text.split()[0])
        self.start_ms = center - self.view_s * 500
        self.draw()

    def zoom(self, step: int) -> None:
        """Vue plus courte (step < 0, on zoome) ou plus longue, centrée sur le curseur s'il est visible."""
        i = VIEW_CHOICES.index(self.view_s) if self.view_s in VIEW_CHOICES else 2
        j = max(0, min(len(VIEW_CHOICES) - 1, i + step))
        if j == i:
            return
        span = self.view_s * 1000.0
        anchor = self.cursor_ms if self.start_ms <= self.cursor_ms <= self.start_ms + span else self.start_ms + span / 2
        ratio = (anchor - self.start_ms) / span if span else 0.5
        if self.fixed_cursor:
            anchor, ratio = self.cursor_ms, 0.5
        self.view_s = VIEW_CHOICES[j]
        self.start_ms = anchor - ratio * self.view_s * 1000.0
        self.view_menu.blockSignals(True)
        self.view_menu.setCurrentText(f"{self.view_s} s")
        self.view_menu.blockSignals(False)
        self.draw()

    def _scrolled(self, value: int) -> None:
        if self.fixed_cursor:
            self._move_cursor(value / SCROLL_STEPS * self.duration_ms)
            self.release()
            return
        self.start_ms = value / SCROLL_STEPS * max(0.0, self.duration_ms - self.view_s * 1000.0)
        self.draw()

    def pan(self, fraction: float) -> None:
        if self.fixed_cursor:                    # molette : le son avance sous le curseur
            self._move_cursor(self.cursor_ms + fraction * self.view_s * 1000)
            self.release()
            return
        self.start_ms += fraction * self.view_s * 1000
        self.draw()

    def press(self, x: float, dragging: bool = False) -> None:
        """Le curseur d'écoute suit la souris (clic ou glisser) ; en lecture, la lecture y saute au
        relâchement (et pendant le glisser, au plus toutes les ~60 ms)."""
        w = max(1, self.canvas.width())
        x = min(max(0.0, x), float(w))
        if not dragging:
            self.active_loop = None
        self.cursor_ms = min(max(0.0, self._ms(x)), float(self.duration_ms))
        self._scrubbing = True
        if self.beats:
            self.selected = G.nearest(self.beats, self.cursor_ms)
            self._refresh_info()
        if dragging:                         # au bord : la vue défile pour suivre
            span = self.view_s * 1000.0
            if x >= w - 4:
                self.start_ms += span * 0.05
            elif x <= 4:
                self.start_ms -= span * 0.05
        self._show_time()
        self.draw()

    def release(self) -> None:
        self._scrubbing = False
        if self.ctrl.player.state in (PLAYING, PAUSED) and self._is_playing_this():
            self._player_seek(self.cursor_ms)

    def _show_time(self) -> None:
        s_ = self.cursor_ms / 1000.0
        self.time_lbl.setText(f"{int(s_ // 60)}:{s_ % 60:06.3f}")

    # ------------------------------------------------------------------- écoute
    def _is_playing_this(self) -> bool:
        item = self.ctrl.current_item
        return item is not None and item.kind == "library" and item.item.content_id == self.track.content_id

    def _play(self) -> None:
        if not self.missing.isHidden():               # B20 : pas d'erreur à chaque clic, le bandeau le dit
            return
        player = self.ctrl.player
        if self._is_playing_this() and player.state in (PLAYING, PAUSED):
            player.toggle_pause()
            return
        self.ctrl.play_queue([self.track], 0)
        start = self.cursor_ms

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                self._player_seek(start)
            elif tries < 40 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek_when_ready(tries + 1))

        QTimer.singleShot(100, seek_when_ready)

    def _tick(self) -> None:
        player = self.ctrl.player
        playing = self._is_playing_this() and player.state == PLAYING
        interval = 16 if playing else 60          # 1.3.0-rc.3 (C39) : ~60 images/s pendant la lecture
        self.exit_btn.setVisible(self.active_loop is not None and playing)
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        self.play_btn.setIcon(qicon("pause" if playing else "play", 16, theme.ON_ACCENT))
        if playing and not self._scrubbing:
            self.cursor_ms = player.position() * 1000.0 + self._lead_ms
            # 1.3.0-rc.3 (C39) : la fin de boucle se décide sur ce qui est ENVOYÉ à la carte son (en avance
            # de sa réserve), pour que le retour au début s'entende pile à la fin de la boucle
            sent_ms = player.sent_position() * 1000.0 + self._lead_ms
            if self.active_loop and sent_ms >= self.active_loop[1]:
                over = sent_ms - self.active_loop[1]
                length = max(1.0, self.active_loop[1] - self.active_loop[0])
                self._player_seek(self.active_loop[0] + over % length)
            self._show_time()
            span = self.view_s * 1000.0
            if self.fixed_cursor:
                self._center()
            elif not (self.start_ms <= self.cursor_ms <= self.start_ms + span * 0.85):
                self.start_ms = self.cursor_ms - span * 0.15
            self.draw()

    # -------------------------------------------------------------- enregistrer
    def _save(self) -> None:
        def go() -> None:
            self.save_btn.setEnabled(False)
            self.save_btn.setText(t("grid.saving"))

            def done(_r: Any) -> None:
                if self.winfo_exists():
                    self._leaving = True
                    self.close()

            def failed(_e: BaseException) -> None:
                if self.winfo_exists():
                    self.save_btn.setEnabled(True)
                    self.save_btn.setText(t("action.save"))

            beats = self.beats if self.beats != self.original else None
            cues = self.cues if self.cues_dirty() else None
            self.ctrl.save_grid_and_cues(self.track.content_id, beats, cues, ok=done, err=failed)

        if self._native and self.beats != self.original:
            ConfirmDialog(self, t("grid.native_title"), t("grid.native_msg"), go, confirm_text=t("action.save"),
                          detail=t("grid.native_detail"))
        else:
            go()

    def is_dirty(self) -> bool:
        return bool(self.beats) and (self.beats != self.original or self.cues_dirty())

    def close(self) -> bool:                 # noqa: D401
        """Quitte la page (sans enregistrer) ; la lecture du son continue. 1.3.0 : grille ou cues
        modifiés et pas enregistrés -> on demande avant de les perdre."""
        if self._closed:
            return True
        if self.is_dirty() and not getattr(self, "_leaving", False):
            def leave() -> None:
                self._leaving = True
                self.close()

            ConfirmDialog(self, t("grid.leave_title"), t("grid.leave_msg"), leave,
                          confirm_text=t("grid.leave_confirm"), danger=True)
            return False
        self._closed = True
        self._timer.stop()
        self.ctrl._emit("grid_page", None)
        callback, self._on_close = self._on_close, None
        self.hide()
        self.deleteLater()
        if callback:
            callback()
        return True
