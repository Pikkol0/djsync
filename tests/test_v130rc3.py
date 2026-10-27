"""1.3.0-rc.3 : version au démarrage (C31), analyse après téléchargement (C32)."""
import json
from types import SimpleNamespace
import pytest

from djsync.settings import Settings
from djsync.ui.ctrl.downloads import DownloadsMixin


# ------------------------------------------------------------------ C32 : analyse après téléchargement
def test_after_download_analysis_is_on_by_default_and_migrated(tmp_path):
    assert Settings().analyze_after_download_usb and Settings().analyze_after_download_local
    old = tmp_path / "old.json"           # réglages d'une 1.3.0-rc.2 : ancienne case décochée
    old.write_text(json.dumps({"analyze_on_add": False, "settings_version": 1}), encoding="utf-8")
    s = Settings.load(old)
    assert s.analyze_after_download_usb and s.analyze_after_download_local and s.settings_version == 2
    chosen = tmp_path / "chosen.json"     # choix fait après la migration : respecté
    chosen.write_text(json.dumps({"analyze_after_download_usb": False, "settings_version": 2}), encoding="utf-8")
    s = Settings.load(chosen)
    assert not s.analyze_after_download_usb and s.analyze_after_download_local


class _Ctrl(DownloadsMixin):
    def __init__(self, local: bool, usb_on: bool = True, local_on: bool = True) -> None:
        self.library = object()
        self.is_local = local
        self.settings = SimpleNamespace(analyze_after_download_usb=usb_on, analyze_after_download_local=local_on)
        self.calls = []

    def analyze(self, ids, quiet=False):
        self.calls.append((list(ids), quiet))


def test_downloaded_track_goes_to_the_analysis_queue_per_library_setting():
    c = _Ctrl(local=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=c.library))
    assert c.calls == [([7], True)]                      # en file, sans message par son
    c = _Ctrl(local=False, usb_on=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=c.library))
    assert c.calls == []
    c = _Ctrl(local=True, usb_on=False, local_on=True)    # réglages séparés clé / PC
    c._analyse_after_download(SimpleNamespace(content_id=8, library=c.library))
    assert c.calls == [([8], True)]
    c = _Ctrl(local=True, local_on=False)
    c._analyse_after_download(SimpleNamespace(content_id=8, library=c.library))
    assert c.calls == []


def test_no_analysis_if_the_library_changed_meanwhile():
    c = _Ctrl(local=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=object()))
    c._analyse_after_download(SimpleNamespace(content_id=0, library=c.library))
    assert c.calls == []


# ------------------------------------------------------------------ C31 : version au démarrage
def test_native_splash_image_carries_the_version(tmp_path):
    from PIL import Image, ImageChops

    from djsync.ui.palettes import DEFAULT_THEME, PALETTES
    from tools.export_logos import make_splash

    plain, versioned = tmp_path / "a.png", tmp_path / "b.png"
    make_splash(plain, PALETTES[DEFAULT_THEME])
    make_splash(versioned, PALETTES[DEFAULT_THEME], "1.3.0-rc.3")
    diff = ImageChops.difference(Image.open(plain).convert("RGB"), Image.open(versioned).convert("RGB")).getbbox()
    assert diff is not None and diff[1] >= 165                # seule la ligne de version, sous « Loading… »


