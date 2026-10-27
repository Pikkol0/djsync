"""1.3.0-rc.6 : B27 (dossiers d'analyse et lignes d'export.pdb comme Rekordbox)."""
import struct
from pathlib import Path

from djsync.analysis import anlz
from djsync.db.pdb import PdbDatabase, rows
from djsync.db.pdb.file import PdbFile
from djsync.db.pdb.format import T
from djsync.db.pdb.sync import TRACK_REBUILT, Mark, Target, apply, plan

from .pdb_fixture import build_pdb, sample_track
from .test_pdb_sync import make_usb, open_lib, pdb_of
from .test_usb_library import make_wav

REAL = Path(__file__).parent / "data" / "real_export.pdb"


def _real_tracks():
    f = PdbFile(REAL.read_bytes())
    for pg in f.data_pages(T.TRACKS):
        page = f.page(pg)
        for _i, pos in page.present_rows():
            yield rows.read_track(f.data, pg * 4096 + pos)


# ------------------------------------------------------------------ B27 : dossiers
def test_rekordbox_folder_hash_matches_a_real_export():
    """Les 213 pistes d'un vrai export : dossier calculé = dossier écrit par Rekordbox."""
    seen = 0
    for r in _real_tracks():
        ap = r["strings"]["analyze_path"]
        if ap:
            assert anlz.rekordbox_anlz_dir(r["path"]) == ap.rsplit("/", 1)[0], r["path"]
            seen += 1
    assert seen == 213


def _ppth_only(path: str) -> bytes:
    return anlz._file([anlz._ppth(path)])


def test_collision_takes_the_next_number_like_rekordbox(tmp_path):
    a, b = "/Contents/A/a.mp3", "/Contents/B/b.mp3"
    folder = tmp_path / anlz.rekordbox_anlz_dir(a).lstrip("/")
    assert anlz.choose_anlz_base(tmp_path, a).endswith("/ANLZ0000")
    folder.mkdir(parents=True)
    (folder / "ANLZ0000.DAT").write_bytes(_ppth_only(b))     # un autre son a déjà ce dossier
    assert anlz.choose_anlz_base(tmp_path, a) == anlz.rekordbox_anlz_dir(a) + "/ANLZ0001"
    (folder / "ANLZ0001.DAT").write_bytes(_ppth_only(a))     # ce son : on réutilise ses fichiers
    assert anlz.choose_anlz_base(tmp_path, a) == anlz.rekordbox_anlz_dir(a) + "/ANLZ0001"
    assert anlz.choose_anlz_dir(tmp_path, a) == anlz.rekordbox_anlz_dir(a)
    assert anlz.is_anlz_dat("ANLZ0001.DAT") and anlz.is_anlz_dat("anlz0000.dat") and not anlz.is_anlz_dat("x.DAT")


def test_write_files_uses_the_rekordbox_folder_and_keeps_old_cues(tmp_path):
    from djsync.analysis.cues import Cue, read_cues
    from djsync.analysis.waveform import compute_waveforms
    import numpy as np

    path = "/Contents/A/B/x.m4a"
    wf = compute_waveforms(np.zeros(22050 * 2, dtype=np.float32), 22050, 2.0)
    old = anlz.anlz_dir_for(path) + "/ANLZ0000.DAT"                 # emplacement de la rc.5
    (tmp_path / old.lstrip("/")).parent.mkdir(parents=True)
    (tmp_path / old.lstrip("/")).write_bytes(anlz.build_dat(path, [(1, 12800, 0)], wf, cues=[Cue(1, 1500)]))
    rel = anlz.write_files(tmp_path, path, [(1, 12800, 0)], wf, previous=old)
    assert rel == anlz.rekordbox_anlz_dir(path) + "/ANLZ0000.DAT"
    dat = (tmp_path / rel.lstrip("/")).read_bytes()
    assert anlz.read_path(dat) == path
    assert [(c.slot, c.ms) for c in read_cues(dat)] == [(1, 1500)]


