"""1.3.1-rc.2 : volet Suggestions qui plantait (B38), trace des plantages natifs dans le journal,
bords des colonnes de la Bibliothèque (B37) et traits entre les en-têtes (C99)."""
from __future__ import annotations

import logging

import pytest

pytest.importorskip("PySide6")

from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v130rc3 import _demo_app  # noqa: E402


# ------------------------------------------------------------------ B38
def _library_with_suggestions(app):
    from .qt_util import pump

    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)
    app.resize(1500, 900)
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 5, lambda: lib.table.total > 0)
    lib.sug_btn.click()
    assert lib.suggestions.isVisible()
    return lib


def test_suggestion_rows_have_no_parentless_nested_layout(tmp_path, monkeypatch):
    """La cause du plantage : une mise en page imbriquée créée sans parent dans chaque ligne."""
    from PySide6.QtWidgets import QLayout

    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        lib = _library_with_suggestions(app)
        ref = next(x for x in lib.all_tracks if x.title == "One More Time")
        lib.table.select([str(ref.content_id)])
        panel = lib.suggestions
        assert pump(app, 6, lambda: panel.ref is not None and panel.list.count() > 0)
        for i in range(panel.list.count()):
            row = panel.list.itemWidget(panel.list.item(i))
            lay = row.layout()
            for k in range(lay.count()):
                assert not isinstance(lay.itemAt(k), QLayout), "mise en page imbriquée dans une ligne"
                w = lay.itemAt(k).widget()
                assert w is None or w.parent() is row
        assert not app.errors
    finally:
        close_window(app)


def test_switching_tracks_fast_with_suggestions_open_does_not_crash(tmp_path, monkeypatch):
    """Ce que faisait le testeur Mac : volet ouvert, changer vite de son (Bibliothèque puis playlist)."""
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        lib = _library_with_suggestions(app)
        panel = lib.suggestions
        calls = []
        real = panel.refresh
        monkeypatch.setattr(panel, "refresh", lambda: calls.append(1) or real())
        panel._pending.timeout.disconnect()
        panel._pending.timeout.connect(panel.refresh)
        ids = [str(x.content_id) for x in lib.all_tracks]
        for _round in range(3):
            for iid in ids:
                lib.table.select([iid])
                pump(app, 0.01)
        assert pump(app, 1, lambda: panel.ref is not None and panel.list.count() == len(panel.items))
        assert len(calls) < 3 * len(ids)                             # rafraîchissements regroupés
        club = next(k for k, p in lib._by_iid.items() if p.name == "Club")
        lib._goto(club)
        assert pump(app, 4, lambda: lib.in_playlist)
        for iid in [r.iid for r in lib.table.all_rows()] * 3:
            lib.table.select([iid])
            pump(app, 0.02)
        pump(app, 0.3)
        assert not app.errors
    finally:
        close_window(app)


def test_native_crash_trace_goes_to_the_log_next_run(tmp_path, monkeypatch, caplog):
    import faulthandler

    from djsync.ui import launcher

    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path))
    from djsync.settings import settings_dir

    folder = settings_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / launcher.CRASH_FILE).write_text("Fatal Python error: Segmentation fault\n  File \"x.py\", line 1\n",
                                              encoding="utf-8")
    enabled = []
    monkeypatch.setattr(faulthandler, "enable", lambda stream, all_threads=True: enabled.append(stream))
    with caplog.at_level(logging.ERROR, logger="djsync"):
        launcher._setup_crash_trace()
    try:
        assert "Previous run crashed" in caplog.text and "Segmentation fault" in caplog.text
        assert enabled and enabled[0].name.endswith(launcher.CRASH_FILE)
        assert (folder / launcher.CRASH_FILE).read_text(encoding="utf-8") == ""      # vidé pour la session
        caplog.clear()
        enabled[0].close()
        with caplog.at_level(logging.ERROR, logger="djsync"):
            launcher._setup_crash_trace()                                            # rien de neuf : rien
        assert "Previous run crashed" not in caplog.text
    finally:
        for s in enabled:
            s.close()


# ------------------------------------------------------------------ B37 / C99
def _library_table(app, width=1400):
    from .qt_util import pump

    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)
    app.resize(width, 800)
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 5, lambda: lib.table.total > 0)
    pump(app, 0.3)
    return lib.table


def _visible_in_order(table):
    head = table.horizontalHeader()
    out = []
    for v in range(head.count()):
        i = head.logicalIndex(v)
        if not head.isSectionHidden(i):
            out.append(i)
    return out


