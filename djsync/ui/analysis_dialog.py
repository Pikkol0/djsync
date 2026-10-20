"""Menu Analyse : BPM, grille de temps, tonalité et formes d'onde des sons choisis.

V0.2.0 : l'analyse n'est plus lancée automatiquement à chaque téléchargement (réglage
« Analyser à l'ajout », désactivé par défaut) ; on la lance ici, sur la sélection ou sur tous les
sons pas encore analysés. Elle tourne en arrière-plan : fermer la fenêtre ne l'arrête pas.
Les sons analysés par Rekordbox ne sont jamais réanalysés.
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
        super().__init__(parent, t("analysis.title"), 520, 380)
        self.ctrl = controller
        self._tracks: List[LibraryTrack] = list(tracks or [])
        self._missing_mode = tracks is None
        self._handle: Any = None
        self.start_btn = self.footer(t("analysis.start"), self._start, cancel_text=t("action.close"))

        theme.label(self, t("analysis.title"), 15, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=20, pady=(18, 2))
        theme.label(self, t("analysis.hint"), 11, theme.DIM, anchor="w", justify="left", wraplength=470).pack(
            fill="x", padx=20)
        self.what = theme.label(self, t("analysis.counting"), 12, theme.TEXT, anchor="w", justify="left", wraplength=470)
        self.what.pack(fill="x", padx=20, pady=(12, 4))
        self.force_var = ctk.BooleanVar(value=False)
        self.force = theme.checkbox(self, t("analysis.force"), variable=self.force_var, command=self._describe)
        if not self._missing_mode:
            self.force.pack(anchor="w", padx=20, pady=(2, 6))
        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=4, fg_color=theme.BORDER,
                                      progress_color=theme.ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=20, pady=(10, 4))
        self.current = theme.label(self, "", 11, theme.DIM, anchor="w")
        self.current.pack(fill="x", padx=20)
        self.problems = theme.label(self, "", 10, theme.WARN, anchor="w", justify="left", wraplength=470)
        self.problems.pack(fill="x", padx=20, pady=(4, 0))
        self._problem_lines: List[str] = []

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
        if not todo:
            return
        self.start_btn.configure(state="disabled", text=t("analysis.running"))
        self.force.configure(state="disabled")
        self._handle = self.ctrl.analyze([x.content_id for x in todo], force=bool(self.force_var.get()),
                                         on_progress=self._progress, on_done=self._done)
        if self._handle is None:
            self.close()
            return
        self.stop_btn = theme.button(self, t("analysis.stop"), self._stop, kind="danger", width=110)
        self.stop_btn.pack(anchor="w", padx=20, pady=(8, 0))

    def _stop(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self.stop_btn.configure(state="disabled", text=t("analysis.stopping"))

    def _progress(self, i: int, total: int, track: Optional[LibraryTrack], problem: str) -> None:
        if not self.winfo_exists():
            return
        self.bar.set(i / max(1, total))
        name = track.display_name if track is not None else "?"
        detail = ""
        if track is not None and track.is_analysed:
            detail = f"  ·  {track.bpm:.1f} BPM" + (f"  ·  {track.camelot}" if track.camelot else "")
        self.current.configure(text=f"{i}/{total}  ·  {name}{detail}")
        if problem:
            self._problem_lines.append(f"{name} : {problem}"[:140])
            self.problems.configure(text="\n".join(self._problem_lines[-4:]))

    def _done(self, result: Any) -> None:
        if not self.winfo_exists():
            return
        self.start_btn.configure(text=t("action.close"), state="normal", command=self.close)
        if getattr(self, "stop_btn", None) is not None:
            self.stop_btn.pack_forget()
        if result is not None:
            done, skipped, failed = result
            self.current.configure(text=t("msg.analysis_done", done=done, skipped=skipped, failed=failed))

    def close(self) -> None:
        if self._handle is not None and not self._handle.finished:
            self.ctrl.message("info", t("analysis.background"))
        super().close()
