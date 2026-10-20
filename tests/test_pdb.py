"""Tests du module export.pdb sur un fichier SYNTHÉTIQUE (voir pdb_fixture.py : cohérence avec le
modèle de DJSync, pas preuve de compatibilité matérielle).   pytest -q tests/test_pdb.py"""
import struct
from pathlib import Path

import pytest

from djsync.db.pdb import PdbCapacityError, PdbDatabase, PdbError, PdbFormatError, PdbStore, TrackMeta
from djsync.db.pdb.file import PdbFile, validate_against
from djsync.db.pdb.format import PAGE_SIZE, T, decode_string, encode_string
from djsync.db.pdb.check import report

from .pdb_fixture import build_pdb, sample_track

P1 = sample_track(1).path
P2 = sample_track(2).path


def base_pdb(n: int = 3, playlists=None) -> bytes:
    tracks = [sample_track(i) for i in range(1, n + 1)]
    return build_pdb(tracks, playlists if playlists is not None else {("Rap",): [t.path for t in tracks[:2]]})


def free_in_last_page(data: bytes, ttype: int) -> int:
    f = PdbFile(data)
    return f.page(f.data_pages(ttype)[-1]).free


def fill_tracks_page(allow_growth: bool = False):
    """Fichier dont la dernière page de pistes est quasi pleine."""
    n = 3
    while True:
        data = base_pdb(n)
        if free_in_last_page(data, T.TRACKS) < 330 and len(PdbFile(data).data_pages(T.TRACKS)) >= 1:
            return data, n
        n += 1


# ---------------------------------------------------------------- chaînes
@pytest.mark.parametrize("text", ["", "abc", "x" * 126, "x" * 127, "x" * 500, "Désaccordé", "日本語", "é" * 300])
def test_string_roundtrip(text):
    raw = encode_string(text)
    assert decode_string(raw, 0) == text


def test_string_headers():
    assert encode_string("")[0] == 0x03
    assert encode_string("abc")[0] == 0x09
    assert encode_string("é")[0] == 0x90
    assert encode_string("x" * 200)[0] == 0x40


# ---------------------------------------------------------------- lecture
def test_fixture_is_recognised():
    db = PdbDatabase(base_pdb())
    assert db.track_count == 3 and db.playlist_count() == 1
    assert db.find_playlist(("rap",)) is not None            # insensible à la casse