def test_qt_splash_shows_the_version_and_a_normal_size_logo():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from djsync import full_version
    from djsync.ui import splash

    app = QApplication.instance() or QApplication([])
    s = splash.Splash(app)
    try:
        img: QImage = s.widget.pixmap().toImage()
        # le logo (56 px, centré à partir de y=30) ne déborde plus sur le nom « DJSync » (y >= 96)
        bg = img.pixelColor(img.width() // 2 + 40, 92)
        assert bg == img.pixelColor(10, 92)
        assert full_version()
    finally:
        s.close()


# ------------------------------------------------------------------ B14 : messages d'export.pdb en anglais
def test_pdb_error_messages_are_english():
    """L'app est en anglais par défaut : aucun message d'erreur technique d'export.pdb en français."""
    import re
    from pathlib import Path

    import djsync.db.pdb as pdb_pkg

    french = re.compile(r"\b(de la|des|du|une|est|pas|inconnus?|drapeaux|clé|fichier)\b", re.I)
    for f in Path(pdb_pkg.__file__).parent.glob("*.py"):
        for m in re.finditer(r'raise \w*Error\(f?"([^"]*)"', f.read_text(encoding="utf-8")):
            assert not french.search(m.group(1)), (f.name, m.group(1))


# ------------------------------------------------------------------ C36 : bouton « Mettre à jour export.pdb »
def _demo_app(tmp_path, monkeypatch):
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.demo_fixture import make_demo_usb

    from .qt_util import make_window
    from .test_ui_smoke import FakeService
    import djsync.ui.controller as controller

    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    return make_window(Settings(), monkeypatch), usb


def test_home_offers_to_update_a_stale_export_pdb(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel, QPushButton

    from djsync.db import UsbDrive
    from djsync.i18n import t
    from djsync.ui.ctrl.library_ops import DriveSummary

    from .qt_util import close_window, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        home = app.views["home"]
        calls = []
        monkeypatch.setattr(home.ctrl, "pdb_sync_now", lambda ok=None, failed=None: calls.append((ok, failed)))
        drive = UsbDrive(root=usb, label="DEMO")
        stale = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True,
                                        pdb_state="stale", pdb_problem="1 playlist(s) missing"))
        buttons = [b for b in stale.findChildren(QPushButton) if b.text() == t("home.pdb_update")]
        assert len(buttons) == 1
        assert any("1 playlist(s) missing" in l.text() for l in stale.findChildren(QLabel))
        buttons[0].click()
        pump(app, 0.1)
        assert len(calls) == 1 and buttons[0].text() == t("home.pdb_updating") and not buttons[0].isEnabled()
        calls[0][0](None)                                     # réconciliation finie : bouton rétabli
        assert buttons[0].isEnabled() and buttons[0].text() == t("home.pdb_update")
        ok = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True, pdb_state="ok"))
        assert not [b for b in ok.findChildren(QPushButton) if b.text() == t("home.pdb_update")]
    finally:
        close_window(app)


def test_sync_now_always_refreshes_home_and_reports_what_is_left(tmp_path, monkeypatch):
    from djsync.ui.ctrl.library_ops import LibraryOpsMixin

    class Lib:
        pdb_state, pdb_problem = "stale", "1 track(s) missing"

        def pdb_catch_up(self):
            return object()

    class Ctrl(LibraryOpsMixin):
        def __init__(self):
            self.library, self.events, self.msgs = Lib(), [], []
            self.dispatcher = SimpleNamespace(submit=self._run)

        def _run(self, fn, ok, err, pool=None):
            try:
                ok(fn())
            except Exception as exc:  # noqa: BLE001
                err(exc)

        def message(self, kind, text):
            self.msgs.append(kind)

        def _emit(self, name, *a):
            self.events.append(name)

        def _on_error(self, exc):
            self.msgs.append("error")

    c = Ctrl()
    c.pdb_sync_now()
    assert c.msgs == ["warn"] and c.events == ["library"]           # écart restant : dit, Accueil redessiné
    c.library.pdb_state = "ok"
    c.msgs, c.events = [], []
    c.pdb_sync_now()
    assert c.msgs == ["ok"] and c.events == ["library"]

    def locked():
        raise OSError("cannot write export.pdb (file used by another program?)")
    c.library.pdb_catch_up = locked
    c.msgs, c.events = [], []
    failed = []
    c.pdb_sync_now(failed=failed.append)
    assert c.msgs == ["warn"] and c.events == ["library"] and failed


# ------------------------------------------------------------------ B16 / B17 : page Grille et cues
from .test_ui_v024 import demo_grid  # noqa: E402,F401


