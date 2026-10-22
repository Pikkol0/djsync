"""1.2.1 : Retours (C18), colonnes et tri retenus (C04, C05), colonne Source (C06), choix de playlist
en arborescence (C02), recherche par champ / albums / durée (C08, C09), zoom de la grille (C03),
doublons (C11, C12), barres de progression (C21)."""
from __future__ import annotations

import io
import json

import pytest

from djsync.models import DownloadJob, TrackResult, source_from_url


# ============================================================================ C06
def test_source_from_url():
    assert source_from_url("https://music.youtube.com/watch?v=abcdefghijk") == "YouTube Music"
    assert source_from_url("https://www.youtube.com/watch?v=abcdefghijk") == "YouTube"
    assert source_from_url("https://youtu.be/abcdefghijk") == "YouTube"
    assert source_from_url("abcdefghijk") == "YouTube"
    assert source_from_url("https://soundcloud.com/artist/track") == "SoundCloud"
    assert source_from_url("") == "" and source_from_url(None) == "" and source_from_url("/Contents/x.mp3") == ""


# ============================================================================ C21
def test_job_progress_and_batch_progress():
    from djsync.ui.ctrl.downloads import DownloadsMixin

    tr = TrackResult("abcdefghijk", "T", "A")
    jobs = [DownloadJob(1, tr, status="done"), DownloadJob(2, tr, status="downloading", percent=50),
            DownloadJob(3, tr, status="queued"), DownloadJob(4, tr, status="error")]
    assert jobs[1].progress == pytest.approx(0.4) and jobs[2].progress == 0 and jobs[0].progress == 1

    class C(DownloadsMixin):
        pass

    c = C.__new__(C)
    c.jobs = jobs
    done, total, frac = c.download_progress()
    assert (done, total) == (1, 3) and frac == pytest.approx((0.4 + 0 + 1) / 3)
    c.jobs = [jobs[0]]
    assert c.download_progress() == (0, 0, 1.0)


# ============================================================================ C08 / C09
class FakeYT:
    def __init__(self):
        self.calls = []

    def search(self, query, filter=None, limit=20):
        self.calls.append(filter)
        if filter == "albums":
            return [{"browseId": "MPREb_1", "title": "Bateau Album", "artists": [{"name": "Bateau"}],
                     "type": "Album", "year": "2024", "thumbnails": [{"url": "https://img/1.jpg"}]},
                    {"title": "no id"}]
        if filter == "artists":
            return [{"browseId": "UC_bateau"}]
        if filter == "songs":
            return [{"videoId": "s0000000001", "title": "Bateau", "artists": [{"name": "Other"}], "duration": "3:00",
                     "resultType": "song"},
                    {"videoId": "s0000000002", "title": "Mer calme", "artists": [{"name": "Bateau"}],
                     "duration": "3:10", "resultType": "song"},
                    {"videoId": "s0000000003", "title": "Bateau mix 1h", "artists": [{"name": "DJ"}],
                     "duration": "1:02:00", "resultType": "song"}]
        return []

    def get_artist(self, browse_id):
        return {"songs": {"results": [{"videoId": "a0000000001", "title": "Mer calme", "artists": [{"name": "Bateau"}]}]}}

    def get_album(self, browse_id):
        return {"title": "Bateau Album", "artists": [{"name": "Bateau"}], "thumbnails": [{"url": "https://img/1.jpg"}],
                "tracks": [{"videoId": "t0000000001", "title": "Un", "artists": [{"name": "Bateau"}]},
                           {"videoId": "t0000000002", "title": "Deux", "artists": [{"name": "Bateau"}]}]}


def test_search_fields_albums_and_duration():
    from djsync.core.search import MusicSearcher
    from djsync.models import SearchMode

    yt = FakeYT()
    s = MusicSearcher(yt)
    # Titre : seulement les titres qui contiennent le mot
    titles = [r.title for r in s.search("bateau", mode=SearchMode.SONGS, field="title")]
    assert titles == ["Bateau", "Bateau mix 1h"]
    # Artiste : les sons de l'artiste « Bateau », pas ceux qui s'appellent Bateau
    arts = s.search("bateau", field="artist")
    assert [r.title for r in arts] == ["Mer calme"] and "artists" in yt.calls
    # durée maximale : le mix d'une heure disparaît
    short = s.search("bateau", mode=SearchMode.SONGS, max_seconds=10 * 60)
    assert "Bateau mix 1h" not in [r.title for r in short]
    # albums : une ligne par album, puis ses titres avec album et pochette
    albums = s.search("bateau", field="album")
    assert len(albums) == 1 and albums[0].is_album and albums[0].video_id == "MPREb_1"
    assert albums[0].album == "Album · 2024"
    tracks = s.album_tracks("MPREb_1")
    assert [t.title for t in tracks] == ["Un", "Deux"]
    assert all(t.album == "Bateau Album" and t.thumbnail_url for t in tracks)


