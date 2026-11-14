"""Suite de test_v131.py (1.4.2, C183 : fichier découpé pour que la passe parallèle --dist loadfile
ne dépende plus d'un seul gros fichier ; mêmes tests, aucun retiré)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .test_v131 import (  # noqa: F401,E402 (fixtures et aides du premier fichier)
    _demo_app,
    _usb_with_genres,
    lib,
    usb,
)


def test_home_pdb_chip_opens_the_libraries_section(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.views["home"].open_settings("libraries")                 # 1.3.1 (C90) : état d'export.pdb dans Bibliothèques
        pump(app, 0.2)
        assert app._current == "settings" and app.views["settings"]._current_section == "libraries"
        assert app.views["settings"].pdb_sync_btn.isVisibleTo(app.views["settings"])
    finally:
        close_window(app)


# ------------------------------------------------------------------ C27 : espace occupé
def test_usb_usage_parts_and_safe_actions(tmp_path):
    from datetime import datetime, timedelta

    from djsync.core import space
    from djsync.db import backups

    root = tmp_path / "key"
    (root / "Contents" / "A").mkdir(parents=True)
    (root / "Contents" / "A" / "a.m4a").write_bytes(b"x" * 5000)
    (root / "PIONEER" / "rekordbox").mkdir(parents=True)
    (root / "PIONEER" / "rekordbox" / "exportLibrary.db").write_bytes(b"x" * 700)
    (root / "PIONEER" / "USBANLZ" / "P001").mkdir(parents=True)
    (root / "PIONEER" / "USBANLZ" / "P001" / "ANLZ0000.DAT").write_bytes(b"x" * 300)
    data = root / ".djsync" / "data"
    (data / "cache" / "grid").mkdir(parents=True)
    (data / "cache" / "grid" / "g.npz").write_bytes(b"x" * 900)
    (data / "settings.json").write_bytes(b"x" * 100)
    (root / "DJSync.exe").write_bytes(b"x" * 2000)
    bdir = root / "DJSync_Backups"
    pts = backups.points_dir(bdir)
    now = datetime(2026, 10, 27, 12, 0)
    for i, kind in enumerate(["origin", "manual"] + ["auto"] * 7):
        folder = pts / f"p{i:02d}-{kind}"
        folder.mkdir(parents=True)
        (folder / "exportLibrary.db").write_bytes(b"x" * 100)
        backups._write_meta(folder, kind, now - timedelta(days=10 - i), "", [], (1, 1))
    u = space.usb_usage(root, "Contents", data)
    p = u.parts
    assert list(p) == list(space.USB_PARTS)
    assert p["music"] == 5000 and p["databases"] == 700 and p["analysis"] == 300
    assert p["caches"] == 900 and p["app"] == 2100                     # cache compté à part
    assert p["backups"] >= 900 and p["free"] == u.free
    assert space.clear_caches(data) == 900 and not any((data / "cache").iterdir())
    kinds = lambda: sorted(x.kind for x in backups.list_points(bdir))    # noqa: E731
    assert kinds().count("auto") == 7
    removed, freed = space.trim_points(bdir, 5)
    assert removed == 2 and freed > 0
    assert kinds() == ["auto"] * 5 + ["manual", "origin"]               # origine et manuel gardés


def test_space_warnings_and_cache():
    from djsync.core import space

    u = space.Usage({"music": 50, "backups": 40, "free": 5}, total=100, free=5)
    assert u.warnings() == ["low_free", "heavy_backups"]
    c = space.UsageCache(seconds=60)
    u.at = __import__("time").time()
    c.put("k", u)
    assert c.get("k") is u
    c.drop("k")
    assert c.get("k") is None


def test_space_card_measures_when_shown_and_home_link(tmp_path, monkeypatch):
    from djsync.core import space

    from .qt_util import close_window, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        calls = []
        real = space.usb_usage
        monkeypatch.setattr(space, "usb_usage", lambda *a, **k: calls.append(a) or real(*a, **k))
        app.resize(1300, 900)
        app.show_view("settings")
        view = app.views["settings"]
        view.show_section("general")
        pump(app, 0.3)
        assert not calls                                         # pas mesuré tant que la carte est cachée
        app.show_view("home")
        app.views["home"].open_space()
        assert pump(app, 8, lambda: view.space.usage is not None)
        assert view._current_section == "libraries" and len(calls) == 1
        assert view.space.usage.parts["music"] > 0
        assert "music" in view.space.usage.folders
        view.show_section("general")
        view.show_section("libraries")
        pump(app, 0.3)
        assert len(calls) == 1                                   # résultat gardé quelques minutes
        view.space.compute(force=True)
        assert pump(app, 8, lambda: len(calls) == 2 and view.space.refresh_btn.isEnabled())
        assert not app.errors
    finally:
        close_window(app)


# ------------------------------------------------------------------ C41 / C43 : Diagnostic en onglets
def test_missing_files_tab_replace_relink_remove(tmp_path, monkeypatch):
    import shutil

    from djsync.ui.diag_tabs import DiagTabs
    from djsync.ui.missing_dialog import DOWNLOAD, RELINK, REMOVE, REPLACE, MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        lib = ctrl.library
        by_title = {x.title: x for x in lib.list_tracks()}
        clip, umbrella, vald = by_title["One More Time (Clip Officiel)"], by_title["Umbrella"], by_title["Désaccordé"]
        lib.absolute_path(clip).unlink()                                     # supprimé
        moved = usb / "Contents" / "Rangé" / lib.absolute_path(umbrella).name
        moved.parent.mkdir(parents=True)
        shutil.move(str(lib.absolute_path(umbrella)), str(moved))            # dossier déplacé
        lib.absolute_path(vald).unlink()
        pls_umbrella = set(lib.playlists_of([umbrella.content_id])[umbrella.content_id])

        app.open_diagnostic("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        dlg = find(app, MissingFilesDialog)
        assert pump(app, 8, lambda: len(dlg.items) == 3)
        assert ctrl.diag_counts["missing"] == 3
        tabs = dlg.findChild(DiagTabs)
        assert "(3)" in tabs.buttons["missing"].text()
        items = {i.track.title: i for i in dlg.items}
        assert [c.title for c in items[clip.title].candidates] == ["One More Time"]
        assert items[umbrella.title].found == moved and not items[vald.title].candidates

        # remplacer le clip par la version présente
        dlg._select(dlg.items.index(items[clip.title]))
        assert dlg._choice.checkedId() == REPLACE * 1000
        dlg._apply()
        assert pump(app, 6, lambda: len(dlg.items) == 2)
        ids = {x.content_id for x in lib.list_tracks()}
        assert clip.content_id not in ids and by_title["One More Time"].content_id in ids

        # relier Umbrella à son fichier déplacé : même son, mêmes playlists
        dlg._select(dlg.items.index(items[umbrella.title]))
        assert dlg._choice.checkedId() == RELINK * 1000
        dlg._apply()
        assert pump(app, 6, lambda: len(dlg.items) == 1)
        x = lib.get_track(umbrella.content_id)
        assert lib.absolute_path(x) == moved and set(lib.playlists_of([x.content_id])[x.content_id]) == pls_umbrella
        if x.analysis_path:
            from djsync.analysis.anlz import read_path

            assert read_path(lib.absolute_path(x.analysis_path).read_bytes()) == x.path

        # retirer l'entrée (pas d'autre choix proposé par défaut que retélécharger / retirer)
        assert dlg._choice.button(DOWNLOAD * 1000) is not None
        dlg._choice.button(REMOVE * 1000).setChecked(True)
        dlg._apply()
        assert pump(app, 6, lambda: not dlg.items)
        assert vald.content_id not in {x.content_id for x in lib.list_tracks()}
        assert ctrl.diag_counts["missing"] == 0 and "(0)" in tabs.buttons["missing"].text()
        assert not app.errors
    finally:
        close_window(app)


def test_diagnostic_tabs_switch_between_tools(tmp_path, monkeypatch):
    from djsync.ui.diag_tabs import DiagTabs
    from djsync.ui.quality_page import QualityPage
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.show_view("library")
        app.views["library"]._duplicates()                            # Outils ▸ Doublons : onglet Doublons
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None)
        dup = find(app, DuplicatesDialog)
        tabs = dup.findChild(DiagTabs)
        assert tabs.buttons["dup"].isChecked() and not tabs.buttons["missing"].isChecked()
        assert pump(app, 6, lambda: ctrl.diag_counts.get("uniformize") is not None)   # comptes rapides
        tabs._go("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None and find(app, DuplicatesDialog) is None)
        page = find(app, MissingFilesDialog)
        page.findChild(DiagTabs)._go("quality")
        assert pump(app, 2, lambda: find(app, QualityPage) is not None and find(app, MissingFilesDialog) is None)
        q = find(app, QualityPage)
        q.close()                                                       # Retour : vue d'origine
        assert pump(app, 2, lambda: app._current == "library" and app.stack.currentWidget() is app.views["library"])
        # Uniformiser : choix de la portée, puis page avec la même barre d'onglets
        app.open_diagnostic("dup")
        dup = find(app, DuplicatesDialog)
        app.open_uniformize(ctrl.library.list_tracks()[:2], "test")
        assert find(app, DuplicatesDialog) is None
        uni = app.uniformize_page
        assert uni.findChild(DiagTabs).buttons["uniformize"].isChecked()
        uni.findChild(DiagTabs)._go("dup")
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None and app.uniformize_page is None)
        assert not app.errors
    finally:
        close_window(app)


def test_relink_updates_export_pdb_and_playlists(tmp_path):
    import shutil

    from .test_pdb_sync import make_usb, open_lib, pdb_of
    from .test_usb_library import make_wav

    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1, 2])
        new = usb / "Contents" / "Moved" / "a.wav"
        new.parent.mkdir(parents=True)
        shutil.move(str(lib.absolute_path(a)), str(new))
        x = lib.relink_track(a.content_id, new)
        assert x.path == "/Contents/Moved/a.wav" and lib.pdb_state == "ok", lib.pdb_problem
    pdb = pdb_of(usb)
    assert pdb.has_track("/Contents/Moved/a.wav") and not pdb.has_track(a.path)
    assert [p.rsplit("/", 1)[-1] for p in pdb.playlist_tracks(("Rap",))] == ["a.wav"]


def test_missing_file_message_links_to_the_diagnostic(tmp_path, monkeypatch):
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.show()
        ctrl._player_event("missing", str(usb / "Contents" / "x.m4a"))
        assert app.toast_action.isVisibleTo(app) and app.toast_action.text() == "See in the Diagnostic"
        app.toast_action.click()
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        ctrl.message("info", "other")
        assert not app.toast_action.isVisibleTo(app)
    finally:
        close_window(app)


# ------------------------------------------------------------------ C30 : suggestions
def _lt(cid, key, bpm, title="t", genre=""):
    from djsync.models import LibraryTrack

    return LibraryTrack(cid, title or f"t{cid}", "a", None, 200, f"/Contents/{cid}.m4a", bpm, 4, None, "", True,
                        key=key, genre=genre)


def test_suggestion_scores_key_bpm_half_double():
    from djsync.core.suggest import bpm_gap, key_relation, suggestions

    assert key_relation("8A", "8A") == "same" and key_relation("8A", "9A") == "near"
    assert key_relation("8A", "8B") == "relative" and key_relation("8A", "10A") == "none"
    assert key_relation("8A", "10A", energy=True) == "far"
    assert bpm_gap(140, 70) == (0.0, 2.0) and bpm_gap(124, 126)[0] == 1.6
    ref = _lt(1, "Am", 124.0, genre="House")                       # 8A
    pool = [ref, _lt(2, "Am", 124.0, "same"), _lt(3, "Em", 126.0, "near"), _lt(4, "C", 62.0, "relative half"),
            _lt(5, "Am", 140.0, "too fast"), _lt(6, "F#m", 124.0, "clash"), _lt(7, "Am", 0.0, "no bpm"),
            _lt(8, "Am", 124.0, "same genre", genre="house")]
    got = suggestions(ref, pool)
    assert [s.track.title for s in got] == ["same genre", "same", "relative half", "near"]
    assert got[2].ratio == 2.0 and got[3].key_reason == "near"
    assert "near" not in [s.track.title for s in suggestions(ref, pool, tolerance=1.0)]


def test_suggestions_panel_follows_selection_and_adds_to_playlist(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.resize(1500, 900)
        app.show_view("library")
        lib = app.views["library"]
        assert pump(app, 5, lambda: lib.table.total > 0)
        lib.sug_btn.click()
        assert lib.suggestions.isVisible() and ctrl.settings.suggestions_open
        ref = next(x for x in lib.all_tracks if x.title == "One More Time")
        lib.table.select([str(ref.content_id)])
        pump(app, 0.2)
        panel = lib.suggestions
        assert panel.ref.content_id == ref.content_id
        titles = [s.track.title for s in panel.items]
        assert titles and "One More Time" not in titles
        assert all(abs(s.bpm_gap) <= 6 for s in panel.items)
        assert panel.list.count() == len(panel.items)
        panel.tol.setValue(1)
        assert all(abs(s.bpm_gap) <= 1 for s in panel.items)
        assert ctrl.settings.suggest_tolerance == 1
        # playlist ouverte : « + » ajoute à la fin, « ✓ » si déjà dedans
        club = next(k for k, p in lib._by_iid.items() if p.name == "Club")
        lib._goto(club)
        assert pump(app, 4, lambda: lib.in_playlist and lib.table.total == 3)
        panel.tol.setValue(10)
        new = next(s.track for s in panel.items if lib.table.row(str(s.track.content_id)) is None)
        panel._add(new.content_id)
        assert pump(app, 6, lambda: lib.table.row(str(new.content_id)) is not None)
        # harmonic filter : BPM ± x %
        lib.set_harmonic(ref)
        n_all = lib.table.count
        lib.harm_bpm.setCurrentIndex(1)
        assert lib.table.count <= n_all
        lib._clear_harmonic()
        lib.show_suggestions(False)
        assert not lib.suggestions.isVisible() and not ctrl.settings.suggestions_open
        assert not app.errors
    finally:
        close_window(app)


def test_duplicates_tab_shows_quality_best_and_clean_versions(tmp_path, monkeypatch):
    from djsync.core.quality import AudioInfo
    from djsync.models import Candidate, TrackResult
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.duplicates_dialog import ALT, DuplicatesDialog

    from .qt_util import close_window, find, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        infos = {}

        def quality(tracks, ok):
            for i, x in enumerate(tracks):
                infos[x.content_id] = AudioInfo("aac", 256 if i == 0 else 128, 44100)
            ok({x.content_id: infos[x.content_id] for x in tracks})

        monkeypatch.setattr(ctrl, "track_quality", quality)
        clean = TrackResult(video_id="C" * 11, title="One More Time", artist="Daft Punk", duration_seconds=320,
                            result_type="song")
        monkeypatch.setattr(ctrl, "find_alternatives", lambda track, ok: ok([Candidate(clean, 95.0)]))
        app.open_diagnostic("dup")
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None)
        dlg = find(app, DuplicatesDialog)
        assert pump(app, 10, lambda: dlg.groups and dlg.current_group)
        group = dlg.current_group
        texts = [dlg._info_labels[x.content_id].text() for x in group]
        assert any("256 kbps" in s for s in texts) and any("128 kbps" in s for s in texts)
        best = dlg._best(group)
        assert best is not None and dlg.keep_index() == group.index(best)          # meilleure qualité proposée
        title_before = dlg.title_entry.text()
        assert title_before                                                          # titre propre gardé
        dlg._find_alternatives()
        assert dlg._keep.button(ALT) is not None
        dlg._keep.button(ALT).setChecked(True)
        assert dlg.download_choice().track is clean
        dlg._apply()
        assert pump(app, 2, lambda: find(app, ConfirmDialog) is not None)
        calls = []
        monkeypatch.setattr(ctrl, "replace_with_download", lambda tr, old: calls.append((tr, list(old))) or object())
        find(app, ConfirmDialog)._ok()
        assert calls and calls[0][0] is clean and len(calls[0][1]) == len(group)
        assert not app.errors
    finally:
        close_window(app)
