"""1.3.0 : format de la clé et export.pdb (T01), hot cues et boucles (C22), report des cues (C13),
doublons par empreinte audio (B02)."""
from __future__ import annotations

from pathlib import Path

import pytest


# ============================================================================ T01
def test_filesystem_names_and_compat():
    from djsync.db.usb import filesystem_compat, normalize_fs

    assert normalize_fs("vfat") == "FAT32" and normalize_fs("msdos") == "FAT32" and normalize_fs("exfat") == "exFAT"
    assert normalize_fs("NTFS") == "NTFS" and normalize_fs("hfsplus") == "HFS+" and normalize_fs("") == ""
    assert filesystem_compat("FAT32") == "ok" and filesystem_compat("HFS+") == "ok"
    assert filesystem_compat("exFAT") == "recent_only"
    assert filesystem_compat("NTFS") == "unsupported" and filesystem_compat("") == ""


def test_drive_filesystem_from_mount_table(monkeypatch, tmp_path):
    import djsync.db.usb as usb

    if usb.os.name == "nt":
        pytest.skip("POSIX mount table")
    key = tmp_path / "KEY"
    key.mkdir()
    monkeypatch.setattr(usb, "_mount_table", lambda: [("/", "ext4"), (str(tmp_path), "tmpfs"), (str(key), "exfat")])
    assert usb.drive_filesystem(key) == "exFAT"
    assert usb.drive_filesystem(key / "PIONEER") == "exFAT"
    assert usb.drive_filesystem(tmp_path) == "tmpfs"


def test_diagnostic_report_warns_about_exfat_and_missing_pdb():
    from djsync.db.diagnose import DiagnosticReport

    rep = DiagnosticReport(drive="E:", journal_mode="wal", filesystem="exFAT", integrity="ok")
    assert any("E-8307" in p for p in rep.problems)
    assert any("Device Library" in line for line in rep.lines())
    assert not DiagnosticReport(drive="E:", journal_mode="wal", filesystem="FAT32", integrity="ok").problems


def _pdb_pair(tmp_path):
    from djsync.db.pdb import PdbDatabase
    from tests.pdb_fixture import build_pdb, sample_track

    ref = build_pdb([sample_track(1), sample_track(2)], {("Rap",): [], ("House",): []})
    (tmp_path / "ref.pdb").write_bytes(ref)
    db = PdbDatabase(ref)
    db.ensure_playlist(("DJSync",))
    db.playlist_set(("DJSync",), list(db.track_paths()))
    (tmp_path / "new.pdb").write_bytes(db.to_bytes())
    return tmp_path / "ref.pdb", tmp_path / "new.pdb"


def test_pdb_compare_report(tmp_path):
    from djsync.db.pdb import compare

    ref, new = _pdb_pair(tmp_path)
    text = "\n".join(compare.compare(ref, new, "DJSync"))
    assert "playlist only in compared file" in text and "'DJSync'" in text
    assert "entries of 'DJSync'" in text and "anomalies: none" in text
    assert compare.main([str(ref), str(new), "-o", str(tmp_path / "r.txt")]) == 0
    assert (tmp_path / "r.txt").read_text(encoding="utf-8").startswith("Reference")


def test_pdb_compare_finds_dangling_entries(tmp_path):
    import struct

    from djsync.db.pdb import compare
    from djsync.db.pdb.file import PdbFile
    from djsync.db.pdb.format import T

    _ref, new = _pdb_pair(tmp_path)
    f = PdbFile(new.read_bytes())
    p, _i, off = next(iter(f.iter_rows(T.PLAYLIST_ENTRIES)))
    struct.pack_into("<I", f.data, f.page(p).base + off + 4, 999)          # son inexistant
    bad = compare.anomalies(f)
    assert any("missing tracks" in b for b in bad)


# ============================================================================ C22 : cues dans les ANLZ
def test_cue_lists_written_like_rekordbox():
    import struct

    from djsync.analysis.cues import Cue, pcob, pco2, read_cues

    mem = [Cue(0, 410), Cue(0, 43733, name="train"), Cue(0, 107749, 118095, 16)]
    raw = pcob(0, mem)
    kind, _u, n, last = struct.unpack(">IHHi", raw[12:24])
    assert (kind, n, last) == (0, 3, 2)
    first = raw[24:24 + 56]
    assert first[:4] == b"PCPT" and struct.unpack(">HH", first[24:28]) == (0xFFFF, 1)     # liste chaînée
    assert struct.unpack(">I", first[16:20])[0] == 0                                         # status 0
    hot = pcob(1, [Cue(1, 410), Cue(3, 43733)])
    assert struct.unpack(">i", hot[20:24])[0] == -1
    ext2 = pco2(1, [Cue(2, 34034, name="drop", color_code=60, rgb=(77, 0, 255))])
    assert len(ext2) == 20 + 98                                                              # 88 + nom UTF-16
    assert read_cues(None, b"PMAI" + struct.pack(">IIIIII", 0x1C, 0x1C + len(ext2), 1, 0x10000, 0x10000, 0) + ext2) \
        [0].name == "drop"


