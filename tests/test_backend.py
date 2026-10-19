"""Tests de la recherche, du filtre, de la correspondance Spotify et du parsing (sans réseau)."""
import json

import pytest

from djsync.core.matcher import (
    LOW_SCORE, OK_SCORE, Candidate, MatchPreference, MatchResult, SpotifyMatcher, apply_preference, choose,
    score_candidate,
)
from djsync.models import SearchMode, TrackResult, format_views
from djsync.core.search import ExcludeFilter, MusicSearcher, parse_view_count, split_exclusions
from djsync.core.spotify import SpotifyError, extract_spotify_id, parse_embed_html, parse_text_list
from djsync.models import SpotifyTrack


# ------------------------------------------------------------------ vues & filtre
@pytest.mark.parametrize("text,expected", [
    ("1.2M", 1_200_000), ("1.2M views", 1_200_000), ("845K", 845_000), ("3.4B", 3_400_000_000),
    ("123", 123), ("123 views", 123), ("12,345 views", 12345), ("12 345 vues", 12345),
    ("1.234.567", 1234567), ("88\xa0k", 88_000), ("1,7\xa0Mrd.", 1_700_000_000),
    ("15 Mio. Aufrufe", 15_000_000), ("1,2 M", 1_200_000), ("", None), (None, None), ("abc", None),
    (5400, 5400),
])
def test_parse_view_count(text, expected):
    assert parse_view_count(text) == expected


@pytest.mark.parametrize("n,expected", [
    (None, "—"), (0, "0"), (999, "999"), (1234, "1,2 k"), (845_000, "845 k"),
    (1_200_000, "1,2 M"), (12_000_000, "12 M"), (3_400_000_000, "3,4 Md"),
])
def test_format_views(n, expected):
    assert format_views(n) == expected


def test_split_exclusions():
    assert split_exclusions("remix live") == ["remix", "live"]
    assert split_exclusions("remix, radio edit ; live") == ["remix", "radio edit", "live"]


def test_exclude_filter_whole_words_accents_and_brackets():
    f = ExcludeFilter("remix, live, radio édit")
    t = lambda title, album=None: TrackResult("x", title, "A", album)  # noqa: E731
    assert not f.allows(t("One More Time (Remix)"))          # contenu des parenthèses conservé
    assert not f.allows(t("Titre - LIVE à Paris"))
    assert not f.allows(t("Titre (Radio Edit)"))             # expression + accents
    assert not f.allows(t("Titre", album="Live at Wembley"))
    assert f.allows(t("Alive"))                              # mot entier : « alive » != « live »
    assert f.allows(t("Remixed")) and f.allows(t("Olive Tree"))
    assert not ExcludeFilter("") and ExcludeFilter("a")


# ---------------------------------------------------------------------- recherche
SONG = {"category": "Songs", "resultType": "song", "videoId": "SONGAAAAAAA", "title": "One More Time",
        "artists": [{"name": "Daft Punk", "id": "UC1"}], "album": {"name": "Discovery", "id": "MPRE1"},
        "duration": "5:20", "duration_seconds": 320, "videoType": "MUSIC_VIDEO_TYPE_ATV",
        "thumbnails": [{"url": "https://lh3/60", "width": 60}, {"url": "https://lh3/120", "width": 120}],
        "isAvailable": True}
SONG_REMIX = {**SONG, "videoId": "SONGREMIX11", "title": "One More Time (Remix)"}
VIDEO = {"category": "Videos", "resultType": "video", "videoId": "VIDEOAAAAAA", "title": "Daft Punk - One More Time (Official Video)",
         "artists": [{"name": "Daft Punk", "id": "UC1"}], "views": "1.2B", "duration": "5:22", "duration_seconds": 322,
         "videoType": "MUSIC_VIDEO_TYPE_OMV", "thumbnails": [{"url": "https://i.ytimg.com/a.jpg"}]}