def test_dragging_a_column_border_resizes_that_column(tmp_path, monkeypatch):
    """Colonnes par défaut : le Titre n'est plus « étiré » ; agrandir une colonne l'agrandit elle, les
    autres gardent leur largeur sauf la dernière, qui comble le reste."""
    from PySide6.QtWidgets import QHeaderView

    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        table = _library_table(app)
        head = table.horizontalHeader()
        title = table.column_index("title")
        assert head.sectionResizeMode(title) == QHeaderView.Interactive and head.stretchLastSection()
        order = _visible_in_order(table)
        last = order[-1]
        assert sum(head.sectionSize(i) for i in order) <= table.viewport().width() + 2      # pas de défilement
        for col in (title, table.column_index("artist")):
            before = {i: head.sectionSize(i) for i in order}
            head.resizeSection(col, before[col] + 40)                                       # bord glissé à droite
            pump(app, 0.1)
            assert head.sectionSize(col) == before[col] + 40
            for i in order:
                if i not in (col, last):
                    assert head.sectionSize(i) == before[i], table.columns[i].key
        saved = app.ctrl.settings.table_layouts["library"]["widths"]
        assert "title" in saved and "artist" in saved
        app.resize(1600, 800)                                                               # largeur retenue
        pump(app, 0.3)
        assert head.sectionSize(table.column_index("artist")) == before[table.column_index("artist")] + 40
        assert not app.errors
    finally:
        close_window(app)