def test_write_and_read_cues_roundtrip(tmp_path):
    from djsync.analysis import anlz
    from djsync.analysis.cues import Cue, read_cues, save_to_files
    from djsync.analysis.waveform import Waveforms

    wf = Waveforms(detail=b"\x00" * 150, color_detail=b"\x00" * 300, preview=b"\x00" * 400,
                   tiny_preview=b"\x00" * 100, color_preview=b"\x00" * 6 * 1200)
    rel = anlz.write_files(tmp_path, "/Contents/a.m4a", [(1, 12000, 500), (2, 12000, 1000)], wf, memory_cues=[500])
    dat = tmp_path / rel.lstrip("/")
    assert [c.ms for c in read_cues(dat.read_bytes(), dat.with_suffix(".EXT").read_bytes())] == [500]
    cues = [Cue(1, 500), Cue(4, 2000, name="Drop"), Cue(5, 3000, 5000, 4), Cue(0, 500), Cue(0, 7000, 8000, 2)]
    save_to_files(dat, cues, tmp_path / "bk")
    back = read_cues(dat.read_bytes(), dat.with_suffix(".EXT").read_bytes())
    assert [(c.slot, c.ms, c.loop_ms, c.name) for c in back] == [
        (1, 500, None, ""), (4, 2000, None, "Drop"), (5, 3000, 5000, ""), (0, 500, None, ""), (0, 7000, 8000, "")]
    assert (tmp_path / "bk" / "ANLZ0000.DAT").is_file()
    # réanalyse : les cues posées sont gardées
    anlz.write_files(tmp_path, "/Contents/a.m4a", [(1, 12000, 500), (2, 12000, 1000)], wf, rel_dir=rel[:-14],
                     memory_cues=[500])
    assert len(read_cues(dat.read_bytes(), dat.with_suffix(".EXT").read_bytes())) == 5


def test_cue_editing_helpers():
    from djsync.analysis.cues import Cue, loop_end_ms, nearest_beat_ms, suggest_cues

    beats = [((i % 4) + 1, 12000, 1000 + i * 500) for i in range(400)]        # 120 BPM, mesure tous les 2 s
    assert nearest_beat_ms(beats, 1240) == 1000 and nearest_beat_ms(beats, 1260) == 1500
    assert loop_end_ms(beats, 1000, 4) == 3000
    assert loop_end_ms(beats, beats[-1][2], 2) == beats[-1][2] + 1000          # au-delà : au tempo du dernier temps
    got = suggest_cues(beats, [Cue(1, 5000), Cue(0, 1000)])
    assert [c.slot for c in got] == [2, 3, 4, 5] and got[0].ms == 1000            # A déjà pris : pads libres seulement
    assert [c.ms for c in got] == [1000 + k * 32 * 2000 for k in range(4)]
    full = [Cue(s, s * 100) for s in range(1, 9)]
    assert suggest_cues(beats, full) == []


def test_master_db_kind_mapping():
    from djsync.analysis.cues import KIND_FOR_SLOT, SLOT_FOR_KIND

    assert [KIND_FOR_SLOT[s] for s in range(9)] == [0, 1, 2, 3, 5, 6, 7, 8, 9]
    assert SLOT_FOR_KIND[5] == 4 and 4 not in SLOT_FOR_KIND


