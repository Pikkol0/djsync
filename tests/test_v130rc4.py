"""1.3.0-rc.4 : corrections des tests KO de la rc.3 (B18, B20, B22, C31, C39) et B23, B24."""
from .test_v122 import demo, usb  # noqa: F401


# ------------------------------------------------------------------ B18 : Uniformiser, aucun bloc écrasé
def _squeezed(page):
    out = []
    for cid, blk in page.blocks.items():
        if blk.isVisible() and blk.height() < blk.sizeHint().height() - 4:
            out.append((cid, blk.height(), blk.sizeHint().height()))
    return out


def test_uniformize_blocks_are_never_squeezed(demo, monkeypatch):  # noqa: F811
    from dataclasses import replace

    from djsync.core import metadata
    from djsync.ui.uniformize_page import ScopeDialog

    from .qt_util import pump

    demo.resize(1100, 640)
    lib = demo.ctrl.library
    base = list(lib.list_tracks())
    many = [replace(base[i % len(base)], content_id=90000 + i, title=f"Son {i} (Official Video)") for i in range(40)]
    monkeypatch.setattr(lib, "list_tracks", lambda: many)
    monkeypatch.setattr(lib, "track_details", lambda cid: {})
    monkeypatch.setattr(metadata, "match", lambda *a, **k: {})
    dlg = ScopeDialog(demo, demo.ctrl)
    dlg.choice.setCurrentIndex(1)
    dlg._ok()
    assert pump(demo, 6, lambda: getattr(demo, "uniformize_page", None) is not None)
    page = demo.uniformize_page
    seen = []
    orig = page._flush_pending

    from PySide6.QtCore import QEvent, QObject

    class Watch(QObject):                       # toute taille donnée à un bloc, même un instant
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Paint and obj.height() < obj.sizeHint().height() - 4:   # ce qui est AFFICHÉ
                seen.append((obj.cid, obj.height(), obj.sizeHint().height()))
            return False

    watch = Watch()

    def spy():
        orig()
        for blk in page.blocks.values():
            blk.installEventFilter(watch)
        pump(demo, 0.05)

    page._flush_pending = spy
    page._flush_timer.timeout.disconnect()
    page._flush_timer.timeout.connect(spy)
    assert pump(demo, 20, lambda: page.scan_finished)
    page.filter.setCurrentText(page._filters["all"])
    pump(demo, 0.3)
    seen.extend(_squeezed(page))
    assert len(page.blocks) >= 3
    assert not seen, seen
    page._leaving = True
    page.close()


# ------------------------------------------------------------------ B20 : un seul lecteur avec Grille et cues
from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v130rc3 import _open_grid  # noqa: E402


def test_bottom_play_button_plays_the_grid_page_track(demo_grid):  # noqa: F811
    from djsync.audio.player import PAUSED, PLAYING

    from .qt_util import pump

    app = demo_grid
    ctrl = app.ctrl
    other = next(x for x in ctrl.library.list_tracks() if x.title != "Grid Test")
    ctrl.play_queue([other], 0)                                  # un autre son était en lecture
    assert pump(app, 6, lambda: ctrl.player.state == PLAYING)
    ctrl.player.toggle_pause()
    assert pump(app, 3, lambda: ctrl.player.state == PAUSED)
    ed = _open_grid(app)
    assert ctrl.grid_editor is ed
    ed.cursor_ms = 2000.0
    ctrl.toggle_play()                                           # bouton Lecture de la barre du bas
    assert pump(app, 6, lambda: ed._is_playing_this() and ctrl.player.state == PLAYING)
    assert pump(app, 4, lambda: ctrl.player.position() >= 1.5)   # depuis le curseur de la page
    ctrl.toggle_play()
    assert pump(app, 3, lambda: ctrl.player.state == PAUSED)
    assert ed._is_playing_this()
    ed.close()
    assert ctrl.grid_editor is None
    ctrl.toggle_play()                                           # page fermée : comportement habituel
    assert pump(app, 3, lambda: ctrl.player.state == PLAYING) and ed is not None


# ------------------------------------------------------------------ C39 : pause immédiate, test du décalage
def test_pause_cuts_the_sound_and_resumes_where_it_was_heard(tmp_path, monkeypatch):
    import time

    from djsync.audio import player as P

    from .audio_fixture import write_wav
    import numpy as np

    path = write_wav(tmp_path / "s.wav", (0.1 * np.sin(np.linspace(0, 2000, 44100 * 20))).astype("float32"))
    p = P.AudioPlayer(post=lambda f: f())
    p.latency_offset_ms = 800                             # casque Bluetooth (~1 s de retard au total)
    p.play(path, P.NowPlaying("s", "a", str(path)))
    t0 = time.time()
    while p.state != P.PLAYING and time.time() - t0 < 10:
        time.sleep(0.02)
    assert p.state == P.PLAYING
    time.sleep(1.6)
    sent = p.sent_position()
    heard = p.position()
    assert sent - heard > 0.8                             # le son entendu a ~1 s de retard sur l'envoi
    p.toggle_pause()
    assert p.state == P.PAUSED and p._device is None      # carte son arrêtée : plus rien ne sort
    assert abs(p.position() - heard) < 0.1                # on reprendra à ce qu'on a entendu…
    assert abs(p._stream.start - heard) < 0.1             # … flux rouvert à cet endroit (pas à ce qui était envoyé)
    p.toggle_pause()
    assert p.state == P.PLAYING and p._device is not None
    time.sleep(0.3)
    assert p.position() >= heard - 0.05                   # jamais en arrière
    p.close()


