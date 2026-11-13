"""1.4.1 (C173) : fichiers introuvables : « Version existante » et « Fusionner avec celle-ci »."""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from djsync.core.duplicates import existing_versions


def _x(cid, title, artist, dur=200):
    return NS(content_id=cid, title=title, artist=artist, duration_seconds=dur)


def test_c173_versions_same_name_close_name_and_duration():
    missing = _x(1, "One More Time", "Daft Punk", 320)
    present = [_x(2, "one more time", "DAFT PUNK", 321),                       # casse
               _x(3, "One More Time (Radio Edit)", "Daft Punk", 322),          # parenthèses
               _x(4, "One More Time feat. Romanthony", "Daft Punk", 319),      # feat.
               _x(5, "One More Time", "Daft Punk", 240),                       # durée différente : non
               _x(6, "One More Tim", "Daft Punk", 320),                        # autre titre : non
               _x(7, "One More Time", "Other", 320),                           # autre artiste : non
               _x(8, "One More Time", "Daft Punk", 0),                         # durée inconnue : oui
               _x(1, "One More Time", "Daft Punk", 320)]                       # elle-même : non
    assert [y.content_id for y in existing_versions(missing, present)] == [2, 3, 4, 8]
    assert existing_versions(_x(9, "", ""), present) == []


qt = pytest.importorskip("PySide6")


def _same_length(lib, a, b):
    """Clé de démonstration : durées tirées de la longueur du titre ; on aligne le clip sur le titre."""
    with lib._write() as conn:
        conn.execute("UPDATE content SET length = ? WHERE content_id = ?", (int(b.duration_seconds) + 2, a.content_id))


def test_c173_list_detail_merge_with_confirmation(tmp_path, monkeypatch):
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        lib = ctrl.library
        by_title = {x.title: x for x in lib.list_tracks()}
        clip, song, vald = by_title["One More Time (Clip Officiel)"], by_title["One More Time"], by_title["Désaccordé"]
        _same_length(lib, clip, song)
        lib.absolute_path(clip).unlink()
        lib.absolute_path(vald).unlink()
        app.open_diagnostic("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        dlg = find(app, MissingFilesDialog)
        assert pump(app, 8, lambda: len(dlg.items) == 2)
        items = {i.track.title: i for i in dlg.items}
        assert [v.content_id for v in items[clip.title].versions] == [song.content_id]
        assert not items[vald.title].versions
        row = dlg.items.index(items[clip.title])
        assert "1 existing version" in dlg.list.item(row).text()
        assert "existing version" not in dlg.list.item(dlg.items.index(items[vald.title])).text()
        dlg._select(row)
        assert pump(app, 4, lambda: "House" in dlg._version_rows[song.content_id].text())   # playlists de la version
        # refus de la confirmation : rien ne change
        dlg.merge_with(song)
        confirm = dlg.merge_dialog
        assert isinstance(confirm, ConfirmDialog) and clip.title.split(" (")[0] in confirm.findChildren(type(dlg.count))[1].text()
        confirm.close()
        pump(app, 0.3)
        assert clip.content_id in {x.content_id for x in lib.list_tracks()} and len(dlg.items) == 2
        # accepté : une seule entrée reste, avec les playlists de l'entrée introuvable
        before = set(lib.playlists_of([clip.content_id])[clip.content_id])
        dlg.merge_with(song)
        dlg.merge_dialog._ok()
        assert pump(app, 6, lambda: len(dlg.items) == 1)
        ids = {x.content_id for x in lib.list_tracks()}
        assert clip.content_id not in ids and song.content_id in ids
        assert before <= set(lib.playlists_of([song.content_id])[song.content_id])
        assert not app.errors
    finally:
        close_window(app)


def test_c173_remove_all_names_the_lines_with_a_version(tmp_path, monkeypatch):
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        lib = ctrl.library
        clip = next(x for x in lib.list_tracks() if x.title == "One More Time (Clip Officiel)")
        _same_length(lib, clip, next(x for x in lib.list_tracks() if x.title == "One More Time"))
        lib.absolute_path(clip).unlink()
        app.open_diagnostic("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        dlg = find(app, MissingFilesDialog)
        assert pump(app, 8, lambda: len(dlg.items) == 1)
        dlg._remove_all()
        confirm = find(app, ConfirmDialog)
        texts = " ".join(w.text() for w in confirm.findChildren(type(dlg.count)))
        assert "have an existing version" in texts and "One More Time" in texts
        confirm.close()
        assert clip.content_id in {x.content_id for x in lib.list_tracks()} and not app.errors
    finally:
        close_window(app)
