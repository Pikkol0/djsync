"""V1.1-A4 : analyse audio (BPM, grille, tonalité), fichiers ANLZ, pochettes, date d'ajout.

Les morceaux sont synthétiques (vérité terrain exacte, voir audio_fixture.py). Les constantes ANLZ
attendues sont celles de VRAIS fichiers exportés par Rekordbox 6 (relevées octet par octet).
    pytest -q tests/test_analysis.py
"""
import struct
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from djsync.analysis import analyze_file, write_anlz
from djsync.analysis import anlz
from djsync.analysis.key import analyze_key
from djsync.analysis.tempo import analyze_tempo
from djsync.db.usb_library import format_date_like

from .audio_fixture import HAS_FFMPEG, SR, cover_png, song, write_m4a, write_wav

REAL_PDB = Path(__file__).parent / "data" / "real_export.pdb"
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg absent")


def _resample(y: np.ndarray, factor: float) -> np.ndarray:
    pos = np.arange(0, y.size - 1, factor)
    return np.interp(pos, np.arange(y.size), y).astype(np.float32)


def _to22k(y: np.ndarray) -> np.ndarray:
    from djsync.analysis.decode import _resample as lowpass_resample   # avec filtre anti-repliement

    return lowpass_resample(y, SR, 22050)


# ------------------------------------------------------------------ BPM / grille / tonalité
CASES = [  # bpm, 1er temps fort (s), accords, mineurs, tonalité attendue, Camelot
    (128.0, 0.37, ["A", "F", "E", "A"], [1, 0, 0, 1], "Am", "8A"),
    (92.46, 0.81, ["F#", "D", "C#", "F#"], [1, 0, 0, 1], "F#m", "11A"),
    (75.0, 0.20, ["C", "F", "G", "C"], [1, 1, 0, 1], "Cm", "5A"),       # i-iv-V-i (sans ambiguïté)
    (174.0, 0.10, ["D", "Bb", "A", "D"], [1, 0, 0, 1], "Dm", "7A"),
    (124.0, 0.05, ["E", "A", "B", "E"], [0, 0, 0, 0], "E", "12B"),
]


@pytest.mark.parametrize("bpm,first,chords,minors,key,camelot", CASES)
def test_tempo_grid_and_key(bpm, first, chords, minors, key, camelot):
    y = _to22k(song(bpm, first, 60, chords, minors))
    grid = analyze_tempo(y, 22050)
    # octave : règle de Rekordbox (rapide sous 168, moitié au-dessus) -> 75 s'affiche 150, 174 -> 87
    expected = bpm * 2 if bpm < 90 else (bpm / 2 if bpm >= 168 else bpm)
    assert abs(grid.bpm - expected) <= 0.02, grid.bpm
    beat = 60.0 / bpm
    # chaque temps de la grille tombe sur un vrai temps (ou un demi-temps si tempo doublé), à ±6 ms
    step = 60.0 / max(grid.bpm, bpm)
    phase = (grid.first_beat - first) % step
    assert min(phase, step - phase) <= 0.006
    if expected == bpm:
        downbeats = [t for n, t in grid.beats if n == 1]
        assert abs(downbeats[0] - first) <= 0.006                   # 1er temps fort à ±6 ms
        assert abs(grid.first_beat - first % beat) <= 0.006
    assert all(1 <= n <= 4 for n, _ in grid.beats)
    res = analyze_key(y, 22050)
    assert (res.name, res.camelot) == (key, camelot)


def test_octave_rule_matches_rekordbox():
    from djsync.analysis.tempo import OCTAVE_SLOW_FROM, _choose_octave

    env = np.random.default_rng(0).random(5000)
    assert OCTAVE_SLOW_FROM == 168.0
    assert _choose_octave(env, env, 86.0, 120.0) == 120.0       # moitié hors plage : inchangé
    assert _choose_octave(env, env, 86.0, 150.0) == 150.0       # 75/150 : Rekordbox affiche 150 le plus souvent
    assert _choose_octave(env, env, 86.0, 174.0) == 87.0        # 87/174 : Rekordbox affiche 87


