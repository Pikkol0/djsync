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


# ------------------------------------------------------------------ C113 : nouvelles colonnes
def test_c113_mytags_history_and_grid_marks(demo, tmp_path):
    from djsync.db import grid_marks

    lib = demo.ctrl.library
    ids = [x.content_id for x in lib.list_tracks()]
    with lib._write() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS myTag(myTag_id integer primary key, sequenceNo integer, name varchar,"
                     " attribute integer, myTag_id_parent integer)")
        conn.execute("CREATE TABLE IF NOT EXISTS myTag_content(myTag_id integer, content_id integer)")
        conn.execute("CREATE TABLE IF NOT EXISTS history(history_id integer primary key, sequenceNo integer, name varchar,"
                     " attribute integer, history_id_parent integer)")
        conn.execute("CREATE TABLE IF NOT EXISTS history_content(history_id integer, content_id integer, sequenceNo integer)")
        conn.execute("INSERT INTO myTag VALUES (1, 2, 'Warm-up', 0, 0), (2, 1, 'Peak', 0, 0)")
        conn.execute("INSERT INTO myTag_content VALUES (1, ?), (2, ?)", (ids[0], ids[0]))
        conn.execute("INSERT INTO history VALUES (1, 1, '2026-10-02', 0, 0), (2, 2, 'HISTORY 2026-11-08 (2)', 0, 0)")
        conn.execute("INSERT INTO history_content VALUES (1, ?, 1), (2, ?, 1)", (ids[0], ids[0]))
    extras = lib.track_extras(ids[:2])
    assert extras[ids[0]] == {"mytags": ["Peak", "Warm-up"], "last_played": "2026-11-08"}
    assert extras[ids[1]] == {"mytags": [], "last_played": ""}
    grid_marks.mark(lib.backup_dir, ids[0])
    assert ids[0] in grid_marks.load(lib.backup_dir)
    view = demo.views["library"]
    demo.show_view("library")
    view.reload(full=True)
    # la lecture d'avant (tables encore absentes) peut arriver après : on attend celle qui voit les My Tags
    assert pump(demo, 10, lambda: (getattr(view, "_extras", None) or {}).get(ids[0], {}).get("mytags"))
    pump(demo, 0.2)
    row = view.table.row(str(ids[0]))
    assert row is not None and "Peak" in row.values["mytags"] and row.values["last_played"] == "2026-11-08"
    assert demo.ctrl.settings.mytags_column_shown and not view.table.isColumnHidden(view.table.column_index("mytags"))
    # « One More Time » et « One More Time (Clip Officiel) » : doublon marqué, clic -> Doublons
    dup = next(r for r in view.table.all_rows() if r.values.get("dup"))
    view._cell_click(dup.iid, "dup")
    assert pump(demo, 4, lambda: type(demo.stack.currentWidget()).__name__ == "DuplicatesDialog")
    assert not demo.errors


# ------------------------------------------------------------------ C144 : couleurs
def test_c144_more_colours_grouped_by_family(demo):
    from djsync.ui.palettes import FAMILIES, PALETTES

    assert len(PALETTES) == 24 and "green" in FAMILIES["deep"] and len(FAMILIES["soft"]) == 4
    settings = demo.views["settings"]
    assert set(settings._swatches) == set(PALETTES)
    sections = [a.text() for a in settings.theme_btn.menu().actions() if a.isSeparator() and a.text()]
    assert sections == [t("theme.family_vivid"), t("theme.family_deep"), t("theme.family_soft")]


# ------------------------------------------------------------------ C149 : choix des playlists
def test_c149_picker_shows_the_checked_playlists(demo):
    from djsync.ui.dialogs import PlaylistPicker

    pls = [p for p in demo.ctrl.library.list_playlists() if p.is_editable]
    picker = PlaylistPicker(demo, demo.ctrl, "Download to", "OK", lambda ids: None, preselect=[pls[-1].playlist_id])
    assert pump(demo, 4, lambda: bool(picker._vars))
    assert picker.chip_names() == [pls[-1].name]
    pid, cb = next((p, c) for p, c in picker._vars.items() if p != pls[-1].playlist_id)
    cb.setChecked(True)
    assert sorted(picker.chip_names()) == sorted([pls[-1].name, next(p.name for p in pls if p.playlist_id == pid)])
    picker._unpick(pls[-1].playlist_id)
    picker._unpick(pid)
    pump(demo, 0.1)
    assert picker.chip_names() == []
    picker.close()


# ------------------------------------------------------------------ C169 : aide de la recherche haute qualité
def test_c169_help_panel(demo):
    hq = demo.views["hq"]
    dlg = hq.show_help()
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert t("hq.help_free_slot") in texts and t("hq.help_queue_text") in texts
    dlg.close()


