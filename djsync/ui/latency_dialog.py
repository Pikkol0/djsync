"""Réglage du décalage audio avec un test (1.3.0-rc.4, C39).

Un casque Bluetooth ou certaines cartes son jouent le son avec du retard (de 100 ms à près d'une
seconde) : le curseur de la page Grille et cues passe alors sur un temps avant qu'on l'entende. Ce test
joue un clic à 120 BPM pendant que des repères défilent vers une ligne rouge ; on règle le décalage
jusqu'à ce que le clic tombe pile quand un repère passe la ligne. Le réglage s'applique en direct.
"""
from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider, QWidget

from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label

BPM = 120
BEAT = 60.0 / BPM
SECONDS = 120
RATE = 44100
CURSOR = "#FF2A3D"            # même rouge que le curseur de lecture


def click_track(folder: Optional[Path] = None) -> Path:
    """WAV de clics à 120 BPM (1er temps de chaque mesure plus aigu), créé une fois."""
    import numpy as np

    folder = Path(folder or tempfile.gettempdir())
    path = folder / "djsync-latency-test.wav"
    if path.is_file() and path.stat().st_size > RATE * 2 * SECONDS:
        return path
    n = RATE * SECONDS
    out = np.zeros(n, dtype=np.float32)
    tk = np.arange(int(RATE * 0.025)) / RATE
    env = np.exp(-tk * 180.0)
    for i in range(int(SECONDS / BEAT)):
        start = int(i * BEAT * RATE)
        freq = 1760.0 if i % 4 == 0 else 1100.0
        seg = (0.7 * np.sin(2 * np.pi * freq * tk) * env).astype(np.float32)
        out[start:start + len(seg)] += seg[: max(0, n - start)]
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    stereo = np.repeat(pcm[:, None], 2, axis=1).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(stereo)
    return path


class _Lane(QWidget):
    """Repères qui défilent de droite à gauche ; un repère touche la ligne rouge au moment où le son
    correspondant DOIT être entendu (position « entendue » du lecteur, décalage compris)."""

    def __init__(self, position: Callable[[], float]) -> None:
        super().__init__()
        self._position = position
        self.setMinimumHeight(theme.px(90))

    def paintEvent(self, _e: Any) -> None:            # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.ELEV))
        pos = self._position()
        span = 3.0                                      # secondes visibles
        x0 = w / 2
        first = int((pos - span / 2) / BEAT) - 1
        for i in range(max(0, first), first + int(span / BEAT) + 3):
            x = x0 + (i * BEAT - pos) / span * w
            strong = i % 4 == 0
            p.setPen(QPen(QColor(theme.TEXT if strong else theme.DIM), theme.px(3 if strong else 2)))
            p.drawLine(QPointF(x, h * 0.2), QPointF(x, h * 0.8))
        # éclair quand un temps vient de passer la ligne (moins de 80 ms)
        since = (pos % BEAT) if pos > 0 else 1.0
        if since < 0.08:
            c = QColor(CURSOR)
            c.setAlpha(int(140 * (1 - since / 0.08)))
            r = theme.px(14)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF(x0 - r, h / 2 - r, 2 * r, 2 * r))
        p.setPen(QPen(QColor(CURSOR), max(2, theme.px(2))))      # trait fin et net : la précision d'abord
        p.drawLine(QPointF(x0, 0), QPointF(x0, h))
        p.end()


class LatencyDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, current_ms: int, on_save: Callable[[int], None]) -> None:
        super().__init__(parent, t("latency.title"), 560)
        self.ctrl = controller
        self._on_save = on_save
        self._initial = int(current_ms)
        self._saved = False
        player = controller.player
        self.heading(t("latency.title"), t("latency.how"))
        self.lane = _Lane(lambda: player.position() if self._mine() else 0.0)
        self.body.addWidget(self.lane)
        row = hbox()
        row.addWidget(label(t("latency.offset"), ""))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-20, 200)                  # par pas de 10 ms : -200 à 2000 ms
        self.slider.setValue(int(round(current_ms / 10)))
        self.slider.valueChanged.connect(self._changed)
        row.addWidget(self.slider, 1)
        self.value = label("", "accent")
        self.value.setMinimumWidth(theme.px(70))
        row.addWidget(self.value)
        self.body.addLayout(row)
        row = hbox()
        for step in (-50, -10, 10, 50):
            row.addWidget(button(f"{step:+d} ms", lambda s=step: self.slider.setValue(self.slider.value() + s // 10),
                                 kind="flat"))
        row.addStretch(1)
        row.addWidget(button(t("latency.reset"), lambda: self.slider.setValue(0), kind="flat"))
        self.body.addLayout(row)
        self.body.addWidget(label(t("latency.note"), "faint", wrap=True))
        self.footer(t("action.save"), self._save, stretch=False)
        self._changed(self.slider.value())
        self._path = click_track()
        from ..audio.player import NowPlaying

        player.play(self._path, NowPlaying(t("latency.title"), "DJSync", str(self._path)))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.lane.update)
        self._timer.start(16)
        self.show_dialog()

    def _mine(self) -> bool:
        meta = self.ctrl.player.meta
        return meta is not None and Path(meta.path) == self._path

    def _changed(self, v: int) -> None:
        ms = v * 10
        self.value.setText(f"{ms:+d} ms")
        self.ctrl.player.latency_offset_ms = ms

    def _save(self) -> None:
        self._saved = True
        self._on_save(self.slider.value() * 10)
        self.close()

    def closeEvent(self, e: Any) -> None:             # noqa: N802
        self._timer.stop()
        if self._mine():
            self.ctrl.player.stop()
        if not self._saved:
            self.ctrl.player.latency_offset_ms = self._initial
        super().closeEvent(e)