def test_settings_migrate_artists_mode():
    from djsync.settings import Settings

    s = Settings()
    s.search_mode = "artists"
    s.normalize()
    assert s.search_field == "artist" and s.search_mode == "all"
    s.search_field = "nope"
    s.search_max_minutes = 99999
    s.normalize()
    assert s.search_field == "all" and s.search_max_minutes == 600


# ============================================================================ C18
def _png(w=2400, h=1500):
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 200)).save(out, "PNG")
    return out.getvalue()


def test_feedback_payload_and_sending(monkeypatch, tmp_path):
    from djsync.core import feedback as fb

    att = fb.shrink_image(_png(), "screen.png")
    from PIL import Image

    assert max(Image.open(io.BytesIO(att.data)).size) == fb.MAX_IMAGE_SIDE and att.name == "screen.jpg"
    with pytest.raises(fb.FeedbackError):
        fb.shrink_image(b"not an image")
    remarks = [fb.Remark("bug", "Grille décalée", "Les barres…", [att, att]), fb.Remark("idea", "", "", []),
               fb.Remark("idea", "Albums", "Chercher un album")]
    info = fb.system_info("1.2.1-rc.1", "USB")
    payload = fb.build_payload(remarks, "me@example.com", info, "log", "client-1", "fr")
    assert [i["kind"] for i in payload["items"]] == ["bug", "idea"]                # vide ignorée
    assert [im["name"] for im in payload["items"][0]["images"]] == ["1-bug-capture-1.jpg", "1-bug-capture-2.jpg"]
    with pytest.raises(fb.FeedbackError, match="empty"):
        fb.build_payload([fb.Remark()], "", info, "", "c")
    sent = []
    fb.send(payload, url="https://script/exec", post=lambda u, b: (sent.append(json.loads(b)), '{"ok": true}')[1])
    assert sent[0]["items"][1]["title"] == "Albums"
    with pytest.raises(fb.FeedbackError, match="limit"):
        fb.send(payload, url="https://x", post=lambda u, b: '{"ok": false, "error": "limit"}')
    monkeypatch.setattr(fb, "FEEDBACK_URL", "")
    monkeypatch.delenv("DJSYNC_FEEDBACK_URL", raising=False)
    with pytest.raises(fb.FeedbackError, match="not_configured"):
        fb.send(payload)
    url = fb.issue_url(remarks, info)
    assert url.startswith(fb.ISSUE_URL) and "Grille" in __import__("urllib.parse").parse.unquote_plus(url)


def test_log_is_anonymised(tmp_path, monkeypatch):
    from pathlib import Path

    from djsync.core import feedback as fb

    monkeypatch.setenv("USER", "stefanxyz")
    monkeypatch.setenv("USERNAME", "stefanxyz")
    home = str(Path.home())
    (tmp_path / "djsync.log").write_text(f"open {home}/Music/a.m4a\nuser StefanXYZ did x\n", encoding="utf-8")
    text = fb.log_tail(tmp_path)
    assert home not in text and "stefanxyz" not in text.lower() and "~/Music/a.m4a" in text


# ============================================================================ C11 : playlists d'un son
def test_playlists_of_usb(tmp_path):
    from tests.demo_fixture import make_demo_usb

    from djsync.db import RekordboxUsbLibrary, drive_from_letter

    usb = make_demo_usb(tmp_path)
    with RekordboxUsbLibrary(drive_from_letter(str(usb)), analyze=False, artwork=False) as lib:
        tracks = lib.list_tracks()
        found = lib.playlists_of([t.content_id for t in tracks])
        names = {p.playlist_id: p.name for p in lib.list_playlists()}
        assert any(found.values())
        assert all(names[pid] for pids in found.values() for pid in pids)
        assert lib.playlists_of([]) == {}


def test_playlists_of_local(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    from tests.test_local_library import local  # noqa: F401

    import shutil

    import djsync.db.local_library as L
    from tests.test_local_library import DATA

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    lib = L.LocalRekordboxLibrary(L.LocalRekordbox(db_dir, tmp_path / "M"), backup_root=tmp_path / "b",
                                  owned_path=tmp_path / "o.json").connect()
    try:
        t0 = lib.list_tracks()[0]
        pl = lib.create_playlist("Mine")
        lib.add_to_playlist(pl.playlist_id, [t0.content_id])
        assert pl.playlist_id in lib.playlists_of([t0.content_id])[t0.content_id]
    finally:
        lib.close()


# ============================================================================ interface
pytest.importorskip("PySide6")


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.demo_fixture import make_demo_usb

    from .qt_util import close_window, make_window
    from .test_ui_smoke import FakeService

    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    app = make_window(Settings(), monkeypatch)
    yield app
    close_window(app)


def test_columns_sort_and_source_are_remembered(demo_app):
    from .qt_util import pump

    app = demo_app
    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 5, lambda: lib.table.total > 0)
    table = lib.table
    assert "album" in table._user_hidden and "source" not in table._user_hidden   # défaut proposé
    table.set_column_visible("album", True)
    assert "album" not in ctrl.settings.table_layouts["library"]["hidden"]
    i = table.column_index("artist")
    table.setColumnWidth(i, 300)
    assert ctrl.settings.table_layouts["library"]["widths"]["artist"] > 200
    table.reset_layout()
    assert "album" in table._user_hidden and not table._user_widths
    # tri retenu par playlist
    table._heading_clicked(table.column_index("bpm"))
    table._heading_clicked(table.column_index("bpm"))                  # décroissant
    slot = lib._sort_slot()
    assert ctrl.settings.playlist_sorts[slot] == ["bpm", True]
    lib._fill_table()
    assert pump(app, 3, lambda: table._sort_key == "bpm" and table._sort_desc)
    assert not app.errors