def _open_grid(app):
    from .qt_util import pump

    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert pump(app, 4, lambda: bool(ed.beats))
    return ed


def test_grid_page_player_overview_and_cursor_modes(demo_grid):  # noqa: F811
    from .qt_util import pump

    app = demo_grid
    ed = _open_grid(app)
    bar = app.player_bar
    # B17 : le lecteur montre la vue d'ensemble 3 bandes (pas la forme d'onde défilante)
    assert bar._grid_editor is ed and not bar.grid_overview.isHidden() and bar.scroll_wave.isHidden()
    bar.grid_overview.resize(400, 40)
    bar.grid_overview._go(200)                                     # milieu de la vue d'ensemble
    assert abs(ed.cursor_ms - ed.duration_ms / 2) < ed.duration_ms * 0.01
    bar.grid_overview.grab()
    # curseur volant par défaut ; case « fixe au centre » gardée dans les réglages
    assert not ed.fixed_cursor and not ed.fixed_box.isChecked()
    ed.fixed_box.setChecked(True)
    assert ed.fixed_cursor and app.ctrl.settings.grid_fixed_cursor
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    ed.grab()
    assert abs(ed._x(ed.cursor_ms) - ed.canvas.width() / 2) < 2          # curseur au milieu
    before = ed.cursor_ms
    ed.begin_scrub(400)
    ed.scrub_to(300)                                                     # le son glisse vers la gauche
    ed.end_scrub(300)
    assert ed.cursor_ms > before and abs(ed._x(ed.cursor_ms) - ed.canvas.width() / 2) < 2
    ed.pan(0.15)                                                         # molette : avance sous le curseur
    assert ed.cursor_ms > before
    ed.fixed_box.setChecked(False)
    assert not app.ctrl.settings.grid_fixed_cursor
    ed.close()
    pump(app, 0.2)
    assert bar._grid_editor is None and bar.grid_overview.isHidden()


def test_grid_page_top_strip_and_pads_fit(demo_grid):  # noqa: F811
    from PySide6.QtGui import QFont, QFontMetrics

    app = demo_grid
    ed = _open_grid(app)
    ed.canvas.resize(900, 220)
    ed.grab()
    fm = QFontMetrics(ed.canvas.font())
    assert ed._label_top >= fm.height() * 0.8 and ed._label_bottom > ed._label_top   # deux niveaux
    pad = ed.cue_panel.pads[0]
    f = QFont(pad.font())
    f.setBold(True)
    assert pad.minimumHeight() >= 2 * QFontMetrics(f).lineSpacing()                # deux lignes tiennent
    ed.close()


# ------------------------------------------------------------------ C39 : position entendue, interpolée
def test_heard_position_is_smooth_and_never_ahead(monkeypatch):
    from djsync.audio import player as P

    p = P.AudioPlayer(post=lambda f: f())
    p.state = P.PLAYING
    clock = [100.0]
    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    assert p.position() == 0.0                                   # rien envoyé : au point de départ
    # la carte son réclame un paquet de 50 ms ; 2 s déjà envoyées
    p._frames = p._cb_frames = 2 * P.RATE
    p._cb_time, p._cb_period = 100.0, 0.05
    heard = [p.position()]
    for _ in range(4):
        clock[0] += 0.01
        heard.append(p.position())
    assert heard[0] == pytest.approx(2.0 - p.output_latency(), abs=1e-6)   # retard de la carte son retiré
    steps = [b - a for a, b in zip(heard, heard[1:])]
    assert all(s == pytest.approx(0.01, abs=1e-6) for s in steps)        # avance avec l'horloge, sans sauts
    clock[0] += 5.0                                                       # plus de paquet : s'arrête
    assert p.position() <= 2.0 - p.output_latency() + 0.05 * 1.5 + 1e-6
    p.latency_offset_ms = 100                                             # réglage Bluetooth
    clock[0] = 100.0
    assert p.position() == pytest.approx(2.0 - p.output_latency() - 0.1, abs=1e-6)
    # après un seek : jamais avant le point demandé
    p._base, p._cb_frames, p._frames, p._cb_time = 10 * P.RATE, 10 * P.RATE + 2205, 10 * P.RATE + 2205, 100.0
    assert p.position() == pytest.approx(10.0)


