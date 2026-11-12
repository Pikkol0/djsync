"""1.4.1 (C171) : bandeau de progression d'une recherche (option C de la fiche).

* Recherche à plusieurs sources (page Haute qualité) : barre sans fin et « 2 / 3 sources terminées ·
  54 résultats · 12 s » ; pour Soulseek, une seconde barre suit le délai d'écoute des réponses : c'est un
  temps, affiché comme tel, pas un pourcentage de résultats.
* Opération dont le total est connu (import de playlist, correspondances) : `set_known(37, 200)` montre
  « 37 / 200 » et un vrai pourcentage.

Une recherche ne s'inscrit pas au registre des tâches (C145) : elle se regarde sur sa page."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QProgressBar, QWidget

from ..i18n import t
from . import theme
from .widgets import hbox, label, vbox

SOURCE_NAMES = {"archive": "Internet Archive", "audius": "Audius", "soulseek": "Soulseek",
                "ytmusic": "YouTube Music"}


class SearchProgress(QWidget):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        lay = vbox(self, spacing=theme.px(3))
        row = hbox(spacing=theme.px(8))
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(theme.px(140))
        self.bar.setFixedHeight(theme.px(6))
        row.addWidget(self.bar)
        self.text = label("", "dim")
        row.addWidget(self.text, 1)
        lay.addLayout(row)
        srow = hbox(spacing=theme.px(8))
        self.slsk_bar = QProgressBar()
        self.slsk_bar.setTextVisible(False)
        self.slsk_bar.setFixedWidth(theme.px(140))
        self.slsk_bar.setFixedHeight(theme.px(6))
        self.slsk_bar.setRange(0, 1000)
        srow.addWidget(self.slsk_bar)
        self.slsk_text = label("", "faint")
        srow.addWidget(self.slsk_text, 1)
        self.slsk_row = QWidget()
        self.slsk_row.setLayout(srow)
        lay.addWidget(self.slsk_row)
        self.slsk_row.hide()
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self.sources: List[str] = []
        self.finished: Dict[str, bool] = {}
        self.failed: List[str] = []
        self.results = 0
        self.started = 0.0
        self.slsk_seconds = 0.0
        self.known: Optional[tuple] = None
        self.hide()

    # ------------------------------------------------------------------ recherche à plusieurs sources
    def start(self, sources: List[str], slsk_seconds: float = 0.0) -> None:
        self.sources = list(sources)
        self.finished = {s: False for s in self.sources}
        self.failed = []
        self.results = 0
        self.known = None
        self.started = time.monotonic()
        self.slsk_seconds = slsk_seconds if "soulseek" in self.sources else 0.0
        self.bar.setRange(0, 0)                               # durée inconnue : barre sans fin
        self.slsk_row.setVisible(bool(self.slsk_seconds))
        self.show()
        self._timer.start()
        self._tick()

    def source_done(self, name: str, failed: bool = False) -> None:
        if name in self.finished:
            self.finished[name] = True
            if failed and name not in self.failed:
                self.failed.append(name)
        self._tick()
        if self.sources and all(self.finished.values()):
            self.finish()

    def set_results(self, n: int) -> None:
        self.results = n
        self._tick()

    @property
    def done_count(self) -> int:
        return sum(1 for v in self.finished.values() if v)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def finish(self) -> None:
        self._timer.stop()
        self.hide()

    def summary(self) -> str:
        """« 2 / 3 sources terminées · 54 résultats · 12 s » (+ « Audius : pas de réponse »)."""
        secs = int(time.monotonic() - self.started) if self.started else 0
        parts = [t("search.sources_done", done=self.done_count, n=len(self.sources)),
                 t("search.results_count", n=self.results), t("search.elapsed", s=secs)]
        if self.failed:
            parts.append(t("search.source_failed", names=", ".join(SOURCE_NAMES.get(x, x) for x in self.failed)))
        return "  ·  ".join(parts)

    def _tick(self) -> None:
        if self.known is not None:
            done, total = self.known
            self.text.setText(f"{done} / {total}")
            return
        self.text.setText(self.summary())
        if self.slsk_seconds:
            waited = time.monotonic() - self.started
            done = self.finished.get("soulseek", False)
            left = max(0.0, self.slsk_seconds - waited)
            self.slsk_bar.setValue(1000 if done else int(1000 * min(1.0, waited / self.slsk_seconds)))
            self.slsk_text.setText(t("search.slsk_done") if done or not left
                                   else t("search.slsk_wait", s=int(left + 0.99)))

    # ------------------------------------------------------------------ total connu
    def set_known(self, done: int, total: int) -> None:
        """Opération à total connu : « 37 / 200 » et un vrai pourcentage (pas de minuterie)."""
        self._timer.stop()
        self.known = (done, total)
        self.slsk_row.hide()
        self.bar.setRange(0, max(1, total))
        self.bar.setValue(done)
        self.text.setText(f"{done} / {total}")
        self.setVisible(done < total)
