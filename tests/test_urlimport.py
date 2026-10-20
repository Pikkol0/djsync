"""Import par URL : classification, entrées yt-dlp -> morceaux, doublons par URL (sans réseau)."""
import pytest

from djsync.core.urlimport import (
    UrlImportError, classify_url, clean_channel, entry_to_track, guess_artist_title, resolve_direct,
)
from djsync.models import TrackResult, UrlKind


@pytest.mark.parametrize("url,kind", [
    ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x", UrlKind.SPOTIFY),
    ("https://open.spotify.com/intl-fr/track/4uLU6hMCjMI75M1A2tKUQC", UrlKind.SPOTIFY),
    ("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", UrlKind.SPOTIFY),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", UrlKind.YOUTUBE),
    ("https://music.youtube.com/playlist?list=PLabc", UrlKind.YOUTUBE),
    ("youtu.be/dQw4w9WgXcQ", UrlKind.YOUTUBE),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", UrlKind.YOUTUBE),
    ("https://soundcloud.com/artist/track", UrlKind.SOUNDCLOUD),
    ("https://on.soundcloud.com/abc123", UrlKind.SOUNDCLOUD),
    ("https://soundcloud.com/artist/sets/my-set", UrlKind.SOUNDCLOUD),
    ("https://example.com/x", UrlKind.UNKNOWN), ("", UrlKind.UNKNOWN), ("pas une url", UrlKind.UNKNOWN),
    ("https://notyoutube.com/watch?v=dQw4w9WgXcQ", UrlKind.UNKNOWN),   # pas de faux positif sur le domaine
])
def test_classify_url(url, kind):
    assert classify_url(url) == kind


def test_guess_artist_title():
    assert guess_artist_title({"artist": "Daft Punk", "track": "One More Time", "title": "x"}) == ("Daft Punk", "One More Time")
    assert guess_artist_title({"title": "PLK - Pilote (Clip officiel)", "uploader": "PLKVEVO"}) == ("PLK", "Pilote (Clip officiel)")
    assert guess_artist_title({"title": "Pilote", "uploader": "PLKVEVO"}) == ("PLK", "Pilote")
    assert guess_artist_title({"title": "Titre seul"}) == ("Inconnu", "Titre seul")
    assert clean_channel("Daft Punk - Topic") == "Daft Punk"


