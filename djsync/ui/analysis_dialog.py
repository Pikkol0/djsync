"""Analyser une sélection : BPM, grille de temps, tonalité et formes d'onde.

V0.2.4 : cette fenêtre ne fait plus que LANCER l'analyse (avec l'option « analyser à nouveau ») ;
l'analyse elle-même tourne en arrière-plan dans la file commune du contrôleur. La progression est
visible dans la barre latérale et dans Bibliothèque ▸ « À analyser » ; le reste de l'appli reste
utilisable. Les sons analysés par Rekordbox ne sont jamais réanalysés.
"""
from __future__ import annotations

from typing import Any, List, Optional

import customtkinter as ctk

from ..i18n import plural, t
from ..models import LibraryTrack
from . import theme
from .dialogs import BaseDialog


class AnalysisDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, tracks: Optional[List[LibraryTrack]]) -> None:
        super().__init__(parent, t("analysis.title"), 500, 290)
        self.ctrl = controller
        self._tracks: List[LibraryTrack] = list(tracks or [])
        self._missing_mode = tracks is None
        self.start_btn = self.footer(t("analysis.start"), self._start, cancel_text=t("action.close"))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(18, 8))
        theme.label(body, t("analysis.title"), 15, theme.TEXT, "bold", anchor="w").pack(fill="x", pady=(0, 2))
        self.hint = theme.label(body, t("analysis.hint"), 11, theme.DIM, anchor="w", justify="left", wraplength=440)
        self.hint.pack(fill="x")
        self.what = theme.label(body, t("analysis.counting"), 12, theme.TEXT, anchor="w", justify="left",
                                wraplength=440)
        self.what.pack(fill="x", pady=(12, 4))
        self.force_var = ctk.BooleanVar(value=False)
        self.force = theme.checkbox(body, t("analysis.force"), variable=self.force_var, command=self._describe)
        if not self._missing_mode:
            self.force.pack(anchor="w", pady=(2, 6))
        theme.label(body, t("analysis.background_hint"), 10, theme.FAINT, anchor="w", justify="left",
                    wraplength=440).pack(fill="x", pady=(4, 0))

        if self._missing_mode:
            self.start_btn.configure(state="disabled")
            controller.unanalysed(self._loaded)
        else:
            self._describe()

    def _loaded(self, tracks: List[LibraryTrack]) -> None:
        if not self.winfo_exists():
            return
        self._tracks = tracks
        self._describe()

    def _todo(self) -> List[LibraryTrack]:
        if self.force_var.get():
            return self._tracks
        return [x for x in self._tracks if not x.is_analysed]

    def _describe(self) -> None:
        todo = self._todo()
        if not self._tracks:
            self.what.configure(text=t("analysis.nothing_missing") if self._missing_mode else t("analysis.nothing"))
            self.start_btn.configure(state="disabled")
            return
        text = plural("analysis.todo_one", "analysis.todo_many", len(todo))
        skipped = len(self._tracks) - len(todo)
        if skipped:
            text += "  ·  " + plural("analysis.skip_one", "analysis.skip_many", skipped)
        self.what.configure(text=text)
        self.start_btn.configure(state="normal" if todo else "disabled")

    def _start(self) -> None:
        todo = self._todo()
        if todo:
            self.ctrl.analyze([x.content_id for x in todo], force=bool(self.force_var.get()))
        self.close()
