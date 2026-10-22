"""1.2.0-rc.4 : grille des m4a (B01), contretemps (B11), version exacte et mise à jour en un clic
(C20), À propos (C19), et les petits correctifs d'interface (B05-B10, C01)."""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

FFMPEG = shutil.which("ffmpeg")


# ============================================================================ B01 : m4a
@pytest.mark.skipif(not FFMPEG, reason="FFmpeg required")
def test_m4a_gets_the_rekordbox_timeline_offset(tmp_path):
    from djsync.analysis.decode import M4A_TIMELINE_OFFSET_MS, decode, mp4_timing, timeline_lead_seconds

    wav = tmp_path / "t.wav"
    m4a = tmp_path / "t.m4a"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=2", str(wav)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", str(m4a)], check=True)
    info = mp4_timing(m4a)
    assert info["timescale"] == 44100 and info["edit_media_time"] and info["edit_media_time"] > 0
    assert timeline_lead_seconds(m4a) == pytest.approx(M4A_TIMELINE_OFFSET_MS / 1000)
    assert timeline_lead_seconds(wav) == 0.0
    d_wav, d_m4a = decode(wav), decode(m4a)
    # même son, le m4a commence 32,5 ms plus tard (silence ajouté = base de temps de Rekordbox)
    lead = int(0.0325 * d_m4a.sr)
    assert float(abs(d_m4a.samples[: lead - 50]).max()) == 0.0
    assert float(abs(d_m4a.samples[lead + 200: lead + 1200]).max()) > 0.1
    assert float(abs(d_wav.samples[200:1200]).max()) > 0.1


def test_mp4_timing_never_raises(tmp_path):
    from djsync.analysis.decode import mp4_timing

    junk = tmp_path / "junk.m4a"
    junk.write_bytes(b"\x00\x00\x00\x08moov" + os.urandom(200))
    assert mp4_timing(junk)["edit_media_time"] is None
    assert mp4_timing(tmp_path / "missing.m4a") == {"edit_media_time": None, "timescale": None, "itunsmpb_delay": None}


# ============================================================================ B11 : demi-temps
def test_shift_half_beat():
    from djsync.analysis import grid as G

    beats = [((i % 4) + 1, 12000, 1000 + i * 500) for i in range(8)]       # 120 BPM : 500 ms par temps
    moved = G.shift_half_beat(beats, 0, 10_000)
    assert 1250 in [b[2] for b in moved] and 1000 not in [b[2] for b in moved]
    twice = G.shift_half_beat(moved, G.nearest(moved, 1250), 10_000)
    assert 1500 in [b[2] for b in twice]                                    # deux demis = un temps
    assert G.shift_half_beat([], 0, 1000) == []


def test_compare_flags_half_beat_grids(monkeypatch, capsys):
    from djsync.analysis import __main__ as M

    M._summary(10, 8, 1, 7, 1, 9, 6, 5, half_n=2)
    out = capsys.readouterr().out
    assert "shifted by half a beat" in out and "2/9" in out


# ============================================================================ C20 : version exacte
def test_full_version_uses_the_build_stamp(monkeypatch):
    import djsync

    monkeypatch.setattr(djsync, "BUILD_VERSION", "1.2.0-rc.4")
    assert djsync.full_version() == "1.2.0-rc.4"
    monkeypatch.setattr(djsync, "BUILD_VERSION", "")
    assert djsync.full_version() == djsync.__version__


def _release(tag, pre, names=("DJSync.exe", "DJSync.exe.sha256", "DJSync-macOS.dmg", "DJSync-macOS.dmg.sha256",
                               "DJSync-Linux-x86_64.tar.gz", "DJSync-Linux-x86_64.tar.gz.sha256")):
    return {"tag_name": tag, "prerelease": pre, "html_url": f"https://example/{tag}",
            "assets": [{"name": n, "browser_download_url": f"https://dl/{tag}/{n}"} for n in names]}


def test_a_test_build_is_offered_the_next_test_build_with_its_checksum(monkeypatch):
    import json

    from djsync.core import updates

    rels = [_release("v1.2.0-rc.5", True), _release("v1.2.0-rc.4", True), _release("v1.1.0", False)]
    fetch = lambda url: json.dumps(rels).encode()                          # noqa: E731
    up = updates.check("1.2.0-rc.4", fetch)
    assert up.version == "1.2.0-rc.5" and up.prerelease
    assert up.checksum == up.asset + ".sha256"
    # la régression corrigée : une rc qui se croyait en « 1.2.0 » ne voyait rien
    assert updates.check("1.2.0", fetch) is None
    # canal « stable seulement » : pas de version de test
    assert updates.check("1.2.0-rc.4", fetch, include_prerelease=False) is None


# ============================================================================ C20 : installation
class _Resp:
    def __init__(self, data):
        self.data = data
        self.headers = {"content-length": str(len(data))}

    def iter_content(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]