# ------------------------------------------------------------- B27 : lignes de pistes
def test_track_rows_take_the_rekordbox_values():
    real = next(_real_tracks())
    template = rows.make_template(real)
    a, b = sample_track(1), sample_track(2)
    m4a = sample_track(3)
    m4a.path, m4a.file_type, m4a.bitrate = "/Contents/x/y/t3.m4a", 4, 256
    out = []
    for meta in (a, b, m4a):
        for tpl in (None, template):
            row = rows.read_track(rows.build_track(meta, 9, 1, 1, 0, tpl), 0)
            fx = row["fixed"]
            assert struct.unpack_from("<HH", fx, 0x18) == (29758, 1535)
            assert 0 < struct.unpack_from("<I", fx, 0x14)[0] < 1 << 28
            assert (row["strings"]["unk2"], row["strings"]["unk3"], row["strings"]["unk4"]) == ("", "1", "")
            out.append((meta.path, struct.unpack_from("<I", fx, 0x14)[0], struct.unpack_from("<I", fx, 0x30)[0]))
    assert len({x[1] for x in out}) == 3                        # propre à chaque son (plus celui du modèle)
    assert {x[2] for x in out if x[0].endswith(".m4a")} == {0}  # m4a : débit à 0, comme Rekordbox
    assert {x[2] for x in out if x[0].endswith(".mp3")} == {320}


def test_rebuild_mark_rewrites_a_track_row_with_the_same_id():
    old = sample_track(1)
    old.analyze_path = "/PIONEER/USBANLZ/P123/00ABCDEF/ANLZ0000.DAT"
    db = PdbDatabase(build_pdb([old, sample_track(2)], {("Rap",): [old.path]}))
    tid = db.track_row(old.path)["id"]
    new = sample_track(1)
    new.analyze_path = anlz.rekordbox_anlz_dir(new.path) + "/ANLZ0000.DAT"
    target = Target([new, sample_track(2)], [(("Rap",), False, [new.path])])
    assert plan(db, target).empty                               # sans marque : jamais réécrite
    marks = [Mark(TRACK_REBUILT, (new.path,))]
    p = plan(db, target, marks)
    assert [m.path for m in p.rebuild_tracks] == [new.path] and p.resolved == marks
    assert "1 track(s) to rewrite" in p.describe()
    apply(db, p)
    row = db.track_row(new.path)
    assert row["id"] == tid and row["strings"]["analyze_path"] == new.analyze_path
    assert db.playlist_tracks(("Rap",)) == [new.path.casefold()] or db.playlist_tracks(("Rap",)) == [new.path]


# ------------------------------------------------------------------ B27 : migration
def _give_old_analysis(lib, track):
    """Analyse « à l'ancienne » (rc.5) : dossier au hachage de DJSync, citée par la base et export.pdb."""
    old = anlz.anlz_dir_for(track.path) + "/ANLZ0000.DAT"
    dat = lib.drive.root / old.lstrip("/")
    dat.parent.mkdir(parents=True, exist_ok=True)
    dat.write_bytes(_ppth_only(track.path))
    dat.with_suffix(".EXT").write_bytes(_ppth_only(track.path))
    with lib._write() as conn:
        conn.execute("UPDATE content SET analysisDataFilePath = ? WHERE content_id = ?", (old, track.content_id))
        lib._stage_tracks(conn, [track.content_id])
    return old