@pytest.mark.parametrize("start,end", [(120.0, 126.0), (126.0, 121.0)])
def test_variable_tempo_gets_a_following_grid(start, end):
    """Tempo qui change (live, raccord) : la grille suit chaque temps au lieu de dériver."""
    truth = []
    y = _to22k(song(start, 0.3, 120, ["A", "F", "E", "A"], [1, 0, 0, 1], bpm_end=end, beats_out=truth))
    grid = analyze_tempo(y, 22050)
    assert grid.variable
    truth = np.array(truth)
    err = [np.min(np.abs(truth - t)) for _, t in grid.beats if t > 0.2]
    assert np.max(err) <= 0.010                                         # chaque temps à ±10 ms
    tempos = grid.beat_tempos()
    assert tempos[0] != tempos[-1] and min(start, end) - 1 < np.median(tempos) < max(start, end) + 1


def test_constant_tempo_keeps_a_constant_grid():
    grid = analyze_tempo(_to22k(song(124, 0.3, 90, ["A", "F", "E", "A"], [1, 0, 0, 1])), 22050)
    assert not grid.variable and set(grid.beat_tempos()) == {124.0}


def test_key_survives_detuned_upload():
    """Vidéo accélérée de +35 centièmes de demi-ton : la tonalité reste juste (accordage estimé)."""
    y = _to22k(song(124, 0.1, 45, ["A", "F", "E", "A"], [1, 0, 0, 1]))
    shifted = _resample(y, 2 ** (35 / 1200))
    res = analyze_key(shifted, 22050)
    assert res.name == "Am" and 25 <= res.tuning_cents <= 45


@needs_ffmpeg
def test_mp3_priming_is_restored_like_rekordbox(tmp_path):
    """Rekordbox/les platines comptent le silence d'amorçage MP3 (FFmpeg le retire) : mesuré à 24,6 ms
    sur 102 MP3 réels. La grille d'un MP3 doit donc tomber ~25 ms après celle du WAV d'origine."""
    import subprocess
    from djsync.analysis.decode import decode, mp3_priming_samples

    wav = write_wav(tmp_path / "s.wav", song(128, 0.37, 30, ["A", "F", "E", "A"], [1, 0, 0, 1]))
    mp3 = tmp_path / "s.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)],
                   check=True)
    priming = mp3_priming_samples(mp3)
    assert priming == 576 + 529                                         # en-tête LAME standard
    g_wav = analyze_tempo(decode(wav).samples, 22050)
    g_mp3 = analyze_tempo(decode(mp3).samples, 22050)
    assert abs((g_mp3.first_beat - g_wav.first_beat) - priming / 44100) <= 0.004


def test_silence_gives_no_tempo_no_key():
    y = np.zeros(22050 * 10, dtype=np.float32)
    assert analyze_tempo(y, 22050).bpm == 0 and analyze_key(y, 22050).name is None


def test_analyze_file_wav_without_ffmpeg(tmp_path, monkeypatch):
    import djsync.analysis.decode as dec

    monkeypatch.setattr(dec, "find_ffmpeg", lambda loc=None: None)
    f = write_wav(tmp_path / "x.wav", song(128, 0.37, 30, ["A", "F", "E", "A"], [1, 0, 0, 1]))
    r = analyze_file(f)
    assert abs(r.bpm - 128) < 0.02 and r.key.camelot == "8A"
    assert r.waveforms.detail_count == int(np.ceil(r.duration * 150))


# ------------------------------------------------------------------------------ ANLZ
# En-têtes relevés sur de vrais ANLZ0000.DAT / .EXT exportés par Rekordbox 6
REAL_PMAI_TAIL = bytes.fromhex("00000001 00010000 00010000 00000000".replace(" ", ""))


