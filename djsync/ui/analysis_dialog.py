"""Analyser une sélection : BPM, grille de temps, tonalité et formes d'onde.

Cette fenêtre ne fait que LANCER l'analyse (avec l'option « analyser à nouveau ») ; l'analyse tourne
en arrière-plan dans la file commune du contrôleur (progression dans la barre latérale et dans
Bibliothèque ▸ « Non analysés »). Les sons analysés par Rekordbox ne sont jamais réanalysés.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtWidgets import QCheckBox

from ..i18n import plural, t
from ..models import LibraryTrack
from .dialogs import BaseDialog
from .widgets import label


class AnalysisDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, tracks: Optional[List[LibraryTrack]]) -> None:
        super().__init__(parent, t("analysis.title"), 460)
        self.ctrl = controller
        self._tracks: List[LibraryTrack] = list(tracks or [])
        self._missing_mode = tracks is None
        self.heading(t("analysis.title"))
        self.what = label(t("analysis.counting"), wrap=True)
        self.body.addWidget(self.what)
        self.force = QCheckBox(t("analysis.force"))
        self.force.toggled.connect(lambda _c: self._describe())
        self.force.setVisible(not self._missing_mode)
        self.body.addWidget(self.force)
        self.start_btn = self.footer(t("analysis.start"), self._start, cancel_text=t("action.close"))
        if self._missing_mode:
            self.start_btn.setEnabled(False)
            controller.unanalysed(self._loaded)
        else:
            self._describe()
        self.show_dialog()

    def _loaded(self, tracks: List[LibraryTrack]) -> None:
        if not self.winfo_exists():
            return
        self._tracks = tracks
        self._describe()

    def _todo(self) -> List[LibraryTrack]:
        if self.force.isChecked():
            return self._tracks
        return [x for x in self._tracks if not x.is_analysed]

    def _describe(self) -> None:
        todo = self._todo()
        if not self._tracks:
            self.what.setText(t("analysis.nothing_missing") if self._missing_mode else t("analysis.nothing"))
            self.start_btn.setEnabled(False)
            return
        text = plural("analysis.todo_one", "analysis.todo_many", len(todo))
        skipped = len(self._tracks) - len(todo)
        if skipped:
            text += "  ·  " + plural("analysis.skip_one", "analysis.skip_many", skipped)
        self.what.setText(text)
        self.start_btn.setEnabled(bool(todo))

    def _start(self) -> None:
        todo = self._todo()
        if todo:
            self.ctrl.analyze([x.content_id for x in todo], force=self.force.isChecked())
        self.close()