def test_picker_tree_and_create_in_folder(demo_app):
    from djsync.ui.dialogs import PlaylistPicker

    from .qt_util import find, pump

    app = demo_app
    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)
    PlaylistPicker(app, ctrl, "Download to…", "OK", lambda ids: None)
    assert pump(app, 4, lambda: find(app, PlaylistPicker) is not None and bool(find(app, PlaylistPicker)._vars))
    pick = find(app, PlaylistPicker)
    folder_item = next(iter(pick._folders.values()))
    assert folder_item.text(0) == "Soirées" and folder_item.childCount() == 1        # Club dans Soirées
    pick._filter.setText("club")
    assert [cb.text().split()[0] for cb in pick._vars.values() if cb.isVisible()] == ["Club"]
    pick._filter.setText("")
    pick._tree.setCurrentItem(folder_item)
    assert "Soirées" in pick._where.text()
    pick._new.setText("Afro")
    pick._create()
    assert pump(app, 5, lambda: any(p.name == "Afro" for p in ctrl.playlists))
    afro = next(p for p in ctrl.playlists if p.name == "Afro")
    assert afro.parent_id == next(iter(pick._folders))                              # créée dans le dossier
    assert pump(app, 3, lambda: afro.playlist_id in pick._vars and pick._vars[afro.playlist_id].isChecked())
    pick.close()
    assert not app.errors


def test_feedback_tab(demo_app, monkeypatch):
    from djsync.core import feedback as fb

    from .qt_util import pump

    app = demo_app
    app.show_view("library")
    app.show_view("feedback")
    view = app.views["feedback"]
    card = view.cards[0]
    card.title.setText("Grille")
    card.text.setPlainText("décalée")
    view.capture_into(card)                                             # capture de l'onglet précédent
    assert pump(app, 3, lambda: len(card.images) == 1)
    assert app.current == "feedback"
    second = view.add_card()
    second.kind.setCurrentText(second._kinds["idea"])
    second.title.setText("Albums")
    sent = []
    monkeypatch.setattr(fb, "send", lambda payload, url=None, post=None: sent.append(payload))
    view.send()
    assert pump(app, 5, lambda: bool(sent))
    items = sent[0]["items"]
    assert [i["kind"] for i in items] == ["bug", "idea"] and items[0]["images"][0]["name"].startswith("1-bug-capture")
    assert sent[0]["client"] == app.ctrl.settings.feedback_id and sent[0]["info"]["version"]
    assert pump(app, 3, lambda: len(view.cards) == 1 and not view.cards[0].title.text())   # formulaire vidé
    # sans script : le formulaire GitHub s'ouvre
    opened = []
    app.ctrl.on("open_url", opened.append)

    def refuse(payload, url=None, post=None):
        raise fb.FeedbackError("not_configured")

    monkeypatch.setattr(fb, "send", refuse)
    view.cards[0].title.setText("Encore")
    view.send()
    assert pump(app, 5, lambda: bool(opened)) and opened[0].startswith(fb.ISSUE_URL)
    assert not app.errors


def test_grid_zoom_and_activity_card(demo_app):
    from djsync.ui.grid_editor import VIEW_CHOICES, GridEditor

    from .qt_util import pump

    app = demo_app
    ctrl = app.ctrl
    assert pump(app, 6, lambda: ctrl.has_library)
    track = ctrl.library.list_tracks()[0]
    if True:
        ed = GridEditor(app, ctrl, track)
        ed.view_s = 8
        ed.zoom(-1)
        assert ed.view_s == 4 and ed.view_menu.currentText() == "4 s"
        ed.zoom(+5)
        assert ed.view_s == VIEW_CHOICES[-1]
        ed.close()
    # carte « Activité » : un téléchargement en cours suffit à l'afficher
    tr = TrackResult("abcdefghijk", "T", "A")
    ctrl.jobs.append(DownloadJob(99, tr, status="downloading", percent=30))
    ctrl._emit("downloads")
    assert app.an_box.isVisible() and app.dl_bar.isVisible() and not app.an_bar.isVisible()
    ctrl.jobs[-1].status = "done"
    ctrl._emit("downloads")
    assert not app.an_box.isVisible()
    assert not app.errors
