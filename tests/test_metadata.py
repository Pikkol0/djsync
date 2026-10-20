"""V0.3.0 : métadonnées complémentaires (album, année, genre, label, n° de piste, ISRC).
Aucun réseau : l'API Deezer est simulée."""
from __future__ import annotations

from djsync.core import metadata
from djsync.models import TrackResult

from .test_usb_library import lib, make_wav, usb  # noqa: F401  (fixtures)

SEARCH = {"data": [
    {"id": 1, "title": "One More Time (Radio Edit)", "duration": 230, "artist": {"name": "Daft Punk"},
     "album": {"id": 10, "title": "Single"}},
    {"id": 2, "title": "One More Time", "duration": 320, "artist": {"name": "Daft Punk"},
     "album": {"id": 20, "title": "Discovery"}},
    {"id": 3, "title": "One More Time", "duration": 321, "artist": {"name": "Somebody Else"},
     "album": {"id": 30, "title": "Covers"}},
]}
TRACK = {"id": 2, "isrc": "GBDUW0000059", "track_position": 1, "release_date": "2001-03-07",
         "album": {"id": 20, "title": "Discovery"}}
ALBUM = {"id": 20, "label": "Parlophone (France)", "release_date": "2001-03-12",
         "genres": {"data": [{"id": 113, "name": "Dance"}]}}


def fake_get(path, params=None):
    return {"/search": SEARCH, "/track/2": TRACK, "/album/20": ALBUM}[path]


def test_lookup_picks_the_right_version(monkeypatch):
    monkeypatch.setattr(metadata, "_get", fake_get)
    # titre de clip + chaîne : nettoyés ; la durée choisit la version album (320 s), l'artiste écarte la reprise
    found = metadata.lookup("Daft Punk - One More Time (Official Video)", "DaftPunkVEVO", 322)
    assert found == {"album": "Discovery", "track_no": 1, "isrc": "GBDUW0000059", "genre": "Dance",
                     "label": "Parlophone (France)", "release_date": "2001-03-12", "year": 2001}


def test_enrich_keeps_existing_fields_and_never_raises(monkeypatch):
    monkeypatch.setattr(metadata, "_get", fake_get)
    t = TrackResult(video_id="x" * 11, title="One More Time", artist="Daft Punk", album="Alive 2007",
                    duration_seconds=320)
    e = metadata.enrich(t)
    assert e.album == "Alive 2007" and e.year == 2001 and e.genre == "Dance" and e.track_no == 1

    def boom(*_a, **_k):
        raise OSError("offline")

    monkeypatch.setattr(metadata, "_get", boom)
    assert metadata.enrich(t) is t
    monkeypatch.setattr(metadata, "_get", lambda *_a, **_k: {"data": []})
    assert metadata.enrich(t) is t


def test_metadata_written_to_the_library(lib):
    with lib._write() as conn:                      # tables présentes dans les vraies bases
        conn.execute("CREATE TABLE genre(genre_id integer primary key, name varchar)")
        conn.execute("CREATE TABLE label(label_id integer primary key, name varchar)")
    meta = {"year": 2001, "release_date": "2001-03-12", "genre": "Dance", "label": "Parlophone", "track_no": 1,
            "isrc": "GBDUW0000059"}
    t = lib.add_track(make_wav(lib, "Daft Punk", "a"), "One More Time", "Daft Punk", "Discovery", meta=meta)
    t2 = lib.add_track(make_wav(lib, "Daft Punk", "b"), "Aerodynamic", "Daft Punk", "Discovery",
                       meta={"genre": "dance"})
    row = lib._read("SELECT c.releaseYear, c.releaseDate, c.trackNo, c.isrc, g.name, l.name FROM content c "
                    "LEFT JOIN genre g ON g.genre_id = c.genre_id LEFT JOIN label l ON l.label_id = c.label_id "
                    "WHERE content_id = ?", (t.content_id,))[0]
    assert row == (2001, "2001-03-12", 1, "GBDUW0000059", "Dance", "Parlophone")
    assert lib._read("SELECT COUNT(*) FROM genre")[0][0] == 1                    # genre réutilisé
    assert lib._read("SELECT genre_id FROM content WHERE content_id = ?", (t2.content_id,))[0][0] == \
        lib._read("SELECT genre_id FROM content WHERE content_id = ?", (t.content_id,))[0][0]


def test_meta_without_genre_table_is_ignored(lib):
    t = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, meta={"genre": "Rap", "year": 2020})
    assert lib._read("SELECT releaseYear, genre_id FROM content WHERE content_id = ?", (t.content_id,))[0] == (2020, None)


def test_tags_include_year_genre_track(tmp_path):
    from mutagen.id3 import ID3

    from djsync.core import tagger

    path = tmp_path / "x.mp3"
    ID3().save(str(path))
    t = TrackResult(video_id="x" * 11, title="T", artist="A", album="Al", year=2001, genre="Dance", label="L",
                    track_no=3, isrc="ISRC1")
    tagger.tag_mp3(str(path), t)
    tags = ID3(str(path))
    assert str(tags.get("TDRC") or tags.get("TYER")) == "2001" and str(tags["TCON"]) == "Dance" and str(tags["TRCK"]) == "3"
    assert str(tags["TPUB"]) == "L" and str(tags["TSRC"]) == "ISRC1"