def _update(name="DJSync.exe"):
    from djsync.core.updates import Update

    return Update("1.2.0-rc.5", "https://example/rel", True, f"https://dl/{name}", f"https://dl/{name}.sha256")


def test_download_checks_the_sha256(tmp_path):
    from djsync.core import selfupdate

    data = os.urandom(600_000)
    good = hashlib.sha256(data).hexdigest()
    seen = []
    out = selfupdate.download(_update(), tmp_path, lambda d, t: seen.append(d), opener=lambda u: _Resp(data),
                              get=lambda u: f"{good}  DJSync.exe\n".encode())
    assert out.read_bytes() == data and seen[-1] == len(data)
    with pytest.raises(selfupdate.UpdateError, match="bad_checksum"):
        selfupdate.download(_update(), tmp_path / "b", opener=lambda u: _Resp(data),
                            get=lambda u: ("0" * 64).encode())
    assert not list((tmp_path / "b").glob("*"))                            # rien d'installé, rien qui traîne
    with pytest.raises(selfupdate.UpdateError, match="no_checksum"):
        selfupdate.download(_update(), tmp_path / "c", opener=lambda u: _Resp(data), get=lambda u: b"")
    with pytest.raises(selfupdate.UpdateError, match="cancelled"):
        selfupdate.download(_update(), tmp_path / "d", cancelled=lambda: True, opener=lambda u: _Resp(data),
                            get=lambda u: good.encode())


def test_plan_per_platform(tmp_path):
    from djsync.core import selfupdate

    assert selfupdate.plan(frozen=False) is None                           # depuis les sources
    exe = tmp_path / "E" / "DJSync.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    p = selfupdate.plan(frozen=True, executable=str(tmp_path / "E/.djsync/app/DJSync.exe"), platform="win32",
                        launcher=str(exe))
    assert p.kind == "windows" and p.target == exe
    app = tmp_path / "USB" / "DJSync.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    p = selfupdate.plan(frozen=True, executable=str(app / "DJSync"), platform="darwin")
    assert p.kind == "mac" and p.target.name == "DJSync.app"
    folder = tmp_path / "L" / "DJSync"
    (folder / "_internal").mkdir(parents=True)
    p = selfupdate.plan(frozen=True, executable=str(folder / "DJSync"), platform="linux")
    assert p.kind == "linux" and p.target == folder


def test_windows_swap_script(tmp_path):
    from djsync.core import selfupdate

    exe = tmp_path / "DJSync.exe"
    exe.write_bytes(b"old")
    p = selfupdate.Plan("windows", exe)
    dl = tmp_path / "dl.exe"
    dl.write_bytes(b"new")
    staged = selfupdate.prepare(p, dl)
    assert staged.read_bytes() == b"new" and staged.parent == exe.parent
    bat = selfupdate._bat(p, staged, [111, 222])
    assert 'PID eq 111' in bat and 'PID eq 222' in bat
    assert f'move /y "{exe}" "{selfupdate.old_path(p)}"' in bat
    assert f'start "" "{exe}"' in bat
    assert bat.index("move /y") < bat.index('start ""')


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")
def test_linux_update_end_to_end(tmp_path):
    """Archive vérifiée -> dossier préparé à côté -> script : échange, réglages repris, relance."""
    from djsync.core import selfupdate

    usb = tmp_path / "usb"
    cur = usb / "DJSync"
    (cur / "_internal").mkdir(parents=True)
    (cur / "VERSION").write_text("old")
    (cur / ".djsync" / "data").mkdir(parents=True)
    (cur / ".djsync" / "data" / "settings.json").write_text("{\"language\": \"fr\"}")
    # nouvelle version : archive comme celle du workflow (dossier DJSync à la racine)
    src = tmp_path / "build" / "DJSync"
    (src / "_internal").mkdir(parents=True)
    (src / "VERSION").write_text("new")
    marker = tmp_path / "launched"
    (src / "DJSync").write_text(f"#!/bin/sh\necho ok > '{marker}'\n")
    (src / "DJSync").chmod(0o755)
    archive = tmp_path / "DJSync-Linux-x86_64.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname="DJSync")
    p = selfupdate.Plan("linux", cur)
    staged = selfupdate.prepare(p, archive)
    assert (staged / "VERSION").read_text() == "new"
    dead = subprocess.Popen(["true"])
    dead.wait()
    script = selfupdate.schedule_swap(p, staged, [dead.pid], run=False)
    subprocess.run(["/bin/sh", str(script)], check=True, timeout=60)
    assert (cur / "VERSION").read_text() == "new"
    assert (cur / ".djsync" / "data" / "settings.json").read_text() == "{\"language\": \"fr\"}"   # réglages gardés
    assert not staged.exists() and selfupdate.old_path(p).exists()          # ancienne gardée jusqu'au lancement
    selfupdate.cleanup(p)
    assert not selfupdate.old_path(p).exists()
    end = time.time() + 10
    while not marker.exists() and time.time() < end:
        time.sleep(0.1)
    assert marker.exists()                                                  # nouvelle version relancée


