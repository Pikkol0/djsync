"""1.3.0 : page « Grille et cues » (C22) — pads, boucles, mémoires, enregistrement sur la clé."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v024 import demo_grid  # noqa: E402,F401


def test_pads_loops_memories_and_save(demo_grid):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    app = demo_grid
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert isinstance(ed, GridEditor) and pump(app, 4, lambda: bool(ed.beats))
    panel = ed.cue_panel
    assert ed.cues == [] or all(not c.slot for c in ed.cues)                # pas de hot cue au départ
    start = list(ed.cues)

    # pad A vide : posé au temps le plus proche du curseur
    beat = ed.beats[6][2]
    ed.cursor_ms = beat + 40
    panel.pad_clicked(1)
    a = panel.cue(1)
    assert a is not None and a.ms == beat and ed.save_btn.isEnabled()
    # boucle de 4 temps, nom, couleur
    panel.set_loop(1, 4)
    assert a.is_loop and a.loop_ms == ed.beats[10][2] and a.loop_beats == 4
    panel._set_colour(a, 56)
    a.name = "Drop"
    # glisser l'étiquette de A d'un temps vers la droite
    assert ed.grab_cue(ed._x(a.ms) + 4, 8)
    ed.drag_cue(ed._x(ed.beats[7][2]) + 3)
    ed.drop_cue()
    assert a.ms == ed.beats[7][2] and a.loop_ms == ed.beats[11][2]
    # une mémoire, des cues proposés sur les pads libres seulement
    ed.cursor_ms = ed.beats[2][2]
    panel.add_memory()
    panel.suggest()
    assert panel.cue(1).ms == ed.beats[7][2]                              # A n'a pas bougé
    assert panel.cue(2) is not None
    ed.grab()                                                             # dessin des cues et de la boucle
    # pad posé : écouter (la boucle tourne)
    panel.pad_clicked(1)
    assert ed.active_loop == (a.ms, a.loop_ms)
    ed.press(10)                                                          # clic sur la forme d'onde : fin de boucle
    assert ed.active_loop is None
    app.ctrl.player.stop()

    # annuler puis refaire, enregistrer
    ed._reset()
    assert [c.slot for c in ed.cues] == [c.slot for c in start] and not ed.save_btn.isEnabled()
    ed.cursor_ms = ed.beats[4][2]
    panel.pad_clicked(3)
    panel.set_loop(3, 2)
    ed._save()
    assert pump(app, 6, lambda: app.grid_editor is None)
    back = app.ctrl.library.track_cues(target.content_id)
    c = next(c for c in back if c.slot == 3)
    assert c.ms == ed.beats[4][2] and c.is_loop and c.loop_beats == 2
    assert not app.errors


def test_leaving_with_unsaved_cues_asks_first(demo_grid):  # noqa: F811
    from djsync.ui.dialogs import ConfirmDialog

    app = demo_grid
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert pump(app, 4, lambda: bool(ed.beats))
    assert ed.close() and pump(app, 2, lambda: app.grid_editor is None)    # rien de modifié : on sort
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert pump(app, 4, lambda: bool(ed.beats))
    ed.cursor_ms = ed.beats[3][2]
    ed.cue_panel.pad_clicked(1)
    assert ed.is_dirty()
    assert ed.close() is False                                             # on demande
    dlg = app.findChildren(ConfirmDialog)[-1]
    assert app.grid_editor is ed
    dlg._ok()                                                              # « Quitter sans enregistrer »
    assert pump(app, 2, lambda: app.grid_editor is None)
    assert app.ctrl.library.track_cues(target.content_id) == [] or \
        all(not c.slot for c in app.ctrl.library.track_cues(target.content_id))
    assert not app.errors
