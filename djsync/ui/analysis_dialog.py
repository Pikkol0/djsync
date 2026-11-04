"""Analyser une sélection : BPM, grille de temps, tonalité et formes d'onde.

1.3.2 (C76) : page plus claire. En haut, le résumé (nombre de sons, durée estimée) et le bouton
« Analyser » juste dessous ; la liste des sons concernés (une case par son pour en retirer) ; la case
« analyser à nouveau » expliquée. Après le lancement, la page reste ouverte et suit l'analyse son par
son (en file, en cours, fait, échec), avec « Arrêter » et « Continuer en arrière-plan ». L'analyse elle-même
tourne toujours dans la file commune du contrôleur ; les sons analysés par Rekordbox ne sont jamais
réanalysés.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QListWidget, QListWidgetItem

from ..core.duplicates import split_display
from ..i18n import plural, t
from ..models import LibraryTrack
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label

SECONDS_PER_TRACK = 4          # ordre de grandeur mesuré (un son de 4 min, PC récent) : estimation affichée


class AnalysisDialog(BaseDialog):
    as_page = True                    # 1.2.3 : page de la fenêtre principale
    modal = False

    def __init__(self, parent: Any, controller: Any, tracks: Optional[List[LibraryTrack]]) -> None:
        super().__init__(parent, t("analysis.title"), 560)
        self.ctrl = controller
        self._tracks: List[LibraryTrack] = list(tracks or [])
        self._missing_mode = tracks is None
        self._removed: set = set()
        self._started: List[int] = []
        self._missing: Dict[int, str] = {}       # 1.3.2-rc.2 (C76) : fichier introuvable -> disque absent ou ""
        self._checked_files = False
        self._t0 = 0.0
        self.heading(t("analysis.title"))

        self.what = label(t("analysis.counting"), wrap=True)
        self.what.setStyleSheet("font-weight:600;")
        self.body.addWidget(self.what)
        row = hbox(spacing=theme.px(6))
        self.start_btn = button(t("analysis.start"), self._start, kind="primary", icon="wave")
        self.stop_btn = button(t("analysis.stop"), self._stop, kind="danger", icon="stop")
        self.bg_btn = button(t("analysis.background_btn"), self.close, kind="flat")
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.bg_btn)
        row.addStretch(1)
        row.addWidget(button(t("action.close"), self.close, kind="flat"))
        self.body.addLayout(row)

        self.force = QCheckBox(t("analysis.force"))
        self.force.toggled.connect(lambda _c: self._describe())
        self.force.setVisible(not self._missing_mode)
        self.body.addWidget(self.force)
        self.force_hint = label(t("analysis.force_hint"), "faint", wrap=True)
        self.force_hint.setVisible(not self._missing_mode)
        self.body.addWidget(self.force_hint)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._item_toggled)
        self.body.addWidget(self.list, 1)
        self.note = label(t("analysis.rekordbox_note"), "faint", wrap=True)
        self.body.addWidget(self.note)

        controller.on("analysis", self._progress)
        if self._missing_mode:
            self.start_btn.setEnabled(False)
            controller.unanalysed(self._loaded)
        else:
            self._describe()
        self._buttons()
        self.show_dialog()

    # ------------------------------------------------------------------ contenu
    def _loaded(self, tracks: List[LibraryTrack]) -> None:
        if not self.winfo_exists():
            return
        self._tracks = tracks
        self._describe()

    def _check_files(self) -> None:
        """1.3.2-rc.2 (C76, test ANA-1) : les sons dont le fichier est introuvable (souvent sur une clé
        débranchée, B40) sont écartés avec la raison, au lieu d'être comptés en échec après l'analyse."""
        if self._checked_files or not self._tracks:
            return
        self._checked_files = True
        lib = self.ctrl.library
        if lib is None:
            return
        tracks = list(self._tracks)

        def work() -> Dict[int, str]:
            from pathlib import Path

            from .ctrl.diagnostic import volume_label, volume_root

            out: Dict[int, str] = {}
            for x in tracks:
                try:
                    path = Path(lib.absolute_path(x))
                    if path.is_file():
                        continue
                    vol = volume_root(path)
                    out[x.content_id] = volume_label(vol) if vol is not None and not vol.exists() else ""
                except Exception:  # noqa: BLE001 - chemin illisible : on laisse l'analyse décider
                    continue
            return out

        def done(found: Dict[int, str]) -> None:
            if not self.winfo_exists():
                return
            self._missing = dict(found)
            self._describe()

        self.ctrl.dispatcher.submit(work, done, lambda _e: None, pool="tools")

    def _todo(self) -> List[LibraryTrack]:
        base = self._tracks if self.force.isChecked() else [x for x in self._tracks if not x.is_analysed]
        return [x for x in base if x.content_id not in self._removed and x.content_id not in self._missing]

    def _describe(self) -> None:
        if not self.winfo_exists():
            return
        todo = self._todo()
        if not self._tracks:
            self.what.setText(t("analysis.nothing_missing") if self._missing_mode else t("analysis.nothing"))
            self.start_btn.setEnabled(False)
            self._fill_list([])
            return
        text = plural("analysis.todo_one", "analysis.todo_many", len(todo))
        if todo:
            minutes = max(1, round(len(todo) * SECONDS_PER_TRACK / 60))
            text += "  ·  " + t("analysis.estimate", n=minutes)
        skipped = len([x for x in self._tracks if x.is_analysed]) if not self.force.isChecked() else 0
        if skipped:
            text += "  ·  " + plural("analysis.skip_one", "analysis.skip_many", skipped)
        if self._missing:
            text += "  ·  " + plural("analysis.missing_one", "analysis.missing_many", len(self._missing))
        self.what.setText(text)
        self.start_btn.setEnabled(bool(todo) and not self._started)
        self._fill_list(self._tracks)
        self._check_files()

    def _fill_list(self, tracks: List[LibraryTrack]) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        force = self.force.isChecked()
        for x in tracks:
            title, artist = split_display(x.title, x.artist)
            item = QListWidgetItem(f"{title}  —  {artist or '—'}")
            item.setData(Qt.UserRole, x.content_id)
            concerned = (force or not x.is_analysed) and x.content_id not in self._missing
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if concerned and x.content_id not in self._removed else Qt.Unchecked)
            if not concerned:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setToolTip(self._state_text(x))
            item.setText(item.text() + "   ·   " + self._state_text(x))
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _state_text(self, x: LibraryTrack) -> str:
        if x.content_id in self._missing:                       # C76 : écarté, avec la raison
            vol = self._missing[x.content_id]
            return "⚠ " + (t("analysis.state_offline", drive=vol) if vol else t("analysis.state_missing"))
        results: Dict[int, str] = getattr(self.ctrl, "analysis_results", {}) or {}
        q = self.ctrl.analysis
        if x.content_id in self._started:
            if results.get(x.content_id) == "ok":
                return "✓ " + t("analysis.state_done")
            if results.get(x.content_id) == "failed":
                return "✗ " + t("analysis.state_failed")
            if q.running and x.content_id in getattr(q, "ids", set()):
                return t("analysis.state_queued")
        return t("analysis.state_analysed") if x.is_analysed else t("analysis.state_todo")

    def _item_toggled(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self._removed.discard(cid)
        else:
            self._removed.add(cid)
        self._describe()

    # ------------------------------------------------------------------ actions
    def _start(self) -> None:
        todo = self._todo()
        if not todo:
            return
        import time

        self._started = [x.content_id for x in todo]
        self._t0 = time.monotonic()
        self.ctrl.analyze(self._started, force=self.force.isChecked())
        self.force.setEnabled(False)
        self._describe()
        self._buttons()

    def _stop(self) -> None:
        self.ctrl.stop_analysis()

    def _progress(self) -> None:
        if not self.winfo_exists() or not self._started:
            return
        q = self.ctrl.analysis
        done = sum(1 for cid in self._started if (getattr(self.ctrl, "analysis_results", {}) or {}).get(cid))
        self.what.setText(t("analysis.progress", i=done, n=len(self._started))
                          + (f"  ·  {self._eta(done)}" if q.running else "")
                          + (f"  ·  {q.current}" if q.running and q.current else ""))
        for i in range(self.list.count()):
            it = self.list.item(i)
            x = next((y for y in self._tracks if y.content_id == it.data(Qt.UserRole)), None)
            if x is not None and x.content_id in self._started:
                title, artist = split_display(x.title, x.artist)
                self.list.blockSignals(True)
                it.setText(f"{title}  —  {artist or '—'}   ·   {self._state_text(x)}")
                self.list.blockSignals(False)
        self._buttons()

    def _eta(self, done: int) -> str:
        """C76 (test ANA-1) : temps restant, d'après les sons déjà faits (estimation de départ sinon)."""
        import time

        left = max(0, len(self._started) - done)
        if not left:
            return ""
        per = (time.monotonic() - self._t0) / done if done and self._t0 else SECONDS_PER_TRACK
        minutes = left * per / 60
        return t("analysis.eta_min", n=max(1, round(minutes))) if minutes >= 1 else t("analysis.eta_less")

    def _buttons(self) -> None:
        running = bool(self._started) and self.ctrl.analysis.running
        self.start_btn.setVisible(not self._started)
        self.stop_btn.setVisible(running)
        self.bg_btn.setVisible(running)