VIDEO_LIVE = {**VIDEO, "videoId": "VIDEOLIVE11", "title": "One More Time (Live)", "views": "845K"}
BROKEN = {"resultType": "song", "title": "no id"}


class FakeYT:
    def __init__(self):
        self.calls = []

    def search(self, query, filter=None, limit=20):
        self.calls.append((query, filter, limit))
        if filter == "songs":
            return [SONG, SONG_REMIX, BROKEN]
        if filter == "videos":
            return [VIDEO, VIDEO_LIVE, {**VIDEO, "videoId": "SONGAAAAAAA"}]  # même id que le titre
        if filter == "artists":
            return [{"resultType": "artist", "artist": "Daft Punk", "browseId": "UCdaft"}]
        raise AssertionError(filter)

    def get_artist(self, browse_id):
        assert browse_id == "UCdaft"
        return {"songs": {"browseId": "VLPLxyz", "results": [SONG]}, "videos": {"results": [VIDEO]}}

    def get_playlist(self, playlist_id, limit=100):
        return {"tracks": [{"videoId": "ART1", "title": "Around the World", "artists": [{"name": "Daft Punk"}],
                            "album": {"name": "Homework"}, "duration": "3:49", "duration_seconds": 229, "views": None,
                            "thumbnails": [{"url": "u"}]}, {"videoId": None, "title": "gone"}]}

    def get_song(self, video_id):
        return {"videoDetails": {"viewCount": "987654"}} if video_id == "SONGAAAAAAA" else {}


def test_search_all_distinguishes_types_and_reads_views():
    res = MusicSearcher(FakeYT()).search("daft punk", limit=10)
    by_id = {t.video_id: t for t in res}
    assert by_id["SONGAAAAAAA"].is_song and by_id["SONGAAAAAAA"].kind_label == "Titre"
    assert by_id["SONGAAAAAAA"].views is None and by_id["SONGAAAAAAA"].album == "Discovery"
    assert not by_id["VIDEOAAAAAA"].is_song and by_id["VIDEOAAAAAA"].kind_label == "Vidéo"
    assert by_id["VIDEOAAAAAA"].views == 1_200_000_000 and by_id["VIDEOAAAAAA"].views_str == "1,2 Md"
    assert by_id["VIDEOAAAAAA"].duration_str == "5:22"
    assert by_id["SONGAAAAAAA"].thumbnail_url == "https://lh3/120"
    assert len(res) == 4                       # id manquant ignoré, doublon d'id dédoublonné
    assert [t.result_type for t in res][:2] == ["song", "song"]  # Titres d'abord


def test_search_modes_call_the_right_filters():
    yt = FakeYT()
    s = MusicSearcher(yt)
    s.search("x", mode=SearchMode.SONGS); assert [c[1] for c in yt.calls] == ["songs"]
    yt.calls.clear(); s.search("x", mode=SearchMode.VIDEOS); assert [c[1] for c in yt.calls] == ["videos"]
    yt.calls.clear(); s.search("x", mode=SearchMode.ALL); assert [c[1] for c in yt.calls] == ["songs", "videos"]


def test_search_exclusion_and_extra_fetch_margin():
    yt = FakeYT()
    res = MusicSearcher(yt).search("x", limit=10, exclude="remix, live")
    assert {t.video_id for t in res} == {"SONGAAAAAAA", "VIDEOAAAAAA"}
    assert yt.calls[0][2] == 20                # marge x2 quand un filtre est actif


def test_search_artist_mode_lists_artist_tracks():
    res = MusicSearcher(FakeYT()).search("daft punk", limit=10, mode=SearchMode.ARTISTS)
    assert [t.video_id for t in res] == ["ART1", "VIDEOAAAAAA"]
    assert res[0].is_song and not res[1].is_song


def test_fetch_view_count_and_failure_is_silent():
    s = MusicSearcher(FakeYT())
    assert s.fetch_view_count("SONGAAAAAAA") == 987_654
    assert s.fetch_view_count("other") is None

    class Boom(FakeYT):
        def get_song(self, v): raise RuntimeError("réseau")
    assert MusicSearcher(Boom()).fetch_view_count("x") is None


