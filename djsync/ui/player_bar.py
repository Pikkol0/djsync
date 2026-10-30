"""Barre de lecture fixée en bas : pochette, titre/artiste, pastille Camelot + BPM, Précédent /
Lecture-Pause / Suivant, progression (mini forme d'onde ANLZ cliquable si le son est analysé,
sinon curseur), volume.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QSlider, QWidget

from ..audio.covers import placeholder
from ..audio.player import LOADING, PAUSED, PLAYING, STOPPED, NowPlaying
from ..i18n import t
from ..models import format_duration
from . import theme
from .covers import CoverLoader, CoverRef, file_cover, url_cover
from .icons import qicon, to_qpixmap
from .widgets import CamelotPill, hbox, icon_button, label, panel, popup_menu, vbox

COVER_PX = 52
WAVE_H = 28


SCROLL_H = 46
SCROLL_SECONDS = 8.0          # largeur de la forme d'onde défilante (± 4 s autour de la tête de lecture)


class ScrollingWave(QWidget):
    """1.2.3 (retour testeur) : forme d'onde détaillée qui défile sous une tête de lecture FIXE au centre,
    comme dans Rekordbox, avec les temps et les débuts de mesure. Sons analysés seulement."""

    RATE = 150                # colonnes ANLZ par seconde

    def __init__(self, position: Any) -> None:
        super().__init__()
        self._detail: List[Tuple[float, str]] = []
        self._beats: List[Tuple[int, int, int]] = []
        self._position = position            # () -> secondes (lecteur)
        self._pos = 0.0
        self.setFixedHeight(theme.px(SCROLL_H))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        from .cursor import FrameMeter, Monotonic

        self._mono = Monotonic()                 # 1.3.2 (C52) : jamais en arrière pendant la lecture
        self._meter = FrameMeter("player")
        self._cache: Any = None                  # (clé, première colonne, image) : forme d'onde en mémoire

    @property
    def has_data(self) -> bool:
        return bool(self._detail)

    def set_data(self, detail: List[Tuple[float, str]], beats: List[Tuple[int, int, int]]) -> None:
        self._detail, self._beats = detail, beats
        self._cache = None
        self._mono.reset()
        self.update()

    def set_running(self, running: bool) -> None:
        if running and self.isVisible() and self._detail:
            if not self._timer.isActive():
                self._timer.start(16)                      # 1.3.2 (C52) : ~60 images/s pendant la lecture
        else:
            self._timer.stop()
            self._meter.stop()
            self._mono.reset()
            self._advance()

    def _advance(self) -> None:
        try:
            pos = float(self._position())
        except Exception:  # noqa: BLE001
            return
        running = self._timer.isActive()
        self._pos = self._mono(pos * 1000.0) / 1000.0 if running else pos
        self.update()

    def _band_image(self, w: int, h: int) -> Any:
        """1.3.2 (C52) : forme d'onde et repères des temps dessinés UNE fois dans une image trois fois plus
        large que la vue, puis recopiée décalée à chaque image (avant : tout redessiné 30 fois par seconde,
        saccades sur Mac). Refaite à la taille, au changement de son, ou quand la vue sort de l'image."""
        from PySide6.QtGui import QPixmap

        dpr = self.devicePixelRatioF()
        span = SCROLL_SECONDS * self.RATE                    # colonnes visibles
        start = self._pos * self.RATE - span / 2
        key = (w, h, id(self._detail), id(self._beats), dpr)
        c = self._cache
        if c is not None and c[0] == key and c[1] <= start and start + span <= c[1] + 3 * span:
            return c
        first = start - span
        pm = QPixmap(int(3 * w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(theme.mix(theme.SURFACE, "#000000", 0.35)))
        q = QPainter(pm)
        per_px = span / w
        mid = h / 2
        n = len(self._detail)
        for x in range(3 * w):
            a = int(first + x * per_px)
            b = int(first + (x + 1) * per_px)
            if b <= 0 or a >= n:
                continue
            a, b = max(0, a), min(n, max(a + 1, b))
            v, color = max(self._detail[a:b], key=lambda d: d[0])
            half = max(1.0, v * (h / 2 - 2))
            q.fillRect(x, int(mid - half), 1, max(1, int(2 * half)), QColor(color))
        t0 = first / self.RATE
        for n_beat, _tempo, ms in self._beats:
            tx = (ms / 1000.0 - t0) / SCROLL_SECONDS * w
            if 0 <= tx < 3 * w:
                bar = n_beat == 1
                col = QColor("#FF4D4D" if bar else theme.mix(theme.TEXT, theme.SURFACE, 0.5))
                q.fillRect(int(tx), 0, 1, theme.px(7 if bar else 4), col)
                q.fillRect(int(tx), h - theme.px(7 if bar else 4), 1, theme.px(7 if bar else 4), col)
        q.end()
        self._cache = (key, first, pm)
        return self._cache

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        import time

        w, h = self.width(), self.height()
        if w < 8:
            return
        t0 = time.perf_counter()
        p = QPainter(self)
        p.fillRect(0, 0, w, h, QColor(theme.mix(theme.SURFACE, "#000000", 0.35)))
        if self._detail:
            _key, first, pm = self._band_image(w, h)
            start = self._pos * self.RATE - SCROLL_SECONDS * self.RATE / 2
            p.drawPixmap(QPointF((first - start) * w / (SCROLL_SECONDS * self.RATE), 0), pm)
        from .cursor import draw_cursor

        draw_cursor(p, w / 2, 0, h)                          # 1.3.2 (C52)
        p.end()
        if self._timer.isActive():
            self._meter.frame((time.perf_counter() - t0) * 1000.0)


class WaveformBar(QWidget):
    """Mini forme d'onde (aperçu ANLZ) : partie lue en couleur d'accent ; clic/glisser = position."""

    def __init__(self, on_seek: Any) -> None:
        super().__init__()
        self._data: List[Tuple[float, str]] = []
        self._ratio = 0.0
        self._on_seek = on_seek
        self.setFixedHeight(theme.px(WAVE_H))
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, data: List[Tuple[float, str]]) -> None:
        self._data = data
        self.update()

    @property
    def has_data(self) -> bool:
        return bool(self._data)

    def set_ratio(self, ratio: float) -> None:
        if abs(ratio - self._ratio) * max(1, self.width()) >= 1:
            self._ratio = ratio
            self.update()

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        w, h = self.width(), self.height()
        if w < 4 or not self._data:
            return
        p = QPainter(self)
        n = len(self._data)
        step = max(2, theme.px(3))
        cols = max(1, w // step)
        played = self._ratio * w
        mid = h / 2
        on, off = QColor(theme.ACCENT), QColor(theme.mix(theme.SURFACE, theme.DIM, 0.55))
        for c in range(cols):
            a = c * n // cols
            b = max(a + 1, (c + 1) * n // cols)
            v = max(x[0] for x in self._data[a:b])
            x = c * step
            half = max(1.0, v * (h / 2 - 1))
            p.fillRect(int(x), int(mid - half), step - 1, max(1, int(2 * half)), on if x < played else off)
        from .cursor import draw_cursor

        draw_cursor(p, played, 0, h, glow=False)             # 1.3.2 (C52)
        p.end()

    def _seek(self, e: Any) -> None:
        self._on_seek(min(1.0, max(0.0, e.position().x() / max(1, self.width()))))

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        self._seek(e)

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        if e.buttons() & Qt.LeftButton:
            self._seek(e)


class JumpSlider(QSlider):
    """1.2.0-rc.4 (B08) : un clic n'importe où sur la barre va à ce point (un QSlider standard avance
    seulement d'un cran) ; on peut ensuite glisser sans relâcher."""

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        if e.button() == Qt.LeftButton and self.maximum() > self.minimum():
            from PySide6.QtWidgets import QStyle, QStyleOptionSlider

            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
            if not handle.contains(e.position().toPoint()):
                groove = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
                span = max(1, groove.width() - handle.width())
                x = int(e.position().x()) - groove.x() - handle.width() // 2
                self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, span))
        super().mousePressEvent(e)