YT = {"id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "duration": 213, "view_count": 1_500_000_000, "channel": "Rick Astley", "thumbnails": [{"url": "t1"}, {"url": "t2"}]}
SC = {"id": "1234567", "title": "Cool Track", "uploader": "DJ Someone", "duration": 200.5,
      "webpage_url": "https://soundcloud.com/dj-someone/cool-track?utm_source=x", "thumbnail": "https://i1.sndcdn.com/a.jpg"}


def test_entry_to_track_youtube_and_soundcloud():
    t = entry_to_track({**YT, "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1&index=3"}, UrlKind.YOUTUBE)
    assert (t.artist, t.title, t.source, t.result_type) == ("Rick Astley", "Never Gonna Give You Up", "youtube", "video")
    assert t.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"        # lien canonique, sans &list=
    assert t.views == 1_500_000_000 and t.duration_str == "3:33" and t.thumbnail_url == "t2" and t.source_label == "YouTube"
    s = entry_to_track(SC, UrlKind.SOUNDCLOUD)
    assert (s.artist, s.title, s.source, s.result_type) == ("DJ Someone", "Cool Track", "soundcloud", "song")
    assert s.url.startswith("https://soundcloud.com/dj-someone/cool-track") and s.source_label == "SoundCloud"
    # miniature de repli pour YouTube sans vignette ; entrées inutilisables ignorées
    assert entry_to_track({k: v for k, v in YT.items() if k != "thumbnails"}, UrlKind.YOUTUBE).thumbnail_url.endswith("/mqdefault.jpg")
    assert entry_to_track({**YT, "title": "[Private video]"}, UrlKind.YOUTUBE) is None
    assert entry_to_track({"id": "", "title": "x", "url": "https://x"}, UrlKind.YOUTUBE) is None
    topic = entry_to_track({**YT, "channel": "Rick Astley - Topic", "uploader": "Rick Astley - Topic"}, UrlKind.YOUTUBE)
    assert topic.result_type == "song"                                    # chaîne « Topic » = titre officiel


def test_resolve_playlist_flat():
    info = {"_type": "playlist", "title": "Ma Playlist", "entries": [YT, None, {**YT, "id": "AAAAAAAAAAA", "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"}, YT]}
    seen = {}
    res = resolve_direct("https://www.youtube.com/playlist?list=PLabc", extractor=lambda u, o: seen.update(opts=o) or info)
    assert res.is_playlist and res.name == "Ma Playlist" and len(res.tracks) == 2        # None ignoré, doublon fusionné
    assert seen["opts"]["extract_flat"] == "in_playlist" and seen["opts"]["noplaylist"] is False


def test_resolve_single_video_and_video_with_list_param():
    res = resolve_direct("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1", extractor=lambda u, o: {**YT, "webpage_url": u} | {"_o": o})
    assert not res.is_playlist and len(res.tracks) == 1 and "only the video" in res.note
    seen = {}
    resolve_direct("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1", extractor=lambda u, o: seen.update(o=o) or YT)
    assert seen["o"]["noplaylist"] is True
    res = resolve_direct("https://soundcloud.com/dj-someone/cool-track", extractor=lambda u, o: SC)
    assert res.kind == UrlKind.SOUNDCLOUD and res.tracks[0].title == "Cool Track" and res.note == ""


def test_resolve_errors_are_user_friendly():
    with pytest.raises(UrlImportError, match="not supported"):
        resolve_direct("https://example.com/x")
    def boom(u, o): raise RuntimeError("\x1b[0;31mERROR:\x1b[0m Video unavailable")
    with pytest.raises(UrlImportError, match="Video unavailable"):
        resolve_direct("https://www.youtube.com/watch?v=dQw4w9WgXcQ", extractor=boom)
    with pytest.raises(UrlImportError, match="No playable track"):
        resolve_direct("https://www.youtube.com/playlist?list=P", extractor=lambda u, o: {"_type": "playlist", "entries": [{"id": "x", "title": "[Deleted video]", "url": "https://x"}]})
    assert resolve_direct("https://www.youtube.com/playlist?list=P", limit=2, extractor=lambda u, o: {"_type": "playlist", "entries": [YT, {**YT, "id": "BBBBBBBBBBB", "url": "https://www.youtube.com/watch?v=BBBBBBBBBBB"}]}).truncated


# ----------------------------------------------- doublons par URL avec la vraie classe DB
def test_db_duplicate_detection_by_url_for_youtube_and_soundcloud(tmp_path):
    from tests.test_usb_library import DDL, make_wav  # noqa: F401
    from djsync.core.duplicates import DuplicateChecker
    from djsync.db import RekordboxUsbLibrary, drive_from_letter, extract_video_id
    from djsync.db._key import get_default_key
    from sqlcipher3 import dbapi2 as sqlcipher

    db_dir = tmp_path / "PIONEER" / "rekordbox"; db_dir.mkdir(parents=True); (tmp_path / "Contents").mkdir()
    c = sqlcipher.connect(str(db_dir / "exportLibrary.db")); c.execute("PRAGMA key = '%s'" % get_default_key())
    c.execute("PRAGMA journal_mode = WAL")
    for ddl in DDL: c.execute(ddl)
    c.execute("INSERT INTO property VALUES ('', '1000', 0, '2026-01-01', 0, 1)"); c.commit(); c.close()

    with RekordboxUsbLibrary(drive_from_letter(str(tmp_path))) as lib:
        yt = entry_to_track(YT, UrlKind.YOUTUBE); sc = entry_to_track(SC, UrlKind.SOUNDCLOUD)
        lib.add_track(make_wav(lib, "Rick", "a"), yt.title, yt.artist, source_url=yt.url)
        lib.add_track(make_wav(lib, "DJ", "b"), sc.title, sc.artist, source_url=sc.url)
        assert lib.find_by_source_url(yt.url).title == "Never Gonna Give You Up"
        assert lib.find_by_source_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ&si=zz") is not None   # même vidéo, autre hôte
        assert lib.find_by_source_url("https://soundcloud.com/dj-someone/cool-track?si=tracking").title == "Cool Track"
        assert lib.find_by_source_url("https://soundcloud.com/dj-someone/autre") is None
        # un slug SoundCloud de 11 caractères n'est JAMAIS pris pour un id YouTube
        assert extract_video_id("https://soundcloud.com/artist/abcdefghijk") is None
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ" and extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=5") == "dQw4w9WgXcQ"
        # le détecteur marque les entrées déjà présentes, quelle que soit la source
        checker = DuplicateChecker(lib, exact_lookup=lib.find_by_source_url)
        marked = checker.annotate([yt, sc, TrackResult("zzzzzzzzzzz", "Inconnu total", "Personne")])
        assert [t.is_duplicate for t in marked] == [True, True, False]