def test_title_fills_the_space_until_resized(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        table = _library_table(app, 1200)
        head = table.horizontalHeader()
        title = table.column_index("title")
        w1 = head.sectionSize(title)
        app.resize(1600, 800)
        pump(app, 0.3)
        assert head.sectionSize(title) > w1 + 200                     # suit la fenêtre tant qu'il n'est pas réglé
        assert "title" not in app.ctrl.settings.table_layouts.get("library", {}).get("widths", {})
        assert not app.errors
    finally:
        close_window(app)


def test_header_sections_show_a_border_between_columns():
    from djsync.ui import theme

    css = theme.stylesheet()
    assert "QHeaderView::section:horizontal" in css and "border-right: 1px solid" in css


# ------------------------------------------------------------------ C75 : boucle active
def test_active_loop_written_and_read_back_in_analysis_files():
    import struct

    import numpy as np

    from djsync.analysis import anlz
    from djsync.analysis.cues import ACTIVE_LOOP_STATUS, Cue, iter_tags, read_cues, write_cues
    from djsync.analysis.waveform import compute_waveforms

    wf = compute_waveforms(np.zeros(22050 * 2, dtype=np.float32), 22050, 2.0)
    dat = anlz.build_dat("/Contents/a/b.mp3", [(1, 12800, 0)], wf)
    ext = anlz.build_ext("/Contents/a/b.mp3", wf)
    cues = [Cue(0, 1000), Cue(0, 2000, 3875, 4, active=True), Cue(1, 500, 900, 1, active=True)]
    d2, e2 = write_cues(dat, ext, cues)
    statuses = []
    for code, raw in iter_tags(d2):
        if code == "PCOB":
            i = struct.unpack(">I", raw[4:8])[0]
            while raw[i:i + 4] == b"PCPT":
                statuses.append((struct.unpack(">I", raw[i + 12:i + 16])[0], struct.unpack(">I", raw[i + 16:i + 20])[0]))
                i += struct.unpack(">I", raw[i + 8:i + 12])[0]
    assert (0, ACTIVE_LOOP_STATUS) in statuses
    assert all(st == 0 for slot, st in statuses if slot)                  # jamais sur un pad (hot cue)
    got = read_cues(d2, e2)                                                # PCO2 lu, drapeau repris de PCOB
    mem = sorted((c for c in got if not c.slot), key=lambda c: c.ms)
    assert [c.is_active_loop for c in mem] == [False, True]
    assert not any(c.is_active_loop for c in got if c.slot)


def test_active_loop_in_computer_library(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    import shutil
    from pathlib import Path

    from djsync.analysis.cues import Cue
    from djsync.db import local_library as L

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in (Path(__file__).parent / "data" / "rekordbox6").glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    lib = L.LocalRekordboxLibrary(L.LocalRekordbox(db_dir, tmp_path / "Music"), backup_root=tmp_path / "bk",
                                  owned_path=tmp_path / "owned.json").connect()
    try:
        cid = lib.list_tracks()[0].content_id
        lib.save_track_cues(cid, [Cue(0, 500), Cue(0, 4000, 6000, 4, active=True)])
        rows = sorted(lib._read("SELECT InMsec, ActiveLoop FROM djmdCue WHERE ContentID = :i", {"i": str(cid)}))
        assert [(int(a), int(b)) for a, b in rows] == [(500, 0), (4000, 1)]
        back = [c for c in lib.track_cues(cid) if not c.slot]
        assert [(c.ms, c.is_active_loop) for c in back] == [(500, False), (4000, True)]
    finally:
        lib.close()


def test_one_active_loop_per_track_and_playback_engages_it(demo_grid):  # noqa: F811
    from djsync.audio.player import PLAYING

    from .test_v130rc3 import _open_grid

    ed = _open_grid(demo_grid)
    panel = ed.cue_panel
    ed.cursor_ms = ed.beats[4][2]
    panel.add_memory_loop(4, active=True)
    ed.cursor_ms = ed.beats[20][2]
    panel.add_memory_loop(2)
    loops = sorted((c for c in panel.cues if not c.slot), key=lambda c: c.ms)
    a, b = loops
    assert a.is_active_loop and not b.is_active_loop
    panel.set_active_loop(b, True)                                          # une seule par son
    assert b.is_active_loop and not a.is_active_loop
    labels = [panel.mem_row.itemAt(i).widget().text() for i in range(panel.mem_row.count())]
    assert any("2" in x and ("active" in x or "actif" in x) for x in labels)
    assert ed.cues_dirty()
    panel.set_memory_loop(b, 0)                                             # plus une boucle : plus active
    assert not b.active
    panel.set_active_loop(a, True)
    # lecture simulée : la tête passe sur le début de la boucle active -> la boucle s'enclenche
    player = demo_grid.ctrl.player
    pos = {"s": (a.ms - 200) / 1000.0}
    ed._is_playing_this = lambda: True
    old_state, player.state = player.state, PLAYING
    try:
        player.position = lambda: pos["s"]
        player.sent_position = lambda: pos["s"]
        ed._lead_ms = 0
        ed._prev_sent_ms = None
        ed.active_loop = None
        ed._tick()
        assert ed.active_loop is None
        pos["s"] = (a.ms + 50) / 1000.0
        ed._tick()
        assert ed.active_loop == (a.ms, a.loop_ms)
        ed.exit_loop()
        pos["s"] = (a.ms + 120) / 1000.0
        ed._tick()
        assert ed.active_loop is None                                       # Exit : elle ne revient pas aussitôt
    finally:
        player.state = old_state
        del player.position, player.sent_position


# ------------------------------------------------------------------ C42 : qualité attendue
def test_expected_quality_shows_the_real_quality_first():
    from djsync.i18n import set_language
    from djsync.ui import levels

    set_language("fr")
    try:
        text, lvl = levels.expected_download("ytmusic", "mp3")
        assert text.startswith("≈ 128 kbps") and "YouTube Music" in text and "MP3 320" in text
        assert text.index("128") < text.index("320")                        # la vraie qualité d'abord
        assert lvl == levels.audio_quality(128)
        assert levels.expected_download("youtube", "m4a")[0].startswith("≈ 128 kbps")
        assert "m4a" in levels.expected_tip("mp3") and levels.expected_tip("m4a") != levels.expected_tip("mp3")
    finally:
        set_language("en")


# ------------------------------------------------------------------ C27 : espace sur l'ordinateur
def test_space_card_on_the_computer_counts_the_rekordbox_collection(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    from djsync.core import space

    from .qt_util import close_window, pump
    from .test_ui_local import app as _local_app  # noqa: F401

    fixture = _local_app.__wrapped__(tmp_path, monkeypatch)
    app = next(fixture)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library and ctrl.is_local)
        lib = ctrl.library
        import dataclasses

        real = lib.list_tracks
        monkeypatch.setattr(lib, "list_tracks", lambda: [dataclasses.replace(x, file_size=7_000_000)
                                                         for x in real()])
        expected = 7_000_000 * len(real())
        assert expected > 0
        app.show_view("home")
        app.views["home"].open_space()
        view = app.views["settings"]
        assert pump(app, 8, lambda: view.space.usage is not None)
        parts = view.space.usage.parts
        assert list(parts) == list(space.LOCAL_PARTS)
        assert parts["music"] == expected                         # la collection, pas le dossier de DJSync
        assert parts["databases"] > 0                              # master.db
        assert "databases" in view.space.usage.folders
        assert not app.errors
    finally:
        close_window(app)
        next(fixture, None)
