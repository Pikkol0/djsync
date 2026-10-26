"""V0.2.0 : métadonnées, doublons, statistiques de playlists, grille de temps (base + export.pdb)."""
from types import SimpleNamespace as S

import pytest

from djsync.analysis import anlz, grid
from djsync.core.duplicates import best_keeper, find_duplicate_groups, split_display
from djsync.db.errors import LibraryError

from .audio_fixture import HAS_FFMPEG, song, write_wav
from .test_pdb_sync import make_usb, open_lib, pdb_of
from .test_usb_library import make_wav


def test_duplicate_groups_like_the_daft_punk_example():
    ts = [S(title="Daft Punk - One More Time (Clip Officiel)", artist="", duration_seconds=320),
          S(title="One More Time", artist="Artiste inconnu", duration_seconds=322),
          S(title="One More Time", artist="Daft Punk", duration_seconds=320, is_analysed=True),
          S(title="One More Time (Extended)", artist="Daft Punk", duration_seconds=600),
          S(title="Love", artist="X", duration_seconds=200), S(title="Love Me Like You Do", artist="X", duration_seconds=200),
          S(title="Umbrella", artist="RihannaVEVO", duration_seconds=270)]
    groups = find_duplicate_groups(ts)
    assert len(groups) == 1 and len(groups[0]) == 3                 # la version longue reste à part
    assert best_keeper(groups[0]).artist == "Daft Punk"
    assert split_display("Vald - Désaccordé", "") == ("Désaccordé", "Vald")
    assert split_display("Désaccordé", "VALD - Topic") == ("Désaccordé", "VALD")


def test_metadata_edit_is_mirrored_with_same_pdb_id(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "x", "x - clip"), "One More Time (Clip Officiel)", "", None, None, [1])
        old_id = pdb_of(usb)._tracks[t.path.casefold()].id
        t2 = lib.update_track_metadata(t.content_id, title="One More Time", artist="Daft Punk")
        assert (t2.title, t2.artist) == ("One More Time", "Daft Punk")
        with pytest.raises(LibraryError):
            lib.update_track_metadata(t.content_id, title="  ")
    pdb = pdb_of(usb)
    row = pdb.track_row(t.path)
    assert row["title"] == "One More Time" and row["id"] == old_id
    assert row["artist_id"] == pdb._artists["daft punk"]
    node = pdb.find_playlist(("Rap",))
    assert [e.track for e in pdb._ordered_entries(node.id)] == [old_id]


def test_merge_duplicates_keeps_playlist_position(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        dup = lib.add_track(make_wav(lib, "A", "a clip"), "a (clip)", "A", None, None, [1, 2])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [2])
        removed, failures = lib.merge_duplicates(a.content_id, [dup.content_id])
        assert (removed, failures) == (1, 0)
        assert [t.content_id for t in lib.get_playlist_tracks(1)] == [a.content_id]
        assert [t.content_id for t in lib.get_playlist_tracks(2)] == [a.content_id, b.content_id]
        assert not lib.absolute_path(dup).exists()
        stats = lib.playlist_stats()
        assert stats[2].track_count == 2 and stats[0].track_count == 2 and len(stats[0].last_added) == 10
    pdb = pdb_of(usb)
    assert not pdb.has_track(dup.path)
    node = pdb.find_playlist(("House",))
    ids = [e.track for e in pdb._ordered_entries(node.id)]
    assert ids == [pdb._tracks[a.path.casefold()].id, pdb._tracks[b.path.casefold()].id]


def test_grid_functions():
    beats = [((k % 4) + 1, 12000, 500 + k * 500) for k in range(8)]
    s = grid.shift(beats, 120, 5000)
    assert s[0][2] == 120 and s[1][2] == 620 and s[-1][2] <= 5000          # temps ajouté avant
    assert s[1][0] == 1                                                    # numérotation conservée
    d = grid.set_downbeat(beats, 2)
    assert [b[0] for b in d[:4]] == [3, 4, 1, 2]
    b = grid.set_bpm(beats, 128, 2, 5000)
    assert all(x[1] == 12800 for x in b) and (1500 in [x[2] for x in b])
    assert grid.nearest(beats, 1240) == 1


@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg absent")
def test_save_beat_grid_rewrites_dat_bpm_and_backs_up(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        folder = lib.default_download_dir("Synth")
        folder.mkdir(parents=True, exist_ok=True)
        f = write_wav(folder / "s.wav", song(128.0, 0.37, 20, ("A", "F", "E", "A"), (1, 0, 0, 1)))
        t = lib.add_track(f, "s", "Synth", None, None, [1])
        g = lib.beat_grid(t.content_id)
        assert abs(g.bpm - 128) < 0.1 and g.is_constant and not g.native
        ext_before = g.dat_path.with_suffix(".EXT").read_bytes()
        new = grid.set_bpm(grid.shift(g.beats, 20, g.duration_ms), 127.5, 4, g.duration_ms)
        t2 = lib.save_beat_grid(t.content_id, new)
        assert abs(t2.bpm - 127.5) < 0.01
        assert anlz.read_beats(g.dat_path.read_bytes()) == new
        assert g.dat_path.with_suffix(".EXT").read_bytes() == ext_before      # pas de PQT2 : intact
        assert list((usb / "DJSync_Backups" / "anlz").rglob("ANLZ0000.DAT"))
        with pytest.raises(LibraryError):
            lib.save_beat_grid(t.content_id, [(1, 12000, 10)])
    assert pdb_of(usb).track_row(t.path)["bpmx100"] == 12750


def test_anlz_rebuild_drops_pqt2_and_keeps_other_tags():
    from djsync.analysis import cues

    tag = anlz._tag
    data = anlz._file([anlz._ppth("/a.mp3"), tag(b"PQT2", b"\0" * 4, b"x" * 8), cues.pcob(1, [])])
    out = anlz.drop_extended_grid(data)
    assert "PQT2" not in anlz.parse(out) and anlz.iter_tags(out)[1][1] == cues.pcob(1, [])
    assert anlz.drop_extended_grid(out) == out


def test_folder_and_explicit_analysis_when_auto_analysis_is_off(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        folder = lib.create_folder("Soirées")
        pl = lib.create_playlist("Club", folder.playlist_id)
        assert folder.is_folder and pl.parent_id == folder.playlist_id
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [pl.playlist_id])
        assert not t.is_analysed                            # réglage V0.2.0 : pas d'analyse à l'ajout
        if HAS_FFMPEG:
            seen = []
            done, skipped, failed = lib.analyze_tracks([t.content_id, t.content_id],
                                                       on_progress=lambda i, n, tr, p: seen.append((i, n)))
            assert seen == [(1, 1)] and skipped == 0
    assert pdb_of(usb).find_playlist(("Soirées", "Club")) is not None
