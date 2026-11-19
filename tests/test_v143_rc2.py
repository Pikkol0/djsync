"""1.4.3-rc.2 : tests ciblés des fiches de la rc.2 (A1-9, B103, A3-x, A2-x, C199, C200, C203, C210, A7-x)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from djsync.db.pdb import PdbDatabase
from djsync.db.pdb.sync import (PLAYLIST_DELETED, TRACK_DELETED, TRACK_FIELDS, TRACK_REBUILT, Mark, Target,
                                plan)

from .pdb_fixture import build_pdb, sample_track


# ----------------------------------------------------------------------------- A3-9 : tests de plan
# export.pdb n'est pas touché (option B) : on fige le comportement de `plan` branche par branche.

def _db(tracks, playlists):
    return PdbDatabase(build_pdb(tracks, playlists))


def _target(tracks, playlists):
    return Target(tracks=list(tracks), playlists=[(tuple(p), f, list(t)) for p, f, t in playlists])


def test_a3_9_plan_up_to_date_is_empty_and_reads_only():
    t1, t2 = sample_track(1), sample_track(2)
    raw = build_pdb([t1, t2], {("Rap",): [t1.path, t2.path]})
    db = PdbDatabase(raw)
    p = plan(db, _target([t1, t2], [(("Rap",), False, [t1.path, t2.path])]))
    assert p.empty and p.describe() == "up to date"
    assert db.to_bytes() == PdbDatabase(raw).to_bytes()        # plan ne modifie rien


def test_a3_9_plan_missing_track_and_playlist():
    t1, t2 = sample_track(1), sample_track(2)
    db = _db([t1], {("Rap",): [t1.path]})
    p = plan(db, _target([t1, t2], [(("Rap",), False, [t1.path]), (("New",), False, [t2.path, t2.path])]))
    assert [m.path for m in p.add_tracks] == [t2.path]
    assert p.add_playlists == [(("New",), False)]
    assert p.set_entries == [(("New",), [t2.path])]             # doublon retiré
    assert p.changed_playlists == 0                             # la nouvelle est comptée à part
    assert "1 track(s) missing" in p.describe() and "1 playlist(s) missing" in p.describe()


def test_a3_9_plan_new_folder_has_no_entries():
    t1 = sample_track(1)
    p = plan(_db([t1], {}), _target([t1], [(("Dossier",), True, [])]))
    assert p.add_playlists == [(("Dossier",), True)] and p.set_entries == []


def test_a3_9_plan_order_change_and_unknown_entries_kept():
    t1, t2, t3 = sample_track(1), sample_track(2), sample_track(3)
    db = _db([t1, t2, t3], {("Rap",): [t1.path, t3.path, t2.path]})
    # t3 n'est plus voulu côté exportLibrary.db (pas de marque) : gardé, en fin de liste
    p = plan(db, _target([t1, t2], [(("Rap",), False, [t2.path, t1.path])]))
    assert p.changed_playlists == 1
    (path, entries), = p.set_entries
    assert path == ("Rap",) and [e.casefold() for e in entries] == [t2.path.casefold(), t1.path.casefold(),
                                                                    t3.path.casefold()]
    assert p.delete_tracks == []                                # jamais retiré sans marque du journal


def test_a3_9_plan_marks_deleted_track():
    t1, t2 = sample_track(1), sample_track(2)
    db = _db([t1, t2], {})
    gone, readded, absent = Mark(TRACK_DELETED, (t2.path,)), Mark(TRACK_DELETED, (t1.path,)), \
        Mark(TRACK_DELETED, ("/Contents/x/y/none.mp3",))
    p = plan(db, _target([t1], []), [gone, readded, absent])
    assert p.delete_tracks == [t2.path]
    assert set(p.resolved) == {gone, readded, absent}


def test_a3_9_plan_marks_deleted_playlists_nested_once():
    t1 = sample_track(1)
    db = _db([t1], {("A",): [], ("A", "B"): [t1.path], ("C",): []})
    marks = [Mark(PLAYLIST_DELETED, ("A",)), Mark(PLAYLIST_DELETED, ("A", "B")), Mark(PLAYLIST_DELETED, ("C",))]
    # « C » est de nouveau voulue : la marque est seulement résolue
    p = plan(db, _target([t1], [(("C",), False, [])]), marks)
    assert p.delete_playlists == [("A",)]                       # l'enfant part avec le parent
    assert set(p.resolved) == set(marks)


def test_a3_9_plan_recreates_a_playlist_deleted_then_wanted_again_under_new_content():
    t1 = sample_track(1)
    db = _db([t1], {("A",): [t1.path]})
    p = plan(db, _target([t1], [(("A", "X"), False, [t1.path])]), [Mark(PLAYLIST_DELETED, ("A",))])
    assert p.delete_playlists == [("A",)]
    assert (("A", "X"), False) in p.add_playlists              # sous un parent supprimé : recréée


def test_a3_9_plan_upgrade_rebuild_and_fields():
    t1, t2, t3 = sample_track(1), sample_track(2), sample_track(3)
    db = _db([t1, t2, t3], {})
    analysed = dataclasses.replace(t1, analyze_path="/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT")
    renamed = dataclasses.replace(t2, title="Nouveau titre", bpmx100=t2.bpmx100 + 100)
    p = plan(db, _target([analysed, renamed, t3], []),
             [Mark(TRACK_FIELDS, (t2.path,)), Mark(TRACK_REBUILT, (t3.path,))])
    assert [m.path for m in p.upgrade_tracks] == [t1.path]
    assert [m.path for m in p.rebuild_tracks] == [t3.path]
    upd = [u for u in p.update_tracks if u[0] == t2.path]
    assert upd and upd[0][1] == "Nouveau titre" and upd[0][2] is None and upd[0][3] == t2.bpmx100 + 100
    assert {m.kind for m in p.resolved} == {TRACK_FIELDS, TRACK_REBUILT}


def test_a3_9_plan_same_fields_without_mark_are_not_rewritten():
    t1 = sample_track(1)
    p = plan(_db([t1], {}), _target([dataclasses.replace(t1, title="Autre")], []))
    assert not [u for u in p.update_tracks if u[1] is not None]     # sans marque : titre jamais recopié


# ------------------------------------------------- A3-7 : mêmes scénarios sur la clé et sur master.db
from djsync.db.errors import LibraryError  # noqa: E402

from .test_usb_library import usb  # noqa: E402,F401 (fixture)
from .test_v050 import _wav, local, usb_lib  # noqa: E402,F401 (fixtures)


@pytest.fixture(params=["usb", "local"])
def any_lib(request):
    return request.getfixturevalue("usb_lib" if request.param == "usb" else "local")


def _folder(lib):
    try:
        return lib.default_download_dir("Art", "")
    except TypeError:
        return lib.default_download_dir("Art")


def _add_plain(lib, name, bpm=124.0):
    return lib.add_track(_wav(_folder(lib), name, bpm=bpm), name, "Art", analyze=False)


def test_a3_7_add_without_analysis_then_analyze_tracks(any_lib):
    t = _add_plain(any_lib, "Flow one")
    assert not t.is_analysed
    seen = []
    done, skipped, failed = any_lib.analyze_tracks([t.content_id, t.content_id, 999999],
                                                   on_progress=lambda i, n, tr, pb: seen.append((i, n, bool(pb))))
    assert (done, skipped, failed) == (1, 0, 1)
    assert [s[:2] for s in seen] == [(1, 2), (2, 2)] and seen[1][2]       # doublon retiré ; échec expliqué
    assert any_lib.get_track(t.content_id).is_analysed
    assert any_lib.analyze_tracks([t.content_id]) == (0, 1, 0)             # déjà analysé : ignoré


def test_a3_7_analyze_tracks_stops_cleanly(any_lib):
    a, b = _add_plain(any_lib, "Stop a"), _add_plain(any_lib, "Stop b")
    calls = []
    res = any_lib.analyze_tracks([a.content_id, b.content_id], should_stop=lambda: bool(calls),
                                 on_progress=lambda *x: calls.append(x))
    assert res == (1, 0, 0) and len(calls) == 1
    assert not any_lib.get_track(b.content_id).is_analysed


def test_a3_7_beat_grid_save_and_refuse(any_lib):
    t = any_lib.add_track(_wav(_folder(any_lib), "Grid me", bpm=120.0), "Grid me", "Art", analyze=True)
    grid = any_lib.beat_grid(t.content_id)
    assert len(grid.beats) > 4
    dat_before = grid.dat_path.read_bytes()
    with pytest.raises(LibraryError):
        any_lib.save_beat_grid(t.content_id, [(1, 12000, 100)])           # une seule battue : refusée
    with pytest.raises(LibraryError):
        any_lib.save_beat_grid(t.content_id, [(1, 12000, 500), (2, 12000, 400)])
    assert grid.dat_path.read_bytes() == dat_before                        # rien d'écrit
    beats = [(n, 13000, ms + 20) for n, _t, ms in grid.beats]
    saved = any_lib.save_beat_grid(t.content_id, beats)
    assert round(saved.bpm) == 130
    assert [b[2] for b in any_lib.beat_grid(t.content_id).beats] == [b[2] for b in beats]
    backups = list((any_lib.backup_dir / "anlz").glob(f"*-{t.content_id}"))
    assert backups and (backups[0] / grid.dat_path.name).read_bytes() == dat_before


def test_a3_7_beat_grid_unanalysed_and_unknown(any_lib):
    from djsync.db.errors import TrackNotFoundError

    t = _add_plain(any_lib, "No grid")
    with pytest.raises(LibraryError):
        any_lib.beat_grid(t.content_id)
    with pytest.raises(TrackNotFoundError):
        any_lib.beat_grid(999999)


def test_a3_7_import_analysis_reuses_files(any_lib):
    src = any_lib.add_track(_wav(_folder(any_lib), "Source", bpm=126.0), "Source", "Art", analyze=True)
    dat = Path(any_lib.beat_grid(src.content_id).dat_path)
    files = {".DAT": dat.read_bytes()}
    if dat.with_suffix(".EXT").is_file():
        files[".EXT"] = dat.with_suffix(".EXT").read_bytes()
    dst = _add_plain(any_lib, "Copy")
    out = any_lib.import_analysis(dst.content_id, files, bpm=126.0, key="Am")
    assert out.is_analysed and round(out.bpm) == 126
    assert len(any_lib.beat_grid(dst.content_id).beats) == len(any_lib.beat_grid(src.content_id).beats)
    again = any_lib.import_analysis(dst.content_id, files, bpm=90.0)        # déjà analysé : inchangé
    assert round(again.bpm) == 126


# ------------------------------------------------------- A2-18 (option A) : enregistrement immédiat
from .qt_util import pump  # noqa: E402
from .test_ui_v020 import demo  # noqa: E402,F401 (fixture)


def test_a2_18_settings_saved_at_once_no_save_button(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t

    saves = []
    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: saves.append(1))
    demo.show_view("settings")
    view = demo.views["settings"]
    from PySide6.QtWidgets import QPushButton

    assert not [b for b in view.findChildren(QPushButton) if b.text() == t("action.save")]
    want = not view.views_var.isChecked()
    view.views_var.setChecked(want)
    assert pump(demo, 3, lambda: demo.ctrl.settings.fetch_views == want)
    assert view.unsaved() == [] and saves
    assert pump(demo, 1, lambda: "✓" in view.saved.text())


def test_a2_18_text_field_saved_when_leaving_the_page(demo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    demo.show_view("settings")
    view = demo.views["settings"]
    view.sc_token.setText("tok-123")                       # saisie en cours, pas encore validée
    demo.show_view("library")
    assert demo.current == "library"                       # plus de question en quittant
    assert demo.ctrl.settings.soundcloud_token == "tok-123"


# ------------------------------------------------------- A2-19, A2-20 : clavier et noms accessibles
def test_a2_19_space_activates_focused_button_not_playback(demo, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QCheckBox

    played = []
    monkeypatch.setattr(demo.ctrl, "toggle_play", lambda: played.append(1))
    demo.show_view("settings")
    box = demo.views["settings"].views_var
    before = box.isChecked()
    monkeypatch.setattr(demo.qapp, "focusWidget", lambda: box)
    demo._space()
    assert pump(demo, 2, lambda: box.isChecked() != before) and not played
    monkeypatch.setattr(demo.qapp, "focusWidget", lambda: None)
    demo._space()
    assert played == [1]
    assert isinstance(box, QCheckBox)


def test_a2_19_buttons_take_focus_from_keyboard_only():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from djsync.ui.widgets import button

    QApplication.instance() or QApplication([])
    assert button("OK").focusPolicy() == Qt.TabFocus


def test_a2_20_icon_buttons_have_accessible_names(demo):  # noqa: F811
    from PySide6.QtWidgets import QAbstractButton

    from djsync.ui.widgets import icon_button, name_icon_buttons

    b = icon_button("close", None, "Close")
    assert b.accessibleName() == "Close"
    for key in ("home", "library", "settings"):
        demo.show_view(key)
        pump(demo, 0.3)
    name_icon_buttons(demo)
    missing = [b for b in demo.findChildren(QAbstractButton)
               if not b.text().strip() and b.toolTip() and not b.accessibleName()]
    assert missing == []


# ------------------------------------------------------- A2-21 : « Retirer » d'une playlist annulable
def test_a2_21_remove_from_playlist_can_be_undone(demo):  # noqa: F811
    from djsync.i18n import t

    ctrl, lib = demo.ctrl, demo.ctrl.library
    pl = next(p for p in lib.list_playlists() if not p.is_folder and len(lib.get_playlist_tracks(p.playlist_id)) >= 3)
    before = [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)]
    actions = []
    ctrl.on("message_action", lambda text, fn: actions.append((text, fn)))
    ctrl.remove_from_playlist(pl.playlist_id, [before[1]])
    assert pump(demo, 5, lambda: actions)
    assert [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)] == before[:1] + before[2:]
    text, fn = actions[-1]
    assert text == t("action.undo")
    fn()
    assert pump(demo, 5, lambda: [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)] == before)


# ------------------------------------------------------- A2-23 : ménage
def test_a2_23_catalogues_same_keys_and_help_lists_page_shortcuts():
    from djsync.i18n import en, fr
    from djsync.ui import help_dialog

    assert set(en.STRINGS) == set(fr.STRINGS)
    assert "settings.leave_title" not in en.STRINGS and "improve.title" not in en.STRINGS
    for _k, key in help_dialog.GRID_SHORTCUTS + help_dialog.UNI_SHORTCUTS:
        assert key in en.STRINGS and key in fr.STRINGS
    src = (Path(__file__).resolve().parent.parent / "tools" / "ui_screenshots.py").read_text(encoding="utf-8")
    assert "diagnostic_dialog" not in src


# ------------------------------------------------------- C200 : place totale de DJSync
def test_c200_footprint_sums_parts(tmp_path):
    from djsync.core import space

    data, music = tmp_path / "data", tmp_path / "music"
    (data / "cache").mkdir(parents=True)
    (data / "Backups" / "rekordbox").mkdir(parents=True)
    music.mkdir()
    (data / "cache" / "a").write_bytes(b"x" * 1000)
    (data / "Backups" / "rekordbox" / "m.db").write_bytes(b"x" * 3000)
    (data / "settings.json").write_bytes(b"x" * 200)
    (music / "t.mp3").write_bytes(b"x" * 50_000)
    fp = space.djsync_footprint(data, music)
    assert fp["caches"] >= 1000 and fp["backups"] >= 3000 and fp["music"] >= 50_000
    assert 200 <= fp["settings"] < 1000                     # sans les caches ni les sauvegardes
    assert fp["app"] > 0
    assert fp["total"] == sum(fp[k] for k in space.FOOTPRINT_PARTS)


def test_c200_space_card_shows_total(demo):  # noqa: F811
    from djsync.i18n import t

    demo.show_view("settings")
    view = demo.views["settings"]
    view.show_section("libraries")
    view.space.compute(force=True)
    assert pump(demo, 10, lambda: view.space.footprint.isVisible() and view.space.footprint.text())
    assert t("space.footprint", size="").split(":")[0] in view.space.footprint.text()


# ------------------------------------------------------- C203 : Transférer et synchroniser
def test_c203_name_tile_and_sync_from_card(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import fr, t

    assert fr.STRINGS["transfer.title"] == "Transférer et synchroniser des playlists"
    home = demo.views["home"]
    assert "transfer" in home.actions
    opened = []
    monkeypatch.setattr(demo, "open_transfer", lambda pre=(), sync_from=None: opened.append(sync_from))
    home.actions["transfer"].click()
    assert opened == [None]                                 # depuis l'Accueil : sens unique par défaut

    class S:
        is_local, drive = False, type("D", (), {"root": "/x"})()

    home.act_transfer(S())
    assert opened[-1] == "/x"
    assert t("transfer.card_button")


# ------------------------------------------------------- C199 : aperçu de la fusion
def _tr(cid, title, artist="Art"):
    from types import SimpleNamespace

    return SimpleNamespace(content_id=cid, title=title, artist=artist)


def test_c199_preview_playlists_cues_and_versions():
    from djsync.analysis.cues import Cue
    from djsync.core import merge_preview as M
    from djsync.i18n import set_language

    set_language("en")
    keep, other = _tr(1, "Song"), _tr(2, "Song (clip)")
    pls = {1: ["House"], 2: ["House", "Rap"]}
    cues = {1: [Cue(1, 1000), Cue(0, 500)], 2: [Cue(1, 1000), Cue(2, 62000, 70000)]}
    lines = M.build(keep, [other], pls, cues, cues_from=2, new_title="Song!")
    got = {(x.sign, x.section, x.text) for x in lines}
    assert ("=", "playlists", "House") in got
    assert ("+", "playlists", "Rap (the kept version takes its place)") in got
    assert ("−", "tracks", "Removed, file deleted: Art — Song (clip)") in got
    assert ("=", "cues", "A 0:01") in got and ("−", "cues", "Memory 0:00") in got
    assert ("+", "cues", "B 1:02 → 1:10") in got
    assert ("−", "info", "Art — Song") in got and ("+", "info", "Art — Song!") in got
    html = M.to_html(lines, "#0f0", "#f00", "#999")
    assert "#0f0" in html and "#f00" in html and "Playlists" in html
    # sans changement de cues : ceux de la version gardée restent
    same = M.build(keep, [other], pls, cues)
    assert not [x for x in same if x.section == "cues" and x.sign != "="]


def test_c199_missing_merge_carries_cues_only_without_hot_cues():
    from djsync.analysis.cues import Cue
    from djsync.core import merge_preview as M

    keep, missing = _tr(1, "A"), _tr(2, "A")
    with_hot = M.build(keep, [missing], {}, {1: [Cue(3, 100)], 2: [Cue(1, 200)]}, cues_from=2,
                       files_deleted=False, cues_if_none=True)
    assert not [x for x in with_hot if x.section == "cues" and x.sign == "+"]
    empty = M.build(keep, [missing], {}, {1: [], 2: [Cue(1, 200)]}, cues_from=2, files_deleted=False,
                    cues_if_none=True)
    assert [x for x in empty if x.section == "cues" and x.sign == "+"]
    assert all("file deleted" not in x.text for x in empty)
