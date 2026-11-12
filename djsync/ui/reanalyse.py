"""1.4.1 (C131, D20) : « Analyser à nouveau » quand la sélection contient des sons analysés par Rekordbox.

La première fois, une fenêtre demande ce qui est refait sur ces sons (grille et BPM, tonalité, formes
d'onde) ; le choix est mémorisé (modifiable dans Paramètres ▸ Analyse). Ensuite : confirmation courte pour
un lot, rien pour un seul son. Les cues ne sont jamais touchés, l'analyse d'origine est gardée à part.
Tant que le choix n'a pas été fait, le moteur laisse ces sons tels quels.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from PySide6.QtWidgets import QCheckBox

from ..i18n import plural, t
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import label

PARTS = ("grid", "key", "waves")


def parts_text(parts: Sequence[str]) -> str:
    return ", ".join(t(f"reanalyse.part_{p}") for p in PARTS if p in parts)


class ReanalyseChoiceDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, count: int, on_ok: Callable[[], None]) -> None:
        super().__init__(parent, t("reanalyse.title"), 480)
        self.ctrl, self._on_ok = controller, on_ok
        self.heading(t("reanalyse.title"), plural("reanalyse.count_one", "reanalyse.count_many", count))
        current = controller.settings.reanalyze_rekordbox
        self.boxes = {}
        for part in PARTS:
            box = QCheckBox(t(f"reanalyse.part_{part}"))
            box.setChecked(part in current)
            box.setToolTip(t(f"reanalyse.hint_{part}"))
            self.body.addWidget(box)
            self.body.addWidget(label(t(f"reanalyse.hint_{part}"), "faint", wrap=True))
            self.boxes[part] = box
        self.body.addWidget(label(t("reanalyse.kept"), "dim", wrap=True))
        self.body.addWidget(label(t("reanalyse.grid_warning"), "dim", wrap=True))
        self.body.addWidget(label(t("reanalyse.remembered"), "faint", wrap=True))
        self.footer(t("analysis.start"), self._ok)
        self.show_dialog()

    def parts(self) -> list:
        return [p for p in PARTS if self.boxes[p].isChecked()]

    def _ok(self) -> None:
        self.ctrl.set_native_parts(self.parts())
        self.close()
        self._on_ok()


def analyse_again(parent: Any, ctrl: Any, content_ids: Sequence[int],
                  start: Optional[Callable[[], None]] = None) -> None:
    """Lance la réanalyse de `content_ids` (ou `start()`), après la question ou la confirmation due aux
    sons analysés par Rekordbox."""
    ids = list(content_ids)
    go = start or (lambda: ctrl.analyze(ids, force=True))

    def got(native: set) -> None:
        n = len(native)
        s = ctrl.settings
        if not n:
            go()
        elif not s.reanalyze_rekordbox_asked:
            ReanalyseChoiceDialog(parent, ctrl, n, go)
        elif len(ids) > 1 and s.reanalyze_rekordbox:
            ConfirmDialog(parent, t("reanalyse.confirm_title"),
                          plural("reanalyse.confirm_one", "reanalyse.confirm_many", n,
                                 parts=parts_text(s.reanalyze_rekordbox)),
                          go, confirm_text=t("analysis.start"), detail=t("reanalyse.kept"))
        else:
            go()

    ctrl.native_ids(ids, got)