def test_linux_archive_with_unsafe_paths_is_refused(tmp_path):
    from djsync.core import selfupdate

    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("../outside")
        data = b"x"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    (tmp_path / "DJSync" / "_internal").mkdir(parents=True)
    with pytest.raises(selfupdate.UpdateError):
        selfupdate.prepare(selfupdate.Plan("linux", tmp_path / "DJSync"), archive)
    assert not (tmp_path / "outside").exists()


def test_cleanup_removes_leftovers(tmp_path):
    from djsync.core import selfupdate

    exe = tmp_path / "DJSync.exe"
    exe.write_bytes(b"x")
    p = selfupdate.Plan("windows", exe)
    selfupdate.old_path(p).write_bytes(b"old")
    selfupdate.staged_path(p).write_bytes(b"half")
    selfupdate.cleanup(p)
    assert exe.exists() and not selfupdate.old_path(p).exists() and not selfupdate.staged_path(p).exists()


# ============================================================================ interface
pytest.importorskip("PySide6")
pytest.importorskip("pyrekordbox")


@pytest.fixture
def env(tmp_path, monkeypatch):
    from djsync.settings import Settings

    from .test_local_library import DATA
    from .test_ui_smoke import FakeService

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.db.local_library as L
    import djsync.ui.controller as controller

    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    s = Settings()
    s.local_db_dir, s.local_music_dir = str(db_dir), str(tmp_path / "Music")
    return s, monkeypatch


def test_settings_update_card_and_offer(env):
    from djsync.core.updates import Update
    from djsync.ui.dialogs import ConfirmDialog

    from .qt_util import close_window, find, make_window, pump

    s, monkeypatch = env
    app = make_window(s, monkeypatch)
    try:
        ctrl = app.ctrl
        app.show_view("settings")
        view = app.views["settings"]
        assert view.version_lbl.text().endswith(__import__("djsync").full_version())
        assert not view.update_install_btn.isVisible()
        up = Update("9.9.9", "https://example/rel", False, "https://dl/DJSync.exe", "https://dl/DJSync.exe.sha256")
        opened = []
        ctrl.on("open_url", opened.append)
        ctrl.available_update = up
        ctrl._emit("app_update_state")
        assert view.update_install_btn.isVisible()
        view.update_install_btn.click()                       # depuis les sources : la page s'ouvre
        assert opened == ["https://example/rel"]
        # canal enregistré
        view.channel_menu.setCurrentText(view._channel_labels["stable"])
        view._save()
        assert ctrl.settings.update_channel == "stable"
        # mise à jour prête : bouton « Redémarrer », proposition de redémarrer
        ctrl.update_ready = (None, None, "9.9.9")
        ctrl._emit("app_update_state")
        ctrl._emit("app_update_ready", "9.9.9")
        assert view.update_restart_btn.isVisible()
        assert pump(app, 2, lambda: find(app, ConfirmDialog) is not None)
        find(app, ConfirmDialog).close()
        assert not app.errors
    finally:
        close_window(app)


def test_ui_fixes(env):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from djsync.i18n import set_language, t
    from djsync.ui.dialogs import PlaylistPicker

    from .qt_util import close_window, find, make_window, pump

    s, monkeypatch = env
    s.language = "fr"
    app = make_window(s, monkeypatch, size=(900, 700))
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        # B06 : traductions
        assert t("tab.import") == "Importer un lien"
        assert app.usb_label.text() == "Cet ordinateur"
        # B09 : la barre latérale se déplie et se replie à la demande, choix retenu
        before = bool(app._compact)
        app.fold_btn.click()
        assert bool(app._compact) != before
        assert ctrl.settings.sidebar_compact == ("on" if not before else "off")
        app.fold_btn.click()
        assert bool(app._compact) == before
        # B08 : un clic sur la barre d'avancement va à ce point
        bar = app.player_bar.seek
        bar.show()
        bar.resize(400, 20)
        x = bar.width() * 3 // 4
        ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(x, 10), QPointF(bar.mapToGlobal(QPoint(x, 10))),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        bar.mousePressEvent(ev)
        assert 650 <= bar.value() <= 850
        # B10 : choix de playlist avec recherche, la liste occupe la hauteur
        PlaylistPicker(app, ctrl, "Download to…", "OK", lambda ids: None)
        pick = None
        assert pump(app, 4, lambda: (find(app, PlaylistPicker) is not None and bool(find(app, PlaylistPicker)._vars)))
        pick = find(app, PlaylistPicker)
        names = [cb.text() for cb in pick._vars.values()]
        word = names[0].split()[0]
        pick._filter.setText("zzz-nothing")
        assert not any(cb.isVisible() for cb in pick._vars.values())
        pick._filter.setText(word)
        assert any(cb.isVisible() for cb in pick._vars.values())
        pick.close()
        assert not app.errors
    finally:
        set_language("en")
        close_window(app)