def test_after_a_seek_the_end_of_the_old_audio_is_still_shown(monkeypatch):
    from djsync.audio import player as P

    p = P.AudioPlayer(post=lambda f: f())
    p.state = P.PLAYING
    clock = [50.0]
    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    lat = p.output_latency()
    p._frames = p._cb_frames = 30 * P.RATE
    p._cb_time, p._cb_period = 50.0, 0.05
    before = p.position()                                           # ≈ 30 s - réserve
    monkeypatch.setattr(P.AudioPlayer, "_swap", P.AudioPlayer._swap)
    fake = type("S", (), {"close": lambda self: None})
    p._stream = fake()
    p._swap(fake(), 5 * P.RATE)                                     # saut à 5 s
    clock[0] += 0.05
    assert p.position() == pytest.approx(before + 0.05, abs=1e-6)   # on entend encore l'ancien passage
    clock[0] += lat + 0.2                                           # ancienne réserve jouée
    assert p.position() == pytest.approx(5.0)
    assert p.sent_position() == pytest.approx(5.0)


# ------------------------------------------------------------------ C40 : sortir de la boucle
def test_exit_loop_keeps_playing_without_seek(demo_grid):  # noqa: F811
    app = demo_grid
    ed = _open_grid(app)
    seeks = []
    ed._player_seek = lambda ms: seeks.append(ms)
    ed.active_loop = (ed.beats[4][2], ed.beats[8][2])
    ed.exit_loop()
    assert ed.active_loop is None and seeks == [] and ed.exit_btn.isHidden()
    ed.active_loop = (ed.beats[4][2], ed.beats[8][2])
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    ed.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_0, Qt.NoModifier, "0"))     # touche 0
    assert ed.active_loop is None
    ed.close()


# ------------------------------------------------------------------ B21 : 3 bandes sans fichier audio
def test_band_wave_from_rekordbox_2ex_and_fallback():
    import numpy as np

    from djsync.analysis import anlz
    from djsync.analysis.waveform import Waveforms

    raw = bytes([10, 60, 120] * 300)
    wf = Waveforms(detail=b"", color_detail=b"", preview=b"", tiny_preview=b"", color_preview=b"",
                   band_detail=raw, band_preview=bytes(3 * 1200))
    two = anlz.build_2ex("/Contents/x.m4a", wf)
    if True:
        band = anlz.read_band_detail(two)
        assert band.rate == 150 and band.low.size == 300
        assert (int(band.low[0]), int(band.mid[0]), int(band.high[0])) == (10, 60, 120)
    fb = anlz.band_from_detail([(1.0, "#FF0000"), (0.5, "#00FF00")])
    assert fb.rate == 150 and int(fb.low[0]) == 127 and int(fb.high[0]) < int(fb.mid[0]) < int(fb.low[0])
    assert anlz.band_from_detail([]) is None and isinstance(fb.low, np.ndarray)


def test_grid_page_without_audio_file_uses_three_bands(demo_grid, monkeypatch):  # noqa: F811
    app = demo_grid
    monkeypatch.setattr(app.ctrl, "load_grid_wave", lambda track, ok: ok(None))     # fichier introuvable
    ed = _open_grid(app)
    from .qt_util import pump
    pump(app, 0.5)
    assert ed.wave is not None and ed._wave_state == "ready"                           # pas de RGB
    ed.close()