def test_migration_moves_djsync_analysis_and_rewrites_export_pdb(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        old_a = _give_old_analysis(lib, a)
        assert pdb_of(usb).track_row(a.path)["strings"]["analyze_path"] == old_a
        before = {p: pdb_of(usb).track_row(p)["id"] for p in (a.path, b.path)}
        assert lib.migrate_analysis() == 1
        new_a = anlz.rekordbox_anlz_dir(a.path) + "/ANLZ0000.DAT"
        assert lib.get_track(a.content_id).analysis_path == new_a
        assert (usb / new_a.lstrip("/")).is_file() and (usb / new_a.lstrip("/")).with_suffix(".EXT").is_file()
        assert not (usb / old_a.lstrip("/")).exists()                  # ancien effacé, export.pdb à jour
        assert not (usb / old_a.lstrip("/")).parent.exists()
        pdb = pdb_of(usb)
        assert pdb.track_row(a.path)["strings"]["analyze_path"] == new_a
        assert {p: pdb.track_row(p)["id"] for p in (a.path, b.path)} == before
        markers = {struct.unpack_from("<I", pdb.track_row(p)["fixed"], 0x14)[0] for p in (a.path, b.path)}
        assert len(markers) == 2                                       # lignes refaites une fois pour tous
        assert lib.pdb_status().state == "ok"
        assert lib.migrate_analysis() == 0                             # rien de plus à l'ouverture suivante
    # le natif n'est jamais déplacé : la clé de test n'a que des sons DJSync ; un son natif garde son chemin
    with open_lib(usb, analyze=False) as lib:
        assert lib.migrate_analysis() == 0


def test_migration_never_touches_rekordbox_tracks_or_foreign_files(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        old_a = _give_old_analysis(lib, a)
        old_b = _give_old_analysis(lib, b)
        (usb / old_b.lstrip("/")).write_bytes(_ppth_only("/Contents/autre/son.mp3"))   # pas le sien
        with lib._write() as conn:                                    # a devient un son « de Rekordbox »
            conn.execute("UPDATE content SET masterDbId = 7 WHERE content_id = ?", (a.content_id,))
        assert lib.migrate_analysis() == 0
        assert lib.get_track(a.content_id).analysis_path == old_a and (usb / old_a.lstrip("/")).is_file()
        assert lib.get_track(b.content_id).analysis_path == old_b and (usb / old_b.lstrip("/")).is_file()


def test_old_files_stay_until_export_pdb_is_up_to_date(tmp_path, monkeypatch):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        old_a = _give_old_analysis(lib, a)
        real_flush = lib._pdb_flush
        monkeypatch.setattr(lib, "_pdb_flush", lambda: None)          # export.pdb pas réécrit (Rekordbox…)
        assert lib.migrate_analysis() == 1
        assert (usb / old_a.lstrip("/")).is_file()                      # export.pdb cite encore l'ancien
        monkeypatch.setattr(lib, "_pdb_flush", real_flush)
        lib.pdb_catch_up()
        assert lib.migrate_analysis() == 0
        assert not (usb / old_a.lstrip("/")).exists()


def test_delete_track_removes_anlz0001_files(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        base = anlz.rekordbox_anlz_dir(a.path) + "/ANLZ0001.DAT"
        dat = usb / base.lstrip("/")
        dat.parent.mkdir(parents=True)
        dat.write_bytes(_ppth_only(a.path))
        with lib._write() as conn:
            conn.execute("UPDATE content SET analysisDataFilePath = ? WHERE content_id = ?", (base, a.content_id))
        lib.delete_track(a.content_id)
        assert not dat.exists()


def test_duration_is_truncated_like_rekordbox(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False) as lib:
        f = make_wav(lib, "A", "a")                                    # 1 s exactement
        import wave
        with wave.open(str(f), "wb") as w:                             # 1,9 s : Rekordbox écrit 1
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes(struct.pack("<hh", 0, 0) * int(44100 * 1.9))
        assert lib._probe_audio(f)["length"] == 1


def test_new_analysis_goes_straight_to_the_rekordbox_folder(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=True, artwork=False) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert a.analysis_path == anlz.rekordbox_anlz_dir(a.path) + "/ANLZ0000.DAT"
        assert pdb_of(usb).track_row(a.path)["strings"]["analyze_path"] == a.analysis_path
        assert lib.migrate_analysis() == 0