# ---------------------------------------------------------------- pistes
def test_add_track_in_place_changes_only_touched_pages():
    data = base_pdb()
    db = PdbDatabase(data)
    meta = sample_track(10, artist="Leto", album="100 visages", title="Macaroni")
    db.add_track(meta)
    new = db.to_bytes()
    assert len(new) == len(data)
    f = PdbFile(data)
    track_page = f.data_pages(T.TRACKS)[-1]
    allowed = {track_page, *f.data_pages(T.ARTISTS), *f.data_pages(T.ALBUMS)}
    for i in range(1, len(data) // PAGE_SIZE):
        if i not in allowed:
            assert data[i * PAGE_SIZE:(i + 1) * PAGE_SIZE] == new[i * PAGE_SIZE:(i + 1) * PAGE_SIZE], f"page {i}"
    again = PdbDatabase(new)
    assert again.track_count == 4 and again.has_track(meta.path.upper())
    assert again.file.seq == f.seq + 1


def test_new_track_fields_are_readable():
    from djsync.db.pdb import rows
    db = PdbDatabase(base_pdb())
    meta = sample_track(7, artist="Vald", album="Agartha", title="Désaccordé – ça va")
    db.add_track(meta)
    again = PdbDatabase(db.to_bytes())
    ref = again._tracks[meta.path.casefold()]
    row = rows.read_track(again.file.data, ref.page * PAGE_SIZE + ref.off)
    assert row["title"] == "Désaccordé – ça va" and row["path"] == meta.path
    assert row["strings"]["filename"] == "t7.mp3" and row["strings"]["date_added"] == "2026-01-01"
    d = again.file.data
    pos = ref.page * PAGE_SIZE + ref.off
    assert struct.unpack_from("<I", d, pos + 0x38)[0] == meta.bpmx100
    assert struct.unpack_from("<H", d, pos + 0x54)[0] == meta.length
    assert struct.unpack_from("<H", d, pos + 0x5A)[0] == 1            # fileType mp3
    assert struct.unpack_from("<I", d, pos + 0x48)[0] == ref.id


def test_add_track_is_idempotent_and_ids_increase():
    db = PdbDatabase(base_pdb())
    a = db.add_track(sample_track(10))
    assert db.add_track(sample_track(10)) == a == 4
    assert db.add_track(sample_track(11)) == 5
    assert db.summary.tracks_added == 2


def test_artist_and_album_reused_case_insensitively():
    db = PdbDatabase(base_pdb())
    db.add_track(sample_track(10, artist="ARTISTE", album="album"))
    again = PdbDatabase(db.to_bytes())
    assert len(list(again.file.iter_rows(T.ARTISTS))) == 1
    assert len(list(again.file.iter_rows(T.ALBUMS))) == 1


def test_template_fields_are_copied_from_existing_track():
    data = base_pdb()
    f = PdbFile(data)
    p, slot, off = next(f.iter_rows(T.TRACKS))
    pos = p * PAGE_SIZE + off
    patched = bytearray(data)
    struct.pack_into("<I", patched, pos + 0x04, 0xDEADBEEF)          # « bitmask » propre à ce fichier
    db = PdbDatabase(bytes(patched))
    db.add_track(sample_track(10))
    again = PdbDatabase(db.to_bytes())
    ref = again._tracks[sample_track(10).path.casefold()]
    assert struct.unpack_from("<I", again.file.data, ref.page * PAGE_SIZE + ref.off + 4)[0] == 0xDEADBEEF


def test_delete_track_removes_entries_and_renumbers():
    db = PdbDatabase(base_pdb())
    assert db.delete_track(P1) and not db.delete_track(P1)
    again = PdbDatabase(db.to_bytes())
    assert not again.has_track(P1) and again.track_count == 2
    rap = again.find_playlist(("Rap",))
    entries = again._ordered_entries(rap.id)
    assert [e.index for e in entries] == [1]
    assert again._tracks[P2.casefold()].id == entries[0].track


# ---------------------------------------------------------------- playlists
def test_playlist_lifecycle():
    db = PdbDatabase(base_pdb())
    pid = db.ensure_playlist(("Soirée", "Vendredi"))
    assert db.find_playlist(("Soirée",)).folder is True and db.find_playlist(("Soirée", "Vendredi")).id == pid
    db.playlist_add(("Soirée", "Vendredi"), [P2, P1, P2])
    db.rename_playlist(("Soirée", "Vendredi"), "Samedi")
    again = PdbDatabase(db.to_bytes())
    node = again.find_playlist(("Soirée", "Samedi"))
    assert node and not node.folder and again.find_playlist(("Soirée", "Vendredi")) is None
    assert [e.track for e in again._ordered_entries(node.id)] == [again._tracks[P2.casefold()].id, again._tracks[P1.casefold()].id]
    d2 = PdbDatabase(again.to_bytes())
    d2.delete_playlist(("Soirée",))
    last = PdbDatabase(d2.to_bytes())
    assert last.find_playlist(("Soirée",)) is None and last.find_playlist(("Soirée", "Samedi")) is None
    assert last.find_playlist(("Rap",)) is not None
    assert not any(e.playlist == node.id for es in last._entries.values() for e in es)


def test_playlist_set_reorders_and_remove_renumbers():
    p3 = sample_track(3).path
    db = PdbDatabase(base_pdb())
    db.playlist_set(("Rap",), [p3, P2, P1])
    again = PdbDatabase(db.to_bytes())
    ids = [e.track for e in again._ordered_entries(again.find_playlist(("Rap",)).id)]
    assert ids == [again._tracks[p.casefold()].id for p in (p3, P2, P1)]
    again.playlist_remove(("Rap",), [P2])
    last = PdbDatabase(again.to_bytes())
    entries = last._ordered_entries(last.find_playlist(("Rap",)).id)
    assert [e.index for e in entries] == [1, 2]


def test_unknown_track_is_skipped_not_fatal():
    db = PdbDatabase(base_pdb())
    db.playlist_add(("Rap",), ["/Contents/nope.mp3"])
    assert db.summary.skipped and db.summary.entries_added == 0


# ---------------------------------------------------------------- capacité / agrandissement
def test_full_page_without_growth_raises_and_changes_nothing(tmp_path):
    data, n = fill_tracks_page()
    path = tmp_path / "export.pdb"
    path.write_bytes(data)
    store = PdbStore(tmp_path, tmp_path / "bk")
    ops = [lambda db, i=i: db.add_track(sample_track(100 + i)) for i in range(5)]
    with pytest.raises(PdbCapacityError):
        store.apply(ops)
    assert path.read_bytes() == data and not (tmp_path / "bk").exists()


def test_growth_adds_a_page_and_leaves_the_index_page_alone():
    data, n = fill_tracks_page()
    f0 = PdbFile(data)
    db = PdbDatabase(data, allow_growth=True)
    added = 0
    while len(db.file.data_pages(T.TRACKS)) == len(f0.data_pages(T.TRACKS)):
        db.add_track(sample_track(1000 + added))
        added += 1
    new = db.to_bytes()
    f = PdbFile(new)
    assert len(f.data_pages(T.TRACKS)) == len(f0.data_pages(T.TRACKS)) + 1
    assert f.tables[T.TRACKS].last_page == f0.tables[T.TRACKS].empty_candidate       # l'ancienne candidate sert
    assert f.tables[T.TRACKS].empty_candidate == f0.next_unused                      # une nouvelle est réservée
    assert f.next_unused == f0.next_unused + 1
    idx = f0.index_pages(T.TRACKS)[0]
    assert new[idx * PAGE_SIZE:(idx + 1) * PAGE_SIZE] == data[idx * PAGE_SIZE:(idx + 1) * PAGE_SIZE]
    assert PdbDatabase(new).track_count == n + added
    touched = set(f.chain(T.TRACKS)) | {f0.tables[T.TRACKS].empty_candidate}
    validate_against(data, new, touched | set(db.file.touched))


def test_growth_refused_when_the_candidate_page_is_not_empty():
    data, _ = fill_tracks_page()
    f = PdbFile(data)
    cand = f.tables[T.TRACKS].empty_candidate
    broken = bytearray(data)
    broken[cand * PAGE_SIZE + 100] = 1
    db = PdbDatabase(bytes(broken), allow_growth=True)
    with pytest.raises(PdbFormatError):
        for i in range(30):
            db.add_track(sample_track(2000 + i))


def test_page_counters_marker_and_flags_follow_the_real_conventions():
    db = PdbDatabase(base_pdb())
    page = db.file.page(db.file.data_pages(T.TRACKS)[-1])
    n0 = page.num_slots
    db.add_track(sample_track(10))
    assert (page.num_slots, page.num_valid) == (n0 + 1, n0 + 1)
    assert page.u16(0x20) == 1 and page.u16(0x22) == n0 and page.flags == 0x24
    assert page.free + page.used + 0x28 + (4 + 2 * ((n0 + 1) % 16)) == PAGE_SIZE
    db.delete_track(P1)
    page = db.file.page(db.file.data_pages(T.TRACKS)[0])
    assert page.flags == 0x34 and page.num_valid == page.num_slots - 1


# ---------------------------------------------------------------- fail-closed
def test_garbage_and_truncated_files_are_rejected():
    for blob in (b"\0", b"\0" * 10000, b"x" * PAGE_SIZE * 3, base_pdb()[:-1], base_pdb()[:PAGE_SIZE]):
        with pytest.raises(PdbFormatError):
            PdbDatabase(blob)


def test_used_size_too_small_is_rejected():
    data = base_pdb()
    f = PdbFile(data)
    p = f.data_pages(T.TRACKS)[0]
    broken = bytearray(data)
    struct.pack_into("<H", broken, p * PAGE_SIZE + 0x1E, 8)           # « used » incohérent : écraserait des lignes
    with pytest.raises(PdbFormatError):
        PdbDatabase(bytes(broken))


def test_report_cli_on_good_and_bad_files(tmp_path, capsys):
    good = tmp_path / "export.pdb"
    good.write_bytes(base_pdb())
    assert "Layout recognised" in "\n".join(report(good))
    bad = tmp_path / "bad.pdb"
    bad.write_bytes(b"\0" * 5000)
    assert "NOT RECOGNISED" in "\n".join(report(bad))
    from djsync.db.pdb.check import main
    assert main([str(good)]) == 0 and main([str(bad)]) == 1


# ---------------------------------------------------------------- disque
def test_store_apply_writes_atomically_with_backup_and_rotation(tmp_path):
    path = tmp_path / "export.pdb"
    original = base_pdb()
    path.write_bytes(original)
    store = PdbStore(tmp_path, tmp_path / "bk", keep=2, session_keep=1)
    for i in range(4):
        summary = store.apply([lambda db, i=i: db.add_track(sample_track(50 + i))])
        assert summary.tracks_added == 1
    assert PdbDatabase(path.read_bytes()).track_count == 3 + 4
    backups = sorted(p.name for p in (tmp_path / "bk").iterdir())
    assert sum(n.endswith("-session.pdb") for n in backups) == 1 and sum(n.endswith("-auto.pdb") for n in backups) == 2
    first = sorted((tmp_path / "bk").glob("*-session.pdb"))[0]
    assert first.read_bytes() == original                              # la sauvegarde de session = l'état d'origine
    assert not list(tmp_path.glob("*.djsync-tmp"))


def test_store_noop_does_not_touch_file_or_make_backup(tmp_path):
    path = tmp_path / "export.pdb"
    path.write_bytes(base_pdb())
    mtime = path.stat().st_mtime_ns
    PdbStore(tmp_path, tmp_path / "bk").apply([lambda db: db.add_track(sample_track(1))])
    assert path.stat().st_mtime_ns == mtime and not (tmp_path / "bk").exists()


def test_store_failure_in_the_middle_leaves_file_untouched(tmp_path):
    path = tmp_path / "export.pdb"
    data = base_pdb()
    path.write_bytes(data)

    def boom(db):
        raise PdbError("échec simulé")

    with pytest.raises(PdbError):
        PdbStore(tmp_path, tmp_path / "bk").apply([lambda db: db.add_track(sample_track(9)), boom])
    assert path.read_bytes() == data


# ---------------------------------------------------------------- fichier RÉEL (Pioneer/Rekordbox)
REAL = Path(__file__).parent / "data" / "real_export.pdb"


def test_real_rekordbox_export_is_recognised_and_editable():
    if not REAL.is_file():
        pytest.skip("tests/data/real_export.pdb absent")
    data = REAL.read_bytes()
    db = PdbDatabase(data)
    assert db.track_count > 0 and db.playlist_count() > 0
    first = sorted(db._tracks)[0]
    meta = sample_track(1, artist="Leto", album="100 visages", title="Macaroni – é")
    db.add_track(meta)
    db.playlist_add((next(t.name for t in db._trees.values() if not t.folder),), [meta.path])
    db.delete_track(first)
    new = db.to_bytes()
    again = PdbDatabase(new)
    assert again.has_track(meta.path) and not again.has_track(first) and again.track_count == len(db._tracks)
    changed = [i for i in range(len(data) // PAGE_SIZE) if data[i * PAGE_SIZE:(i + 1) * PAGE_SIZE] != new[i * PAGE_SIZE:(i + 1) * PAGE_SIZE]]
    assert 0 in changed and len(changed) < 12                # en-tête + quelques pages seulement


def test_real_export_growth_beyond_end_of_file_candidate():
    if not REAL.is_file():
        pytest.skip("tests/data/real_export.pdb absent")
    data = REAL.read_bytes()
    db = PdbDatabase(data, allow_growth=True)
    for i in range(300):
        db.add_track(sample_track(i, artist=f"Art{i}", album=f"Alb{i}"))
    again = PdbDatabase(db.to_bytes())
    assert again.track_count == PdbDatabase(data).track_count + 300
