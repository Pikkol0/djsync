"""V0.4.0 : bibliothèque Rekordbox de l'ordinateur (master.db), sur la base de démonstration de
pyrekordbox (vrai schéma Rekordbox 6). Aucun Rekordbox nécessaire."""
from __future__ import annotations

import shutil
import struct
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("pyrekordbox")

from djsync.db import local_library as L  # noqa: E402
from djsync.db.errors import DatabaseLockedError, LibraryError  # noqa: E402

DATA = Path(__file__).parent / "data" / "rekordbox6"


def make_wav(folder: Path, name: str, seconds: float = 4.0, bpm: float = 0.0) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.wav"
    rate = 22050
    n = int(rate * seconds)
    frames = bytearray()
    beat = int(rate * 60 / bpm) if bpm else 0
    for i in range(n):
        v = 0
        if beat and i % beat < 800:                       # clics réguliers : un tempo à trouver
            v = int(20000 * (1 - (i % beat) / 800))
        frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


@pytest.fixture
def local(tmp_path, monkeypatch):
    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    target = L.LocalRekordbox(db_dir, tmp_path / "Music" / "DJSync")
    lib = L.LocalRekordboxLibrary(target, backup_root=tmp_path / "backups", owned_path=tmp_path / "owned.json",
                                  analyze=True).connect()
    yield lib
    lib.close()


def usn(lib):
    return int(lib._read("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'")[0][0])


def xml_ids(lib):
    root = ET.parse(lib.drive.db_dir / "masterPlaylists6.xml").getroot()
    return {int(n.get("Id"), 16) for n in root.iter("NODE")}


def test_find_and_read(local, tmp_path):
    assert L.find_local_rekordbox(str(local.drive.db_dir)).db_path == local.db_path
    assert L.find_local_rekordbox(str(tmp_path / "nope")) is None
    tracks = local.list_tracks()
    assert {t.title for t in tracks} == {"Demo Track 1", "Demo Track 2"}      # échantillons du sampler masqués
    assert all(t.is_analysed and t.analysis_path.startswith("/PIONEER/USBANLZ/") for t in tracks)
    names = {p.name for p in local.list_playlists()}
    assert "Trial playlist - Cloud Library Sync" in names
    assert local.playlist_stats()[0].track_count == 2


def test_add_track_with_analysis_artwork_and_metadata(local, tmp_path):
    before = usn(local)
    music = local.default_download_dir("Daft Punk", "Discovery")
    path = make_wav(music, "One More Time", 6, bpm=120)
    pl = local.create_playlist("Soirée")
    meta = {"year": 2001, "genre": "House", "label": "Virgin", "track_no": 1, "isrc": "GBDUW0000059"}
    t = local.add_track(path, "One More Time", "Daft Punk", "Discovery",
                        "https://music.youtube.com/watch?v=FGBhQbmPwH8", [pl.playlist_id], meta=meta)
    assert t.title == "One More Time" and t.artist == "Daft Punk" and t.album == "Discovery"
    assert t.is_analysed and t.bpm > 0 and t.source_url
    row = local._read("SELECT c.UUID, c.Analysed, c.ReleaseYear, c.TrackNo, c.ISRC, g.Name, l.Name, c.MasterDBID, "
                      "c.DeviceID, c.StockDate, c.FolderPath, c.rb_local_usn FROM djmdContent c "
                      "LEFT JOIN djmdGenre g ON g.ID = c.GenreID LEFT JOIN djmdLabel l ON l.ID = c.LabelID "
                      "WHERE c.ID = :id", {"id": str(t.content_id)})[0]
    uuid = row[0]
    assert row[1:7] == (105, 2001, 1, "GBDUW0000059", "House", "Virgin")
    assert row[7] and row[8] and len(row[9]) == 10 and row[10] == path.resolve().as_posix()
    assert row[11] and row[11] > before                                   # numéro de séquence attribué
    # analyse rangée d'après l'UUID, avec ses lignes contentFile (MD5)
    assert t.analysis_path == f"/PIONEER/USBANLZ/{uuid[:3]}/{uuid[3:]}/ANLZ0000.DAT"
    dat = local.share_dir / t.analysis_path.lstrip("/")
    assert dat.is_file() and dat.with_suffix(".EXT").is_file() and dat.with_suffix(".2EX").is_file()
    from djsync.analysis.anlz import read_path

    assert read_path(dat.read_bytes()) == "?/One More Time.wav"           # comme Rekordbox sur l'ordinateur
    files = dict(local._read("SELECT Path, Hash FROM contentFile WHERE ContentID = :id", {"id": str(t.content_id)}))
    import hashlib

    assert files[t.analysis_path] == hashlib.md5(dat.read_bytes()).hexdigest() and len(files) == 3
    assert [x.content_id for x in local.get_playlist_tracks(pl.playlist_id)] == [t.content_id]
    assert local.is_owned(t.content_id) and usn(local) > before
    assert any(local.backup_dir.glob("master-*/master.db"))
    # même fichier une 2e fois : pas de doublon, seulement la playlist
    again = local.add_track(path, "x", "y")
    assert again.content_id == t.content_id and local.track_count() == 3


