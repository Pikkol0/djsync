"""Test de fumée de l'interface : fenêtre réelle (Qt offscreen), faux service réseau, fausse clé USB.
Aucun accès réseau : la recherche/le téléchargement sont simulés."""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from djsync.core.service import MusicService  # noqa: E402
from djsync.db import UsbDrive  # noqa: E402
from djsync.models import DownloadedTrack, SearchMode, TrackResult  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .qt_util import close_window, find, make_window, pump  # noqa: E402,F401
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
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="TEST")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(), monkeypatch)
    yield window
    close_window(window)


def test_search_download_reorder_and_backup(app, usb):
    assert pump(app, 5, lambda: app.ctrl.has_library), "la clé de test doit se connecter toute seule"
    backups = usb / "DJSync_Backups"

    # recherche -> 3 lignes
    search = app.views["search"]
    search.entry.setText("artiste")
    search.run_search()
    assert pump(app, 5, lambda: search.table.count == 3), (search.info.text(), app.errors, app.status.text())

    # téléchargement vers une nouvelle playlist (popup réel)
    from djsync.ui.dialogs import PlaylistPicker

    search.table.select(search.table.displayed_iids())
    search._download()
    assert pump(app, 3, lambda: find(app, PlaylistPicker) is not None)
    picker = find(app, PlaylistPicker)
    picker._new.setText("Soirée")
    picker._create()
    assert pump(app, 5, lambda: len(picker._vars) == 3 and any(v.isChecked() for v in picker._vars.values()))
    picker._confirm()
    assert pump(app, 10, lambda: len(app.ctrl.jobs) == 3 and all(j.status == "done" for j in app.ctrl.jobs)), \
        [(j.status, j.message) for j in app.ctrl.jobs]
    assert any(backups.glob("exportLibrary-*.db")), "sauvegarde automatique avant écriture"

    # bibliothèque : ordre
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 5, lambda: any(p.name == "Soirée" for p in app.ctrl.playlists))
    playlist = next(p for p in app.ctrl.playlists if p.name == "Soirée")
    iid = f"p{playlist.playlist_id}"
    assert pump(app, 3, lambda: iid in lib._items)
    lib.nav.setCurrentItem(lib._items[iid])
    ok = pump(app, 5, lambda: lib.in_playlist and lib.table.total == 3 and lib.table.reorderable)
    assert ok, (lib.current, lib.in_playlist, lib.table.total, lib.table.reorderable)
    first = lib.table.displayed_iids()[0]
    lib.table.select([first])
    assert lib.table.move_selected(+1) and lib._dirty
    wanted = [int(i) for i in lib.table.displayed_iids()]
    lib._save_order()
    pump(app, 1.5)
    saved = [t.content_id for t in app.ctrl.library.get_playlist_tracks(playlist.playlist_id)]
    assert saved == wanted
    assert not app.errors
