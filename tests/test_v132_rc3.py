"""1.3.2-rc.3 : tests de la rc.2 (auteur, 04/11) et signalements de testeurs."""
from __future__ import annotations

from .test_v122 import demo, usb  # noqa: F401
from .qt_util import pump


def _tracks(demo, n=3):  # noqa: F811
    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > n - 1)
    return [r.data for r in lib.table.all_rows() if r.data is not None][:n]


# ------------------------------------------------------------------ B49 : introuvables pas « en échec »
def test_find_missing_names_the_absent_drive(tmp_path):
    from pathlib import Path, PureWindowsPath

    from djsync.models import LibraryTrack
    from djsync.ui.ctrl.diagnostic import find_missing, missing_reason
    from djsync.ui.ctrl.library_ops import missing_summary

    here = tmp_path / "a.m4a"
    here.write_bytes(b"x")
    gone = tmp_path / "b.m4a"
    other = Path("/Volumes/NO_SUCH_DRIVE_DJSYNC/Contents/c.m4a")
    paths = {1: here, 2: gone, 3: other}

    class Lib:
        def absolute_path(self, x):
            return paths[x.content_id]

    tracks = [LibraryTrack(content_id=i, title=str(i), artist="", album=None, duration_seconds=1, bpm=0,
                           file_type="m4a", source_url=None, date_added="", is_analysed=False, path=str(p))
              for i, p in paths.items()]
    found = find_missing(Lib(), tracks)
    assert found == {2: "", 3: "NO_SUCH_DRIVE_DJSYNC"}
    assert missing_reason(Lib(), tracks[0]) is None and missing_reason(Lib(), tracks[1]) == ""
    from djsync.i18n import set_language

    set_language("fr")
    try:
        text = missing_summary({2: "", 3: "E:", 4: "E:"})
        assert text.startswith("3 fichiers introuvables") and "2 sur E: (pas branché)" in text
    finally:
        set_language("en")
    assert PureWindowsPath("E:/x").drive == "E:"


def test_analyse_all_leaves_out_missing_files(demo):  # noqa: F811
    """« Tout analyser » / bouton Analyser : un fichier introuvable est mis à part, pas compté en échec."""
    tracks = _tracks(demo)
    ctrl = demo.ctrl
    gone = ctrl.library.absolute_path(tracks[0])
    gone.unlink()
    results = []
    ctrl.analyze([tracks[0].content_id], force=True, on_done=lambda r: results.append(r))
    assert pump(demo, 10, lambda: results)
    ok_n, skipped, failed = results[0]
    assert failed == 0 and ok_n == 0
    assert ctrl.analysis_results.get(tracks[0].content_id) == "missing"
    assert tracks[0].content_id in ctrl.missing_files
    down = demo.views["downloads"]
    text, tags = down._state(tracks[0])
    assert "dup" in tags and ("introuvable" in text or "not found" in text)
    assert not demo.errors


# ------------------------------------------------------------------ C124 : pastille et entrée « Introuvables »
def test_library_marks_missing_files(demo):  # noqa: F811
    from djsync.ui.views.library_view import MISS

    tracks = _tracks(demo)
    lib = demo.views["library"]
    ctrl = demo.ctrl
    ctrl.library.absolute_path(tracks[1]).unlink()
    ctrl.__dict__.pop("_missing_checked", None)
    ctrl.check_missing_files(lib.all_tracks)
    assert pump(demo, 6, lambda: tracks[1].content_id in ctrl.missing_files)
    pump(demo, 0.3)
    row = lib.table.row(str(tracks[1].content_id))
    assert row is not None and "missing" in row.tags and row.values.get("_tip")
    assert lib._items[MISS].text(1) == "1"
    assert tracks[1].content_id not in [x.content_id for x in lib._unanalysed()]
    lib._goto(MISS)
    assert [r.data.content_id for r in lib.table.all_rows()] == [tracks[1].content_id]
    assert lib.miss_btn.isVisibleTo(lib)
    assert not demo.errors
