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
