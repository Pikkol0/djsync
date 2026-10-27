"""1.3.0-rc.5 : C39 (son en retard sous Windows : réserve de la carte son mesurée et réduite, saut entendu
tout de suite)."""
from __future__ import annotations

import time

import numpy as np
import pytest

from .audio_fixture import write_wav


def test_output_latency_is_measured_from_the_device_calls(monkeypatch):
    from djsync.audio import player as P

    p = P.AudioPlayer(post=lambda f: f())
    clock = [10.0]
    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    n = int(P.RATE * 0.04)
    # au démarrage la carte son remplit sa réserve d'un coup (3 paquets), puis réclame au rythme du son
    for _ in range(3):
        p._fill(n)
    for _ in range(20):
        clock[0] += 0.04
        p._fill(n)
    assert p.output_latency() == pytest.approx(0.12, abs=1e-3)       # 3 paquets de 40 ms d'avance
    # la position entendue retire ce retard mesuré (et plus la valeur prévue de 200 ms)
    p.state = P.PLAYING
    p._frames = p._cb_frames = 5 * P.RATE
    p._cb_time, p._cb_period = clock[0], 0.04
    assert p.position() == pytest.approx(5.0 - 0.12, abs=1e-3)


def test_reserve_is_small_outside_macos():
    import sys

    from djsync.audio import player as P

    total = P.BUFFER_MS * (P.PERIODS or 3)
    if sys.platform == "darwin":
        assert P.BUFFER_MS == 200
    else:
        assert total <= 100                                  # ~80 ms au lieu de ~600 ms


def _playing(tmp_path):
    from djsync.audio import player as P

    path = write_wav(tmp_path / "s.wav", (0.1 * np.sin(np.linspace(0, 4000, 44100 * 30))).astype("float32"))
    p = P.AudioPlayer(post=lambda f: f())
    p.play(path, P.NowPlaying("s", "a", str(path)))
    t0 = time.time()
    while p.state != P.PLAYING and time.time() - t0 < 10:
        time.sleep(0.02)
    assert p.state == P.PLAYING
    return p


def test_seek_while_playing_is_heard_at_once(tmp_path):
    p = _playing(tmp_path)
    time.sleep(0.5)
    assert p.output_latency() > 0
    old_device = p._device
    p.seek(12.0)
    assert p._device is not None and p._device is not old_device    # réserve vidée : carte son relancée
    assert p._prev is None                                         # plus d'ancien passage à afficher
    time.sleep(0.3)
    assert 12.0 <= p.position() < 12.6                             # on entend le nouvel endroit
    p.close()


def test_loop_jump_keeps_the_reserve(tmp_path):
    p = _playing(tmp_path)
    time.sleep(0.3)
    device = p._device
    p.seek(3.0, flush=False)                                       # retour au début d'une boucle
    assert p._device is device                                     # la fin de boucle déjà envoyée se joue
    p.close()


