"""Barre de lecture fixée en bas : pochette, titre/artiste, pastille Camelot + BPM, Précédent /
Lecture-Pause / Suivant, progression (mini forme d'onde ANLZ cliquable si le son est analysé,
sinon curseur), volume.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QSlider, QWidget

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
        p.fillRect(int(played), 0, max(1, theme.px(1)), h, QColor(theme.TEXT))
        p.end()

    def _seek(self, e: Any) -> None:
        self._on_seek(min(1.0, max(0.0, e.position().x() / max(1, self.width()))))

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        self._seek(e)

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        if e.buttons() & Qt.LeftButton:
            self._seek(e)


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
        row = hbox(box, margins=theme.px(8), spacing=theme.px(10))

        # ---- gauche : pochette + titre + tonalité/BPM
        self.cover = QLabel()
        self.cover.setFixedSize(theme.px(COVER_PX), theme.px(COVER_PX))
        self.cover.setScaledContents(True)
        row.addWidget(self.cover)
        text = vbox(spacing=theme.px(1))
        self.title = label(t("player.nothing"))
        self.title.setStyleSheet("font-weight:600;")
        self.artist = label(t("player.hint"), "dim")
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
        left.setMinimumWidth(theme.px(160))
        row.addWidget(left, 3)

        # ---- centre : boutons + progression
        mid = vbox(spacing=theme.px(2))
        buttons = hbox(spacing=theme.px(2))
        buttons.addStretch(1)
        self.prev_btn = icon_button("prev", self.ctrl.play_previous, t("player.previous"))
        self.play_btn = icon_button("play", self.ctrl.toggle_play, t("player.play_pause"), size=18,
                                    color=theme.ON_ACCENT)
        self.play_btn.setProperty("kind", "primary")
        self.next_btn = icon_button("next", self.ctrl.play_next, t("player.next"))
        self.stop_btn = icon_button("stop", self.player.stop, t("player.stop"))
        for b in (self.prev_btn, self.play_btn, self.next_btn, self.stop_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        mid.addLayout(buttons)
        prog = hbox(spacing=theme.px(6))
        self.elapsed = label("0:00", "dim")
        self.total = label("0:00", "dim")
        for lbl in (self.elapsed, self.total):
            lbl.setMinimumWidth(theme.px(34))
            lbl.setAlignment(Qt.AlignCenter)
        self.seek = QSlider(Qt.Horizontal)
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
        row.addLayout(mid, 4)

        # ---- droite : outils du son en cours + volume
        self.grid_btn = icon_button("grid", self._edit_grid, t("player.edit_grid"))
        self.more_btn = icon_button("menu", self._track_menu, t("player.track_options"))
        row.addWidget(self.grid_btn)
        row.addWidget(self.more_btn)
        vol = QLabel()
        vol.setPixmap(qicon("volume", 16, theme.DIM).pixmap(QSize(theme.px(16), theme.px(16))))
        row.addWidget(vol)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(theme.px(90))
        self.volume.setValue(int(self.player.volume * 100))
        self.volume.valueChanged.connect(lambda v: self.player.set_volume(v / 100))
        row.addWidget(self.volume)

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
            from .grid_editor import GridEditor

            GridEditor(self, self.ctrl, track)

        self._with_track(go)

    def _track_menu(self) -> None:
        def show(track: Any) -> None:
            entries: list = []
            if track.is_analysed:
                entries.append((t("lib.edit_grid"), self._edit_grid))
            entries.append((t("action.edit_metadata"), lambda: self._edit_metadata(track)))
            entries.append((t("player.analyse_again") if track.is_analysed else t("action.analyse"),
                            lambda: self.ctrl.analyze([track.content_id], force=track.is_analysed)))
            if track.camelot:
                entries += [None, (t("lib.show_compatible", code=track.camelot), lambda: self._compatible(track))]
            entries += [None, (t("player.show_in_library"), lambda: self._show_in_library(track))]
            b = self.more_btn
            popup_menu(b, entries, b.mapToGlobal(b.rect().topLeft()))

        self._with_track(show)

    def _edit_metadata(self, track: Any) -> None:
        from .dialogs import MetadataDialog

        MetadataDialog(self, track.title, track.artist,
                       lambda title, artist: self.ctrl.update_metadata(track.content_id, title, artist))

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

    def _refresh_state(self, state: str) -> None:
        playing = state == PLAYING
        self.play_btn.setIcon(qicon("pause" if playing else "play", 18, theme.ON_ACCENT))
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
            return

        def show(data: list) -> None:
            if token != self._wave_token or not self.winfo_exists():
                return
            self.wave.set_data(data)
            self._use_wave(bool(data))

        self.ctrl.load_overview(track, show)

    def _use_wave(self, on: bool) -> None:
        self.wave.setVisible(on)
        self.seek.setVisible(not on)

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
        self.play_btn.setIcon(qicon("pause" if self.player.state == PLAYING else "play", 18, theme.ON_ACCENT))
        self.wave.update()

    # ---------------------------------------------------------------- timer
    def _tick(self) -> None:
        self.player.poll()
        if self.player.state in (PLAYING, PAUSED) and self.player.duration > 0 and not self._dragging:
            pos = min(self.player.position(), self.player.duration)
            ratio = pos / self.player.duration
            self.seek.setValue(int(ratio * 1000))
            self.wave.set_ratio(ratio)
            self.elapsed.setText(format_duration(int(pos)))