def test_latency_test_dialog_sets_the_offset_live(demo):  # noqa: F811
    from djsync.ui.latency_dialog import BEAT, LatencyDialog, click_track

    from .qt_util import pump

    path = click_track()
    import wave

    with wave.open(str(path)) as w:
        assert w.getframerate() == 44100 and w.getnframes() >= 44100 * 60
    saved = []
    ctrl = demo.ctrl
    ctrl.player.latency_offset_ms = 0
    dlg = LatencyDialog(demo, ctrl, 0, saved.append)
    assert pump(demo, 6, lambda: ctrl.player.state == "playing" and dlg._mine())
    dlg.slider.setValue(35)                               # 350 ms : appliqué en direct
    assert ctrl.player.latency_offset_ms == 350 and dlg.value.text() == "+350 ms"
    dlg.lane.repaint()
    dlg._save()
    assert saved == [350] and ctrl.player.state == "stopped" and BEAT == 0.5
    dlg2 = LatencyDialog(demo, ctrl, 350, saved.append)
    dlg2.slider.setValue(0)
    dlg2.close()                                          # annuler : le réglage d'avant revient
    assert ctrl.player.latency_offset_ms == 350 and saved == [350]


# ------------------------------------------------------------------ B24 / C31 : écran de démarrage
def test_native_splash_closed_before_qt_and_qt_splash_always_shown(monkeypatch):
    import inspect
    import sys
    import types

    from PySide6.QtWidgets import QApplication

    from djsync.ui import launcher, splash

    src = inspect.getsource(launcher.main)
    assert src.index("splash.close_native()") < src.index("QApplication(sys.argv")   # avant le réglage d'échelle
    closed = []
    monkeypatch.setitem(sys.modules, "pyi_splash", types.SimpleNamespace(close=lambda: closed.append(1)))
    monkeypatch.setattr(splash, "_native_closed", False)
    splash.close_native()
    splash.close_native()
    assert closed == [1]                                   # une seule fermeture
    app = QApplication.instance() or QApplication([])
    screen = splash.show(app)                              # exe Windows compris : l'écran Qt s'affiche
    try:
        assert screen is not None and screen.widget is not None and screen.widget.isVisible()
        geo, avail = screen.widget.frameGeometry(), app.primaryScreen().availableGeometry()
        assert abs(geo.center().x() - avail.center().x()) <= 2 and abs(geo.center().y() - avail.center().y()) <= 2
    finally:
        if screen is not None:
            screen.close()


# ------------------------------------------------------------------ B23 : nouvelle couleur partout, sans redémarrer
def _accent_pixels(widget):
    """Couleurs (r, g, b) des icônes des boutons d'un widget."""
    from PySide6.QtWidgets import QAbstractButton

    found = set()
    for b in widget.findChildren(QAbstractButton):
        ic = b.icon()
        if ic.isNull():
            continue
        img = ic.pixmap(32, 32).toImage()
        for x in range(0, img.width(), 2):
            for y in range(0, img.height(), 2):
                c = img.pixelColor(x, y)
                if c.alpha() > 200:
                    found.add((c.red() // 16, c.green() // 16, c.blue() // 16))
    return found


def test_new_accent_recolors_home_tools_without_restart(demo):  # noqa: F811
    from PySide6.QtGui import QColor

    from djsync.ui import theme
    from djsync.ui.palettes import PALETTES

    from .qt_util import pump

    demo.show_view("home")
    pump(demo, 0.2)
    red = QColor(PALETTES["red"])
    key = (red.red() // 16, red.green() // 16, red.blue() // 16)
    assert key not in _accent_pixels(demo.views["home"])
    demo.ctrl.settings.theme = "red"
    demo.ctrl._emit("restyle")
    pump(demo, 0.3)
    assert theme.ACCENT.upper() == PALETTES["red"].upper()
    assert demo._current == "home"
    assert key in _accent_pixels(demo.views["home"])          # Outils de l'Accueil dans la nouvelle couleur
    assert demo.player_bar is not None and demo.views["settings"] is not None


# ------------------------------------------------------------------ B22 : clé retirée sans éjecter
def test_removed_drive_one_clear_message_then_reopens(demo, monkeypatch):  # noqa: F811
    import shutil

    from djsync.ui import controller as C

    from .qt_util import pump

    ctrl = demo.ctrl
    root = ctrl.drive.root
    msgs = []
    monkeypatch.setattr(ctrl, "message", lambda kind, text: msgs.append((kind, text)))
    hidden = root.parent / (root.name + "_away")
    shutil.move(str(root), str(hidden))                       # clé arrachée
    ctrl._poll()                                              # surveillance des clés (toutes les 4 s)
    assert pump(demo, 6, lambda: ctrl.library is None)
    assert [k for k, _ in msgs] == ["warn"] and str(root) in msgs[0][1]
    # tâches lancées avant le retrait : leurs erreurs ne s'affichent plus
    ctrl._on_error(OSError("disk I/O error"))
    from sqlcipher3 import dbapi2

    ctrl._on_error(dbapi2.OperationalError("disk I/O error"))
    ctrl._on_error(FileNotFoundError(2, "No such file or directory", str(root / "Contents" / "a.m4a")))
    assert [k for k, _ in msgs] == ["warn"]
    ctrl._on_error(ValueError("something else"))             # une autre erreur reste montrée
    assert msgs[-1][0] == "error"
    shutil.move(str(hidden), str(root))                       # rebranchée
    ctrl.drives = []
    ctrl.refresh_drives(then=ctrl._auto_connect)
    assert pump(demo, 8, lambda: ctrl.library is not None)
    assert C is not None