# ------------------------------------------------------------------ B22 : clé retirée
def test_removed_drive_gives_a_clear_message(tmp_path, monkeypatch):
    from djsync.ui import controller as C

    msgs, closed = [], []
    ctrl = SimpleNamespace(is_local=False, drive=SimpleNamespace(root=tmp_path / "gone"), library=object())
    ctrl.message = lambda kind, text: msgs.append((kind, text))
    ctrl.disconnect = lambda by_user=True: closed.append(by_user)
    ctrl.drive_gone = lambda: C.AppController.drive_gone(ctrl)
    ctrl._drive_removed = lambda cause=None: C.AppController._drive_removed(ctrl, cause)   # rc.4 : même message
    C.AppController._on_error(ctrl, OSError("disk I/O error"))
    assert msgs and msgs[0][0] == "warn" and "gone" in msgs[0][1] and closed == [False]


# ------------------------------------------------------------------ B18 / B19 : Uniformiser
from .test_v122 import demo, usb  # noqa: E402,F401


def test_search_results_are_two_line_cards_that_fit(demo, monkeypatch):  # noqa: F811
    from djsync.ui.uniformize_page import CandidateCard, ScopeDialog

    from .qt_util import pump

    dlg = ScopeDialog(demo, demo.ctrl)
    dlg.choice.setCurrentIndex(1)
    dlg._ok()
    assert pump(demo, 6, lambda: getattr(demo, "uniformize_page", None) is not None)
    page = demo.uniformize_page
    assert pump(demo, 10, lambda: page.scan_finished)
    assert page.scan_bar.isHidden()                                           # avancement fini : barre cachée
    page.filter.setCurrentText(page._filters["all"])
    cid = next(iter(page.blocks))
    blk = page.blocks[cid]
    cands = [{"title": f"Titre très long numéro {i} " * 3, "artists": ["Artiste"], "album": "Album", "duration": 180}
             for i in range(5)]
    blk.show_candidates(cands)
    pump(demo, 0.3)
    cards = blk.cands.findChildren(CandidateCard)
    assert len(cards) == 5
    fm = cards[0].fontMetrics()
    assert all(c.minimumHeight() >= 2 * fm.lineSpacing() for c in cards)
    assert blk.cands_lay.itemAtPosition(1, 0) is not None                     # retour à la ligne (3 + 2)
    demo.grab().save("/tmp/claude-0/-home-claude/7654d4ba-1bad-5978-9785-24ca386eb8d1/scratchpad/uni.png")
    page._leaving = True
    page.close()


# ------------------------------------------------------------------ B20 : fichier introuvable
def test_missing_file_message_depends_on_the_library(tmp_path):
    from djsync.i18n import set_language, t
    from djsync.ui.ctrl.playback import PlaybackMixin

    class C(PlaybackMixin):
        pass

    c = C()
    c.is_local, c.drive = True, None
    msg = c.missing_file_text(tmp_path / "Music" / "set" / "B.M.S.mp4")
    assert "B.M.S.mp4" in msg and "Music" in msg and "drive" not in msg.lower()
    c.is_local, c.drive = False, SimpleNamespace(root="E:\\")
    assert "E:\\" in c.missing_file_text("E:\\Contents\\a.m4a")
    try:
        set_language("fr")
        c.is_local = True
        assert "cet ordinateur" in c.missing_file_text(tmp_path / "x.mp4")
    finally:
        set_language("en")


def test_player_reports_a_missing_file_without_hardcoded_text(tmp_path):
    from djsync.audio import player as P

    events = []
    p = P.AudioPlayer(post=lambda f: f(), on_event=lambda k, v: events.append((k, v)))
    p.play(tmp_path / "nope.m4a", P.NowPlaying("t", "a", str(tmp_path / "nope.m4a")))
    assert events == [("missing", str(tmp_path / "nope.m4a"))]


def test_grid_page_banner_when_the_file_is_missing(demo_grid, monkeypatch):  # noqa: F811
    app = demo_grid
    monkeypatch.setattr(type(app.ctrl), "file_missing", lambda self, track: True)
    ed = _open_grid(app)
    assert not ed.missing.isHidden()
    called = []
    monkeypatch.setattr(app.ctrl, "play_queue", lambda *a, **k: called.append(a))
    ed._play()
    assert called == []
    ed.close()
