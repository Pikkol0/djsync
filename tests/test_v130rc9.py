"""1.3.0-rc.9 : diagnostic du retour au bureau sur Mac (B32), mesure des retards audio (B33),
journal moins bavard sur les empreintes manquantes."""
import logging
import threading

from .test_v122 import demo, usb  # noqa: F401
from .qt_util import pump


# ------------------------------------------------------------------ B32
def test_a_window_open_for_a_fraction_of_a_second_is_logged_with_its_timing(demo, caplog):  # noqa: F811
    """L'enregistrement du testeur Mac : une fenêtre s'ouvre ~0,4 s après Doublons et se referme ~0,3 s
    plus tard. Le contrôle unique de la rc.8 (à 400 ms) la ratait ; la surveillance la voit apparaître
    et disparaître, avec les délais."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QWidget

    from djsync.ui.duplicates_dialog import DuplicatesDialog

    caplog.set_level(logging.INFO, logger="djsync.ui.app")
    extra = QWidget()
    extra.setObjectName("brief")
    QLabel("Bref", extra)
    QTimer.singleShot(150, extra.show)
    QTimer.singleShot(450, extra.hide)
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)     # ouvre la page : surveillance lancée
    assert pump(demo, 2, lambda: "window gone after" in caplog.text)
    shown = next(r.getMessage() for r in caplog.records if "window shown after" in r.getMessage())
    assert "Page DuplicatesDialog" in shown and "QWidget" in shown and "name=brief" in shown
    assert "'Bref'" in shown
    gone = next(r.getMessage() for r in caplog.records if "window gone after" in r.getMessage())
    assert "visible" in gone
    extra.deleteLater()
    dup.close()
    assert not demo.errors


def test_the_page_itself_and_tooltips_are_not_reported(demo, caplog):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    caplog.set_level(logging.INFO, logger="djsync.ui.app")
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    pump(demo, 0.5)
    assert "window shown" not in caplog.text
    dup.close()


def test_watching_stops_after_its_duration(demo):  # noqa: F811
    demo.watch_windows("Test", seconds=0.2)
    timer = demo._win_watch[0]
    assert pump(demo, 1, lambda: demo._win_watch is None)
    from shiboken6 import isValid

    assert not isValid(timer) or not timer.isActive()


def test_app_state_and_main_window_state_are_logged(demo, caplog):  # noqa: F811
    """Les signaux de Qt sont branchés une fois (au premier affichage) : perte de premier plan et
    sortie du plein écran notées, avec le délai depuis la dernière page ouverte."""
    from PySide6.QtCore import Qt

    caplog.set_level(logging.INFO, logger="djsync.ui.app")
    if not getattr(demo, "_app_state_watched", False):
        demo._app_state_watched = True
        demo._watch_app_state()
    demo.watch_windows("Test", seconds=0.1)
    demo.qapp.applicationStateChanged.emit(Qt.ApplicationInactive)
    assert "App state: inactive" in caplog.text and "after opening Test" in caplog.text


def test_window_state_names():
    from PySide6.QtCore import Qt

    from djsync.ui.app import window_state_name, window_type_name

    assert window_state_name(Qt.WindowFullScreen) == "fullscreen"
    assert window_state_name(Qt.WindowNoState) == "normal"
    assert window_type_name(Qt.Tool) == "Tool"
    assert window_type_name(Qt.Dialog | Qt.WindowStaysOnTopHint) == "Dialog"


# ------------------------------------------------------------------ B33
def _player(monkeypatch, clock):
    from djsync.audio import player as P

    class _S:
        done = False

        def read(self, n):
            return b"\0" * n

    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    pl = P.AudioPlayer.__new__(P.AudioPlayer)
    pl._lock, pl._stream, pl._paused, pl._frames, pl._volume = threading.Lock(), _S(), False, 0, 1.0
    pl._dev_t0, pl._dev_frames, pl._dev_lead = None, 0, 0.0
    pl.state = P.STOPPED
    return P, pl


def test_restart_of_the_sound_card_is_not_a_delay(monkeypatch, caplog):
    """Journaux du testeur Mac : « Audio late by 145611 ms » après un arrêt de la carte son entre deux
    sons. Un appel plus d'une seconde après le précédent est un redémarrage, pas un retard."""
    clock = [100.0]
    P, pl = _player(monkeypatch, clock)
    caplog.set_level(logging.INFO, logger=P.__name__)
    n = P.RATE // 10
    for _ in range(3):
        pl._fill(n)
        clock[0] += 0.1
    clock[0] += 145.0                                           # carte son arrêtée 2 min 25
    pl._fill(n)
    clock[0] += 0.1
    pl._fill(n)
    pl.position()
    assert "Audio late" not in caplog.text


def test_pause_does_not_count_as_delay(monkeypatch, caplog):
    clock = [100.0]
    P, pl = _player(monkeypatch, clock)
    caplog.set_level(logging.INFO, logger=P.__name__)
    n = P.RATE // 10
    pl._fill(n)
    pl._paused = True
    for _ in range(5):                                          # la carte son tourne, rien n'est joué
        clock[0] += 0.3
        pl._fill(n)
    pl._paused = False
    clock[0] += 0.1
    pl._fill(n)
    pl.position()
    assert "Audio late" not in caplog.text


def test_a_real_delay_is_still_logged_with_the_worst(monkeypatch, caplog):
    clock = [100.0]
    P, pl = _player(monkeypatch, clock)
    caplog.set_level(logging.INFO, logger=P.__name__)
    n = P.RATE // 10
    for late in (0.0, 0.0, 0.18, 0.0, 0.09):                    # le blanc d'un quart de seconde
        clock[0] += 0.1 + late
        pl._fill(n)
    pl.position()
    msg = next(r.getMessage() for r in caplog.records if "Audio late" in r.getMessage())
    assert "worst since last note 180 ms" in msg


# ------------------------------------------------------------------ journal
def test_missing_fingerprints_are_counted_after_the_first_five(monkeypatch, caplog):
    from djsync.ui.ctrl import library_ops as L

    class _Lib:
        def absolute_path(self, track):
            return "apple-music:tracks:1"

    class _T:
        title = "Son"

    ops = L.LibraryOpsMixin.__new__(L.LibraryOpsMixin)
    ops.settings = type("S", (), {"ffmpeg_location": ""})()
    caplog.set_level(logging.INFO, logger=L.__name__)
    for _ in range(250):
        assert ops._fingerprint(_Lib(), _T()) is None
    lines = [r.getMessage() for r in caplog.records]
    assert sum("No fingerprint for Son:" in m for m in lines) == L.FP_FAILURES_LOGGED
    assert any("No fingerprint for 200 sounds so far" in m for m in lines)
    assert len(lines) < 12