def _result(seconds=20):
    y = _to22k(song(128, 0.37, seconds, ["A", "F", "E", "A"], [1, 0, 0, 1]))
    from djsync.analysis import AnalysisResult
    from djsync.analysis.waveform import compute_waveforms

    return AnalysisResult(y.size / 22050, analyze_tempo(y, 22050), analyze_key(y, 22050),
                          compute_waveforms(y, 22050, y.size / 22050))


def test_anlz_files_match_rekordbox_layout(tmp_path):
    r = _result()
    rel = write_anlz(tmp_path, "/Contents/A/B/x.m4a", r, file_type=4)
    assert rel.startswith("/PIONEER/USBANLZ/P") and rel.endswith("/ANLZ0000.DAT")
    dat = (tmp_path / rel.lstrip("/")).read_bytes()
    ext = (tmp_path / rel.lstrip("/")).with_suffix(".EXT").read_bytes()
    for blob in (dat, ext):
        assert blob[:4] == b"PMAI" and struct.unpack(">II", blob[4:12]) == (0x1C, len(blob))
        assert blob[12:28] == REAL_PMAI_TAIL
    d, e = anlz.parse(dat), anlz.parse(ext)
    assert list(d) == ["PPTH", "PVBR", "PQTZ", "PWAV", "PWV2", "PCOB"] and len(d["PCOB"]) == 2
    assert list(e) == ["PPTH", "PWV3", "PCOB", "PCO2", "PWV5", "PWV4"]
    # constantes d'en-tête identiques aux fichiers Rekordbox
    assert d["PQTZ"][0][0][:8] == bytes.fromhex("0000000000080000")
    assert d["PWAV"][0][0] == bytes.fromhex("0000019000010000")
    assert d["PWV2"][0][0] == bytes.fromhex("0000006400010000")
    assert [h for h, _ in d["PCOB"]] == [bytes.fromhex("0000000100000000ffffffff"), bytes.fromhex("0000000000000000ffffffff")]
    assert [h for h, _ in e["PCO2"]] == [bytes.fromhex("0000000100000000"), bytes.fromhex("0000000000000000")]
    n = r.waveforms.detail_count
    assert e["PWV3"][0][0] == struct.pack(">III", 1, n, 0x00960000)
    assert e["PWV5"][0][0] == struct.pack(">III", 2, n, 0x00960305)
    assert e["PWV4"][0][0] == struct.pack(">III", 6, 1200, 0)
    assert len(d["PVBR"][0][1]) == 1604 and len(e["PWV4"][0][1]) == 7200
    assert anlz.read_path(dat) == anlz.read_path(ext) == "/Contents/A/B/x.m4a"
    beats = d["PQTZ"][0][1]
    nb, tempo, ms = struct.unpack(">HHI", beats[:8])
    assert tempo == 12800 and abs(ms - 370) <= 6


def test_2ex_three_band_waveforms_match_rekordbox_layout(tmp_path):
    """V0.3.0 : .2EX (PWV7 / PWV6 / PWVC) écrit comme Rekordbox ; sans lui Rekordbox 6/7 réglé sur
    « 3Band » affichait un aperçu bleu des sons DJSync (liste et aperçu du morceau entier)."""
    r = _result()
    rel = write_anlz(tmp_path, "/Contents/A/B/x.m4a", r, file_type=4)
    two = (tmp_path / rel.lstrip("/")).with_suffix(".2EX").read_bytes()
    assert two[:4] == b"PMAI" and two[12:28] == REAL_PMAI_TAIL
    t = anlz.parse(two)
    assert list(t) == ["PPTH", "PWV7", "PWV6", "PWVC"]
    n = r.waveforms.detail_count
    assert t["PWV7"][0][0] == struct.pack(">III", 3, n, 0x00960000) and len(t["PWV7"][0][1]) == 3 * n
    assert t["PWV6"][0][0] == struct.pack(">II", 3, 1200) and len(t["PWV6"][0][1]) == 3600
    assert t["PWVC"][0][0] == b"\x00\x00" and len(t["PWVC"][0][1]) == 6       # en-tête de 14 octets, comme les vrais
    assert max(t["PWV7"][0][1]) <= 127 and max(t["PWV6"][0][1]) <= 127 and any(t["PWV6"][0][1])
    assert anlz.read_path(two) == "/Contents/A/B/x.m4a"