def test_local_library_cues_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    import shutil

    from djsync.analysis.cues import Cue
    from djsync.db import local_library as L

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    data = Path(__file__).parent / "data" / "rekordbox6"
    for f in data.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    lib = L.LocalRekordboxLibrary(L.LocalRekordbox(db_dir, tmp_path / "Music"), backup_root=tmp_path / "bk",
                                  owned_path=tmp_path / "owned.json").connect()
    try:
        cid = lib.list_tracks()[0].content_id
        assert lib.track_cues(cid) == []
        cues = [Cue(1, 500, name="Intro"), Cue(5, 9000, 11000, 4, color_code=56, rgb=(0xB3, 0, 0xFF)), Cue(0, 500)]
        lib.save_track_cues(cid, cues)
        back = lib.track_cues(cid)
        assert [(c.slot, c.ms, c.loop_ms, c.loop_beats, c.name, c.color_code) for c in back] == \
            [(1, 500, None, 0, "Intro", 0), (5, 9000, 11000, 4, "", 56), (0, 500, None, 0, "", 0)]
        kinds = sorted(int(k) for (k,) in lib._read("SELECT Kind FROM djmdCue WHERE ContentID = :i", {"i": str(cid)}))
        assert kinds == [0, 1, 6]                                          # E = Kind 6 dans master.db
        assert lib._read("SELECT rb_cue_count FROM contentCue WHERE ContentID = :i", {"i": str(cid)})[0][0] == 3
        lib.save_track_cues(cid, [])                                       # tout effacer
        assert lib.track_cues(cid) == []
        with pytest.raises(Exception):
            lib.save_track_cues(cid, [Cue(1, 0), Cue(1, 500)])            # deux cues sur un même pad
    finally:
        lib.close()


# ============================================================================ C25 : Uniformiser v2
def test_video_id_removed_from_titles():
    from djsync.core.uniformize import clean_title, needs_review, strip_video_id

    assert clean_title("Charger (feat. MC YOSHI, Mauvais djo & Kokosvoice) [Om_gqUBQzll]")[:2] == \
        ("Charger", ["MC YOSHI", "Mauvais djo", "Kokosvoice"])
    assert strip_video_id("X (dQw4w9WgXcQ)") == "X"
    for keep in ("Y [Instrumental]", "Song [Remastered1]", "Z (Extended Mix)"):
        assert strip_video_id(keep) == keep
    from types import SimpleNamespace as N
    assert needs_review(N(title="Charger [Om_gqUBQzll]", artist="", artwork_path="a.jpg"))
    assert needs_review(N(title="Slow", artist="DANNTZ!", artwork_path=None))              # pas de pochette
    assert not needs_review(N(title="Slow", artist="DANNTZ!", artwork_path="a.jpg"))


def test_deezer_cascade_uses_guests_and_duration(monkeypatch):
    from djsync.core import metadata as M

    calls = []

    def hit(i, title, artist, dur):
        return {"id": i, "title": title, "artist": {"name": artist}, "duration": dur, "album": {"title": "A", "id": 0}}

    def fake_get(path, params=None):
        if path == "/search":
            q = params["q"]
            calls.append(q)
            if q == 'artist:"Mauvais djo" track:"Charger"':
                return {"data": [hit(7, "Charger", "Mauvais djo", 200)]}
            return {"data": []}
        if path.startswith("/track/"):
            return {"title": "Charger", "artist": {"name": "Mauvais djo"},
                    "contributors": [{"name": "Mauvais djo"}, {"name": "MC YOSHI"}], "album": {}}
        return {}

    monkeypatch.setattr(M, "_get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: None)
    out = M.match("Charger", "MC YOSHI, Mauvais djo, Kokosvoice", 201, cleaned=True)
    assert out["sure"] and out["artists"] == ["Mauvais djo", "MC YOSHI"] and out["candidates"][0]["id"] == 7
    assert calls.index('artist:"Mauvais djo" track:"Charger"') == 2                # 3e essai, puis arrêt
    assert len(calls) == 3

    # titre seul : jamais « sûr », et la durée doit coller à ± 3 s
    def title_only(path, params=None):
        if path == "/search":
            return {"data": [hit(1, "Namba Namba", "Zola", 180), hit(2, "Namba Namba", "Other", 260)]}
        return {"title": "Namba Namba", "artist": {"name": "Zola"}, "album": {}}

    monkeypatch.setattr(M, "_get", title_only)
    got = M.match("Namba Namba (2015 Revisit)", "", 181, cleaned=True)
    assert got["id"] == 1 and not got["sure"] and got["score"] < M.SURE
    assert M.match("Namba Namba", "", 220, cleaned=True) == {}


def test_manual_search_ranks_by_text_and_duration(monkeypatch):
    from djsync.core import metadata as M

    def fake_get(path, params=None):
        return {"data": [{"id": 1, "title": "Charger", "artist": {"name": "Mauvais djo"}, "duration": 300},
                         {"id": 2, "title": "Charger", "artist": {"name": "Mauvais djo"}, "duration": 201},
                         {"id": 3, "title": "Other", "artist": {"name": "X"}, "duration": 201}]}

    monkeypatch.setattr(M, "_get", fake_get)
    got = M.search_candidates("mauvais djo charger", 200)
    assert [c["id"] for c in got][:2] == [2, 1] and got[-1]["id"] == 3
