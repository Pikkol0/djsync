"""1.2.2 : modifier les infos d'un son (S04), Uniformiser (C14, S01-S06), playlists par genre (C07, S07-S09)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from djsync.core import genre_playlists as gp
from djsync.core import uniformize as uni
from djsync.db.base import KEEP
from djsync.models import LibraryTrack


def track(cid=1, title="", artist="", album="", source="https://music.youtube.com/watch?v=abcdefghijk"):
    return LibraryTrack(cid, title, artist, album, 0, "", 180.0, 0, None, source, False)


# ============================================================================ règles de titre
@pytest.mark.parametrize("title, artist, expected", [
    ("Dr. Dre - Still D.R.E. (Lyrics) ft. Snoop Dogg", "Lyrics Channel", ("Still D.R.E.", ["Snoop Dogg"], "Dr. Dre")),
    ("Jul - Tchikita (Son Officiel)", "Jul", ("Tchikita", [], "Jul")),
    ("Ninho - Lettre à une femme (Vidéo officielle)", "Ninho", ("Lettre à une femme", [], "Ninho")),
    ("Blinding Lights (Official Video)", "The Weeknd", ("Blinding Lights", [], "")),
])
def test_clean_title(title, artist, expected):
    assert uni.clean_title(title, artist) == expected


def test_versions_are_kept_in_title():
    title, feats, head = uni.clean_title("One More Time (Radio Edit) [Official Video]", "Daft Punk")
    assert "Radio Edit" in title and "Official" not in title


def test_artist_helpers():
    assert uni.split_artists("Booba feat. Damso & Gims") == ["Booba", "Damso", "Gims"]
    assert uni.join_artists(["Booba", "Damso", "booba"]) == "Booba, Damso"
    assert uni.clean_artist("DaftPunkVEVO") == "DaftPunk" or uni.looks_like_channel("DaftPunkVEVO")


# ============================================================================ propositions
def test_propose_sure_deezer_replaces_artists_and_fills_empty_fields():
    x = track(title="Still D.R.E. (Lyrics) ft. Snoop Dogg", artist="Dr. Dre")
    dz = {"title": "Still D.R.E.", "artists": ["Dr. Dre", "Snoop Dogg"], "album": "2001", "year": 1999,
          "genre": "Rap/Hip Hop", "cover": "https://img/c.jpg", "score": 96, "sure": True}
    p = uni.propose(x, {"album": "", "year": 0, "genre": "", "artwork_path": ""}, dz, owned=True)
    vals = p.values()
    assert p.confidence == "sure"
    assert vals["title"] == "Still D.R.E." and vals["artist"] == "Dr. Dre, Snoop Dogg"
    assert vals["year"] == 1999 and vals["genre"] == "Rap/Hip Hop" and vals["artwork"] == "https://img/c.jpg"


def test_propose_keeps_existing_values_and_unowned_is_unchecked():
    x = track(title="Umbrella (Official Video)", artist="Rihanna", source="")
    dz = {"title": "Umbrella", "artists": ["Rihanna", "JAY-Z"], "album": "Good Girl Gone Bad", "year": 2007,
          "genre": "Pop", "cover": "https://img/u.jpg", "score": 95, "sure": True}
    p = uni.propose(x, {"album": "Mon album", "year": 2008, "genre": "R&B", "artwork_path": "x.jpg"}, dz, owned=False)
    fields = {c.field for c in p.changes}
    assert "album" not in fields and "year" not in fields and "genre" not in fields and "artwork" not in fields
    assert p.changes and not any(c.checked for c in p.changes)          # pas téléchargé par DJSync : décoché
    assert p.values() == {} and p.values(only_checked=False)


def test_propose_doubtful_is_unchecked_and_clean_is_empty():
    x = track(title="Song (Official Video)", artist="Someone")
    p = uni.propose(x, {}, {"title": "Other", "artists": ["X"], "score": 50, "sure": False})
    assert p.confidence == "doubtful" and not p.values()
    clean = uni.propose(track(title="Umbrella", artist="Rihanna"), {}, {})
    assert clean.empty


def test_review_store_persists_and_resets_on_change(tmp_path):
    path = tmp_path / "u" / "r.json"
    s = uni.ReviewStore(path)
    a = track(1, "A (Official Video)", "X")
    s.set(a, "validated", {"title": "A"})
    s.save()
    s2 = uni.ReviewStore(path)
    assert s2.state(a) == "validated" and s2.values(a) == {"title": "A"} and s2.validated() == [1]
    changed = track(1, "A modifié", "X")
    assert s2.state(changed) == ""                                       # modifié ailleurs : repart à revoir
    s2.mark_applied(track(1, "A", "X"))
    assert s2.state(track(1, "A", "X")) == "applied"


# ============================================================================ bibliothèque clé
def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def usb(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db._key import get_default_key
    from tests.demo_fixture import make_demo_usb

    root = make_demo_usb(tmp_path)
    conn = sqlcipher.connect(str(root / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("CREATE TABLE genre(genre_id integer primary key, name varchar)")
    conn.commit()
    conn.close()
    return root


def open_usb(root):
    from djsync.db import RekordboxUsbLibrary, drive_from_letter

    return RekordboxUsbLibrary(drive_from_letter(str(root)), analyze=False, artwork=False)


def test_edit_track_metadata_usb(usb):
    with open_usb(usb) as lib:
        t = next(x for x in lib.list_tracks() if x.title == "Umbrella")
        after = lib.edit_track_metadata(t.content_id, title="Umbrella", artist="Rihanna, JAY-Z", album="GGGB",
                                        year=2007, genre="Pop", artwork=_png())
        assert after.artist == "Rihanna, JAY-Z" and after.album == "GGGB"
        d = lib.track_details(t.content_id)
        assert d["year"] == 2007 and d["genre"] == "Pop" and d["artwork_path"]
        assert lib.artwork_file(after) is not None
        assert lib.track_genres() == {t.content_id: "Pop"}
        # KEEP : pochette inchangée ; None : retirée ; "" / 0 : effacés
        lib.edit_track_metadata(t.content_id, genre="", year=0)
        d = lib.track_details(t.content_id)
        assert d["genre"] == "" and not d["year"] and d["artwork_path"]
        lib.edit_track_metadata(t.content_id, artwork=None)
        assert not lib.track_details(t.content_id)["artwork_path"]
        assert lib.edit_track_metadata(t.content_id, artwork=KEEP).content_id == t.content_id
    files = list((usb / "Contents").rglob("*.wav"))
    assert files and all(f.stat().st_size > 0 for f in files)                 # fichiers audio intacts


# ============================================================================ playlists par genre
def test_genre_default_groups_and_new_genres():
    genres = {1: "Rap", 2: "Rap", 3: "Rap", 4: "House", 5: "Pop"}
    groups = gp.default_groups(genres, min_tracks=3, others_name="Others")
    assert [g["name"] for g in groups] == ["Rap", "Others"] and groups[1]["genres"] == ["House", "Pop"]
    cfg = {"groups": [{"genres": ["rap"]}]}
    assert gp.merge_new_genres(cfg, genres) == ["House", "Pop"]


def test_genre_sync_and_disable(usb):
    with open_usb(usb) as lib:
        tracks = {x.title: x for x in lib.list_tracks()}
        for title in ("Mon Survet", "Désaccordé", "Kalash Hyperpop"):
            lib.edit_track_metadata(tracks[title].content_id, genre="Rap français")
        for title in ("One More Time", "Pump It Up"):
            lib.edit_track_metadata(tracks[title].content_id, genre="House")
        before = {p.playlist_id for p in lib.list_playlists()}
        cfg = gp.default_config()
        assert gp.sync(lib, cfg).created == 0                                  # désactivé par défaut : rien
        cfg["enabled"] = True
        cfg["groups"] = [{"name": "Rap", "genres": ["Rap français", "Rap/Hip Hop"], "enabled": True},
                         {"name": "House", "genres": ["House"], "enabled": True},
                         {"name": "Vide", "genres": ["Jazz"], "enabled": True},
                         {"name": "Off", "genres": ["House"], "enabled": False}]
        rep = gp.sync(lib, cfg)
        assert rep.created == 2 and rep.added == 5
        pls = {p.playlist_id: p for p in lib.list_playlists()}
        names = {p.name for p in pls.values()}
        assert {"DJSync", "Genres", "Rap", "House"} <= names and "Vide" not in names and "Off" not in names
        rap = cfg["groups"][0]["playlist_id"]
        assert pls[pls[rap].parent_id].name == "Genres"
        assert {x.title for x in lib.get_playlist_tracks(rap)} == {"Mon Survet", "Désaccordé", "Kalash Hyperpop"}
        # un son ajouté à la main reste ; un son qui change de genre sort
        lib.add_to_playlist(rap, [tracks["Umbrella"].content_id])
        lib.edit_track_metadata(tracks["Kalash Hyperpop"].content_id, genre="House")
        rep = gp.sync(lib, cfg)
        rap_titles = {x.title for x in lib.get_playlist_tracks(rap)}
        assert "Umbrella" in rap_titles and "Kalash Hyperpop" not in rap_titles and rep.removed == 1
        # déplacée et renommée : toujours tenue à jour
        lib.rename_playlist(rap, "Mon rap")
        lib.edit_track_metadata(tracks["Freestyle Funk"].content_id, genre="Rap/Hip Hop")
        gp.sync(lib, cfg)
        assert "Freestyle Funk" in {x.title for x in lib.get_playlist_tracks(rap)}
        # supprimée par l'utilisateur : pas recréée, groupe décoché
        house = cfg["groups"][1]["playlist_id"]
        lib.delete_playlist(house)
        rep = gp.sync(lib, cfg)
        assert rep.disabled == ["House"] and not cfg["groups"][1]["enabled"] and rep.created == 0
        # désactiver : supprime les playlists DJSync et les dossiers vides, jamais les autres
        assert gp.disable(lib, cfg) == 1
        after = {p.playlist_id for p in lib.list_playlists()}
        assert after == before


def test_settings_keep_genre_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    from djsync.settings import Settings

    s = Settings()
    s.genre_playlists["usb:X"] = {"enabled": True, "groups": []}
    s.save()
    assert Settings.load().genre_playlists["usb:X"]["enabled"] is True


# ============================================================================ interface
qt = pytest.importorskip("PySide6")


@pytest.fixture
def demo(usb, tmp_path, monkeypatch):
    from djsync.core import metadata
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.qt_util import make_window, pump
    from tests.test_ui_v020 import FakeService

    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    def fake_match(title, artist, duration=0, cleaned=False):
        if title == "Umbrella":
            return {"title": "Umbrella", "artists": ["Rihanna", "JAY-Z"], "album": "Good Girl Gone Bad",
                    "year": 2007, "genre": "Pop", "cover": "", "score": 97, "sure": True}
        return {}

    monkeypatch.setattr(metadata, "match", fake_match)
    monkeypatch.setattr(metadata, "cover_candidates", lambda *a, **k: [])
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(), monkeypatch)
    assert pump(window, 6, lambda: window.ctrl.has_library)
    yield window
    from tests.qt_util import close_window

    close_window(window)


def test_track_info_dialog_saves_all_fields(demo):
    from djsync.ui.track_info_dialog import TrackInfoDialog
    from tests.qt_util import find, pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    x = next(t for t in lib.all_tracks if t.title == "Mon Survet")
    dlg = TrackInfoDialog(demo, demo.ctrl, x)
    assert pump(demo, 3, lambda: dlg._details != {})
    dlg.artist_e.setText("Jok'Air, Guest")
    dlg.album_e.setText("Album test")
    dlg.year_e.setValue(2019)
    dlg.genre_e.setText("Rap français")
    dlg._artwork = _png()
    assert set(dlg.values()) == {"artist", "album", "year", "genre", "artwork"}
    dlg._ok()
    assert pump(demo, 4, lambda: any(t.artist == "Jok'Air, Guest" for t in lib.all_tracks))
    d = demo.ctrl.library.track_details(x.content_id)
    assert d["genre"] == "Rap français" and d["year"] == 2019 and d["artwork_path"]
    assert find(demo, TrackInfoDialog) is None and not demo.errors


def test_uniformize_page_validate_then_save(demo):
    """1.3.0 (C25) : deux lignes Actuellement / Après, validation un par un, le suivant prend la place."""
    from tests.qt_util import pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    demo.ctrl._emit("open_uniformize", list(lib.all_tracks), "Toute la clé")
    page = demo.uniformize_page
    assert page is not None and pump(demo, 10, lambda: len(page.props) == 10)
    assert pump(demo, 4, lambda: page.scan_finished) and page.blocks
    umbrella = next(cid for cid, x in page.tracks.items() if x.title == "Umbrella")
    clip = next(cid for cid, x in page.tracks.items() if x.title == "One More Time (Clip Officiel)")
    assert list(page.blocks)[0] == umbrella                                   # sûrs (Deezer) d'abord
    # sons pas téléchargés par DJSync (démo) : proposition remplie mais incertaine (orange, S06)
    b = page.blocks[clip]
    assert page.state(clip) == "todo" and b.edits["title"].text() == "One More Time" and "title" in b.uncertain
    assert page.blocks[umbrella].values()["artist"] == "Rihanna, JAY-Z"
    # modifier sur place puis « ↺ »
    b.edits["album"].setText("Discovery")
    b._edited("album")
    assert b.values()["album"] == "Discovery"
    b._revert("album")
    assert "album" not in b.values()
    page.make_current(umbrella)
    page.validate(umbrella)
    assert umbrella not in page.blocks and page._current is not None           # le suivant prend la place
    page.validate(clip)
    assert page.state(clip) == "validated" and page.state(umbrella) == "validated"
    page.undo()                                                                # Ctrl+Z : revient à revoir
    assert page.state(clip) == "todo" and clip in page.blocks
    page.validate(clip)
    # progression gardée : une nouvelle page retrouve les validations
    assert set(demo.ctrl.review_store().validated()) == {clip, umbrella}
    page._save()
    assert pump(demo, 6, lambda: page.state(umbrella) == "applied")
    titles = {t.title: t for t in demo.ctrl.library.list_tracks()}
    assert "One More Time (Clip Officiel)" not in titles and titles["Umbrella"].artist == "Rihanna, JAY-Z"
    assert demo.ctrl.library.track_details(umbrella)["genre"] == "Pop"
    page._leaving = True
    page.close()
    assert pump(demo, 2, lambda: demo.uniformize_page is None) and not demo.errors


def test_uniformize_from_home_and_search_differently(demo, monkeypatch):
    """1.3.0 (C25) : tuile de l'Accueil (portée au choix), « Chercher autrement », pochette."""
    from djsync.core import metadata
    from djsync.ui.uniformize_page import ScopeDialog
    from tests.qt_util import pump

    monkeypatch.setattr(metadata, "search_candidates", lambda text, duration=0, limit=5: [
        {"id": 42, "title": "Ma Version", "artists": ["Quelqu'un"], "album": "Album X", "duration": 200, "score": 95}])
    monkeypatch.setattr(metadata, "details_for", lambda tid, score=100.0: {
        "title": "Ma Version", "artists": ["Quelqu'un", "Invité"], "album": "Album X", "year": 2001, "genre": "House",
        "score": 100, "sure": True, "id": tid})
    demo.show_view("home")
    dlg = ScopeDialog(demo, demo.ctrl)
    dlg.choice.setCurrentIndex(1)                                             # toute la bibliothèque
    dlg._ok()
    assert pump(demo, 6, lambda: getattr(demo, "uniformize_page", None) is not None)
    page = demo.uniformize_page
    assert pump(demo, 10, lambda: page.scan_finished)
    page.filter.setCurrentText(page._filters["all"])
    cid = next(c for c, x in page.tracks.items() if x.title == "Mon Survet")
    assert pump(demo, 2, lambda: cid in page.blocks)
    page.search(cid, "ma version")
    b = page.blocks[cid]
    assert pump(demo, 4, lambda: page.blocks[cid].edits["title"].text() == "Ma Version")
    b = page.blocks[cid]
    assert b.values()["artist"] == "Quelqu'un, Invité" and b.cands.isVisible() is not None
    b._cover_file(_png())
    assert isinstance(b.values()["artwork"], bytes)
    b._cover_remove()
    assert "artwork" not in b.values() or b.values()["artwork"] is None
    page.validate(cid)
    assert page.state(cid) == "validated"
    page._leaving = True
    page.close()
    assert pump(demo, 2, lambda: demo.uniformize_page is None) and not demo.errors


