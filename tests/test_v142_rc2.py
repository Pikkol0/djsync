"""1.4.2-rc.2 : audits (A1-1, A1-3, A3-1, A6-3, A6-6, A6-7, A6-8), retours des testeurs et tests KO de la rc1."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from djsync.analysis.cues import Cue
from djsync.core import importer
from djsync.db import transfer as T

from .test_v142_c23 import _add, _pdb_matches, _playlist, app, key, key2, not_system_disk  # noqa: F401
from .test_v050 import local  # noqa: F401 (fixture : bibliothèque de l'ordinateur)
from .test_ui_v020 import demo  # noqa: F401 (fixture : fenêtre avec une clé de démonstration)


# ------------------------------------------------------------------ A1-1 : 64 Ko lus, pas le fichier entier
def test_same_file_reads_only_the_first_64_kb(tmp_path, monkeypatch):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    data = bytes(range(256)) * 4096                                  # 1 Mo
    a.write_bytes(data)
    b.write_bytes(data)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("whole file read"))
    assert importer._same_file(a, b)
    b.write_bytes(data[:-1] + b"x")                                  # même début, même taille : même fichier
    assert importer._same_file(a, b)
    b.write_bytes(b"y" + data[1:])
    assert not importer._same_file(a, b)
    assert not importer._same_file(a, tmp_path / "missing")


# ------------------------------------------------------------------ A3-1 + A6-3 : « Copier vers… »
def test_copy_to_never_overwrites_another_file_with_the_same_name(key, key2):  # noqa: F811
    t = _add(key, "Intro", artist="Art", seconds=2.0)
    pl = _playlist(key, "Set", [t])
    other = _add(key2, "Intro (Live)", artist="Art", seconds=3.0)
    folder = Path(key2.default_download_dir("Art", None))
    (folder / "Intro.wav").write_bytes(b"another sound, kept")       # fichier d'un autre son, même nom
    res = T.copy_playlist(key, pl.playlist_id, key2)
    assert (res.copied, res.failed) == (1, 0)
    assert (folder / "Intro.wav").read_bytes() == b"another sound, kept"
    got = key2.get_playlist_tracks(res.playlist_id)[0]
    assert key2.absolute_path(got).name == "Intro (2).wav"
    assert key2.absolute_path(key2.get_track(other.content_id)).is_file()
    _pdb_matches(key2)


def test_copy_to_keeps_the_cues_of_a_computer_track(key, local):  # noqa: F811
    t = _add(local, "Cued", artist="PC")
    local.save_track_cues(t.content_id, [Cue(ms=1000, slot=1), Cue(ms=2500, slot=2)])
    pl = _playlist(local, "With cues", [t])
    res = T.copy_playlist(local, pl.playlist_id, key)
    assert res.copied == 1 and not res.problems
    got = key.get_playlist_tracks(res.playlist_id)[0]
    hot = sorted(c.ms for c in key.track_cues(got.content_id) if c.slot)
    assert hot == [1000, 2500]


# ------------------------------------------------------------------ A1-3 : lots de 25 sons
def test_copy_to_writes_in_batches_of_25(key, key2, monkeypatch):  # noqa: F811
    tracks = [_add(key, f"S{i:02d}", seconds=1.0) for i in range(30)]
    pl = _playlist(key, "Big", tracks)
    flushes = []
    real = key2._pdb_flush
    monkeypatch.setattr(key2, "_pdb_flush", lambda *a, **k: (flushes.append(1), real(*a, **k))[1])
    progress = []
    res = T.copy_playlist(key, pl.playlist_id, key2, lambda i, n, _name: progress.append((i, n)))
    assert res.copied == 30 and not res.problems
    assert progress[0] == (1, 30) and progress[-1] == (30, 30)
    # 2 lots (25 + 5) + l'ajout final à la playlist ; avant : 2 réécritures par son
    assert len(flushes) <= 4
    assert [x.title for x in key2.get_playlist_tracks(res.playlist_id)] == [x.title for x in tracks]
    _pdb_matches(key2)


# ------------------------------------------------------------------ A6-6 : clé pleine (spec claude/spec-a6-6.md)
import errno  # noqa: E402

from djsync.db import KeyFullError, LibraryError, backups, key_space  # noqa: E402


def _fill(monkeypatch, free: int = 1000) -> None:
    """Clé « pleine » : place libre simulée, copie de sécurité en échec ENOSPC."""
    monkeypatch.setattr(key_space, "free_bytes", lambda path: free)


def _no_room(lib, monkeypatch) -> None:
    def fail() -> None:
        raise LibraryError("Backup failed, write cancelled for safety") from OSError(errno.ENOSPC, "No space left")

    monkeypatch.setattr(lib, "_backup_copy", fail)


def test_a66_threshold_is_base_plus_pdb_plus_10_mb(key):  # noqa: F811
    folder = key.db_path.parent
    expected = (folder / "exportLibrary.db").stat().st_size + (folder / "export.pdb").stat().st_size + 10 * 1024 * 1024
    assert key_space.threshold(folder) == expected


def test_a66_space_error_is_key_full_only_under_the_threshold(key, monkeypatch):  # noqa: F811
    err = LibraryError("Backup failed")
    err.__cause__ = OSError(errno.ENOSPC, "No space left on device")
    assert key.full_error(err) is None                                # place libre réelle : pas « pleine »
    _fill(monkeypatch)
    full = key.full_error(err)
    assert isinstance(full, KeyFullError) and full.free == 1000 and full.needed > 10 * 1024 * 1024
    assert key.full_error(LibraryError("database or disk is full")) is not None
    assert key.full_error(LibraryError("disk I/O error")) is not None
    assert key.full_error(LibraryError("something else")) is None


def test_a66_any_write_is_refused_with_key_full(key, monkeypatch):  # noqa: F811
    t = _add(key, "Keep me")
    _fill(monkeypatch)
    _no_room(key, monkeypatch)
    with pytest.raises(KeyFullError):
        key.create_playlist("New")
    with pytest.raises(KeyFullError):
        key.update_track_metadata(t.content_id, title="Renamed")
    with pytest.raises(KeyFullError):                                  # suppression sans accord : refusée aussi
        key.delete_tracks([t.content_id], True)
    assert key.track_count() == 1 and key.absolute_path(key.get_track(t.content_id)).is_file()


def test_a66_delete_without_copy_frees_space_and_keeps_pdb(key, monkeypatch, caplog):  # noqa: F811
    tracks = [_add(key, f"T{i}") for i in range(4)]
    _playlist(key, "Set", tracks)
    files = [key.absolute_path(t) for t in tracks]
    _fill(monkeypatch)
    _no_room(key, monkeypatch)
    point = key.full_return_point()
    assert point is not None and point.kind in ("auto", "origin")
    with caplog.at_level("WARNING"):
        removed, failures = key.delete_tracks([t.content_id for t in tracks[:3]], True, without_copy=point.id)
    assert (removed, failures) == (3, 0)
    assert not any(f.is_file() for f in files[:3]) and files[3].is_file()
    assert f"way back: {point.id}" in caplog.text
    monkeypatch.undo()                                                  # place rendue : tout redevient normal
    _pdb_matches(key)
    key.create_playlist("After")                                        # règle 5 : écriture habituelle


def test_a66_without_copy_needs_file_deletion(key, monkeypatch):  # noqa: F811
    t = _add(key, "Stay")
    _fill(monkeypatch)
    _no_room(key, monkeypatch)
    point = key.full_return_point()
    with pytest.raises(KeyFullError):
        key.delete_tracks([t.content_id], False, without_copy=point.id)  # sans effacer les fichiers : refusé
    assert key.track_count() == 1


def test_a66_no_return_point_means_no_offer(tmp_path):
    assert key_space.return_point(tmp_path / "DJSync_Backups") is None
    folder = tmp_path / "DJSync_Backups" / "Points" / "20260101-000000-auto"
    folder.mkdir(parents=True)
    (folder / "exportLibrary.db").write_bytes(b"not a database")
    (folder / "point.json").write_text('{"kind": "auto", "created": "2026-01-01T00:00:00"}', "utf-8")
    assert key_space.return_point(tmp_path / "DJSync_Backups") is None      # base qui ne s'ouvre pas


def test_a66_purge_keeps_two_copies_of_each_kind_and_every_point(key):  # noqa: F811
    for i in range(3):                                                  # points + copies automatiques
        key.create_playlist(f"P{i}")
    bdir = key.backup_dir
    for i in range(6):
        (bdir / f"exportLibrary-20250101-00000{i}-000-auto.db").write_bytes(b"x" * 1000)
        (bdir / f"exportLibrary-20250101-00000{i}-000-session.db").write_bytes(b"y" * 1000)
    points = sorted(p.id for p in backups.list_points(bdir))
    assert any(p.kind == "origin" for p in backups.list_points(bdir))
    auto_before, session_before = (len(k) for k in key_space.copies(bdir))
    gained = key_space.purge_copies(bdir)
    auto, session = key_space.copies(bdir)
    assert len(auto) == 2 and len(session) == 2 and gained >= (auto_before - 2) * 1000
    assert auto[-1].name > auto[0].name and auto == sorted(auto)
    assert sorted(p.id for p in backups.list_points(bdir)) == points  # points (et origine) intacts
    assert session_before >= 6


def test_a66_ui_key_full_message_never_takes_the_replug_path(demo, monkeypatch):  # noqa: F811
    from .qt_util import pump

    ctrl = demo.ctrl
    _fill(monkeypatch)
    replugged = []
    monkeypatch.setattr(ctrl, "_drive_replugged", lambda *a: replugged.append(a))
    reports = []
    monkeypatch.setattr(ctrl, "error_reporter", NS(report=lambda *a: reports.append(a)), raising=False)
    ctrl._on_error(LibraryError("disk I/O error"))
    assert not replugged and not reports
    assert pump(demo, 2, lambda: "full" in demo.status.text() or "pleine" in demo.status.text())
    assert demo.toast_action.isVisible()                                # bouton « Espace… »
    demo._toast_clicked()
    assert pump(demo, 2, lambda: demo.current == "settings")


def test_a66_ui_delete_on_full_key_asks_with_the_point_date(demo, monkeypatch):  # noqa: F811
    from djsync.ui.dialogs import ConfirmDialog

    from .qt_util import find, pump

    ctrl = demo.ctrl
    lib = ctrl.library
    lib.create_playlist("Make a session point")
    t = lib.list_tracks()[0]
    _fill(monkeypatch)
    _no_room(lib, monkeypatch)
    ctrl.delete_tracks([t.content_id], True)
    assert pump(demo, 5, lambda: find(demo, ConfirmDialog) is not None)
    dlg = find(demo, ConfirmDialog)
    point = lib.full_return_point()
    assert point.created.strftime("%d/%m/%Y") in " ".join(w.text() for w in dlg.findChildren(type(demo.status)))
    dlg._ok()
    assert pump(demo, 5, lambda: lib.track_count() == 9)
    assert not demo.errors


def test_a66_ui_full_key_that_cannot_open_offers_to_free_space(demo, monkeypatch, tmp_path):  # noqa: F811
    from djsync.db import UsbDrive

    ctrl = demo.ctrl
    drive = ctrl.drive
    bdir = Path(drive.root) / "DJSync_Backups"
    bdir.mkdir(exist_ok=True)
    for i in range(5):
        (bdir / f"exportLibrary-20250101-00000{i}-000-auto.db").write_bytes(b"x" * 1000)
    asked = []
    ctrl.on("key_full_open", lambda d: asked.append(d))
    ctrl.disconnect()
    _fill(monkeypatch)
    monkeypatch.setattr("djsync.db.RekordboxUsbLibrary.connect",
                        lambda self: (_ for _ in ()).throw(LibraryError("disk I/O error")))
    from .qt_util import pump

    ctrl.connect(drive)
    assert pump(demo, 5, lambda: asked)
    assert isinstance(asked[0], UsbDrive)
    monkeypatch.undo()
    ctrl.free_key_space(drive)
    assert pump(demo, 8, lambda: ctrl.has_library)
    assert len(key_space.copies(bdir)[0]) == 2


# ------------------------------------------------------------------ B104 : bas du volet replié aligné
def test_b104_help_and_fold_are_centred_like_the_icons_above(demo):  # noqa: F811
    from .qt_util import pump

    demo.ctrl.settings.sidebar_compact = "on"
    demo._compact = None
    demo._update_compact()
    pump(demo, 0.3)

    def centre_x(w) -> int:
        return w.mapTo(demo.sidebar, w.rect().center()).x()

    ref = centre_x(demo._nav["home"])
    for b in (demo.feedback_btn, demo.help_btn, demo.fold_btn):
        assert abs(centre_x(b) - ref) <= 1, b
        assert b.height() == demo._nav["home"].height()
    demo.ctrl.settings.sidebar_compact = "auto"


# ------------------------------------------------------------------ B107 : gain d'un candidat YouTube
def test_b107_youtube_candidate_shows_the_expected_quality():
    from djsync.core import improve
    from djsync.i18n import set_language, t

    set_language("en")
    yt = NS(source="youtube", quality="", slsk=None)
    label = improve.candidate_label(yt, "original")
    assert label != "YouTube" and "M4A" in label and "estimated" in label
    assert "MP3 320" in improve.candidate_label(yt, "mp3_320")
    assert "192" in improve.candidate_label(yt, "yt_best")
    improve.download_quality = "mp3_192"
    row = improve.QualityRow(track=NS(), info=None, finds=[yt])
    assert "MP3 192" in row.gain
    improve.download_quality = "original"
    set_language("fr")
    assert "estimé" in improve.candidate_label(yt, "original")
    set_language("en")
    assert improve.candidate_label(NS(source="deezer", quality="FLAC", slsk=None)) == "FLAC"
    assert t("quality.estimated", label="x") == "x (estimated)"


# ------------------------------------------------------------------ B108 : Diagnostic et changement de bibliothèque
@pytest.mark.parametrize("tab", ["dup", "quality", "missing"])
def test_b108_library_change_brings_back_analyse_now(demo, monkeypatch, tab):  # noqa: F811
    from djsync.ui.ctrl import diagnostic

    from .qt_util import pump

    monkeypatch.setattr(diagnostic, "ALWAYS_READY", False)
    ctrl = demo.ctrl
    demo.open_diagnostic(tab)
    page = demo.stack.currentWidget()
    before = page.analyse_now_btn
    page.analyse_now()
    pump(demo, 0.5)
    assert not getattr(page, "_is_idle", False)
    monkeypatch.setattr(type(ctrl), "_diag_key", lambda self, lib=None: "usb:OTHER|/other")
    ctrl._emit("drive")                                                     # autre bibliothèque ouverte
    pump(demo, 0.3)
    btn = page.analyse_now_btn
    assert btn is not before and not btn.isHidden()                         # nouveau panneau « Analyser maintenant »
    if tab != "dup":
        assert page._is_idle
    assert not demo.errors


# ------------------------------------------------------------------ B109 + B112 : fenêtre de choix des playlists
def test_b109_b112_picker_from_the_library_fits_the_screen_and_shows_contrasted_chips(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui import theme
    from djsync.ui.dialogs import PlaylistPicker

    from .qt_util import find, pump

    demo.show_view("library")
    lib = demo.views["library"]
    pump(demo, 3, lambda: lib.table.total == 10)
    lib._ids = lambda: [demo.ctrl.library.list_tracks()[0].content_id]
    lib._add_to()                                                       # même fenêtre que pour un téléchargement
    assert pump(demo, 3, lambda: find(demo, PlaylistPicker) is not None and find(demo, PlaylistPicker)._vars)
    p = find(demo, PlaylistPicker)
    pump(demo, 0.3)
    assert p._chips_title.isVisible() and t("picker.selected_nothing") in p._chips.itemAt(0).widget().text()
    geo = p.screen().availableGeometry()
    frame = p.frameGeometry()
    assert frame.top() >= geo.top() and frame.bottom() <= geo.bottom()          # B109 : jamais sous l'écran
    pid = list(p._vars)[0]
    p._vars[pid].setChecked(True)
    pump(demo, 0.2)
    chip = p._chips.itemAt(0).widget()
    assert p.chip_names() and theme.ACCENT in chip.styleSheet() and theme.ON_ACCENT in chip.styleSheet()
    p.close()


def test_b109_picker_is_moved_back_into_the_screen(demo, monkeypatch):  # noqa: F811
    from djsync.ui.dialogs import PlaylistPicker

    from .qt_util import pump

    p = PlaylistPicker(demo, demo.ctrl, "T", "OK", on_ok=lambda ids: None, allow_empty=True)
    pump(demo, 1, lambda: bool(p._vars))
    geo = p.screen().availableGeometry()
    p.move(geo.left() + 10, geo.bottom() - 50)                          # placée trop bas, comme chez le testeur
    p.resize(p.width(), int(geo.height() * 0.8))
    p._place()
    frame = p.frameGeometry()
    assert frame.bottom() <= geo.bottom() and frame.top() >= geo.top()
    assert t_none(p)
    p.close()


def t_none(p) -> bool:
    from djsync.i18n import t

    return t("picker.selected_none") in p._chips.itemAt(0).widget().text()      # téléchargement : bibliothèque seule


# ------------------------------------------------------------------ B110 : clés branchées / retirées, page ouverte
def test_b110_transfer_page_follows_plugged_drives_and_keeps_choices(app):  # noqa: F811
    from djsync.ui.transfer_page import TransferPage

    from .qt_util import pump

    ctrl = app.ctrl
    both = list(ctrl.drives)
    ctrl.drives = both[:1]                                              # une seule clé à l'ouverture
    app.open_transfer()
    page = app.stack.currentWidget()
    assert isinstance(page, TransferPage)
    assert not page.compare_btn.isEnabled() and page.to_box.count() <= 1
    ctrl.drives = both                                                  # 2e clé branchée
    ctrl._emit("drives")
    assert page.direction_key() == "usb2usb" and page.to_box.count() == 2
    assert pump(app, 10, lambda: len(page.side_a._items) == 4)
    page.side_a.select_all()
    checked = page.side_a.checked()
    to_key = page.to_box.currentData()
    ctrl._emit("drives")                                                # rien n'a changé : rien n'est relu
    assert page.side_a.checked() == checked
    ctrl.drives = both + []                                             # même liste, autre objet
    ctrl._emit("drive")
    assert page.side_a.checked() == checked and page.to_box.currentData() == to_key
    assert page.compare_btn.isEnabled()
    ctrl.drives = both[:1]                                              # 2e clé retirée
    ctrl._emit("drives")
    assert not page.compare_btn.isEnabled()
    assert not app.errors


# ------------------------------------------------------------------ C201 : sons déjà présents (import)
def test_c201_tracks_already_here_stay_checked_with_a_pill(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t
    from djsync.models import ResolvedUrl, TrackResult, UrlKind
    from djsync.ui.views.common import CHECKED

    from .qt_util import pump

    view = demo.views["import"]
    there = TrackResult(video_id="aaaaaaaaaaa", title="One More Time", artist="Daft Punk").with_duplicate("x")
    new = [TrackResult(video_id=f"bbbbbbbbbb{i}", title=f"New {i}", artist="Someone") for i in range(2)]
    monkeypatch.setattr(demo.ctrl, "reannotate", lambda tracks, cb: cb(list(tracks)))
    view._load_direct(ResolvedUrl(kind=UrlKind.YOUTUBE, name="Mix", tracks=[there] + new, is_playlist=True))
    pump(demo, 0.2)
    rows = {r.iid: r for r in view.dl_table.all_rows()}
    assert all(r.values.get("chk") == CHECKED for r in rows.values())          # tous cochés
    assert rows["aaaaaaaaaaa"].values["lib"] == t("import.already_here")      # pastille « déjà là »
    assert len(view._checked_tracks()) == 2 and len(view._present_tracks()) == 1
    assert view.dl_btn.text() == t("import.download_and_add", n=2, m=1)
    sent = []
    import djsync.ui.views.import_view as iv

    monkeypatch.setattr(iv, "ask_and_download", lambda *a, **k: sent.append((a, k)))
    view._download()
    (args, kw), = sent
    assert [x.title for x in args[2]] == ["New 0", "New 1"] and [x.title for x in kw["existing"]] == ["One More Time"]


# ------------------------------------------------------------------ B111 : boutons de décalage sur deux lignes
def test_b111_shift_buttons_wrap_instead_of_overlapping(demo):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    track = demo.ctrl.library.list_tracks()[0]
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        pump(demo, 0.5)
        box = ed.shift_box
        lay = box.layout()
        widgets = [lay.itemAt(i).widget() for i in range(lay.count())]
        for width in (900, 380, 240):
            h = lay.heightForWidth(width)
            box.setFixedWidth(width)
            box.setFixedHeight(h)
            lay.setGeometry(box.rect())
            widgets[1].layout().activate()
            pump(demo, 0.05)
            rects = [w.geometry() for w in widgets]
            for i, a in enumerate(rects):                              # jamais l'un sur l'autre
                for b in rects[i + 1:]:
                    assert not a.intersects(b), (width, a, b)
            seg = widgets[1]
            btns = [b.geometry() for b in ed._shift_btns]
            assert all(not a.intersects(b) for i, a in enumerate(btns) for b in btns[i + 1:])
            assert all(b.width() >= b.fontMetrics().horizontalAdvance(b.text()) for b in ed._shift_btns)
            if width == 900:
                assert len({r.top() for r in rects}) == 1                 # une ligne quand la place suffit
            if width == 240:
                assert len({r.top() for r in rects}) >= 2                 # deux lignes ou plus sinon
            assert seg.geometry().right() <= max(width, seg.width()) + 1
    finally:
        ed.close()


# ------------------------------------------------------------------ C204 : « Grille juste » sans modification
def test_c204_grid_is_right_marks_the_grid_without_writing(demo):  # noqa: F811
    from djsync.db import grid_marks
    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    lib = demo.ctrl.library
    track = lib.list_tracks()[0]
    db_before = lib.db_path.read_bytes()
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        pump(demo, 1)
        ed.duration_ms = 240000
        ed.beats = [((i % 4) + 1, 12000, 500 * i) for i in range(480)]
        ed.original = list(ed.beats)
        ed._refresh_info()
        assert ed.checked_btn.isEnabled() and not ed.save_btn.isEnabled()
        ed._shift(1)                                                        # modifié : « Enregistrer » s'en charge
        assert not ed.checked_btn.isEnabled()
        ed._reset()
        assert ed.checked_btn.isEnabled()
        ed.checked_btn.click()
        assert pump(demo, 5, lambda: track.content_id in grid_marks.load(lib.backup_dir))
        assert pump(demo, 2, lambda: not ed.checked_btn.isEnabled())
        assert lib.db_path.read_bytes() == db_before                       # base inchangée
    finally:
        ed._leaving = True
        ed.close()
    ed2 = GridEditor(demo, demo.ctrl, track)
    try:
        pump(demo, 1)
        ed2.beats = ed2.original = [(1, 12000, 0)]
        ed2._refresh_info()
        assert not ed2.checked_btn.isEnabled()                              # déjà vérifiée
    finally:
        ed2.close()


# ------------------------------------------------------------------ C205 : familles de couleurs côte à côte
def test_c205_colour_families_side_by_side(demo):  # noqa: F811
    from PySide6.QtWidgets import QBoxLayout

    from djsync.ui.palettes import FAMILIES

    from .qt_util import pump

    demo.show_view("settings")
    view = demo.views["settings"]
    box = view._family_box
    assert box.layout().direction() == QBoxLayout.LeftToRight
    box.adjustSize()
    box.layout().activate()
    lefts = [col.itemAt(0).widget().geometry().left() for col in view._family_cols]
    assert lefts == sorted(lefts) and len(set(lefts)) == 3                 # trois colonnes, dans l'ordre
    assert [col.count() - 2 for col in view._family_cols] == [len(v) for v in FAMILIES.values()]
    view._swatches["teal"].trigger()
    pump(demo, 0.3)
    assert demo.ctrl.settings.theme == "teal"


# ------------------------------------------------------------------ C207 : panneau replié en haut
def test_c207_folded_panel_moves_to_the_top(demo, monkeypatch):  # noqa: F811
    s = demo.ctrl.settings
    monkeypatch.setattr(s, "save", lambda *a, **k: None)
    s.panels_folded = {}
    view = demo.views["downloads"]
    demo.show_view("downloads")
    top, bottom = view._panels["downloads"][0], view._panels["analysis"][0]
    split = view._split
    assert split.indexOf(top) == 0 and split.indexOf(bottom) == 1
    view._toggle_fold("analysis")                                        # Analyse repliée : en haut
    assert split.indexOf(bottom) == 0 and split.indexOf(top) == 1
    view._toggle_fold("analysis")                                        # dépliée : retour à sa place
    assert split.indexOf(top) == 0 and split.indexOf(bottom) == 1
    view._toggle_fold("downloads")                                       # Téléchargements repliés : déjà en haut
    assert split.indexOf(top) == 0
    view._toggle_fold("downloads")


# ------------------------------------------------------------------ C208 : « export.pdb » dans les libellés
def test_c208_home_chip_says_export_pdb_and_explains_older_players(demo):  # noqa: F811
    from PySide6.QtWidgets import QLabel

    from djsync.i18n import t

    from .qt_util import pump

    home = demo.views["home"]
    demo.show_view("home")
    assert pump(demo, 8, lambda: any(w.text().startswith("export.pdb") for w in home.findChildren(QLabel)))
    chip = next(w for w in home.findChildren(QLabel) if w.text().startswith("export.pdb"))
    assert "CDJ-2000NXS2" in chip.toolTip()
    assert t("set.row_pdb") == "export.pdb"


# ------------------------------------------------------------------ A6-7 : effacement définitif dit clairement
def test_a67_delete_confirmations_say_the_audio_is_gone_for_good():
    from djsync.i18n import en, fr

    for cat, word in ((en.STRINGS, "for good"), (fr.STRINGS, "pour de bon")):
        for k in ("lib.delete_detail", "lib.delete_local_detail", "dup.confirm_detail", "diag.replace_detail"):
            assert word in cat[k], k
            assert "backed up before" not in cat[k] and "sauvegardée avant" not in cat[k]


# ------------------------------------------------------------------ A6-8 : désinstaller avec les deux cases
def test_a68_both_uninstall_boxes_show_a_warning(demo):  # noqa: F811
    from djsync.ui.backups_dialog import UninstallDialog

    dlg = UninstallDialog(demo, demo.ctrl, mode="drive")
    try:
        assert dlg.both_warn.isHidden()
        dlg.restore_var.setChecked(True)
        assert dlg.both_warn.isHidden()
        dlg.backups_var.setChecked(True)
        assert not dlg.both_warn.isHidden()
        dlg.restore_var.setChecked(False)
        assert dlg.both_warn.isHidden()
    finally:
        dlg.close()
