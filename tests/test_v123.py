"""1.2.3 : « Envoyer les logs » (onglet Retours) et rapports d'erreur proposés à l'utilisateur."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from djsync.core import error_reports as er
from djsync.core import feedback as fb


@pytest.fixture
def usb(tmp_path):
    from tests.demo_fixture import make_demo_usb

    return make_demo_usb(tmp_path)


def test_drive_report_and_library_zip(usb):
    report = fb.drive_report(usb)
    text = "\n".join(report)
    assert "File system" in text and "exportLibrary.db" in text and "Contents" in text
    z = fb.library_zip(usb)
    assert z is not None and z.mime == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.data)).namelist()
    assert "PIONEER/rekordbox/exportLibrary.db" in names
    assert fb.library_zip(usb, limit=10) is None            # trop gros (et pas d'export.pdb ici)
    assert fb.drive_report(None) == ["No USB drive open."] and fb.library_zip(None) is None


def test_logs_payload(usb):
    z = fb.library_zip(usb)
    p = fb.build_logs_payload("XDJ-1000 test\nmore", "a@b.c", {"version": "1.2.3"}, "log", ["File system : FAT32"],
                              "client", z)
    item = p["items"][0]
    assert item["kind"] == "logs" and item["title"] == "XDJ-1000 test" and "FAT32" in item["text"]
    files = {f["name"]: f for f in item["images"]}
    assert set(files) == {"djsync-report.txt", "rekordbox-library.zip"}
    assert base64.b64decode(files["djsync-report.txt"]["data"]).decode() == "File system : FAT32"
    assert len(json.dumps(p)) < 15 * 1024 * 1024


def _boom(cls=RuntimeError, msg="boom"):
    try:
        raise cls(msg)
    except Exception as exc:  # noqa: BLE001
        return exc


def _reporter(tmp_path, mode, sent, asked=None):
    def ask(summary, answer):
        asked.append(summary)
        answer(True)

    ctx = {"version": "1.2.3", "library": "USB", "drive_root": None, "client": "c", "log_dir": tmp_path}
    return er.ErrorReporter(tmp_path / "state.json", lambda: mode, lambda: ctx, send=sent.append,
                            ask=ask if asked is not None else None)


def test_expected_errors_are_not_reported():
    from djsync.db.errors import DriveNotFoundError, ReadOnlyError

    assert er.expected(DriveNotFoundError("x")) and er.expected(ReadOnlyError("x"))
    assert er.expected(OSError("Max retries exceeded: Name or service not known"))
    assert er.expected(fb.FeedbackError("limit"))
    assert not er.expected(RuntimeError("boom")) and not er.expected(KeyError("k"))


def test_reporter_modes_and_daily_dedupe(tmp_path, monkeypatch):
    monkeypatch.delenv("DJSYNC_ERROR_REPORTS", raising=False)
    sent, asked = [], []
    r = _reporter(tmp_path, "ask", sent, asked)
    exc = _boom()
    assert r.report(exc, wait=True)
    for th in __import__("threading").enumerate():
        if th.name == "error-report":
            th.join(10)
    assert asked == ["RuntimeError: boom"] and len(sent) == 1
    payload = sent[0]
    assert payload["items"][0]["kind"] == "crash" and "Traceback" in payload["items"][0]["text"]
    assert not r.report(exc)                                  # même problème : une fois par jour
    never = _reporter(tmp_path / "n", "never", [])
    assert not never.report(_boom())
    sent2 = []
    always = _reporter(tmp_path / "a", "always", sent2)
    for i in range(er.MAX_PER_DAY + 2):                       # signatures différentes (lignes différentes)
        exec(f"try:\n    raise ValueError({i})\nexcept ValueError as e:\n    x = e", {}, loc := {})
        always.report(loc["x"], wait=True)
    assert len(sent2) <= er.MAX_PER_DAY


def test_reports_disabled_by_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DJSYNC_ERROR_REPORTS", "off")
    sent = []
    assert not _reporter(tmp_path, "always", sent).report(_boom(), wait=True) and not sent


def test_settings_error_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    from djsync.settings import Settings

    s = Settings()
    assert s.error_reports == "ask"
    s.error_reports = "bogus"
    assert s.normalize().error_reports == "ask"


# ============================================================================ interface
pytest.importorskip("PySide6")


@pytest.fixture
def window(usb, tmp_path, monkeypatch):
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.qt_util import close_window, make_window, pump
    from tests.test_ui_v020 import FakeService

    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    w = make_window(Settings(), monkeypatch)
    assert pump(w, 6, lambda: w.ctrl.has_library)
    yield w
    close_window(w)


def test_send_logs_button(window, monkeypatch):
    from tests.qt_util import pump

    sent = []
    monkeypatch.setattr(fb, "send", lambda payload, *a, **k: sent.append(payload))
    window.show_view("feedback")
    view = window.views["feedback"]
    view.logs_note.setText("CDJ-2000NXS2 : playlist absente")
    view.send_logs()
    assert pump(window, 6, lambda: bool(sent))
    item = sent[0]["items"][0]
    assert item["kind"] == "logs" and "CDJ-2000NXS2" in item["title"]
    assert {f["name"] for f in item["images"]} == {"djsync-report.txt", "rekordbox-library.zip"}
    assert pump(window, 2, lambda: view.logs_status.text() != "") and not window.errors


def test_error_report_dialog(window, monkeypatch):
    from djsync.ui.dialogs import ErrorReportDialog
    from tests.qt_util import find, pump

    answers = []
    window._ask_error_report("RuntimeError: boom", answers.append)
    dlg = find(window, ErrorReportDialog)
    assert dlg is not None
    window._ask_error_report("second", answers.append)        # une seule fenêtre à la fois
    assert answers == [False]
    dlg.always.setChecked(True)
    dlg._send()
    assert answers == [False, True] and window.ctrl.settings.error_reports == "always"
    window._ask_error_report("third", answers.append)
    dlg = find(window, ErrorReportDialog)
    dlg.close()
    assert pump(window, 1, lambda: answers == [False, True, False])
