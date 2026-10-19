"""Test de fumée de l'interface : fenêtre réelle, faux service réseau, fausse clé USB.

Ignoré s'il n'y a pas d'écran (Linux : lancer avec `xvfb-run -a pytest`). Sur Windows il
ouvre brièvement une fenêtre. Aucun accès réseau : la recherche/le téléchargement sont simulés.
"""
from __future__ import annotations

import shutil
import time
import wave
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")
pytest.importorskip("PIL")

from djsync.core.service import MusicService  # noqa: E402
from djsync.db import UsbDrive  # noqa: E402
from djsync.models import DownloadedTrack, SearchMode, TrackResult  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .test_usb_library import usb  # noqa: E402,F401  (fixture)


class FakeService(MusicService):
    def search(self, query, limit=20, mode=SearchMode.ALL, exclude=None):
        return self.annotate([
            TrackResult(video_id=f"id{i:09d}", title=f"Titre {i}", artist="Artiste", duration_seconds=180,
                        result_type="song" if i % 2 else "video", views=None if i % 2 else 1000 * i)
            for i in range(1, 4)
        ])

    def fetch_views(self, video_id):
        return 4242

    def download(self, track, dest_dir, on_progress=None, tag=True):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{track.artist} - {track.title}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
            w.writeframes(b"\0\0" * 800)
        return DownloadedTrack(track, str(path))


@pytest.fixture
def app(usb, tmp_path, monkeypatch):
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="TEST")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    from djsync.ui.app import DJSyncApp

    try:
        window = DJSyncApp(Settings())
    except tk.TclError as exc:
        pytest.skip(f"pas d'écran disponible : {exc}")
    errors = []
    window.report_callback_exception = lambda *a: errors.append(a[1])
    window.errors = errors
    yield window
    window.ctrl.shutdown()
    window.destroy()


def pump(app, seconds=1.0, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        if until and until():
            return True
        time.sleep(0.01)
    return bool(until and until())


def test_search_download_reorder_and_backup(app, usb):
    assert pump(app, 5, lambda: app.ctrl.has_library), "la clé de test doit se connecter toute seule"
    backups = usb / "DJSync_Backups"

    # recherche -> 3 lignes
    search = app.views["search"]
    search.entry.insert(0, "artiste")
    search.run_search()
    assert pump(app, 5, lambda: search.table.count == 3)

    # téléchargement vers une nouvelle playlist (popup réel)
    search.table.select(search.table.displayed_iids())
    search._download()
    from djsync.ui.dialogs import PlaylistPicker

    def find(root):
        for w in root.winfo_children():
            if isinstance(w, PlaylistPicker):
                return w
            hit = find(w)
            if hit:
                return hit

    assert pump(app, 3, lambda: find(app) is not None)
    picker = find(app)
    picker._new.insert(0, "Soirée")
    picker._create()
    assert pump(app, 5, lambda: len(picker._vars) == 3 and any(v.get() for v in picker._vars.values()))
    picker._confirm()
    assert pump(app, 10, lambda: len(app.ctrl.jobs) == 3 and all(j.status == "done" for j in app.ctrl.jobs)), \
        [(j.status, j.message) for j in app.ctrl.jobs]
    assert any(backups.glob("exportLibrary-*.db")), "sauvegarde automatique avant écriture"

    # bibliothèque : ordre
    app.show("library")
    lib = app.views["library"]
    assert pump(app, 5, lambda: any(p.name == "Soirée" for p in app.ctrl.playlists))
    playlist = next(p for p in app.ctrl.playlists if p.name == "Soirée")
    assert pump(app, 3, lambda: lib.nav.exists(f"p{playlist.playlist_id}"))
    lib.nav.selection_set(f"p{playlist.playlist_id}")
    ok = pump(app, 5, lambda: lib.in_playlist and lib.table.total == 3 and lib.table.reorderable)
    assert ok, (lib.current, lib.in_playlist, lib.table.total, lib.table.reorderable, [(j.playlist_ids, j.status) for j in app.ctrl.jobs])
    first = lib.table.displayed_iids()[0]
    lib.table.select([first])
    assert lib.table.move_selected(+1) and lib._dirty
    wanted = [int(i) for i in lib.table.displayed_iids()]
    lib._save_order()
    pump(app, 1.5)
    saved = [t.content_id for t in app.ctrl.library.get_playlist_tracks(playlist.playlist_id)]
    assert saved == wanted
    assert not app.errors
