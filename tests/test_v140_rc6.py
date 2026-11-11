"""1.4.0-rc.6 : retours de tests de la rc.5 (B85, B94, C160, C180)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


def _wav(path: Path) -> Path:
    from .audio_fixture import song, write_wav

    path.parent.mkdir(parents=True, exist_ok=True)
    return write_wav(path, song(120, 0.0, 4.0, ["C"], [False]))


# ------------------------------------------------------------------ B85 : barre stable (hystérésis)
def _bar():
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    app = QApplication.instance() or QApplication([])
    from djsync.ui.icons import qicon
    from djsync.ui.widgets import FitBar

    holder = QWidget()
    holder.resize(4200, 60)
    bar = FitBar(holder)
    main = [QPushButton(f"Main button {i}") for i in range(3)]
    side = [QPushButton(f"Secondary {i}") for i in range(3)]
    for b in main + side:
        b.setIcon(qicon("plus", 16, "#ffffff"))
    for b in main:
        bar.add(b)
    bar.add_stretch()
    for b in side:
        bar.add(b, secondary=True)
    holder.show()

    def width(w):
        bar.resize(w, 40)
        for _ in range(5):
            app.processEvents()
        return bar.level

    return bar, side, width, holder


def test_b85_hysteresis_no_flip_flop_at_the_threshold():
    from djsync.ui import theme

    bar, side, width, holder = _bar()
    width(4000)
    full = bar._need(0)
    assert width(full - 1) == 1                      # plus assez : réduit tout de suite
    assert width(full + 2) == 1                      # juste assez : reste en icônes (marge)
    assert width(full - 1) == 1 and width(full + 2) == 1
    assert width(full + theme.px(bar.MARGIN)) == 0   # avec la marge : textes revenus
    assert side[0].text() == "Secondary 0"
    holder.close()


def test_b85_settled_bar_is_never_touched_again():
    """Plus de boucle de mise en page : une fois le palier choisi, plus aucune modification des boutons."""
    from PySide6.QtWidgets import QApplication

    bar, side, width, holder = _bar()
    for w in (4000, 900, 300, 900, 4000, 600):
        width(w)
    before = bar.applies
    for _ in range(30):
        QApplication.instance().processEvents()
    assert bar.applies == before
    holder.close()


@pytest.mark.parametrize("zoom", [100, 150])
def test_b85_repeated_resizes_do_not_oscillate(demo, zoom):  # noqa: F811
    lib = demo.views["library"]
    try:
        demo.ctrl.settings.zoom = zoom
        demo.restyle()
        demo.show_view("library")
        editable = next((p for p in lib.playlists if p.is_editable and not p.is_folder), None)
        if editable is not None:
            lib._goto(f"p{editable.playlist_id}")
        bar = lib.bar
        for _round in range(3):
            for width in (1280, 1024, 900, 1024, 1280):
                demo.resize(width, 800)
                pump(demo, 0.05)
        for width in (1280, 1024, 900):
            demo.resize(width, 800)
            pump(demo, 0.3)
            before, level = bar.applies, bar.level
            pump(demo, 0.5)                                # rien ne bouge plus tout seul
            assert bar.applies == before and bar.level == level, (width, zoom)
            shown = [w for w, *_r in bar._items if w.isVisibleTo(bar)]
            for w in shown:                                # jamais de texte coupé
                assert w.width() >= w.sizeHint().width() - 1, (width, zoom, w.text() if hasattr(w, "text") else "")
    finally:
        demo.ctrl.settings.zoom = 100
        demo.restyle()


# ------------------------------------------------------------------ B94 : volet replié borné
@pytest.mark.parametrize("zoom", [80, 100, 150])
def test_b94_collapsed_sidebar_never_cuts_a_ring(demo, zoom):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.app import SIDEBAR_COMPACT
    from djsync.ui.mini_ring import RING_PX

    try:
        demo.ctrl.settings.zoom = zoom
        demo.ctrl.settings.sidebar_compact = "on"
        demo.restyle()
        pump(demo, 0.2)
        side = demo.sidebar
        assert side.width() >= SIDEBAR_COMPACT                     # jamais plus étroit qu'à 100 %
        m = side.layout().contentsMargins()
        inner = side.width() - m.left() - m.right()
        for ring, box in ((demo.usb_ring, demo.usb_box), (demo.an_ring, demo.an_box)):
            assert ring.width() >= RING_PX and ring.width() >= theme.px(RING_PX) - 1
            cm = box.layout().contentsMargins()
            assert ring.width() + cm.left() + cm.right() <= inner, (zoom, ring.width(), inner)
        for b in demo._nav.values():
            assert b.width() >= b.iconSize().width() + 4, (zoom, b.width())
    finally:
        demo.ctrl.settings.zoom = 100
        demo.ctrl.settings.sidebar_compact = "auto"
        demo.restyle()


# ------------------------------------------------------------------ C160 : l'œil du dossier surveillé
def test_c160_watched_import_shows_the_eye(demo, tmp_path):  # noqa: F811
    from djsync.core import watched
    from djsync.i18n import t

    watched.use_store(tmp_path / "watched.json")
    try:
        ctrl, lib = demo.ctrl, demo.views["library"]
        src = _wav(tmp_path.parent / (tmp_path.name + "_watch") / "DJSync imported" / "Artist - Bought.wav")
        assert ctrl.import_files([str(src)], quiet=True, playlist_name=t("watch.playlist"),
                                 watched_from=str(src.parent.parent))
        assert pump(demo, 10, lambda: any(x.title == "Bought" for x in ctrl.library.list_tracks()))
        pump(demo, 0.5)
        track = next(x for x in ctrl.library.list_tracks() if x.title == "Bought")
        values = lib._source_values(track)
        assert values.get("source__icon") == "watch"
        assert pump(demo, 5, lambda: any(lib._is_watch_playlist(p) for p in lib.playlists))
        pl = next(p for p in lib.playlists if lib._is_watch_playlist(p))
        it = lib._items[f"p{pl.playlist_id}"]
        assert not it.icon(0).isNull() and it.toolTip(0) == t("watch.empty_title")
    finally:
        watched.use_store(None)


def test_c160_lookup_by_name_when_the_size_is_unknown(tmp_path):
    from types import SimpleNamespace

    from djsync.core import watched

    watched.use_store(tmp_path / "w.json")
    try:
        watched.record([("Song.wav", 1000)], "C:/Achats", "2026-11-06")
        assert watched.lookup_track(SimpleNamespace(path="/x/Song.wav", file_size=0))["folder"] == "C:/Achats"
        assert watched.lookup_track(SimpleNamespace(path="/x/Song.wav", file_size=1200)) is not None   # tags réécrits
        watched.record([("Song.wav", 2000)], "D:/Autre", "2026-11-07")
        assert watched.lookup_name("song.wav") is None                     # deux entrées : pas de devinette
        assert watched.lookup_track(SimpleNamespace(path="/x/Song.wav", file_size=2000))["folder"] == "D:/Autre"
    finally:
        watched.use_store(None)


def test_c160_watch_playlist_recognised_in_every_language(demo):  # noqa: F811
    from djsync.i18n import en, fr
    from djsync.models import PlaylistInfo

    lib = demo.views["library"]

    def pl(name):
        return PlaylistInfo(playlist_id=1, name=name, parent_id=0, kind=0, sequence=0, track_count=0)

    for name in (en.STRINGS["watch.playlist"], fr.STRINGS["watch.playlist"], fr.STRINGS["watch.playlist_old"]):
        assert lib._is_watch_playlist(pl(name)), name
    assert not lib._is_watch_playlist(pl("Party"))


def test_c160_other_language_playlist_is_reused(demo):  # noqa: F811
    from djsync.i18n import fr

    ctrl = demo.ctrl
    made = ctrl.library.create_playlist(fr.STRINGS["watch.playlist"])
    assert ctrl._watch_playlist(ctrl.library, "Watched folder") == made.playlist_id


def test_c160_icons_checked_by_the_packaged_self_test(tmp_path):
    import json

    from djsync import selftest

    out = tmp_path / "report.json"
    selftest.run(str(out))
    check = json.loads(out.read_text("utf-8"))["checks"]["icons"]
    assert check["ok"] and check["value"]["count"] > 40


# ------------------------------------------------------------------ C180 : recalculer la qualité supposée
def test_c180_force_measures_again(tmp_path, monkeypatch):
    from djsync.analysis import spectrum

    spectrum.use_store(tmp_path / "q.json")
    try:
        f = tmp_path / "a.flac"
        f.write_bytes(b"x" * 100)
        calls = []
        monkeypatch.setattr(spectrum, "measure", lambda p, *a, **k: calls.append(p) or (16000 if len(calls) == 1 else 21000))
        assert spectrum.measure_and_remember(f) == 16000
        assert spectrum.measure_and_remember(f) == 16000 and len(calls) == 1          # déjà connue
        assert spectrum.measure_and_remember(f, force=True) == 21000 and len(calls) == 2
        assert spectrum.known(f) == 21000
        monkeypatch.setattr(spectrum, "measure", lambda *a, **k: None)
        assert spectrum.measure_and_remember(f, force=True) == 21000                  # mesure ratée : gardée
    finally:
        spectrum.use_store(None)


def test_c180_batched_save_then_flush(tmp_path):
    import json

    from djsync.analysis import spectrum

    store = tmp_path / "q.json"
    spectrum.use_store(store)
    try:
        f = tmp_path / "b.mp3"
        f.write_bytes(b"y" * 50)
        spectrum.remember(f, 16000, save=False)
        assert not store.exists() and spectrum.known(f) == 16000
        spectrum.flush()
        assert list(json.loads(store.read_text("utf-8")).values()) == [16000]
    finally:
        spectrum.use_store(None)


def test_c180_recompute_in_background_without_full_analysis(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.analysis import spectrum

    spectrum.use_store(tmp_path / "q.json")
    try:
        ctrl = demo.ctrl
        measured = []
        monkeypatch.setattr(spectrum, "measure", lambda p, *a, **k: measured.append(p) or 16000)
        monkeypatch.setattr(ctrl, "analyse_tracks", lambda *a, **k: pytest.fail("full analysis started"),
                            raising=False)
        for x in ctrl.library.list_tracks():
            spectrum.remember(ctrl.library.absolute_path(x), 20000)
        changed, progress, result = [], [], []
        ctrl.on("quality_changed", lambda: changed.append(True))
        assert ctrl.measure_quality(None, result.append, lambda i, n: progress.append((i, n)), force=True)
        assert not ctrl.measure_quality(None, result.append, force=True)               # une seule à la fois
        assert pump(demo, 20, lambda: bool(result))
        existing = [x for x in ctrl.library.list_tracks() if ctrl.library.absolute_path(x).exists()]
        assert len(measured) == len(existing) and changed and not ctrl.quality_running
        if existing:
            assert progress and progress[-1][0] == progress[-1][1]
            assert spectrum.known(ctrl.library.absolute_path(existing[0])) == 16000
    finally:
        spectrum.use_store(None)


def test_c180_stop(demo, monkeypatch):  # noqa: F811
    import threading

    from djsync.analysis import spectrum

    ctrl = demo.ctrl
    gate = threading.Event()
    measured = []

    def slow(p, *a, **k):
        measured.append(p)
        gate.wait(5)
        return None

    monkeypatch.setattr(spectrum, "measure", slow)
    monkeypatch.setattr(ctrl.library.__class__, "absolute_path", lambda self, x: Path(__file__), raising=False)
    tracks = ctrl.library.list_tracks() * 5
    result = []
    assert ctrl.measure_quality(tracks, result.append, force=True)
    assert pump(demo, 5, lambda: bool(measured))
    ctrl.stop_quality()
    gate.set()
    assert pump(demo, 10, lambda: bool(result))
    assert len(measured) < len(tracks) and not ctrl.quality_running


def test_c180_menu_and_diagnostic_button(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import en, fr, t

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 5, lambda: bool(lib.table.displayed_rows()))
    rows = lib.table.displayed_rows()
    monkeypatch.setattr(lib, "_selected_tracks", lambda: [rows[0].data])
    entries = [e for e in lib._menu([rows[0].iid]) if e]
    assert any(e[0] == t("quality.recompute_sel", n=1) for e in entries)
    for key in ("quality.recompute_sel", "quality.recompute_all", "quality.recompute_all_tip",
                "quality.recompute_stop", "quality.busy", "watch.source_tip_old"):
        assert en.STRINGS[key] and fr.STRINGS[key] and en.STRINGS[key] != fr.STRINGS[key]