def test_empty_query():
    assert MusicSearcher(FakeYT()).search("   ") == []


# ------------------------------------------------------------------ correspondance
def cand(video_id, title, artist, seconds, song=True, album=None):
    return TrackResult(video_id, title, artist, album, seconds, result_type="song" if song else "video")


SRC = SpotifyTrack("Pilote (feat. Hamza)", ("PLK", "Hamza"), duration_seconds=185)


def test_score_exact_official_song_is_high():
    assert score_candidate(SRC, cand("a", "Pilote (feat. Hamza)", "PLK, Hamza", 185)) >= 95


def test_score_video_with_artist_in_title_and_vevo_channel():
    s = score_candidate(SRC, cand("b", "PLK - Pilote (Clip officiel)", "PLKVEVO", 187, song=False))
    assert s >= OK_SCORE


def test_score_penalises_remix_live_and_wrong_duration():
    good = score_candidate(SRC, cand("a", "Pilote", "PLK", 185))
    remix = score_candidate(SRC, cand("c", "Pilote (Remix)", "PLK", 185))
    live = score_candidate(SRC, cand("d", "Pilote (Live)", "PLK", 230))
    unrelated = score_candidate(SRC, cand("e", "Totally different song", "Someone", 300))
    assert good - remix >= 20 and good > live and unrelated < LOW_SCORE


def test_score_remix_is_fine_when_the_source_is_a_remix():
    src = SpotifyTrack("Pilote - Remix", ("PLK",), duration_seconds=200)
    assert score_candidate(src, cand("a", "Pilote (Remix)", "PLK", 200)) >= 90


def cands(*items):
    return [Candidate(t, s) for t, s in items]


def test_choose_auto_prefers_song_but_switches_to_much_better_video():
    song, video = cand("s", "t", "a", 1), cand("v", "t", "a", 1, song=False)
    assert cands((song, 90), (video, 85))[choose(cands((song, 90), (video, 85)), MatchPreference.AUTO)].track is song
    c = cands((video, 98), (song, 80))
    assert c[choose(c, MatchPreference.AUTO)].track is video       # +18 > marge de 12
    c = cands((video, 88), (song, 80))
    assert c[choose(c, MatchPreference.AUTO)].track is song        # +8 < marge


def test_choose_auto_falls_back_to_video_when_official_song_not_found():
    song, video = cand("s", "t", "a", 1), cand("v", "t", "a", 1, song=False)
    c = cands((song, 40), (video, 80))
    assert c[choose(c, MatchPreference.AUTO)].track is video       # bootleg
    assert choose(cands((song, 40), (video, 50)), MatchPreference.AUTO) is None
    assert choose([], MatchPreference.AUTO) is None


def test_choose_forced_preferences():
    song, video = cand("s", "t", "a", 1), cand("v", "t", "a", 1, song=False)
    c = cands((song, 70), (video, 95))
    assert c[choose(c, MatchPreference.SONG)].track is song        # Titre plausible : il gagne
    assert c[choose(c, MatchPreference.VIDEO)].track is video
    c = cands((song, 30), (video, 95))
    assert c[choose(c, MatchPreference.SONG)].track is video       # Titre trop faible : repli
    c = cands((song, 95), (video, 30))
    assert c[choose(c, MatchPreference.VIDEO)].track is song


def test_match_result_status_manual_override_and_cycle():
    song, video = cand("s", "t", "a", 1), cand("v", "t", "a", 1, song=False)
    m = MatchResult(SRC, cands((song, 90), (video, 60)))
    apply_preference(m, MatchPreference.AUTO)
    assert m.status == "ok" and m.candidate.track is song
    m.cycle()
    assert m.candidate.track is video and m.status == "review" and m.manual
    apply_preference(m, MatchPreference.SONG)                       # choix manuel conservé
    assert m.candidate.track is video
    assert MatchResult(SRC).status == "missing"
    dup = MatchResult(SRC, [Candidate(song.with_duplicate("X - t"), 90)], chosen=0)
    assert dup.status == "duplicate"


