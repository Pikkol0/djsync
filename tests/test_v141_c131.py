"""1.4.1 : C131 (D20, réanalyser un son analysé par Rekordbox) et B96 (cues illisibles : rien de réécrit)."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from djsync.analysis import anlz
from djsync.analysis.cues import Cue
from djsync.db.errors import LibraryError
from djsync.db.library import metadata as M

from .audio_fixture import HAS_FFMPEG, song, write_wav
from .test_local_library import local, make_wav as local_wav  # noqa: F401 (fixture)
from .test_pdb_sync import make_usb, open_lib, pdb_of

def _song(bpm, seconds):
    return song(bpm, 0.37, seconds, ("A", "F", "E", "A"), (1, 0, 0, 1))


WAVE_TAGS = {"PWAV", "PWV2", "PWV3", "PWV4", "PWV5", "PWV6", "PWV7", "PWVC"}


def _tag(code: bytes, body: bytes) -> bytes:
    return code + struct.pack(">II", 12, 12 + len(body)) + body


def _tags(path: Path) -> dict:
    """{code: [octets bruts]} d'un fichier d'analyse."""
    out: dict = {}
    for code, raw in anlz.iter_tags(path.read_bytes()):
        out.setdefault(code, []).append(raw)
    return out


def _changed(before: dict, path: Path) -> set:
    after = _tags(path)
    return {code for code in set(before) | set(after) if before.get(code) != after.get(code)}


def _like_rekordbox(dat: Path) -> None:
    """Donne aux fichiers ce que seul Rekordbox écrit : table PVBR remplie, PQT2 et PSSI, autre grille."""
    data = dat.read_bytes()
    pvbr = anlz._tag(b"PVBR", struct.pack(">I", 0), bytes(range(256)) * 6 + b"\x07" * 64 + struct.pack(">I", 1234))
    beats = [(n, 12700, ms + 9) for n, _t, ms in anlz.read_beats(data)]
    dat.write_bytes(anlz.replace_beats(anlz.rebuild(data, {"PVBR": pvbr}), beats))
    ext = dat.with_suffix(".EXT")
    body = b"".join(raw for _c, raw in anlz.iter_tags(ext.read_bytes()))
    ext.write_bytes(anlz._file([body, _tag(b"PQT2", b"\x01" * 40), _tag(b"PSSI", b"\x02" * 64)]))
    for f in (dat, ext, dat.with_suffix(".2EX")):                     # formes d'onde « de Rekordbox » : autres octets
        if f.is_file():
            swap = {}
            for code, raw in anlz.iter_tags(f.read_bytes()):
                if code in WAVE_TAGS:
                    lh = struct.unpack(">I", raw[4:8])[0]
                    swap[code] = raw[:lh] + bytes((b + 1) & 0x7F for b in raw[lh:])
            f.write_bytes(anlz.rebuild(f.read_bytes(), swap))


@pytest.fixture
def usb_native(tmp_path):
    """Clé avec un son « analysé par Rekordbox » (masterDbId, PQT2, PSSI, PVBR, 2 cues) et un son de DJSync."""
    usb = make_usb(tmp_path)
    lib = open_lib(usb, analyze=True)
    folder = lib.default_download_dir("Synth")
    folder.mkdir(parents=True, exist_ok=True)
    nat = lib.add_track(write_wav(folder / "nat.wav", _song(128.0, 20)), "Nat", "Synth")
    own = lib.add_track(write_wav(folder / "own.wav", _song(124.0, 20)), "Own", "Synth")
    lib.save_track_cues(nat.content_id, [Cue(1, 1500, name="drop"), Cue(0, 4000)])
    dat = lib.absolute_path(lib.get_track(nat.content_id).analysis_path)
    _like_rekordbox(dat)
    with lib._write() as conn:
        conn.execute("INSERT INTO key (name) VALUES ('Fm')")
        fm = conn.execute("SELECT key_id FROM key WHERE name = 'Fm'").fetchone()[0]
        conn.execute("UPDATE content SET masterDbId = 77, bpmx100 = 12700, key_id = ? WHERE content_id = ?",
                     (fm, nat.content_id))
    yield lib, nat.content_id, own.content_id, dat
    lib.close()


def _row(lib, cid):
    return lib._read("SELECT c.bpmx100, k.name, c.masterDbId, c.analysisDataFilePath FROM content c "
                     "LEFT JOIN key k ON k.key_id = c.key_id WHERE c.content_id = ?", (cid,))[0]


needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg absent")


# ------------------------------------------------------------------------- greffe (anlz.py)
def test_graft_validates_and_keeps_everything_else(usb_native):
    _lib, _nat, _own, dat = usb_native
    files = {s: dat.with_suffix(s).read_bytes() for s in (".DAT", ".EXT", ".2EX") if dat.with_suffix(s).is_file()}
    assert anlz.graft(files) == {}                                   # rien demandé : rien à écrire
    with pytest.raises(ValueError):
        anlz.graft({".EXT": files[".EXT"]})
    with pytest.raises(ValueError):
        anlz.graft({**files, ".EXT": files[".EXT"][:-5]})            # tronqué : illisible, rien à écrire
    new = anlz.graft(files, beats=[(1, 12800, 10), (2, 12800, 479)])
    assert set(new) == {".DAT", ".EXT"}
    assert anlz.read_beats(new[".DAT"]) == [(1, 12800, 10), (2, 12800, 479)]
    assert anlz.cue_tags(new[".DAT"]) == anlz.cue_tags(files[".DAT"])
    assert anlz.cue_tags(new[".EXT"]) == anlz.cue_tags(files[".EXT"])


def test_with_cues_of_is_byte_exact_when_cues_did_not_move(usb_native):
    _lib, _nat, _own, dat = usb_native
    original = dat.read_bytes()
    grafted = anlz.graft({".DAT": original}, beats=[(1, 12800, 10), (2, 12800, 479)])[".DAT"]
    assert anlz.with_cues_of(original, grafted) == original


# ----------------------------------------------------------------------------- clé USB
def test_native_track_is_skipped_without_reanalyse_or_without_choice(usb_native):
    lib, nat, _own, dat = usb_native
    before = {s: dat.with_suffix(s).read_bytes() for s in (".DAT", ".EXT")}
    lib.native_parts = ("grid", "key", "waves")
    assert lib.analyze_tracks([nat]) == (0, 1, 0)                    # sans « Analyser à nouveau »
    lib.native_parts = ()
    assert lib.analyze_tracks([nat], force=True) == (0, 1, 0)        # rien de choisi : laissé tel quel
    assert {s: dat.with_suffix(s).read_bytes() for s in before} == before
    assert not lib.has_rekordbox_original(nat) and lib.native_ids([nat, _own]) == {nat}


@pytest.mark.parametrize("parts", [("grid",), ("key",), ("waves",), ("grid", "key"), ("grid", "waves"),
                                   ("key", "waves"), ("grid", "key", "waves")])
def test_each_choice_changes_only_its_tags(usb_native, parts):
    lib, nat, _own, dat = usb_native
    files = [dat.with_suffix(s) for s in (".DAT", ".EXT", ".2EX") if dat.with_suffix(s).is_file()]
    before = {f: _tags(f) for f in files}
    cues = lib.track_cues(nat)
    lib.native_parts = parts
    assert lib.analyze_tracks([nat], force=True) == (1, 0, 0)
    changed = set().union(*(_changed(before[f], f) for f in files))
    expected = set()
    if "grid" in parts:
        expected |= {"PQTZ", "PQT2", "PSSI"}
    if "waves" in parts:
        expected |= WAVE_TAGS
    assert changed <= expected and ("PQTZ" in changed) == ("grid" in parts)
    assert bool(changed & WAVE_TAGS) == ("waves" in parts)
    for f in files:                                                   # cues, PVBR, PPTH : à l'octet près
        after = _tags(f)
        for code in ("PCOB", "PCO2", "PVBR", "PPTH"):
            assert after.get(code) == before[f].get(code)
        assert ("PQT2" in after or "PSSI" in after) == ("grid" not in parts and f.suffix == ".EXT")
    assert lib.track_cues(nat) == cues
    bpm, key, master, path = _row(lib, nat)
    assert master == 77 and lib.absolute_path(path) == dat           # marque d'origine et chemin gardés
    assert (bpm == 12800) == ("grid" in parts) and (key != "Fm") == ("key" in parts)
    assert lib.has_rekordbox_original(nat)
    if "grid" in parts:
        assert pdb_of(lib.drive.root).track_row(lib.get_track(nat).path)["bpmx100"] == 12800


def test_original_is_kept_once_and_restored_byte_for_byte(usb_native):
    lib, nat, _own, dat = usb_native
    files = [dat.with_suffix(s) for s in (".DAT", ".EXT", ".2EX") if dat.with_suffix(s).is_file()]
    before = {f: f.read_bytes() for f in files}
    lib.native_parts = ("grid", "key", "waves")
    lib.analyze_tracks([nat], force=True)
    folder = lib._rekordbox_original_dir(nat)
    kept = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert kept["ANLZ.DAT"] == before[dat] and folder.parent.name == "anlz-rekordbox"
    lib.analyze_tracks([nat], force=True)                             # 2e fois : l'original reste le premier
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == kept
    M.prune_folders(lib.backup_dir / "anlz", 1)                       # la purge des grilles ne le concerne pas
    t = lib.restore_rekordbox_analysis(nat)
    assert {f: f.read_bytes() for f in files} == before
    assert _row(lib, nat)[:3] == (12700, "Fm", 77) and t.bpm == 127.0
    assert lib.has_rekordbox_original(nat)                            # jamais retiré


def test_restore_keeps_cues_set_since(usb_native):
    lib, nat, _own, dat = usb_native
    grid = anlz.read_beats(dat.read_bytes())
    lib.native_parts = ("grid",)
    lib.analyze_tracks([nat], force=True)
    lib.save_track_cues(nat, [Cue(1, 1500, name="drop"), Cue(2, 9000, name="new"), Cue(0, 4000)])
    cues = lib.track_cues(nat)
    lib.restore_rekordbox_analysis(nat)
    assert anlz.read_beats(dat.read_bytes()) == grid and lib.track_cues(nat) == cues
    assert "PSSI" in _tags(dat.with_suffix(".EXT"))


def test_unreadable_file_or_failed_copy_writes_nothing(usb_native, monkeypatch):
    lib, nat, _own, dat = usb_native
    lib.native_parts = ("grid", "waves")
    ext = dat.with_suffix(".EXT")
    good = ext.read_bytes()
    ext.write_bytes(good[:-9])                                        # .EXT illisible
    stamp = dat.read_bytes()
    problems = []
    assert lib.analyze_tracks([nat], force=True, on_progress=lambda i, n, t, p: problems.append(p)) == (0, 0, 1)
    assert "Unreadable analysis file" in problems[0] and dat.read_bytes() == stamp and ext.read_bytes() == good[:-9]
    assert not lib.has_rekordbox_original(nat)
    ext.write_bytes(good)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("djsync.db.library.ingest.keep_rekordbox_original", boom)
    problems.clear()
    assert lib.analyze_tracks([nat], force=True, on_progress=lambda i, n, t, p: problems.append(p)) == (0, 0, 1)
    assert "could not be kept" in problems[0] and dat.read_bytes() == stamp and ext.read_bytes() == good
    assert _row(lib, nat)[0] == 12700


def test_files_are_put_back_when_the_database_refuses(usb_native, monkeypatch):
    lib, nat, _own, dat = usb_native
    lib.native_parts = ("grid",)
    stamp = dat.read_bytes()
    job = lib._analysis_job(nat, True)

    def boom(*_a, **_k):
        raise LibraryError("locked")

    monkeypatch.setattr(lib, "_key_id_for", boom)
    monkeypatch.setattr(lib, "_pdb_mark", boom)
    with pytest.raises(LibraryError):
        lib._apply_analysis(job)
    assert dat.read_bytes() == stamp and _row(lib, nat)[0] == 12700


# ------------------------------------------------------------------------------- B96
def test_b96_unreadable_cues_stop_the_reanalysis_of_a_djsync_track(usb_native):
    lib, _nat, own, _dat = usb_native
    dat = lib.absolute_path(lib.get_track(own).analysis_path)
    lib.save_track_cues(own, [Cue(1, 2000)])
    raw = _tags(dat)["PCOB"][0]
    lh = struct.unpack(">I", raw[4:8])[0]
    cut = bytearray(raw[:lh] + b"PCPT" + b"\x00" * 10)                # entrée de cue coupée
    struct.pack_into(">I", cut, 8, len(cut))
    dat.write_bytes(anlz.rebuild(dat.read_bytes(), {"PCOB": bytes(cut)}))
    anlz.parse(dat.read_bytes())                                      # le fichier lui-même reste lisible
    stamp, row = dat.read_bytes(), _row(lib, own)
    problems = []
    assert lib.analyze_tracks([own], force=True, on_progress=lambda i, n, t, p: problems.append(p)) == (0, 0, 1)
    assert "cues" in problems[0] and dat.read_bytes() == stamp and _row(lib, own) == row


def test_b96_write_files_raises_instead_of_dropping_cues(tmp_path, monkeypatch):
    from djsync.analysis import cues as C

    usb = make_usb(tmp_path)
    with open_lib(usb, analyze=True) as lib:
        folder = lib.default_download_dir("S")
        folder.mkdir(parents=True, exist_ok=True)
        t = lib.add_track(write_wav(folder / "a.wav", _song(126.0, 12)), "A", "S")
        dat = lib.absolute_path(t.analysis_path)
        stamp = dat.read_bytes()

        def boom(*_a, **_k):
            raise ValueError("bad PCOB")

        monkeypatch.setattr(C, "read_cues", boom)
        assert lib.analyze_tracks([t.content_id], force=True) == (0, 0, 1)
        assert dat.read_bytes() == stamp and any("cues" in p for p in lib.last_problems)


# --------------------------------------------------------------------- ordinateur (master.db)
@pytest.fixture
def pc_native(local):
    music = local.default_download_dir("A", "")
    t = local.add_track(local_wav(music, "n", 8, bpm=128), "N", "A")
    uuid = local._read("SELECT UUID FROM djmdContent WHERE ID = :id", {"id": str(t.content_id)})[0][0]
    local.save_track_cues(t.content_id, [Cue(1, 1000), Cue(0, 3000)])
    dat = local.absolute_path(local.get_track(t.content_id).analysis_path)
    _like_rekordbox(dat)
    local.owned.remove(uuid)                                          # comme un son analysé par Rekordbox
    with local._write():
        c = local._content(t.content_id)
        c.BPM = 12700
    return local, t.content_id, uuid, dat


def _djmd_cues(local, cid):
    return local._read("SELECT ID, InMsec, OutMsec, Kind, Comment FROM djmdCue WHERE ContentID = :id ORDER BY ID",
                       {"id": str(cid)})


def test_pc_native_is_grafted_and_stays_not_owned(pc_native):
    local, cid, uuid, dat = pc_native
    assert local.native_ids([cid]) == {cid}
    assert local.analyze_tracks([cid], force=True) == (0, 1, 0)       # rien de choisi
    files = [dat.with_suffix(s) for s in (".DAT", ".EXT", ".2EX") if dat.with_suffix(s).is_file()]
    before = {f: _tags(f) for f in files}
    raw = {f: f.read_bytes() for f in files}
    rows, cues = _djmd_cues(local, cid), local.track_cues(cid)
    local.native_parts = ("grid",)
    assert local.analyze_tracks([cid], force=True) == (1, 0, 0)
    assert set().union(*(_changed(before[f], f) for f in files)) == {"PQTZ", "PQT2", "PSSI"}
    assert _djmd_cues(local, cid) == rows and local.track_cues(cid) == cues
    assert uuid not in local.owned.all() and local.beat_grid(cid).native
    assert local.get_track(cid).bpm == 128.0 and local.has_rekordbox_original(cid)
    assert local.restore_rekordbox_analysis(cid).bpm == 127.0
    assert {f: f.read_bytes() for f in files} == raw and _djmd_cues(local, cid) == rows


def test_pc_refuses_while_rekordbox_is_open(pc_native, monkeypatch):
    import djsync.db.local_library as L

    local, cid, _uuid, dat = pc_native
    local.native_parts = ("grid",)
    stamp = dat.read_bytes()
    monkeypatch.setattr(L, "rekordbox_running", lambda: True)
    assert local.analyze_tracks([cid], force=True) == (0, 0, 1)
    assert dat.read_bytes() == stamp and not local.has_rekordbox_original(cid)


# ------------------------------------------------------------------------------ interface
pytest.importorskip("PySide6")


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from .qt_util import close_window
    from .test_ui_v024 import _app

    window = _app(tmp_path, monkeypatch)
    yield window
    close_window(window)


def _gate(demo, monkeypatch, native):
    """Passage « Analyser à nouveau » avec `native` sons de Rekordbox ; renvoie la liste des lancements."""
    ctrl, started = demo.ctrl, []
    monkeypatch.setattr(ctrl, "native_ids", lambda ids, ok: ok(set(list(ids)[:native])))
    monkeypatch.setattr(ctrl, "analyze", lambda ids, force=False, **_k: started.append((list(ids), force)))
    return started


def test_setting_is_empty_until_the_choice_is_made():
    from djsync.settings import Settings

    s = Settings()
    assert s.reanalyze_rekordbox == ["grid"] and s.native_parts() == ()
    s.reanalyze_rekordbox, s.reanalyze_rekordbox_asked = ["waves", "bogus", "grid"], True
    assert s.normalize().native_parts() == ("grid", "waves")


def test_choice_window_once_then_confirmation_for_a_batch(demo, monkeypatch):
    from djsync.i18n import t
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.reanalyse import ReanalyseChoiceDialog, analyse_again

    from .qt_util import find

    ctrl = demo.ctrl
    started = _gate(demo, monkeypatch, 0)
    analyse_again(demo, ctrl, [1, 2])                                 # aucun son de Rekordbox : direct
    assert started == [([1, 2], True)] and find(demo, ReanalyseChoiceDialog) is None

    started = _gate(demo, monkeypatch, 1)
    analyse_again(demo, ctrl, [1])                                    # première fois, même pour un seul son
    dlg = find(demo, ReanalyseChoiceDialog)
    assert dlg is not None and started == [] and ctrl.library.native_parts == ()
    assert [p for p, b in dlg.boxes.items() if b.isChecked()] == ["grid"]
    dlg.close()                                                       # annulé : rien de lancé, rien de mémorisé
    assert started == [] and not ctrl.settings.reanalyze_rekordbox_asked

    analyse_again(demo, ctrl, [1])
    dlg = find(demo, ReanalyseChoiceDialog)
    dlg.boxes["waves"].setChecked(True)
    dlg._ok()
    assert started == [([1], True)] and ctrl.settings.reanalyze_rekordbox == ["grid", "waves"]
    assert ctrl.settings.reanalyze_rekordbox_asked and ctrl.library.native_parts == ("grid", "waves")

    started.clear()
    analyse_again(demo, ctrl, [1])                                    # un seul son, choix fait : direct
    assert started == [([1], True)] and find(demo, ReanalyseChoiceDialog) is None
    started.clear()
    analyse_again(demo, ctrl, [1, 2, 3])                              # lot : confirmation courte avec le nombre
    conf = find(demo, ConfirmDialog)
    assert conf is not None and started == []
    from PySide6.QtWidgets import QLabel

    text = " ".join(w.text() for w in conf.findChildren(QLabel))
    assert "1" in text and t("reanalyse.part_grid") in text and t("reanalyse.part_waves") in text
    conf._ok()
    assert started == [([1, 2, 3], True)]


def test_settings_page_holds_the_three_boxes(demo):
    v = demo.views["settings"]
    assert list(v.reanalyse_vars) == ["grid", "key", "waves"]
    assert [p for p, b in v.reanalyse_vars.items() if b.isChecked()] == ["grid"]
    v._save()
    assert not demo.ctrl.settings.reanalyze_rekordbox_asked            # rien changé : la fenêtre viendra
    v.reanalyse_vars["key"].setChecked(True)
    v._save()
    s = demo.ctrl.settings
    assert s.reanalyze_rekordbox == ["grid", "key"] and s.reanalyze_rekordbox_asked
    assert demo.ctrl.library.native_parts == ("grid", "key")


def test_analyse_page_has_one_box_and_goes_through_the_gate(demo, monkeypatch):
    from PySide6.QtWidgets import QCheckBox

    from djsync.i18n import t
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.reanalyse import ReanalyseChoiceDialog

    from .qt_util import find, pump

    ctrl = demo.ctrl
    tracks = ctrl.library.list_tracks()[:3]
    for x in tracks:
        object.__setattr__(x, "is_analysed", True)
    started = _gate(demo, monkeypatch, 2)
    page = AnalysisDialog(demo.views["library"], ctrl, tracks)
    pump(demo, 0.3)
    boxes = [b for b in page.findChildren(QCheckBox) if b.text() == t("analysis.force")]
    assert len(boxes) == 1 and "Rekordbox" in t("analysis.force_hint") and "DJSync" not in t("analysis.force")
    page.force.setChecked(True)
    page._missing = {}
    page._start()
    dlg = find(demo, ReanalyseChoiceDialog)
    assert dlg is not None and started == [] and not page._started
    dlg._ok()
    assert started == [([x.content_id for x in tracks], True)] and page._started


def test_restore_entry_only_when_an_original_is_kept(demo, monkeypatch):
    from djsync.i18n import t

    from .qt_util import pump

    lib = demo.views["library"]
    demo.show_tab("library") if hasattr(demo, "show_tab") else None
    pump(demo, 0.5)
    x = demo.ctrl.library.list_tracks()[0]
    object.__setattr__(x, "is_analysed", True)
    monkeypatch.setattr(lib, "_selected_tracks", lambda: [x])
    labels = lambda: [e[0] for e in lib._menu(["x"]) if e]            # noqa: E731
    assert t("player.analyse_again") in labels() and t("reanalyse.restore") not in labels()
    demo.ctrl.__dict__["_rekordbox_originals"] = {x.content_id}
    assert t("reanalyse.restore") in labels()
    called = []
    monkeypatch.setattr(demo.ctrl, "_write", lambda fn, ok=None, success="", err=None: called.append(success))
    demo.ctrl.restore_rekordbox_analysis(x.content_id)
    assert called == [t("msg.rekordbox_restored")]


def test_compare_counts_only_grids_written_by_rekordbox(usb_native):
    from djsync.analysis.__main__ import _grid_from_rekordbox

    lib, nat, own, _dat = usb_native
    assert _grid_from_rekordbox(lib, lib.get_track(nat))          # PQT2 présente : grille de Rekordbox
    assert not _grid_from_rekordbox(lib, lib.get_track(own))      # écrite par DJSync
    lib.native_parts = ("grid",)
    lib.analyze_tracks([nat], force=True)                         # grille refaite par DJSync : ne compte plus
    assert not _grid_from_rekordbox(lib, lib.get_track(nat))
