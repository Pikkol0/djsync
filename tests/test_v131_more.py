"""1.3.1 : C75 (mémoires de boucle), C55 (remerciements), C61 (conseil Rekordbox, erreur qui reste)."""
from djsync.analysis.cues import Cue, read_cues, write_cues

from .test_ui_v024 import demo_grid  # noqa: F401
from .test_v130rc3 import _open_grid


# ------------------------------------------------------------------ C75
def test_memory_loop_from_the_menu_and_the_button(demo_grid):  # noqa: F811
    ed = _open_grid(demo_grid)
    panel = ed.cue_panel
    panel.add_memory()
    m = next(c for c in panel.cues if not c.slot)
    panel.set_memory_loop(m, 4)
    assert m.is_loop and m.loop_beats == 4 and m.loop_ms > m.ms
    labels = [panel.mem_row.itemAt(i).widget().text() for i in range(panel.mem_row.count())]
    assert labels and labels[0].startswith("⟳ 4")
    panel.set_memory_loop(m, 0)
    assert not m.is_loop
    ed.cursor_ms = 4000
    panel.add_memory_loop(8)
    loops = [c for c in panel.cues if not c.slot and c.is_loop]
    assert len(loops) == 1 and loops[0].loop_beats == 8


def test_memory_loops_are_written_like_rekordbox():
    from djsync.analysis import anlz
    from djsync.analysis.waveform import compute_waveforms
    import numpy as np

    wf = compute_waveforms(np.zeros(22050 * 2, dtype=np.float32), 22050, 2.0)
    path = "/Contents/a/b.mp3"
    dat = anlz.build_dat(path, [(1, 12800, 0)], wf)
    ext = anlz.build_ext(path, wf)
    cues = [Cue(0, 1000), Cue(0, 2000, 3875, 4), Cue(1, 500)]
    d2, e2 = write_cues(dat, ext, cues)
    got = read_cues(d2, e2)
    mem = sorted((c for c in got if not c.slot), key=lambda c: c.ms)
    assert [(c.ms, c.loop_ms, c.loop_beats) for c in mem] == [(1000, None, 0), (2000, 3875, 4)]


# ------------------------------------------------------------------ C55
def test_thanks_in_one_place():
    from pathlib import Path

    from djsync.credits import THANKS, thanks_text

    assert THANKS == ["Tazyh", "Vogue", "Paf", "Kuss"]
    assert "Tazyh, Vogue, Paf and Kuss" in thanks_text("en")
    assert "Tazyh, Vogue, Paf et Kuss" in thanks_text("fr")
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    head = readme[:readme.index("---")]                       # tout en haut, avant la présentation
    assert thanks_text("en") in head and thanks_text("fr") in head


# ------------------------------------------------------------------ C61
def test_busy_file_errors_get_the_rekordbox_tip(demo_grid, monkeypatch):  # noqa: F811
    from sqlcipher3 import dbapi2

    from djsync.db import local_library as L

    ctrl = demo_grid.ctrl
    msgs = []
    monkeypatch.setattr(ctrl, "message", lambda kind, text: msgs.append((kind, text)))
    ctrl.error_reporter = None
    monkeypatch.setattr(L, "rekordbox_running", lambda: True)
    ctrl._on_error(PermissionError(13, "Permission denied", "export.pdb"))
    assert msgs[-1][0] == "error" and "close Rekordbox" in msgs[-1][1]
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    ctrl._rekordbox_was_running = False
    ctrl._on_error(dbapi2.OperationalError("database table is locked"))
    assert "Another program" in msgs[-1][1]
    ctrl._on_error(ValueError("other"))
    assert "💡" not in msgs[-1][1]


def test_error_bubble_is_wide_and_stays(demo_grid):  # noqa: F811
    app = demo_grid
    app._message("error", "x" * 400)
    assert app.toast.isVisible() and not app._status_timer.isActive() and app.toast_copy.isVisible()
    assert app.status.maximumWidth() > 600
    app._copy_toast()
    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text() == "x" * 400
    app._hide_toast()
    assert not app.toast.isVisible()
    app._message("ok", "done")
    assert app._status_timer.isActive() and not app.toast_copy.isVisible()