def test_genre_dialog_enable_and_turn_off(demo):
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.genre_dialog import GenrePlaylistsDialog
    from tests.qt_util import find, pump

    lib = demo.ctrl.library
    for x in lib.list_tracks():
        if x.title in ("Mon Survet", "Désaccordé", "Kalash Hyperpop"):
            lib.edit_track_metadata(x.content_id, genre="Rap français")
    dlg = GenrePlaylistsDialog(demo, demo.ctrl)
    assert pump(demo, 3, lambda: len(dlg.rows) == 1)
    assert dlg.rows[0]["name"].text() == "Rap français" and "3" in dlg.rows[0]["count"].text()
    assert not dlg.enabled.isChecked()                                     # désactivé par défaut
    dlg.enabled.setChecked(True)
    dlg.rows[0]["name"].setText("Rap FR auto")
    dlg._apply()
    assert pump(demo, 4, lambda: any(p.name == "Rap FR auto" for p in lib.list_playlists()))
    assert pump(demo, 4, lambda: demo.ctrl.genre_config().get("enabled"))
    cfg = demo.ctrl.genre_config()
    assert cfg["enabled"] and cfg["groups"][0]["playlist_id"]
    dlg = GenrePlaylistsDialog(demo, demo.ctrl)
    assert pump(demo, 3, lambda: len(dlg.rows) == 1)
    dlg.enabled.setChecked(False)
    dlg._apply()
    confirm = find(demo, ConfirmDialog)
    assert confirm is not None
    confirm._ok()
    assert pump(demo, 4, lambda: not any(p.name in ("Rap FR auto", "Genres", "DJSync") for p in lib.list_playlists()))
    assert pump(demo, 4, lambda: not demo.ctrl.genre_config()["enabled"]) and not demo.errors


# ============================================================================ C17 : voix off (outil vidéo)
def test_narration_schedule_and_spoken_text():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import narrate

    assert narrate.spoken({"key": "x", "text": "BPM × 2 (export.pdb)"}, "fr") == "B P M fois 2"
    plan = narrate.schedule([(0.0, "a", 2.0), (1.0, "b", 1.0), (10.0, "c", 1.0)], end=12.0)
    assert plan[0]["start"] == 0.15 and plan[0]["tempo"] == narrate.MAX_TEMPO     # trop long : accéléré
    assert plan[1]["start"] >= plan[0]["start"] + plan[0]["length"]                # jamais deux voix à la fois
    assert plan[2]["start"] == 10.15 and plan[2]["late"] == 0
    length = narrate.voice_length("en")
    assert 1.0 < length("Open Search now please", "Open Search now please") < 2.5