# ------------------------------------------------------------------ B25 : formes d'onde comme Rekordbox
def _heights(level, sr=44100, seconds=4.0):
    from djsync.analysis.waveform import compute_waveforms

    t = np.arange(int(sr * seconds)) / sr
    x = (level * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    wf = compute_waveforms(x, sr, seconds)
    v = np.frombuffer(wf.color_detail, ">u2")
    return (v >> 2) & 31, wf


def test_waveform_height_follows_the_real_level():
    loud, _ = _heights(0.95)
    quiet, _ = _heights(0.4)
    # Rekordbox : ≈ 16 pour un son à fond, ≈ 2-3 à -8 dB ; avant, DJSync étirait tout jusqu'à 31
    assert 13 <= np.median(loud) <= 19
    assert np.median(quiet) <= 4 and np.median(quiet) < np.median(loud)


def test_waveform_is_one_point_later_like_rekordbox():
    from djsync.analysis.waveform import DETAIL_RATE, compute_waveforms

    sr = 44100
    x = np.zeros(sr * 3, dtype=np.float32)
    x[sr: sr + 200] = 0.95                                  # un coup à 1,000 s
    wf = compute_waveforms(x, sr, 3.0)
    h = (np.frombuffer(wf.color_detail, ">u2") >> 2) & 31
    assert int(np.argmax(h)) == DETAIL_RATE + 1             # point 151 (6,7 ms plus tard), comme Rekordbox


# ------------------------------------------------------------------ C62 / C63 : doublons
from types import SimpleNamespace as _T  # noqa: E402

from .test_ui_v020 import demo  # noqa: E402,F401


def _tr(cid, title, artist="Jul", dur=200, path=None):
    return _T(content_id=cid, title=title, artist=artist, duration_seconds=dur, path=path or f"/Contents/{cid}.m4a")


def test_part_numbers_and_versions_are_not_duplicates():
    from djsync.core.duplicates import find_duplicate_groups, variant_tokens

    a, b = _tr(1, "Afro Trap Pt. 3 (Fais pas la mala)"), _tr(2, "AFRO TRAP Pt.3")
    c, d = _tr(3, "Afro Trap Part 7"), _tr(4, "Afro Trap Pt. 3 (Remix)")
    groups = find_duplicate_groups([a, b, c, d])
    assert [{x.content_id for x in g} for g in groups] == [{1, 2}]
    assert variant_tokens("One More Time (2001 Remaster)") == variant_tokens("One More Time")


def test_not_a_duplicate_is_remembered_and_reversible(tmp_path):
    from djsync.core.dup_ignore import DuplicateIgnores
    from djsync.core.duplicates import find_duplicate_groups

    a, b, c = _tr(1, "Bande organisée"), _tr(2, "Bande organisee"), _tr(3, "Bande Organisée !")
    store = DuplicateIgnores(tmp_path / "ign.json")
    assert [len(g) for g in find_duplicate_groups([a, b, c], ignored=store.pairs())] == [3]
    added = store.add(c, [a, b])                                     # c n'est pas un doublon : a et b restent
    again = DuplicateIgnores(tmp_path / "ign.json")                  # retenu sur disque
    groups = find_duplicate_groups([a, b, c], ignored=again.pairs())
    assert [{x.content_id for x in g} for g in groups] == [{1, 2}]
    again.remove(added)                                              # Annuler
    assert [len(g) for g in find_duplicate_groups([a, b, c], ignored=again.pairs())] == [3]
    again.add_group([a, b, c])
    assert find_duplicate_groups([a, b, c], ignored=again.pairs()) == []
    again.clear()
    assert DuplicateIgnores(tmp_path / "ign.json").entries == []


def test_duplicates_page_lists_at_once_then_checks_audio_and_sets_aside(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog, IgnoredDialog
    from tests.qt_util import find, pump

    calls = []
    real = demo.ctrl.refine_duplicate_group
    demo.ctrl.refine_duplicate_group = lambda g, ok: (calls.append(len(g)), real(g, ok))
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert pump(demo, 6, lambda: all(dup.verified)) and calls == [2]       # son vérifié ensuite, groupe par groupe
    gone = dup.current_group[1]
    dup._exclude(1)                                                         # « Pas un doublon »
    assert dup.groups == [] and len(demo.ctrl.duplicate_ignores.entries) == 1
    dup._reload()                                                           # ne revient pas
    assert pump(demo, 4, lambda: dup.count.text() != "") and pump(demo, 2, lambda: dup.groups == []) is True
    dup._full_scan()                                                        # détection complète : revient
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert gone.content_id in {x.content_id for x in dup.current_group}
    dup._show_ignored()
    ign = find(demo, IgnoredDialog)
    assert ign is not None and ign.list.count() == 1
    ign._undo_all()
    ign.close()
    assert demo.ctrl.duplicate_ignores.entries == []
    dup.close()
    assert not demo.errors


def test_diagnostic_merges_through_the_duplicates_tool(demo):  # noqa: F811
    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from tests.qt_util import find, pump

    diag = DiagnosticDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 8, lambda: any(k == "dup" for k, _p in diag.items))
    diag._select(next(i for i, (k, _p) in enumerate(diag.items) if k == "dup"))
    group = list(diag.current[1])
    diag._choice.button(1).setChecked(True)                                 # garder la 2e version
    assert diag.apply_btn.text() == "Merge in Duplicates…"
    diag._apply()
    assert pump(demo, 4, lambda: find(demo, DuplicatesDialog) is not None)
    dup = find(demo, DuplicatesDialog)
    assert pump(demo, 4, lambda: dup.current_group is not None)
    assert dup.current_group[dup.keep_index()].content_id == group[1].content_id
    dup.close()
    assert not demo.errors


# ------------------------------------------------------------------ B26 : « Rekordbox ouvert » à tort
def test_only_the_main_rekordbox_program_counts():
    from djsync.db.local_library import rekordbox_process_name

    assert rekordbox_process_name(["explorer.exe", "rekordbox.exe"]) == "rekordbox.exe"
    assert rekordbox_process_name(["rekordbox"]) == "rekordbox"                        # macOS
    for other in ("rekordboxAgent.exe", "rekordbox_updater.exe", "rekordbox_crash_reporter.exe",
                  "rekordbox_media_server", "rekordboxAgent"):
        assert rekordbox_process_name(["explorer.exe", other]) == ""


def test_rekordbox_open_needs_two_polls_and_closes_at_once():
    from djsync.ui.controller import AppController as Controller

    ctrl = Controller.__new__(Controller)
    emitted = []
    ctrl._emit = lambda *a: emitted.append(a)
    ctrl.library, ctrl.drive = None, None
    ctrl._rekordbox_warned = False
    Controller._warn_rekordbox(ctrl, True)
    assert not ctrl._rekordbox_was_running                  # vu une fois : pas encore « ouvert »
    Controller._warn_rekordbox(ctrl, True)
    assert ctrl._rekordbox_was_running
    Controller._warn_rekordbox(ctrl, False)
    assert not ctrl._rekordbox_was_running                  # fermé : tout de suite
