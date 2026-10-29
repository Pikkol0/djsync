"""1.4.0 : zoom de l'interface au clavier et à la molette (C102), colonne « Playlists » (C103)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401
from .test_v130rc3 import _open_grid  # noqa: E402


# ------------------------------------------------------------------ C102
def _wheel(widget, dy, ctrl=True):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(widget.width() / 2, widget.height() / 2)
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy), Qt.NoButton,
                     Qt.ControlModifier if ctrl else Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_zoom_shortcuts_wheel_and_badge(demo):  # noqa: F811
    from djsync.ui import theme

    from .qt_util import pump

    keys = demo.zoom_keys
    texts = [x[0] for x in keys.shortcuts]
    assert len(texts) == len(set(texts)) and {"Ctrl+=", "Ctrl+-", "Ctrl+0"} <= set(texts)
    assert keys.step(1) == 110 and keys.step(1) == 120
    assert keys.badge.isVisible() and keys.badge.text() == "120 %"
    assert demo.ctrl.settings.zoom == 100                       # appliqué après une courte pause
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 120)
    assert abs(theme.zoom() - 1.2) < 1e-6
    # Ctrl + molette sur une page ordinaire : zoom de l'interface
    lib = demo.views["library"]
    demo.show_view("library")
    _wheel(lib.table.viewport(), -120)
    assert keys.pending == 110
    _wheel(lib.table.viewport(), 120, ctrl=False)              # molette seule : défilement, pas de zoom
    assert keys.pending == 110
    assert keys.step(0) == 100
    for _ in range(20):
        keys.step(1)
    assert keys.pending == 200                                  # bornes
    for _ in range(30):
        keys.step(-1)
    assert keys.pending == 80
    keys.step(0)
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 100)


def test_ctrl_wheel_on_the_waveform_keeps_zooming_the_waveform(demo_grid):  # noqa: F811
    app = demo_grid
    ed = _open_grid(app)
    keys = app.zoom_keys
    before = ed.view_s
    _wheel(ed.canvas, 120)
    assert keys.pending is None and ed.view_s != before        # la forme d'onde zoome, pas l'interface
    ed.close()


def test_settings_have_buttons_not_a_slider(demo):  # noqa: F811
    from PySide6.QtWidgets import QSlider

    from .qt_util import pump

    demo.show_view("settings")
    view = demo.views["settings"]
    assert not view.findChildren(QSlider) or all(s.objectName() != "zoom" for s in view.findChildren(QSlider))
    assert not hasattr(view, "zoom")
    view._zoom_step(1)
    assert view.zoom_val.text() == "110 %"
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 110)
    view._zoom_step(0)
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 100)


# ------------------------------------------------------------------ C103
def test_playlists_column_shows_where_each_track_is(demo):  # noqa: F811
    from .qt_util import pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 5, lambda: lib.table.total > 0)
    table = lib.table
    col = table.column_index("playlists")
    assert not table.isColumnHidden(col)                        # affichée par défaut
    assert pump(demo, 5, lambda: getattr(lib, "_member", None) is not None)
    pump(demo, 0.3)
    member = lib._member
    club = next(p for p in lib.playlists if p.name == "Club")
    inside = next(cid for cid, pids in member.items() if club.playlist_id in pids)
    row = table.row(str(inside))
    assert "Club" in row.values["playlists"] and "Club" in row.values["playlists__tip"]
    outside = next((x.content_id for x in lib.all_tracks if not member.get(x.content_id)), None)
    if outside is not None:
        assert table.row(str(outside)).values["playlists"] == "—"
    # la recherche trouve les sons par nom de playlist
    table.set_filter("club")
    assert str(inside) in [r.iid for r in table.all_rows()] or table.count >= 1
    table.set_filter("")
    # clic droit : ouvrir la playlist
    table.select([str(inside)])
    entries = [e for e in lib._menu([str(inside)]) if e]
    opener = next(e for e in entries if "Club" in e[0])
    opener[1]()
    assert lib.in_playlist and lib.playlist.playlist_id == club.playlist_id
    # ajouter un son à une playlist : la colonne suit
    other = next(x for x in lib.all_tracks if club.playlist_id not in member.get(x.content_id, []))
    demo.ctrl.add_to_playlists([other.content_id], [club.playlist_id])
    assert pump(demo, 6, lambda: club.playlist_id in (getattr(lib, "_member", {}) or {}).get(other.content_id, []))
    assert not demo.errors


# ------------------------------------------------------------------ C86 : Deezer
_DZ_PLAYLIST = {"id": 1, "title": "Warm-up Deezer", "nb_tracks": 3, "tracks": {"data": [
    {"title": "One More Time", "duration": 320, "artist": {"name": "Daft Punk"}, "album": {"title": "Discovery"}},
    {"title": "Umbrella", "duration": 275, "artist": {"name": "Rihanna"}, "album": {"title": "GGGB"}}],
    "next": "https://api.deezer.com/playlist/1/tracks?index=2"}}
_DZ_PAGE = {"data": [{"title": "Désaccordé", "duration": 200, "artist": {"name": "Vald"}, "album": {"title": "X"}}]}


class _Resp:
    def __init__(self, data, url=""):
        self._data, self.url = data, url

    def json(self):
        return self._data


class _Http:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, timeout=0, allow_redirects=True):
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                return value if isinstance(value, _Resp) else _Resp(value, url)
        return _Resp({"error": {"type": "DataException", "message": "no data", "code": 800}}, url)


def test_deezer_links_recognised_and_listed_as_a_source():
    from djsync.core.urlimport import SOURCES, classify_url
    from djsync.models import UrlKind

    for u in ("https://www.deezer.com/fr/playlist/908622995", "deezer.com/album/302127", "https://deezer.page.link/abc",
              "https://link.deezer.com/s/30ABC", "https://www.deezer.com/track/3135556"):
        assert classify_url(u) == UrlKind.DEEZER, u
    assert "deezer" in {s.key for s in SOURCES}


def test_deezer_playlist_read_with_pages_and_private_message():
    from djsync.core import deezer as D

    http = _Http({"/playlist/1/tracks": _DZ_PAGE, "api.deezer.com/playlist/1": _DZ_PLAYLIST})
    pl = D.fetch_deezer("https://www.deezer.com/fr/playlist/1", session=http)
    assert pl.name == "Warm-up Deezer" and [t.title for t in pl.tracks] == ["One More Time", "Umbrella", "Désaccordé"]
    assert pl.tracks[0].artists == ("Daft Punk",) and pl.tracks[0].duration_seconds == 320 and not pl.truncated
    # lien court suivi
    short = _Http({"deezer.page.link": _Resp({}, "https://www.deezer.com/playlist/1"),
                   "/playlist/1/tracks": _DZ_PAGE, "api.deezer.com/playlist/1": _DZ_PLAYLIST})
    assert D.fetch_deezer("https://deezer.page.link/xyz", session=short).name == "Warm-up Deezer"
    # privée ou introuvable
    with pytest.raises(D.DeezerError) as e:
        D.fetch_deezer("https://www.deezer.com/playlist/999", session=_Http({}))
    assert e.value.private


def test_deezer_import_uses_the_spotify_matching_and_says_make_it_public(demo, monkeypatch):  # noqa: F811
    from djsync.core import deezer as D
    from djsync.i18n import t

    from .qt_util import pump

    got, errs = [], []
    monkeypatch.setattr(demo.ctrl.service, "fetch_deezer", lambda url: D.parse_deezer("playlist", _DZ_PLAYLIST))
    demo.ctrl.import_url("https://www.deezer.com/playlist/1", lambda kind, data: got.append((kind, data)), errs.append)
    assert pump(demo, 4, lambda: got or errs)
    assert got and got[0][0] == "spotify" and got[0][1].name == "Warm-up Deezer"

    def private(_url):
        raise D.DeezerError("no data", private=True)

    monkeypatch.setattr(demo.ctrl.service, "fetch_deezer", private)
    demo.ctrl.import_url("https://www.deezer.com/playlist/2", lambda *a: None, errs.append)
    assert pump(demo, 4, lambda: errs)
    assert str(errs[-1]) == t("error.deezer_private")


# ------------------------------------------------------------------ C65 : mode léger
def test_light_mode_choice_and_machine_detection(monkeypatch):
    from djsync.core import machine as M
    from djsync.settings import Settings

    s = Settings()
    assert s.light_mode == "auto"
    weak, strong = M.MachineInfo(2, 8.0), M.MachineInfo(8, 4.0)
    assert weak.modest and strong.modest                          # 2 cœurs, ou 4 Go : modeste
    assert not M.MachineInfo(4, 8.0).modest and not M.MachineInfo(8, None).modest
    assert M.light_active(s, weak) and not M.light_active(s, M.MachineInfo(8, 16.0))
    s.light_mode = "off"
    assert not M.light_active(s, weak) and not M.should_offer(s, weak)
    s.light_mode = "on"
    assert M.light_active(s, M.MachineInfo(16, 64.0))
    s.light_mode, s.light_prompt_off = "auto", False
    assert M.should_offer(s, weak)
    s.light_prompt_off = True
    assert not M.should_offer(s, weak)


def test_light_mode_effects(demo_grid, monkeypatch):  # noqa: F811
    from djsync.core import machine as M

    from .qt_util import pump

    app = demo_grid
    monkeypatch.setattr(M, "_INFO", M.MachineInfo(2, 4.0))
    ed = _open_grid(app)
    ed.canvas.paint_ms = 1.0
    assert min(ed._frame_interval() for _ in range(40)) >= M.LIGHT_FRAME_MS        # 30 images/s au plus
    # analyse en arrière-plan : un son à la fois
    from djsync.ui.ctrl.library_ops import AnalysisQueue

    q = AnalysisQueue()
    q.add([1, 2, 3, 4, 5, 6, 7], False)
    assert q.take(1) == [1] and len(q.take()) == AnalysisQueue.BATCH
    ed.close()
    pump(app, 0.1)


def test_light_mode_offer_at_start(demo, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QPushButton

    from djsync.core import machine as M
    from djsync.i18n import t

    from .qt_util import pump

    s = demo.ctrl.settings
    btn = lambda dlg, key: next(b for b in dlg.findChildren(QPushButton) if b.text() == t(key))  # noqa: E731
    dlg = demo.offer_light_mode(M.MachineInfo(2, 4.0))
    assert pump(demo, 1, dlg.isVisible)
    dlg.never_box.setChecked(True)
    btn(dlg, "light.keep").click()
    assert s.light_mode == "auto" and s.light_prompt_off
    dlg = demo.offer_light_mode(M.MachineInfo(2, 4.0))
    btn(dlg, "light.off").click()
    assert s.light_mode == "off"
