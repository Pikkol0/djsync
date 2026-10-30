"""Compteurs Soulseek (1.4.0, C10.2) dans Téléchargements : vitesses reçue / envoyée sur les 5 dernières
minutes (graphe), pairs connectés, transferts en cours, file d'attente, octets échangés, partage."""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..i18n import t
from . import theme
from .widgets import button, hbox, label, panel, vbox

DOWN, UP = "#39C98A", "#FF9F43"


def human_rate(bps: float) -> str:
    for unit, k in (("unit.mbps", 1e6), ("unit.kbps_s", 1e3)):
        if bps >= k:
            return t(unit, n=f"{bps / k:.1f}")
    return t("unit.bps", n=f"{bps:.0f}")


def human_bytes(n: int) -> str:
    return t("unit.mb", n=f"{n / 1e6:.1f}") if n >= 1e5 else t("unit.kb", n=f"{n / 1e3:.0f}")


class SpeedGraph(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.down: Sequence[float] = ()
        self.up: Sequence[float] = ()
        self.setMinimumHeight(theme.px(70))

    def set_data(self, down: Sequence[float], up: Sequence[float]) -> None:
        self.down, self.up = list(down), list(up)
        self.update()

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.mix(theme.SURFACE, "#000000", 0.3)))
        top = max([1.0, *self.down, *self.up]) * 1.15
        p.setPen(QPen(QColor(theme.FAINT), 1, Qt.DotLine))
        for frac in (0.25, 0.5, 0.75):
            p.drawLine(QPointF(0, h * frac), QPointF(w, h * frac))
        for values, color in ((self.down, DOWN), (self.up, UP)):
            if len(values) < 2:
                continue
            n = 300
            pts = [QPointF(w - (len(values) - 1 - i) * w / (n - 1), h - 2 - v / top * (h - 4))
                   for i, v in enumerate(values)]
            p.setPen(QPen(QColor(color), max(1.5, theme.px(1.5))))
            p.drawPolyline(QPolygonF(pts))
        p.setPen(QColor(theme.DIM))
        p.drawText(self.rect().adjusted(6, 4, -6, -4), Qt.AlignTop | Qt.AlignRight, human_rate(top / 1.15))
        p.end()


class P2PPanel(QWidget):
    def __init__(self, controller: Any) -> None:
        super().__init__()
        self.ctrl = controller
        box = panel()
        outer = vbox(self)
        outer.addWidget(box)
        lay = vbox(box, margins=theme.px(10), spacing=theme.px(6))
        head = hbox(spacing=theme.px(8))
        head.addWidget(label(t("slsk.panel_title"), "h2"))
        self.state = label("", "dim")
        head.addWidget(self.state, 1)
        self.toggle = button(t("slsk.disconnect"), self._toggle, kind="flat")
        head.addWidget(self.toggle)
        lay.addLayout(head)
        self.graph = SpeedGraph()
        lay.addWidget(self.graph)
        self.stats = label("", "dim", wrap=True)
        lay.addWidget(self.stats)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        controller.on("slsk", self.refresh)
        self.refresh()

    def _toggle(self) -> None:
        if self.ctrl.slsk is not None:
            self.ctrl.slsk_disconnect()
        else:
            self.ctrl.slsk_connect()

    def refresh(self) -> None:
        self.setVisible(bool(self.ctrl.slsk_ready))
        m = self.ctrl.slsk_metrics()
        connected = m is not None and m.connected
        self.toggle.setText(t("slsk.disconnect") if connected else t("slsk.connect"))
        self.state.setText(t("slsk.state_on", user=self.ctrl.settings.soulseek_user) if connected else t("slsk.state_off"))
        if m is None:
            self.graph.set_data((), ())
            self.stats.setText("")
            return
        self.graph.set_data(m.down, m.up)
        down = m.down[-1] if m.down else 0.0
        up = m.up[-1] if m.up else 0.0
        share = t("slsk.sharing_on") if self.ctrl.settings.soulseek_share else t("slsk.sharing_off")
        self.stats.setText(t("slsk.stats", down=human_rate(down), up=human_rate(up), peers=m.peers,
                             dl=m.downloads, ul=m.uploads, queued=m.queued, received=human_bytes(m.bytes_in),
                             sent=human_bytes(m.bytes_out), share=share))
