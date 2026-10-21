"""V0.4.0 : la bibliothèque Rekordbox de l'ordinateur dans l'interface (aucune clé branchée)."""
from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyrekordbox")

from djsync.settings import Settings  # noqa: E402

from .qt_util import close_window, make_window, pump  # noqa: E402
from .test_local_library import DATA  # noqa: E402
from .test_ui_smoke import FakeService  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
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
    window = make_window(s, monkeypatch)
    yield window
    close_window(window)


def test_computer_library_opens_and_works(app, tmp_path):
    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)              # aucune clé : l'ordinateur, d'office
    assert ctrl.is_local and ctrl.settings.active_drive == "local"
    home = app.views["home"]
    assert pump(app, 6, lambda: home._summaries and home._summaries[0].connected)
    s = home._summaries[0]
    assert s.is_local and s.tracks == 2 and not s.has_pdb
    assert app.usb_label.text() == "This computer"
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 6, lambda: lib.table.total == 2)
    ctrl.create_playlist("Warm-up", 0)
    assert pump(app, 6, lambda: any(p.name == "Warm-up" for p in lib.playlists))
    # téléchargement simulé : rangé dans le dossier de musique choisi, ajouté à la collection
    ctrl.settings.fetch_metadata = False
    from djsync.models import TrackResult

    ctrl.enqueue([TrackResult(video_id="x" * 11, title="Titre", artist="Artiste")], [])
    assert pump(app, 10, lambda: ctrl.jobs and ctrl.jobs[0].status == "done"), [(j.status, j.message) for j in ctrl.jobs]
    assert str(tmp_path / "Music") in ctrl.jobs[0].file_path
    assert pump(app, 6, lambda: lib.table.total == 3)
    assert not app.errors
