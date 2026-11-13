"""1.4.2, lot 1 : C182 (reste d'A06), C67 (« Prêt pour le set ? »), C174 (mode léger, une fois par PC)."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from djsync.i18n import t  # noqa: E402

from .qt_util import pump  # noqa: E402
from .test_ui_v024 import _app  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from .qt_util import close_window

    window = _app(tmp_path, monkeypatch)
    yield window
    close_window(window)


# ------------------------------------------------------------------ C182 : volet court, onglets, menus
def test_c182_short_sidebar_and_search_tabs(demo):
    from djsync.ui.app import NAV

    assert [k for k, *_ in NAV] == ["home", "search", "library", "downloads", "diagnostic", "settings"]
    assert "feedback" not in demo._nav and demo.feedback_btn.text() == t("tab.feedback")
    assert demo._nav["downloads"].text().startswith(t("nav.downloads"))
    for key in ("search", "hq", "import"):
        demo.show_view(key)
        view = demo.views[key]
        assert view.search_tabs.buttons[key].isChecked()
        assert demo._nav["search"].isChecked() and not demo._nav["home"].isChecked()
    demo.views["import"].search_tabs.buttons["search"].click()
    assert demo.current == "search"
    demo.show_view("feedback")
    assert demo.feedback_btn.isChecked() and not any(b.isChecked() for b in demo._nav.values())
    assert not demo.errors


def test_c182_shortcuts_follow_pages(demo):
    from PySide6.QtGui import QShortcut

    keys = {sc.key().toString() for sc in demo.findChildren(QShortcut)}
    assert {f"Ctrl+{i}" for i in range(1, 10)} <= keys
    demo.go("library")
    assert demo.current == "library"
    demo.go("diagnostic")
    assert pump(demo, 3, lambda: demo._nav["diagnostic"].isChecked())


def test_c182_one_track_menu_everywhere(demo):
    from djsync.ui.track_menu import track_entries

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 5, lambda: bool(lib.table.displayed_rows()))
    x = lib.table.displayed_rows()[0].data
    labels = [e[0] for e in track_entries(lib, demo.ctrl, [x], where="player") if e]
    assert labels[0] == t("menu.track_diagnostic") and t("action.edit_metadata") in labels
    assert t("player.show_in_library") in labels
    lib.table.select([lib.table.displayed_rows()[0].iid])
    lib_labels = [e[0] for e in lib._menu([lib.table.displayed_rows()[0].iid]) if e]
    assert t("menu.track_diagnostic") in lib_labels and t("player.show_in_library") not in lib_labels
    # « Diagnostic de ce son » : onglet « Un son », ce son choisi
    from djsync.ui.one_track_page import OneTrackPage

    entry = next(e for e in track_entries(lib, demo.ctrl, [x], where="player") if e and e[0] == t("menu.track_diagnostic"))
    entry[1]()
    assert pump(demo, 4, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage)
                and demo.stack.currentWidget().track is not None)
    assert demo.stack.currentWidget().track.content_id == x.content_id
    assert demo._nav["diagnostic"].isChecked()
    assert not demo.errors


def test_c182_library_tools_menu_lists_only_list_tools(demo, monkeypatch):
    from djsync.ui.views import library_view as L

    lib = demo.views["library"]
    demo.show_view("library")
    shown = []
    monkeypatch.setattr(L, "popup_menu", lambda w, entries, pos: shown.extend(e[0] for e in entries if e))
    lib._tools_menu()
    assert t("genre.menu") + "…" in shown and t("meta.complete_all") in shown
    assert t("lib.edit_grid") not in shown and t("lib.find_duplicates") not in shown


def test_c182_drive_card_menu_and_home_todo(demo):
    labels = [e[0] for e in demo.drive_menu_entries() if e]
    assert labels[0] == t("nav.space") and t("set.button") in labels and t("eject.hint") in labels
    demo.open_space()
    assert demo.current == "settings"
    home = demo.views["home"]
    demo.show_view("home")
    assert pump(demo, 6, lambda: "missing" in demo.ctrl.diag_counts)
    pump(demo, 0.2)
    assert home.todo_row.isVisibleTo(home)
    assert t("diagtab.dup") in home.todo["dup"].text()
    home.todo["missing"].click()
    assert pump(demo, 3, lambda: type(demo.stack.currentWidget()).__name__ == "MissingFilesDialog")


def test_c182_grid_page_keeps_the_library_entry(demo):
    lib = demo.views["library"]
    demo.show_view("library")
    from PySide6.QtWidgets import QWidget

    page = QWidget()
    demo.stack.addWidget(page)
    demo._show_page(page)
    assert demo._nav["library"].isChecked()


# ------------------------------------------------------------------ C67 : « Prêt pour le set ? »
def test_c67_checks_core(tmp_path):
    from djsync.core import set_check as S

    assert S.check_filesystem("FAT32", "all").level == "ok"
    assert S.check_filesystem("exFAT", "old").level == "error"
    assert S.check_filesystem("exFAT", "recent").level == "ok"
    assert S.check_filesystem("NTFS", "recent").level == "error"
    assert S.check_filesystem("", "all").level == "skip"
    track = lambda cid, path, rate=44100, analysed=True: SimpleNamespace(   # noqa: E731
        content_id=cid, path=path, sample_rate=rate, is_analysed=analysed)
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.flac").write_bytes(b"x")
    (tmp_path / "c.wav").write_bytes(b"x")
    lib = SimpleNamespace(absolute_path=lambda x: tmp_path / x.path)
    tracks = [track(1, "a.mp3"), track(2, "b.flac"), track(3, "c.wav", 96000, False), track(4, "gone.mp3")]
    rows = {c.key: c for c in S.check_tracks(lib, tracks, "old", marks={1: SimpleNamespace(empty=False)})}
    assert rows["files"].level == "error" and rows["files"].ids == [4]
    assert rows["analysis"].ids == [3] and rows["analysis"].action == "analyse"
    assert sorted(rows["formats"].ids) == [2, 3]
    assert rows["cues"].ids == [2, 3, 4]
    assert {c.key: c for c in S.check_tracks(lib, tracks, "recent")}["formats"].level == "ok"
    old = SimpleNamespace(created=datetime.now() - timedelta(days=45))
    assert S.check_backup([old]).level == "warn" and S.check_backup([]).action == "backup"
    assert S.check_backup([SimpleNamespace(created=datetime.now())]).level == "ok"
    pl = lambda pid, n, kind=0: SimpleNamespace(playlist_id=pid, name=f"P{pid}", track_count=n,   # noqa: E731
                                                is_folder=kind == 1, is_editable=kind == 0)
    assert S.check_playlists([pl(1, 3), pl(2, 0), pl(3, 0, 1)]).ids == [2]
    assert S.check_pdb(SimpleNamespace(state="stale", detail="2 sons")).action == "pdb"
    checks = [S.Check("fs", "ok", "x"), S.Check("pdb", "warn", "y")]
    assert S.verdict(checks) == "warn"
    text = S.report(checks, "DEMO", "all")
    assert "DEMO" in text and "✓" in text and t("set.verdict_warn") in text


def test_c67_page_on_the_demo_drive(demo, monkeypatch):
    from djsync.ui.set_check_dialog import SetCheckDialog

    demo.open_set_check()
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), SetCheckDialog))
    page = demo.stack.currentWidget()
    assert pump(demo, 10, lambda: bool(page.checks))
    keys = [c.key for c in page.checks]
    assert keys == ["fs", "pdb", "files", "analysis", "formats", "cues", "playlists", "space", "backup"]
    analysis = next(c for c in page.checks if c.key == "analysis")
    assert analysis.level == "warn" and analysis.ids                       # sons de démo jamais analysés
    started = []
    monkeypatch.setattr(demo.ctrl, "analyze", lambda ids: started.append(list(ids)))
    page.rows["analysis"]["action"].click()
    assert started == [analysis.ids]
    page.players.setCurrentIndex(page._players.index("recent"))
    assert demo.ctrl.settings.set_players == "recent"
    assert "DEMO" in page.report_text()
    assert not demo.errors


# ------------------------------------------------------------------ C174 : mode léger, une fois par PC
def test_c174_offer_once_per_pc_then_a_notice(demo, monkeypatch):
    from djsync.core import machine as M

    s = demo.ctrl.settings
    weak = M.MachineInfo(2, 4.0)
    s.light_offered, s.light_prompt_off, s.light_mode = [], False, "auto"
    assert M.should_offer(s, weak)
    dlg = demo.offer_light_mode(weak)
    assert M.machine_id() in s.light_offered and not M.should_offer(s, weak)
    dlg.close()
    s.light_offered = ["autre-pc"]                         # la clé portable arrive sur un autre PC
    assert M.should_offer(s, weak)
    assert len(M.machine_id()) == 16 and M.machine_id() == M.machine_id()
    demo.light_notice(weak)
    assert demo.toast.isVisible() and weak.describe() in demo.status.text()
    assert demo.toast_action.text() == t("light.notice_settings")
