"""1.3.0-rc.7 : B28 (clé retirée puis rebranchée), C63 (un seul outil Doublons), C39 (saut pendant la lecture)."""
from sqlcipher3 import dbapi2

from .test_v122 import demo, usb  # noqa: F401
from .qt_util import pump


class _Reporter:
    def __init__(self):
        self.sent = []

    def report(self, exc, where=""):
        self.sent.append(exc)


# ------------------------------------------------------------------ B28
def test_disk_io_error_on_a_replugged_drive_reopens_it_quietly(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    msgs, rep = [], _Reporter()
    monkeypatch.setattr(ctrl, "message", lambda kind, text: msgs.append((kind, text)))
    ctrl.error_reporter = rep
    old = ctrl.library
    ctrl._on_error(dbapi2.OperationalError("disk I/O error"))
    assert [k for k, _ in msgs] == ["info"] and "plugged back" in msgs[0][1]
    assert rep.sent == []                                     # pas de rapport d'erreur proposé
    assert pump(demo, 6, lambda: ctrl.library is not None and ctrl.library is not old)
    # une 2e erreur juste après (tâche lancée avant le retrait) : pas de nouvelle réouverture en boucle
    again = ctrl.library
    n = len([k for k, _ in msgs if k == "info"])
    ctrl._on_error(dbapi2.OperationalError("disk I/O error"))
    pump(demo, 1.5)
    assert ctrl.library is again and len([k for k, _ in msgs if k == "info"]) == n


def test_other_errors_are_still_shown(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    msgs = []
    monkeypatch.setattr(ctrl, "message", lambda kind, text: msgs.append((kind, text)))
    ctrl.error_reporter = _Reporter()
    ctrl._on_error(ValueError("something else"))
    ctrl._on_error(dbapi2.OperationalError("database is locked"))
    assert [k for k, _ in msgs] == ["error", "error"]


def test_watch_notices_a_dead_connection_although_the_drive_is_back(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    msgs = []
    monkeypatch.setattr(ctrl, "message", lambda kind, text: msgs.append((kind, text)))
    lib = ctrl.library
    assert lib.alive() is True                                # connexion saine
    monkeypatch.setattr(lib, "alive", lambda: False)          # retirée puis rebranchée entre deux contrôles
    ctrl._polling = False
    ctrl._poll()
    assert pump(demo, 6, lambda: any(k == "info" for k, _ in msgs))
    assert pump(demo, 6, lambda: ctrl.library is not None and ctrl.library is not lib)


def test_alive_never_blocks_a_busy_library(demo):  # noqa: F811
    lib = demo.ctrl.library
    import threading

    got = []
    with lib._lock:
        t = threading.Thread(target=lambda: got.append(lib.alive()))
        t.start()
        t.join(2)
    assert got == [None]