class PlayerBar(QWidget):
    def __init__(self, parent: Any, controller: Any, loader: CoverLoader) -> None:
        super().__init__(parent)
        self.ctrl, self.loader = controller, loader
        self.player = controller.player
        self._dragging = False
        self._cover_token = 0
        self._wave_token = 0

        outer = hbox(self)
        box = panel(role="bar")
        outer.addWidget(box)
        col = vbox(box, margins=theme.px(8), spacing=theme.px(6))
        self.scroll_wave = ScrollingWave(lambda: min(self.player.position(), self.player.duration or 1e9))
        self.scroll_wave.hide()
        col.addWidget(self.scroll_wave)
        # 1.3.2 (C51) : la vue d'ensemble 3 bandes de la page « Grille et cues » est dans la page elle-même ;
        # le lecteur garde sa forme d'onde habituelle (la forme défilante est masquée pendant la page)
        self._grid_editor: Any = None
        controller.on("grid_page", self._grid_page)
        row = hbox(spacing=theme.px(10))
        col.addLayout(row)

        # 1.3.1 (C34) : trois zones, gauche et droite de MÊME largeur (taille souhaitée ignorée), pour que
        # boutons et progression tombent au centre de la fenêtre quelle que soit sa largeur
        def side() -> Tuple[QWidget, Any]:
            w = QWidget()
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            w.setMinimumWidth(theme.px(230))
            return w, hbox(w, spacing=theme.px(10))
        left_side, left_row = side()
        right_side, right_row = side()

        # ---- gauche : pochette + titre + tonalité/BPM
        self.cover = QLabel()
        self.cover.setFixedSize(theme.px(COVER_PX), theme.px(COVER_PX))
        self.cover.setScaledContents(True)
        left_row.addWidget(self.cover)
        text = vbox(spacing=theme.px(1))
        self.title = label(t("player.nothing"))
        self.title.setStyleSheet("font-weight:600;")
        self.artist = label("", "dim")
        meta = hbox(spacing=theme.px(6))
        self.key_pill = CamelotPill()
        self.bpm = label("", "dim")
        meta.addWidget(self.key_pill)
        meta.addWidget(self.bpm)
        meta.addStretch(1)
        text.addWidget(self.title)
        text.addWidget(self.artist)
        text.addLayout(meta)
        left = QWidget()
        left.setLayout(text)
        left.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        left_row.addWidget(left, 1)
        row.addWidget(left_side, 1)

        # ---- centre : boutons + progression
        mid = vbox(spacing=theme.px(2))
        buttons = hbox(spacing=theme.px(2))
        buttons.addStretch(1)
        self.prev_btn = icon_button("prev", self.ctrl.play_previous, t("player.previous"))
        self.play_btn = icon_button("play", self.ctrl.toggle_play, t("player.play_pause"), size=18,
                                    color=theme.ON_ACCENT)
        self.play_btn.setProperty("kind", "primary")
        self.play_btn.setFixedSize(theme.px(34), theme.px(34))
        self.next_btn = icon_button("next", self.ctrl.play_next, t("player.next"))
        self.stop_btn = icon_button("stop", self.player.stop, t("player.stop"))
        pad = QWidget()                                    # C34 : contrepoids de Stop, Lecture pile au centre
        pad.setFixedSize(self.stop_btn.sizeHint())
        for b in (pad, self.prev_btn, self.play_btn, self.next_btn, self.stop_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        mid.addLayout(buttons)
        prog = hbox(spacing=theme.px(6))
        self.elapsed = label("0:00", "dim")
        self.total = label("0:00", "dim")
        for lbl in (self.elapsed, self.total):
            lbl.setMinimumWidth(theme.px(34))
            lbl.setAlignment(Qt.AlignCenter)
        self.seek = JumpSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.seek.sliderReleased.connect(self._seek_release)
        self.seek.sliderMoved.connect(self._seek_moved)
        self.wave = WaveformBar(self._wave_seek)
        self.wave.hide()
        prog.addWidget(self.elapsed)
        prog.addWidget(self.seek, 1)
        prog.addWidget(self.wave, 1)
        prog.addWidget(self.total)
        mid.addLayout(prog)
        mid_box = QWidget()
        mid_box.setLayout(mid)
        mid_box.setMaximumWidth(theme.px(860))             # progression lisible sur grand écran
        mid_box.setMinimumWidth(theme.px(320))
        row.addWidget(mid_box, 2)

        # ---- droite : outils du son en cours + volume
        self.grid_btn = icon_button("grid", self._edit_grid, t("player.edit_grid"))
        self.more_btn = icon_button("menu", self._track_menu, t("player.track_options"))
        right_row.addStretch(1)
        right_row.addWidget(self.grid_btn)
        right_row.addWidget(self.more_btn)
        vol = QLabel()
        vol.setPixmap(qicon("volume", 16, theme.DIM).pixmap(QSize(theme.px(16), theme.px(16))))
        right_row.addWidget(vol)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(theme.px(90))
        self.volume.setValue(int(self.player.volume * 100))
        self.volume.valueChanged.connect(lambda v: self.player.set_volume(v / 100))
        right_row.addWidget(self.volume)
        row.addWidget(right_side, 1)
        m = max(theme.px(230), left_side.minimumSizeHint().width(), right_side.minimumSizeHint().width())
        for w in (left_side, right_side):                  # même minimum des deux côtés : centre exact
            w.setMinimumWidth(m)

        self._set_placeholder()
        controller.on("player", self._on_player)
        controller.on("queue", self._refresh_nav)
        self._refresh_nav()
        if self.player.meta is not None:          # reconstruction de l'interface pendant une lecture
            self._show_meta(self.player.meta, self.player.duration)
            self._refresh_state(self.player.state)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return isValid(self)

    # ---------------------------------------------------------------- actions
    def _seek_moved(self, value: int) -> None:
        if self.player.duration > 0:
            self.elapsed.setText(format_duration(int(value / 1000 * self.player.duration)))

    def _seek_release(self) -> None:
        if self.player.duration > 0:
            self.player.seek(self.seek.value() / 1000 * self.player.duration)
        self._dragging = False

    def _wave_seek(self, ratio: float) -> None:
        if self.player.duration > 0 and self.player.state in (PLAYING, PAUSED):
            self.player.seek(ratio * self.player.duration)
            self.wave.set_ratio(ratio)

    def _refresh_nav(self) -> None:
        if not self.winfo_exists():
            return
        self.prev_btn.setEnabled(self.ctrl.current_item is not None)
        self.next_btn.setEnabled(bool(self.ctrl.has_next))
        on_drive = self.ctrl.current_library_id() is not None
        self.grid_btn.setEnabled(on_drive)
        self.more_btn.setEnabled(on_drive)

    # ------------------------------------------------- outils du son en cours
    def _with_track(self, action: Any) -> None:
        """Relit le son en cours dans la base (analyse, BPM, tonalité à jour) puis lance l'action."""
        cid = self.ctrl.current_library_id()
        if cid is None:
            self.ctrl.message("info", t("player.not_on_drive"))
            return
        self.ctrl.fresh_track(cid, lambda track: action(track) if self.winfo_exists() else None)

    def _edit_grid(self) -> None:
        def go(track: Any) -> None:
            if not track.is_analysed:
                self.ctrl.message("info", t("grid.not_analysed"))
                return
            self.ctrl._emit("open_grid", track)

        self._with_track(go)

    def _track_menu(self) -> None:
        def show(track: Any) -> None:
            entries: list = []
            if track.is_analysed:
                entries.append((t("lib.edit_grid"), self._edit_grid, "grid"))
            entries.append((t("action.edit_metadata"), lambda: self._edit_metadata(track), "edit"))
            entries.append((t("player.analyse_again") if track.is_analysed else t("action.analyse"),
                            lambda: self.ctrl.analyze([track.content_id], force=track.is_analysed), "wave"))
            if track.camelot:
                entries += [None, (t("lib.show_compatible", code=track.camelot), lambda: self._compatible(track), "key")]
            entries += [None, (t("player.show_in_library"), lambda: self._show_in_library(track), "library")]
            b = self.more_btn
            popup_menu(b, entries, b.mapToGlobal(b.rect().topLeft()))

        self._with_track(show)

    def _edit_metadata(self, track: Any) -> None:
        from .track_info_dialog import TrackInfoDialog

        TrackInfoDialog(self, self.ctrl, track)

    def _library_view(self) -> Any:
        self.ctrl._emit("navigate", "library")
        return getattr(self.window(), "views", {}).get("library")

    def _compatible(self, track: Any) -> None:
        view = self._library_view()
        if view is not None:
            view.set_harmonic(track)

    def _show_in_library(self, track: Any) -> None:
        view = self._library_view()
        if view is not None:
            view.reveal(track.content_id)

    # ---------------------------------------------------------------- évènements
    def _on_player(self, kind: str, payload: Any) -> None:
        if not self.winfo_exists():
            return
        if kind == "state":
            self._refresh_state(payload)
        elif kind == "loaded":
            meta, duration = payload if isinstance(payload, tuple) else (payload, self.player.duration)
            self._show_meta(meta, float(duration or 0))
        elif kind == "error":
            self.ctrl.message("error", str(payload))
        elif kind == "ended":
            self._reset_progress()

    def _reset_progress(self) -> None:
        self.seek.setValue(0)
        self.wave.set_ratio(0)
        self.elapsed.setText("0:00")

    def _spinner_icon(self) -> Any:
        """Cercle qui tourne dans le bouton lecture pendant le chargement (1.2.0-rc.4, C01)."""
        from PySide6.QtGui import QIcon, QPen, QPixmap

        size = theme.px(18)
        ratio = 2
        pix = QPixmap(size * ratio, size * ratio)
        pix.setDevicePixelRatio(ratio)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.ON_ACCENT))
        pen.setWidthF(max(1.5, size / 9))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        m = size / 6
        p.drawArc(int(m), int(m), int(size - 2 * m), int(size - 2 * m), int(-self._spin * 16), 270 * 16)
        p.end()
        return QIcon(pix)

    def _spin_tick(self) -> None:
        if self.player.state != LOADING:
            self._spin_timer.stop()
            self.play_btn.setIcon(qicon("pause" if self.player.state == PLAYING else "play", 18, theme.ON_ACCENT))
            return
        self._spin = (self._spin + 30) % 360
        self.play_btn.setIcon(self._spinner_icon())

    def _refresh_state(self, state: str) -> None:
        playing = state == PLAYING
        self.scroll_wave.set_running(playing)
        if state == STOPPED:
            self.scroll_wave.hide()
        self.play_btn.setIcon(qicon("pause" if playing else "play", 18, theme.ON_ACCENT))
        if not hasattr(self, "_spin_timer"):
            self._spin = 0
            self._spin_timer = QTimer(self)
            self._spin_timer.timeout.connect(self._spin_tick)
        if state == LOADING:
            self._spin_timer.start(70)
            self.play_btn.setIcon(self._spinner_icon())
            self.play_btn.setToolTip(t("player.loading"))
        else:
            self._spin_timer.stop()
            self.play_btn.setToolTip(t("player.play_pause"))
        if state == LOADING and self.player.meta:
            self._show_meta(self.player.meta, 0.0)
            self.artist.setText(f"{self.player.meta.artist}  ·  {t('player.loading')}")
        elif state == STOPPED:
            self._reset_progress()
            if self.player.meta:
                self.artist.setText(self.player.meta.artist)
        self._refresh_nav()

    def _show_meta(self, meta: NowPlaying, duration: float) -> None:
        self.title.setText(meta.title or t("player.untitled"))
        self.artist.setText(meta.artist or "")
        self.total.setText(format_duration(int(duration)))
        self._set_cover(self._cover_ref(meta))
        item = self.ctrl.current_item
        track = item.library_track if item is not None else None
        if track is not None and track.path and str(meta.path).replace("\\", "/").endswith(track.path.lstrip("/")):
            self._show_track_info(track)
        else:
            self._show_track_info(None)

    def _show_track_info(self, track: Any) -> None:
        self.key_pill.set(track.camelot if track is not None else None)
        if track is not None and track.bpm:
            self.bpm.setText(f"{track.bpm:.1f} BPM".replace(".0 ", " "))
        else:
            self.bpm.setText("")
        self._wave_token += 1
        token = self._wave_token
        if track is None or not track.analysis_path:
            self._use_wave(False)
            self._use_scroll(None)
            return

        def show(data: list) -> None:
            if token != self._wave_token or not self.winfo_exists():
                return
            self.wave.set_data(data)
            self._use_wave(bool(data))

        self.ctrl.load_overview(track, show)

        def show_detail(data: Any) -> None:
            if token != self._wave_token or not self.winfo_exists():
                return
            self._use_scroll(data)

        from ..core.machine import light_active

        # 1.4.0 (C65) : en mode léger, pas de forme d'onde défilante (le lecteur garde sa forme d'onde fixe)
        if getattr(self.ctrl.settings, "scrolling_wave", True) and not light_active(self.ctrl.settings):
            self.ctrl.load_detail(track, show_detail)
        else:
            self._use_scroll(None)

    def _use_wave(self, on: bool) -> None:
        self.wave.setVisible(on)
        self.seek.setVisible(not on)

    def _grid_page(self, editor: Any) -> None:
        """La page Grille et cues s'ouvre (editor) ou se ferme (None)."""
        self._grid_editor = editor
        if editor is not None:
            self.scroll_wave.hide()
        else:
            self.scroll_wave.setVisible(self.scroll_wave.has_data and self.player.state != STOPPED)

    def _use_scroll(self, data: Any) -> None:
        detail, beats = data if data else ([], [])
        self.scroll_wave.set_data(detail, beats)
        self.scroll_wave.setVisible(bool(detail) and self._grid_editor is None)
        self.scroll_wave.set_running(self.player.state == PLAYING)

    @staticmethod
    def _cover_ref(meta: NowPlaying) -> Optional[CoverRef]:
        if meta.cover_url:
            return url_cover(meta.cover_url)
        return file_cover(Path(meta.cover_path) if meta.cover_path else None, Path(meta.path), f"bar:{meta.path}")

    def _set_placeholder(self) -> None:
        self.cover.setPixmap(to_qpixmap(placeholder(theme.px(COVER_PX) * 2)))

    def _set_cover(self, ref: Optional[CoverRef]) -> None:
        """Pochette chargée/décodée en arrière-plan ; un jeton ignore les réponses périmées."""
        self._cover_token += 1
        token = self._cover_token
        self._set_placeholder()

        def show(img: Any) -> None:
            if token != self._cover_token or not self.winfo_exists():
                return
            self.cover.setPixmap(to_qpixmap(img))

        self.loader.load_pil(ref, theme.px(COVER_PX) * 2, show)

    def on_scale(self) -> None:
        self.cover.setFixedSize(theme.px(COVER_PX), theme.px(COVER_PX))
        self.wave.setFixedHeight(theme.px(WAVE_H))
        self.scroll_wave.setFixedHeight(theme.px(SCROLL_H))
        self.play_btn.setIcon(qicon("pause" if self.player.state == PLAYING else "play", 18, theme.ON_ACCENT))
        self.wave.update()

    # ---------------------------------------------------------------- timer
    def _tick(self) -> None:
        # 1.3.2 (C52) : ~30 mises à jour par seconde pendant la lecture (curseur fluide), 4 au repos
        want = 33 if self.player.state == PLAYING else 250
        if self._timer.interval() != want:
            self._timer.setInterval(want)
        self.player.poll()
        if self.player.state in (PLAYING, PAUSED) and self.player.duration > 0 and not self._dragging:
            pos = min(self.player.position(), self.player.duration)
            ratio = pos / self.player.duration
            self.seek.setValue(int(ratio * 1000))
            self.wave.set_ratio(ratio)
            self.elapsed.setText(format_duration(int(pos)))
            if self.player.state == PAUSED and self.scroll_wave.isVisible():
                self.scroll_wave._advance()
