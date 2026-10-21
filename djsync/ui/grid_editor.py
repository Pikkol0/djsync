"""Éditeur de grille de temps (comme le mode GRID de Rekordbox).

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

from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QShortcut, QKeySequence
from PySide6.QtWidgets import QComboBox, QLineEdit, QScrollBar, QWidget

from ..analysis import grid as G
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
        self.setMinimumHeight(theme.px(190))
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
            self.ed.press(x)
        else:
            self._drag_x, self._drag_start = x, self.ed.start_ms

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        x = e.position().x()
        if e.buttons() & Qt.LeftButton:
            self.ed.press(x, dragging=True)
        elif self._drag_x is not None and e.buttons() & (Qt.RightButton | Qt.MiddleButton):
            self.ed.start_ms = self._drag_start - (x - self._drag_x) / self.ed.px_per_ms
            self.ed.draw()

    def mouseReleaseEvent(self, e: Any) -> None:    # noqa: N802
        if e.button() == Qt.LeftButton:
            self.ed.release()
        self._drag_x = None

    def contextMenuEvent(self, e: Any) -> None:     # noqa: N802
        e.accept()                                  # clic droit = défilement, pas de menu

    def wheelEvent(self, e: Any) -> None:           # noqa: N802
        self.ed.pan(-0.15 if e.angleDelta().y() > 0 else 0.15)


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
        self._native = False
        self._scrubbing = False
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
        self.body.addLayout(head)

        self.canvas = GridCanvas(self)
        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.canvas.setToolTip(t("grid.hint"))
        self.body.addWidget(self.canvas, 1)
        self.scroll = QScrollBar(Qt.Horizontal)
        self.scroll.setRange(0, SCROLL_STEPS)
        self.scroll.valueChanged.connect(self._scrolled)
        self.body.addWidget(self.scroll)

        tools = hbox()
        self.play_btn = icon_button("play", self._play, t("grid.play_tip"), color=theme.ON_ACCENT)
        self.play_btn.setProperty("kind", "primary")
        tools.addWidget(self.play_btn)
        self.time_lbl = label("0:00.000", "dim")
        self.time_lbl.setMinimumWidth(theme.px(64))
        tools.addWidget(self.time_lbl)
        tools.addSpacing(theme.px(8))
        tools.addWidget(label(t("grid.shift"), "dim"))
        for ms in (-100, -10, -1, 1, 10, 100):
            b = button(f"{ms:+d}".replace("-", "−"), lambda m=ms: self._shift(m), tooltip=t("grid.shift_tip", ms=ms))
            b.setMinimumWidth(theme.px(40))
            tools.addWidget(b)
        tools.addStretch(1)
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
        self.duration_ms = max(g.duration_ms, g.beats[-1][2] + 1000, int(len(self.detail) / COLS_PER_S * 1000))
        self._native = g.native
        self.selected = next((i for i, b in enumerate(self.beats) if b[0] == 1), 0)
        self.cursor_ms = self.beats[self.selected][2]
        self.start_ms = max(0.0, self.cursor_ms - 1000)
        self._refresh_info()
        self.draw()
        self.ctrl.load_grid_wave(self.track, self._wave_loaded)

    def _wave_loaded(self, wave: Any) -> None:
        if not self.winfo_exists():
            return
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
        self.start_ms = max(0.0, min(self.start_ms, max(0.0, self.duration_ms - span)))
        total = max(1.0, self.duration_ms - span)
        self.scroll.blockSignals(True)
        self.scroll.setValue(int(SCROLL_STEPS * self.start_ms / total))
        self.scroll.blockSignals(False)

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
            p.drawLine(QPointF(x, 14), QPointF(x, h))
            if down:
                p.drawText(QPointF(x + 4, 12), str(bar_no))
            if i == self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.WARN))
                p.drawPolygon(QPolygonF([QPointF(x - 6, h), QPointF(x + 6, h), QPointF(x, h - 10)]))
                p.setBrush(Qt.NoBrush)
        xc = self._x(self.cursor_ms)
        if 0 <= xc <= w:
            p.setPen(QPen(QColor(theme.TEXT), 1, Qt.DashLine))
            p.drawLine(QPointF(xc, 0), QPointF(xc, h))
        p.setPen(QColor(theme.FAINT))
        p.drawText(self.canvas.rect().adjusted(0, 2, -6, 0), Qt.AlignRight | Qt.AlignTop,
                   format_duration(int(self.start_ms / 1000)))

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
        changed = self.beats != self.original
        self.save_btn.setEnabled(changed)
        self.state_lbl.setText(t("grid.modified", ms=f"{delta:+d}") if changed else "")

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
        self.selected = min(self.selected, len(self.beats) - 1)
        self._refresh_info()
        self.draw()

    # --------------------------------------------------------------- navigation
    def _view_changed(self, text: str) -> None:
        center = self.start_ms + self.view_s * 500
        self.view_s = int(text.split()[0])
        self.start_ms = center - self.view_s * 500
        self.draw()

    def _scrolled(self, value: int) -> None:
        self.start_ms = value / SCROLL_STEPS * max(0.0, self.duration_ms - self.view_s * 1000.0)
        self.draw()

    def pan(self, fraction: float) -> None:
        self.start_ms += fraction * self.view_s * 1000
        self.draw()

    def press(self, x: float, dragging: bool = False) -> None:
        """Le curseur d'écoute suit la souris (clic ou glisser) ; en lecture, la lecture y saute au
        relâchement (et pendant le glisser, au plus toutes les ~60 ms)."""
        w = max(1, self.canvas.width())
        x = min(max(0.0, x), float(w))
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
            self.ctrl.player.seek(self.cursor_ms / 1000.0)

    def _show_time(self) -> None:
        s_ = self.cursor_ms / 1000.0
        self.time_lbl.setText(f"{int(s_ // 60)}:{s_ % 60:06.3f}")

    # ------------------------------------------------------------------- écoute
    def _is_playing_this(self) -> bool:
        item = self.ctrl.current_item
        return item is not None and item.kind == "library" and item.item.content_id == self.track.content_id

    def _play(self) -> None:
        player = self.ctrl.player
        if self._is_playing_this() and player.state in (PLAYING, PAUSED):
            player.toggle_pause()
            return
        self.ctrl.play_queue([self.track], 0)
        start = self.cursor_ms / 1000.0

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                player.seek(start)
            elif tries < 40 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek_when_ready(tries + 1))

        QTimer.singleShot(100, seek_when_ready)

    def _tick(self) -> None:
        player = self.ctrl.player
        playing = self._is_playing_this() and player.state == PLAYING
        self.play_btn.setIcon(qicon("pause" if playing else "play", 16, theme.ON_ACCENT))
        if playing and not self._scrubbing:
            self.cursor_ms = player.position() * 1000.0
            self._show_time()
            span = self.view_s * 1000.0
            if not (self.start_ms <= self.cursor_ms <= self.start_ms + span * 0.85):
                self.start_ms = self.cursor_ms - span * 0.15
            self.draw()

    # -------------------------------------------------------------- enregistrer
    def _save(self) -> None:
        def go() -> None:
            self.save_btn.setEnabled(False)
            self.save_btn.setText(t("grid.saving"))

            def done(_r: Any) -> None:
                if self.winfo_exists():
                    self.close()

            def failed(_e: BaseException) -> None:
                if self.winfo_exists():
                    self.save_btn.setEnabled(True)
                    self.save_btn.setText(t("action.save"))

            self.ctrl.save_grid(self.track.content_id, self.beats, ok=done, err=failed)

        if self._native:
            ConfirmDialog(self, t("grid.native_title"), t("grid.native_msg"), go, confirm_text=t("action.save"),
                          detail=t("grid.native_detail"))
        else:
            go()

    def close(self) -> bool:                 # noqa: D401
        """Quitte la page (sans enregistrer) ; la lecture du son continue."""
        if self._closed:
            return True
        self._closed = True
        self._timer.stop()
        callback, self._on_close = self._on_close, None
        self.hide()
        self.deleteLater()
        if callback:
            callback()
        return True
