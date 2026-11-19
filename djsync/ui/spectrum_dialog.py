"""1.4.3 (A04) : clic droit ▸ Spectre : le spectrogramme du son, comme Spek, avec les lignes 16 / 19 / 20 kHz.

C'est ce que les DJ regardent pour juger un fichier : un 128 kbps s'arrête vers 16 kHz, un 320 vers 20 kHz, un
vrai sans perte monte jusqu'à 22 kHz. Le calcul (décodage du son entier, ~1 s) se fait hors du fil de l'interface.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import t
from ..models import format_duration
from . import theme
from .dialogs import BaseDialog
from .widgets import label

MARKS_KHZ = (16, 19, 20)
# dégradé de Spek : noir, bleu nuit, violet, rouge, orange, jaune, blanc
_STOPS = ((0.0, (0, 0, 0)), (0.2, (0, 0, 110)), (0.4, (120, 0, 160)), (0.6, (225, 30, 40)),
          (0.78, (255, 150, 0)), (0.92, (255, 240, 80)), (1.0, (255, 255, 255)))


def palette() -> np.ndarray:
    """Table de 256 couleurs RGB (uint8)."""
    pos = np.array([s[0] for s in _STOPS])
    rgb = np.array([s[1] for s in _STOPS], dtype=np.float64)
    v = np.linspace(0, 1, 256)
    return np.stack([np.interp(v, pos, rgb[:, k]) for k in range(3)], axis=1).astype(np.uint8)


def to_image(db: np.ndarray, floor: float = -120.0) -> QImage:
    """Niveaux (fréquences x colonnes, grave en bas) -> image (aigu en haut)."""
    level = np.clip((db - floor) / -floor, 0, 1)
    idx = (level[::-1] * 255).astype(np.uint8)
    rgb = np.ascontiguousarray(palette()[idx])                    # (h, w, 3)
    h, w = idx.shape
    img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return img.copy()                                              # la mémoire numpy n'est pas gardée


class SpectrumCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.image: Optional[QImage] = None
        self.sr = 44100
        self.duration = 0.0
        self.text = t("spectrum.loading")
        self.setMinimumSize(theme.px(560), theme.px(300))

    def set_data(self, db: np.ndarray, sr: int, duration: float) -> None:
        self.image, self.sr, self.duration = to_image(db), sr, duration
        self.update()

    def set_text(self, text: str) -> None:
        self.image, self.text = None, text
        self.update()

    def paintEvent(self, _e: Any) -> None:        # noqa: N802
        p = QPainter(self)
        fm = QFontMetrics(p.font())
        left, bottom = fm.horizontalAdvance("22 kHz") + theme.px(10), fm.height() + theme.px(6)
        w, h = self.width() - left - theme.px(4), self.height() - bottom - theme.px(4)
        area = QRectF(left, theme.px(4), max(1, w), max(1, h))
        p.fillRect(self.rect(), QColor(theme.ELEV))
        if self.image is None:
            p.setPen(QColor(theme.DIM))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.text)
            p.end()
            return
        p.drawImage(area, self.image)
        nyq = self.sr / 2.0

        def y_of(hz: float) -> float:
            return area.bottom() - hz / nyq * area.height()

        p.setPen(QColor(theme.DIM))
        for khz in range(0, int(nyq // 1000) + 1, 2):                 # graduations tous les 2 kHz
            y = y_of(khz * 1000)
            p.drawText(QRectF(0, y - fm.height() / 2, left - theme.px(6), fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                       f"{khz} kHz" if khz % 4 == 0 else f"{khz}")
        for khz in MARKS_KHZ:                                          # repères des DJ
            if khz * 1000 >= nyq:
                continue
            y = y_of(khz * 1000)
            p.setPen(QPen(QColor(theme.ON_ACCENT if khz != 16 else theme.WARN), 1, Qt.DashLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(theme.TEXT))
            p.drawText(QPointF(area.right() - fm.horizontalAdvance(f"{khz} kHz") - theme.px(4), y - theme.px(3)),
                       f"{khz} kHz")
        p.setPen(QColor(theme.DIM))
        steps = 4
        for i in range(steps + 1):
            x = area.left() + i / steps * area.width()
            text = format_duration(int(self.duration * i / steps))
            tw = fm.horizontalAdvance(text)
            p.drawText(QPointF(min(max(area.left(), x - tw / 2), area.right() - tw), self.height() - theme.px(4)), text)
        p.end()


class SpectrumDialog(BaseDialog):
    """Fenêtre « Spectre » d'un son (clic droit dans la Bibliothèque, le lecteur, Qualité…)."""

    modal = False

    def __init__(self, parent: Any, controller: Any, track: Any) -> None:
        super().__init__(parent, t("spectrum.title", title=track.display_name), 760, 520)
        self.ctrl, self.track = controller, track
        self.heading(t("spectrum.title", title=track.display_name), t("spectrum.hint"))
        self.summary = label(self._summary(), "dim", wrap=True)
        self.body.addWidget(self.summary)
        self.canvas = SpectrumCanvas()
        self.body.addWidget(self.canvas, 1)
        self.footer(t("action.close"), self.close, show_cancel=False, stretch=False)
        self.show_dialog()
        self._compute()

    def _summary(self) -> str:
        from .views.library_view import extra_values

        try:
            v = extra_values(self.track)
        except Exception:  # noqa: BLE001
            return ""
        real = v.get("real")
        return " · ".join(x for x in (real, v.get("real__tip", "")) if x)

    def _compute(self) -> None:
        lib = getattr(self.ctrl, "library", None)
        if lib is None:
            self.canvas.set_text(t("spectrum.missing"))
            return
        path = lib.absolute_path(self.track)
        if not path.exists():
            self.canvas.set_text(t("spectrum.missing"))
            return
        ffmpeg = self.ctrl.settings.ffmpeg_location or None

        def work() -> Any:
            from ..analysis.encoder import read_and_remember
            from ..analysis.spectrum import spectrogram

            read_and_remember(path)                       # en-tête relu : la bulle de la qualité le montre aussi
            return spectrogram(path, ffmpeg)

        def ok(res: Any) -> None:
            if self.winfo_exists():
                self.canvas.set_data(*res)
                self.summary.setText(self._summary())

        def failed(exc: BaseException) -> None:
            if self.winfo_exists():
                self.canvas.set_text(t("spectrum.failed", error=str(exc)[:200]))

        self.ctrl.dispatcher.submit(work, ok, failed, pool="match")