def test_anlz_parsed_by_independent_reader(tmp_path):
    pyrekordbox = pytest.importorskip("pyrekordbox.anlz")
    r = _result()
    rel = write_anlz(tmp_path, "/Contents/A/B/x.mp3", r, file_type=1, native_sr=44100)
    dat = pyrekordbox.AnlzFile.parse_file(str(tmp_path / rel.lstrip("/")))
    ext = pyrekordbox.AnlzFile.parse_file(str((tmp_path / rel.lstrip("/")).with_suffix(".EXT")))
    assert dat.get("path") == "/Contents/A/B/x.mp3"
    nums, bpms, times = dat.get("beat_grid")
    assert set(np.unique(bpms)) == {128.0} and abs(times[0] - 0.37) < 0.006 and nums[0] == 1
    heights, colors = ext.get("wf_color_detail")
    # (pyrekordbox décale le rouge d'un bit de trop : 0..14 ; vert et bleu 0..7)
    assert heights.max() == 1.0 and colors[:, 0].max() <= 14 and colors[:, 1:].max() <= 7
    assert dat.build() == (tmp_path / rel.lstrip("/")).read_bytes()           # relu puis reconstruit à l'identique
    two = pyrekordbox.AnlzFile.parse_file(str((tmp_path / rel.lstrip("/")).with_suffix(".2EX")))
    assert {tag.type for tag in two.tags} >= {"PWV6", "PWV7"}


def test_anlz_dir_never_overwrites_another_track(tmp_path):
    r = _result(8)
    rel_a = write_anlz(tmp_path, "/Contents/a.m4a", r, 4)
    assert write_anlz(tmp_path, "/Contents/a.m4a", r, 4) == rel_a              # même son : même dossier
    # dossier attendu occupé par un AUTRE son -> dossier suivant
    target = tmp_path / anlz.anlz_dir_for("/Contents/b.m4a").lstrip("/")
    target.mkdir(parents=True)
    (target / "ANLZ0000.DAT").write_bytes(anlz.build_dat("/Contents/zzz.m4a", [], r.waveforms))
    rel_b = write_anlz(tmp_path, "/Contents/b.m4a", r, 4)
    assert rel_b != anlz.anlz_dir_for("/Contents/b.m4a") + "/ANLZ0000.DAT"
    assert anlz.read_path((target / "ANLZ0000.DAT").read_bytes()) == "/Contents/zzz.m4a"


def test_mp3_pvbr_holds_total_samples(tmp_path):
    r = _result(8)
    rel = write_anlz(tmp_path, "/Contents/x.mp3", r, file_type=1, native_sr=44100)
    body = anlz.parse((tmp_path / rel.lstrip("/")).read_bytes())["PVBR"][0][1]
    assert struct.unpack(">I", body[-4:])[0] == int(round(r.duration * 44100))   # comme Rekordbox pour un mp3


# ------------------------------------------------------------------------------ dates
NOW = datetime(2026, 10, 20, 11, 23, 45, 123456, tzinfo=timezone.utc)


@pytest.mark.parametrize("sample,expected", [
    (None, "2026-10-20 11:23:45.123 +00:00"),                       # base vide : format OneLibrary complet
    ("2025-04-12 19:11:29.274 +00:00", "2026-10-20 11:23:45.123 +00:00"),
    ("2025-04-12T19:11:29Z", "2026-10-20T11:23:45Z"),
    ("2024-10-18", None),                                            # date seule : date locale
])
def test_date_follows_native_format(sample, expected):
    out = format_date_like(sample, NOW)
    if expected is None:
        assert out == NOW.astimezone().strftime("%Y-%m-%d")
    else:
        assert out == expected


# ------------------------------------------------------------------- bibliothèque (clé)
from djsync.db.pdb import PdbDatabase  # noqa: E402

from .test_pdb_sync import make_usb, open_lib  # noqa: E402


