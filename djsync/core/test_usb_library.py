"""Tests du module DB sur une base chiffrée SYNTHÉTIQUE (même schéma qu'un vrai exportLibrary.db).

Lancer :  pip install pytest  &&  pytest -q
"""
import struct
import wave
from pathlib import Path

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from djsync.db import (
    DuplicatePlaylistError, LibraryError, ReadOnlyError, RekordboxUsbLibrary, TrackNotFoundError,
    drive_from_letter,
)
from djsync.db._key import get_default_key

# Schéma relevé sur une vraie base (tables utilisées par DJSync uniquement)
DDL = [
    "CREATE TABLE content(content_id integer primary key, title varchar, titleForSearch varchar, subtitle varchar, bpmx100 integer, length integer, trackNo integer, discNo integer, artist_id_artist integer, artist_id_remixer integer, artist_id_originalArtist integer, artist_id_composer integer, artist_id_lyricist integer, album_id integer, genre_id integer, label_id integer, key_id integer, color_id integer, image_id integer, djComment varchar, rating integer, releaseYear integer, releaseDate varchar, dateCreated varchar, dateAdded varchar, path varchar, fileName varchar, fileSize integer, fileType integer, bitrate integer, bitDepth integer, samplingRate integer, isrc varchar, djPlayCount integer, isHotCueAutoLoadOn integer, isKuvoDeliverStatusOn integer, kuvoDeliveryComment varchar, masterDbId integer, masterContentId integer, analysisDataFilePath varchar, analysedBits integer, contentLink integer, hasModified integer, cueUpdateCount integer, analysisDataUpdateCount integer, informationUpdateCount integer)",
    "CREATE TABLE playlist(playlist_id integer primary key, sequenceNo integer, name varchar, image_id integer, attribute integer, playlist_id_parent integer)",
    "CREATE TABLE playlist_content(playlist_id integer, content_id integer, sequenceNo integer)",
    "CREATE TABLE artist(artist_id integer primary key, name varchar, nameForSearch varchar)",
    "CREATE TABLE album(album_id integer primary key, name varchar, artist_id integer, image_id integer, isComplation integer, nameForSearch varchar)",
    "CREATE TABLE property(deviceName varchar, dbVersion varchar, numberOfContents integer, createdDate varchar, backGroundColorType integer, myTagMasterDBID integer)",
]