def test_matcher_searches_both_families_and_sorts():
    class S:
        def search(self, q, limit, mode):
            assert q == "PLK Pilote (feat. Hamza)"
            return ([cand("s1", "Pilote (feat. Hamza)", "PLK, Hamza", 185)] if mode == SearchMode.SONGS
                    else [cand("v1", "PLK - Pilote", "PLKVEVO", 186, song=False), cand("s1", "dup id", "x", 1)])
    out = SpotifyMatcher(S()).find_candidates(SRC)
    assert [c.track.video_id for c in out][0] == "s1" and len(out) == 2
    assert out == sorted(out, key=lambda c: c.score, reverse=True)


# -------------------------------------------------------------------------- Spotify
def test_extract_spotify_id():
    pid = "37i9dQZF1DXcBWIGoYBM5M"
    for url in (f"https://open.spotify.com/playlist/{pid}?si=abc", f"https://open.spotify.com/intl-fr/playlist/{pid}",
                f"spotify:playlist:{pid}", f"https://open.spotify.com/embed/playlist/{pid}"):
        assert extract_spotify_id(url) == ("playlist", pid)
    assert extract_spotify_id(f"https://open.spotify.com/album/{pid}") == ("album", pid)
    assert extract_spotify_id("https://youtube.com/watch?v=abc") is None


def _embed(track_list, name="Ma playlist", wrap=True):
    entity = {"name": name, "trackList": track_list} if wrap else track_list
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def test_parse_embed_html():
    pl = parse_embed_html(_embed([
        {"uri": "spotify:track:1", "title": "Pilote", "subtitle": "PLK,\xa0Hamza", "duration": 185000},
        {"uri": "spotify:track:2", "title": "Simon & Garfunkel Song", "subtitle": "Simon & Garfunkel", "duration": 200000},
        {"uri": "spotify:track:3", "title": "", "subtitle": "x"},
    ]))
    assert pl.name == "Ma playlist" and len(pl.tracks) == 2 and not pl.truncated
    assert pl.tracks[0].artists == ("PLK", "Hamza") and pl.tracks[0].duration_seconds == 185
    assert pl.tracks[1].artists == ("Simon & Garfunkel",)          # pas de découpe sur « & »
    assert pl.tracks[0].query == "PLK Pilote" and pl.tracks[0].display == "PLK, Hamza – Pilote"


def test_parse_embed_html_tolerates_unknown_structure_and_flags_truncation():
    items = [{"title": f"t{i}", "subtitle": "a", "duration": 1000} for i in range(100)]
    pl = parse_embed_html(_embed(items, wrap=False).replace('"state"', '"autreChemin"'))
    assert len(pl.tracks) == 100 and pl.truncated


@pytest.mark.parametrize("html", ["<html>rien</html>", _embed([]), '<script id="__NEXT_DATA__">{oops</script>'])
def test_parse_embed_html_errors_are_user_friendly(html):
    with pytest.raises(SpotifyError):
        parse_embed_html(html)


def test_parse_text_list():
    pl = parse_text_list("1. PLK - Pilote\nNiska, Ninho – Macaroni\n# commentaire\n\nTitre seul\n")
    assert [(t.artists, t.title) for t in pl.tracks] == [(("PLK",), "Pilote"), (("Niska", "Ninho"), "Macaroni"), ((), "Titre seul")]
    with pytest.raises(SpotifyError):
        parse_text_list("  \n# rien")


def test_original_is_not_accepted_for_a_requested_remix():
    src = SpotifyTrack("Pilote - Remix", ("PLK",), duration_seconds=200)
    assert score_candidate(src, cand("o", "Pilote", "PLK", 200)) < LOW_SCORE + 5
    assert score_candidate(src, cand("r", "Pilote (Remix)", "PLK", 200)) > 90