def test_playlists_and_xml(local):
    folder = local.create_folder("Sets")
    pl = local.create_playlist("Warm-up", folder.playlist_id)
    assert {folder.playlist_id, pl.playlist_id} <= xml_ids(local)             # masterPlaylists6.xml tenu à jour
    ids = [t.content_id for t in local.list_tracks()]
    assert local.add_to_playlist(pl.playlist_id, ids) == 2
    assert local.add_to_playlist(pl.playlist_id, ids) == 0
    local.set_playlist_order(pl.playlist_id, list(reversed(ids)))
    assert [t.content_id for t in local.get_playlist_tracks(pl.playlist_id)] == list(reversed(ids))
    other = local.create_playlist("Peak")
    local.move_tracks([ids[0]], pl.playlist_id, other.playlist_id)
    assert [t.content_id for t in local.get_playlist_tracks(pl.playlist_id)] == [ids[1]]
    assert [t.sequence for t in local.get_playlist_tracks(pl.playlist_id)] == [1]
    local.rename_playlist(other.playlist_id, "Peak time")
    assert local.get_playlist(other.playlist_id).name == "Peak time"
    local.delete_playlist(folder.playlist_id)
    assert folder.playlist_id not in {p.playlist_id for p in local.list_playlists()}
    assert pl.playlist_id not in xml_ids(local)
    with pytest.raises(LibraryError):
        local.add_to_playlist(100000, ids)                                    # playlist spéciale : lecture seule


def test_never_writes_while_rekordbox_is_open(local, monkeypatch):
    monkeypatch.setattr(L, "rekordbox_running", lambda: True)
    with pytest.raises(DatabaseLockedError):
        local.create_playlist("x")
    assert local.list_tracks()                                               # la lecture reste possible


def test_metadata_grid_duplicates_and_delete(local):
    music = local.default_download_dir("A", "")
    a = local.add_track(make_wav(music, "a", 6, bpm=128), "Track", "A")
    b = local.add_track(make_wav(music, "b", 6, bpm=128), "Track (Clip)", "")
    pl = local.create_playlist("P")
    native = next(t for t in local.list_tracks() if t.title == "Demo Track 1")
    local.add_to_playlist(pl.playlist_id, [native.content_id, b.content_id])
    t = local.update_track_metadata(b.content_id, "Track", "A")
    assert (t.title, t.artist) == ("Track", "A")
    # grille : sauvegarde d'origine, BPM mis à jour
    grid = local.beat_grid(a.content_id)
    assert not grid.native
    moved = [(n, 13000, ms + 10) for n, _t, ms in grid.beats]
    assert local.save_beat_grid(a.content_id, moved).bpm == 130.0
    assert local.beat_grid(a.content_id).beats[0][2] == grid.beats[0][2] + 10
    # doublons : a prend la place de b dans la playlist, b est effacé (fichier compris)
    b_file = Path(b.path)
    assert local.merge_duplicates(a.content_id, [b.content_id]) == (1, 0)
    assert [x.content_id for x in local.get_playlist_tracks(pl.playlist_id)] == [native.content_id, a.content_id]
    assert not b_file.exists()
    # un son natif n'est jamais effacé du disque ni réanalysé
    assert local.analyze_tracks([native.content_id], force=True) == (0, 1, 0)
    removed, failures = local.delete_tracks([native.content_id, a.content_id])
    assert removed == 2 and failures == 0
    assert local.track_count() == 1 and not Path(a.path).exists()
    assert not local.get_playlist_tracks(pl.playlist_id)


def test_unanalysed_then_analyse(local):
    local.analyze = False
    t = local.add_track(make_wav(local.default_download_dir("B", ""), "c", 6, bpm=125), "C", "B")
    assert not t.is_analysed and t.content_id in {x.content_id for x in local.unanalysed_tracks()}
    seen = []
    assert local.analyze_tracks([t.content_id], on_progress=lambda *a: seen.append(a[2])) == (1, 0, 0)
    assert local.get_track(t.content_id).is_analysed and seen[0].is_analysed
    assert local.analyze_tracks([t.content_id], force=True)[0] == 1          # son DJSync : réanalyse permise