@pytest.fixture
def usb(tmp_path: Path):
    """Fausse clé : <tmp>/PIONEER/rekordbox/exportLibrary.db (WAL + SQLCipher) et /Contents."""
    db_dir = tmp_path / "PIONEER" / "rekordbox"
    db_dir.mkdir(parents=True)
    (tmp_path / "Contents").mkdir()
    conn = sqlcipher.connect(str(db_dir / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("PRAGMA journal_mode = WAL")
    for ddl in DDL:
        conn.execute(ddl)
    conn.execute("INSERT INTO property VALUES ('', '1000', 0, '2026-01-01', 0, 1)")
    conn.execute("INSERT INTO playlist VALUES (1, 0, 'Rap', NULL, 0, 0)")
    conn.execute("INSERT INTO playlist VALUES (2, 1, 'House', NULL, 0, 0)")
    conn.execute("INSERT INTO playlist VALUES (3, 2, 'Dossier', NULL, 1, 0)")
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture
def lib(usb: Path):
    with RekordboxUsbLibrary(drive_from_letter(str(usb))) as library:
        yield library


def make_wav(lib: RekordboxUsbLibrary, artist: str, name: str) -> Path:
    folder = lib.default_download_dir(artist)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(struct.pack("<hh", 0, 0) * 44100)
    return path


def test_journal_mode_is_wal(lib):
    assert lib.journal_mode.lower() == "wal"


def test_add_track_and_playlists(lib):
    f = make_wav(lib, "Leto", "Leto - Macaroni")
    t = lib.add_track(f, "Macaroni", "Leto", "100 visages", "https://music.youtube.com/watch?v=BBBBBBBBBBB", [1, 2])
    assert t.path == "/Contents/Leto/UnknownAlbum/Leto - Macaroni.wav"
    assert t.file_type == 11 and not t.is_analysed
    assert [p.track_count for p in lib.list_playlists()][:2] == [1, 1]
    assert lib.find_by_source_url("BBBBBBBBBBB").content_id == t.content_id
    assert lib._read("SELECT numberOfContents FROM property")[0][0] == 1
    assert ("Macaroni", "Leto") in list(lib.iter_tracks())


def test_add_track_is_idempotent_and_reuses_artist(lib):
    f = make_wav(lib, "Leto", "a")
    t1 = lib.add_track(f, "A", "Leto")
    t2 = lib.add_track(f, "A", "Leto", playlist_ids=[1])
    assert t1.content_id == t2.content_id and lib.track_count() == 1
    assert lib._read("SELECT COUNT(*) FROM artist")[0][0] == 1


def test_file_must_be_on_the_usb(lib, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "x.wav"
    outside.write_bytes(b"")
    with pytest.raises(LibraryError):
        lib.add_track(outside, "x", "y")


def test_playlist_crud(lib):
    p = lib.create_playlist("  Soirée  ")
    assert p.name == "Soirée"
    with pytest.raises(DuplicatePlaylistError):
        lib.create_playlist("soirée")
    lib.rename_playlist(p.playlist_id, "Soirée 2")
    assert lib.get_playlist(p.playlist_id).name == "Soirée 2"
    lib.delete_playlist(p.playlist_id)
    assert p.playlist_id not in [x.playlist_id for x in lib.list_playlists()]


def test_folder_content_is_not_editable(lib):
    f = make_wav(lib, "X", "x")
    t = lib.add_track(f, "x", "X")
    with pytest.raises(LibraryError):
        lib.add_to_playlist(3, [t.content_id])  # 3 = dossier


def test_move_reorder_remove(lib):
    ids = [lib.add_track(make_wav(lib, "A", n), n, "A", playlist_ids=[1]).content_id for n in "abc"]
    lib.reorder_track(1, ids[2], 1)
    assert [t.content_id for t in lib.get_playlist_tracks(1)] == [ids[2], ids[0], ids[1]]
    lib.move_tracks([ids[0]], 1, 2)
    assert [t.content_id for t in lib.get_playlist_tracks(2)] == [ids[0]]
    assert [r[0] for r in lib._read("SELECT sequenceNo FROM playlist_content WHERE playlist_id=1 ORDER BY 1")] == [1, 2]
    lib.remove_from_playlist(1, [ids[2]])
    assert lib.get_track(ids[2])  # retiré de la playlist, pas de la bibliothèque


def test_delete_track_removes_file_and_empty_dirs(lib, usb):
    f = make_wav(lib, "Solo", "solo")
    t = lib.add_track(f, "solo", "Solo", playlist_ids=[1])
    assert lib.delete_track(t.content_id) is True
    assert not f.exists() and not (usb / "Contents" / "Solo").exists() and (usb / "Contents").exists()
    assert lib.track_count() == 0 and lib.get_playlist(1).track_count == 0
    with pytest.raises(TrackNotFoundError):
        lib.get_track(t.content_id)


def test_wal_truncated_and_backup_created(lib, usb):
    lib.create_playlist("x")
    wal = usb / "PIONEER" / "rekordbox" / "exportLibrary.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    assert len(list((usb / "DJSync_Backups").glob("exportLibrary-*.db"))) == 1


def test_read_only_blocks_writes(usb):
    with RekordboxUsbLibrary(drive_from_letter(str(usb)), read_only=True) as ro:
        with pytest.raises(ReadOnlyError):
            ro.create_playlist("nope")


def test_rollback_on_error(lib):
    f = make_wav(lib, "R", "r")
    with pytest.raises(LibraryError):
        lib.add_track(f, "r", "R", playlist_ids=[999])  # playlist inexistante -> tout est annulé
    assert lib.track_count() == 0