def _native_rows(usb: Path):
    from sqlcipher3 import dbapi2 as sqlcipher
    from djsync.db._key import get_default_key

    conn = sqlcipher.connect(str(usb / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    for name in ("Cm", "Am", "F#m"):
        conn.execute("INSERT INTO key (name) VALUES (?)", (name,))
    conn.execute("INSERT INTO content (title, path, fileName, fileSize, fileType, dateAdded, masterDbId, "
                 "analysisDataFilePath, analysedBits, color_id) VALUES ('natif', '/Contents/n.mp3', 'n.mp3', 1, 1, "
                 "'2025-04-12 19:11:29.274 +00:00', 77, '/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT', 7, 0)")
    conn.commit()
    conn.close()


def _m4a(lib, name, bpm=128.0, chords=("A", "F", "E", "A"), minors=(1, 0, 0, 1), cover=True):
    folder = lib.default_download_dir("Synth")
    folder.mkdir(parents=True, exist_ok=True)
    return write_m4a(folder / f"{name}.m4a", song(bpm, 0.37, 30, chords, minors), cover_png() if cover else None)


@needs_ffmpeg
@pytest.mark.skipif(not REAL_PDB.is_file(), reason="export réel absent")
def test_added_track_is_cdj_ready_in_both_databases(tmp_path):
    from PIL import Image

    usb = make_usb(tmp_path, pdb_bytes=REAL_PDB.read_bytes())
    _native_rows(usb)
    with open_lib(usb) as lib:
        t = lib.add_track(_m4a(lib, "am128"), "Am 128", "Synth", None, None, [1])
        # (état « stale » attendu : la ligne native de test n'existe pas dans le vrai export.pdb)
        assert lib.last_problems == [] and lib.pdb_problem == "" and lib.pdb_last_summary.tracks_added == 1
        row = lib._read("SELECT c.bpmx100, k.name, im.path, c.analysisDataFilePath, c.analysedBits, c.dateAdded, "
                        "c.dateCreated FROM content c LEFT JOIN key k ON k.key_id = c.key_id "
                        "LEFT JOIN image im ON im.image_id = c.image_id WHERE c.content_id = ?", (t.content_id,))[0]
        bpmx100, key, art, anlz_path, bits, added, created = row
    assert bpmx100 == 12800 and key == "Am"                      # « auto » : notation déjà présente sur la clé
    assert t.camelot == "8A" and t.is_analysed and abs(t.bpm - 128) < 0.01
    assert bits == 7                                              # convention des sons natifs recopiée
    assert len(added) == len("2026-10-20 11:23:45.123 +00:00") and added.endswith("+00:00") and added == created
    # pochettes : numérotation après les 136 de l'export réel, 80 et 240 px
    # (comme sur la vraie clé : bN.jpg pour exportLibrary.db, aN.jpg pour export.pdb, mêmes octets)
    assert art == "/PIONEER/Artwork/00007/b137.jpg"
    for name, size in (("a137.jpg", 80), ("a137_m.jpg", 240), ("b137.jpg", 80), ("b137_m.jpg", 240)):
        assert Image.open(usb / "PIONEER" / "Artwork" / "00007" / name).size == (size, size)
    assert (usb / art.lstrip("/")).read_bytes() == (usb / art.lstrip("/").replace("/b137", "/a137")).read_bytes()
    assert (usb / anlz_path.lstrip("/")).is_file() and (usb / anlz_path.lstrip("/")).with_suffix(".EXT").is_file()
    # export.pdb : même chemin d'analyse, tonalité « Am » existante (id 10), pochette 137, BPM, date
    pdb = PdbDatabase((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes())
    r = pdb.track_row(t.path)
    assert r["bpmx100"] == 12800 and r["key_id"] == 10 and r["artwork_id"] == pdb.artwork_id("/PIONEER/Artwork/00007/a137.jpg") == 137
    assert r["strings"]["analyze_path"] == anlz_path and r["strings"]["date_added"] == added[:10]
    assert r["strings"]["analyze_date"] == added[:10]


@needs_ffmpeg
def test_key_notation_camelot_and_album_artwork_reuse(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb, key_notation="camelot") as lib:
        a = lib.add_track(_m4a(lib, "a"), "a", "Synth", "Album X")
        b = lib.add_track(_m4a(lib, "b"), "b", "Synth", "Album X")
        assert a.key == "8A" and b.key == "8A" and a.artwork_path == b.artwork_path   # pochette d'album partagée
        assert lib._read("SELECT COUNT(*) FROM key")[0][0] == 1 and lib._read("SELECT COUNT(*) FROM image")[0][0] == 1
    pdb = PdbDatabase((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes())
    assert pdb.track_row(a.path)["key_id"] == pdb.key_id("8A") != 0


@needs_ffmpeg
def test_old_djsync_track_is_upgraded_in_place(tmp_path):
    """Son ajouté sans analyse (version précédente) : analyze_missing le complète ; dans export.pdb la
    ligne garde le MÊME id, donc les playlists restent valides."""
    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=False, artwork=False) as lib:
        t = lib.add_track(_m4a(lib, "old", cover=True), "old", "Synth", None, None, [1])
        assert not t.is_analysed and t.artwork_path is None
    before = PdbDatabase((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes())
    old_id = before.track_row(t.path)["id"]
    assert before.track_row(t.path)["strings"]["analyze_path"] == ""
    with open_lib(usb) as lib:
        assert [x.content_id for x in lib.unanalysed_tracks()] == [t.content_id]
        assert lib.analyze_missing() == (1, 0)
        t2 = lib.get_track(t.content_id)
        assert t2.is_analysed and t2.key == "8A" and t2.artwork_path and abs(t2.bpm - 128) < 0.01
        assert lib.pdb_last_summary.tracks_updated == 1
        assert lib.unanalysed_tracks() == []
    after = PdbDatabase((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes())
    row = after.track_row(t.path)
    assert row["id"] == old_id and row["strings"]["analyze_path"] and row["bpmx100"] == 12800
    node = after.find_playlist(("Rap",))
    assert [e.track for e in after._ordered_entries(node.id)] == [old_id] and after.track_count == before.track_count


def test_analysis_failure_never_blocks_the_add(tmp_path, monkeypatch):
    import djsync.analysis as analysis

    def boom(*a, **k):
        raise RuntimeError("décodeur en panne")

    monkeypatch.setattr(analysis, "analyze_file", boom)
    usb = make_usb(tmp_path)
    from .test_usb_library import make_wav

    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A")
        assert not t.is_analysed and lib.track_count() == 1
        assert any("décodeur en panne" in p for p in lib.last_problems)


def test_reanalysis_is_skipped_for_analysed_and_native_tracks(tmp_path):
    usb = make_usb(tmp_path)
    _native_rows(usb)
    from .test_usb_library import make_wav

    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A")
        dat = lib.absolute_path(lib._read("SELECT analysisDataFilePath FROM content WHERE content_id=?",
                                          (t.content_id,))[0][0])
        stamp = dat.stat().st_mtime_ns
        lib.add_track(lib.absolute_path(t), "a", "A", playlist_ids=[1])      # ré-ajout : pas de réanalyse
        assert dat.stat().st_mtime_ns == stamp
        native = lib._read("SELECT content_id FROM content WHERE masterDbId IS NOT NULL")[0][0]
        assert lib.analyze_track(native, force=True).path == "/Contents/n.mp3"   # natif : jamais touché
        assert lib.unanalysed_tracks() == []


def test_delete_track_removes_its_analysis_files(tmp_path):
    usb = make_usb(tmp_path)
    from .test_usb_library import make_wav

    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A")
        rel = lib._read("SELECT analysisDataFilePath FROM content")[0][0]
        dat = usb / rel.lstrip("/")
        assert dat.is_file()
        assert lib.delete_track(t.content_id) is True
        assert not dat.exists() and not dat.with_suffix(".EXT").exists() and not dat.parent.exists()