# ------------------------------------------------------------------ C172 : playlists de plus de 200 titres
def test_c172_page_by_page():
    from djsync.core.urlimport import resolve_direct

    def entry(i):
        vid = f"V{i:010d}"
        return {"id": vid, "title": f"T{i}", "url": f"https://www.youtube.com/watch?v={vid}", "duration": 200,
                "channel": "C"}

    seen = []

    def extractor(url, opts):
        seen.append(opts)
        first = opts.get("playliststart", 1)
        last = opts["playlistend"]
        return {"_type": "playlist", "title": "Long", "playlist_count": 534,
                "entries": [entry(i) for i in range(first, min(last, 534) + 1)]}

    res = resolve_direct("https://www.youtube.com/playlist?list=PLx", extractor=extractor)
    assert len(res.tracks) == 200 and res.truncated and res.total == 534 and res.start == 1
    more = resolve_direct("https://www.youtube.com/playlist?list=PLx", extractor=extractor, start=401)
    assert seen[-1]["playliststart"] == 401 and len(more.tracks) == 134 and not more.truncated


def test_c172_banner_and_load_more(demo, monkeypatch):
    from djsync.models import ResolvedUrl, TrackResult, UrlKind

    view = demo.views["import"]
    demo.show_view("import")

    def tr(i):
        return TrackResult(video_id=f"V{i:010d}", title=f"T{i}", artist="A", album=None, duration_seconds=200,
                           thumbnail_url="", result_type="video")

    first = ResolvedUrl(UrlKind.YOUTUBE, "Long", [tr(i) for i in range(1, 201)], "https://youtube.com/playlist?list=PLx",
                        True, "", True, 534, 1)
    view._load_direct(first)
    assert view.more_box.isVisibleTo(view) and "534" in view.more_lbl.text()
    asked = []

    def import_more(url, start, ok, err=None):
        asked.append(start)
        ok(ResolvedUrl(UrlKind.YOUTUBE, "Long", [tr(i) for i in range(201, 401)], url, True, "", True, 534, start))

    monkeypatch.setattr(demo.ctrl, "import_more", import_more)
    view.load_more()
    assert asked == [201] and len(view.resolved.tracks) == 400 and view.more_box.isVisibleTo(view)
    assert not demo.errors


# ------------------------------------------------------------------ C178 : Accueil (maquette A) et visite guidée
def test_c178_home_actions_and_tour(demo, monkeypatch):
    from djsync.ui import tour

    home = demo.views["home"]
    demo.show_view("home")
    assert list(home.actions) == ["download", "analyse", "prepare", "uniformize"]
    # cartes des bibliothèques au-dessus des actions (maquette A)
    assert home.cards.mapTo(home, home.cards.rect().topLeft()).y() < home.actions_row.mapTo(home, home.actions_row.rect().topLeft()).y()
    home.actions["download"].click()
    assert demo.current == "search"
    s = demo.ctrl.settings
    s.tour_state = ""
    monkeypatch.setattr(tour, "OFFER_AT_START", True)
    assert tour.should_offer(s)
    dlg = tour.offer(demo)
    dlg.later_btn.click()
    assert s.tour_state == "later" and tour.should_offer(s)
    dlg = tour.offer(demo)
    dlg.start_btn.click()
    ov = demo.tour
    assert ov is not None and ov.isVisible() and demo.current == "home"
    assert not ov.hole.isNull()                                  # projecteur sur l'entrée « Accueil »
    for _i in range(len(tour.STEPS) - 1):
        ov.next()
    assert ov.next_btn.text() == t("tour.finish")
    ov.next()
    assert demo.tour is None and s.tour_state == "done" and not tour.should_offer(s)
    dlg = tour.offer(demo)
    dlg.never_btn.click()
    assert s.tour_state == "never" and not tour.should_offer(s)
    ov = tour.start(demo)                                        # Aide ▸ Visite guidée
    ov.skip()
    assert s.tour_state == "never" and demo.tour is None
    assert not demo.errors


# ------------------------------------------------------------------ B97 : navigateur YouTube réglé au démarrage
def test_b97_start_with_youtube_browser_set(tmp_path, monkeypatch):
    """Plantage au lancement (« 'AppController' object has no attribute 'jobs' ») quand un navigateur
    YouTube était choisi : la relance des refus « robot » (B66) partait avant la création de self.jobs."""
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    import djsync.ui.controller as controller

    from .demo_fixture import make_demo_usb
    from .qt_util import close_window, make_window
    from .test_ui_smoke import FakeService

    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(youtube_browser="firefox"), monkeypatch)
    try:
        c = window.ctrl
        assert c.jobs == []
        assert c.service._downloader.youtube_auth == {"cookiesfrombrowser": ("firefox",)}
        retried = []
        monkeypatch.setattr(c, "retry_bot_failures", lambda: retried.append(1))
        c._apply_output()                                    # enregistrement des Paramètres : relance gardée
        assert retried == [1]
        assert not window.errors
    finally:
        close_window(window)
