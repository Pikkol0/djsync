"""1.3.2-rc.5 : blocage toutes les ~8 s pendant la lecture (B50, test GRI-4 de la rc.4)."""
from __future__ import annotations

import gc
import logging
import time


def _dispatcher():
    from djsync.ui.runner import UiDispatcher

    return UiDispatcher(schedule=lambda ms, fn: None)


# ------------------------------------------------------------------ ramasse-miettes réglé sur l'horloge
def test_collections_follow_the_clock_not_the_queue():
    from djsync.ui import runner as R

    d = _dispatcher()
    try:
        t0 = d._gc_at[0]
        assert d._collect(t0 + 0.1) is None                       # rien avant 0,5 s
        assert d._collect(t0 + R.GC_YOUNG_S + 0.01) == 0
        assert d._collect(t0 + R.GC_MIDDLE_S + 0.01) == 1
        assert d._collect(t0 + R.GC_MIDDLE_S + 0.02) is None      # vient d'être fait
    finally:
        d.shutdown()


def test_no_full_collection_while_playing_then_freeze():
    from djsync.ui import runner as R

    d = _dispatcher()
    try:
        t0 = d._gc_at[2]
        d.gc_busy = lambda: True
        assert d._collect(t0 + R.GC_FULL_S + 1) == 1             # lecture : seulement l'intermédiaire
        d.gc_busy = lambda: False
        assert d._collect(t0 + R.GC_FULL_S + 2) == 2              # à l'arrêt : complet…
        assert gc.get_freeze_count() > 0                          # … puis objets durables mis à part
        d.gc_busy = lambda: True
        t2 = d._gc_at[2]
        assert d._collect(t2 + R.GC_FULL_MAX_S + 1) == 2          # lecture sans fin : quand même
    finally:
        d.shutdown()
    assert gc.get_freeze_count() == 0                             # rendu à la fermeture


def test_slow_collection_is_logged(caplog):
    from djsync.ui import runner as R

    w = R.GcWatch()
    try:
        w._cb("start", {"generation": 1})
        w._t0 -= 0.2                                              # 200 ms
        w._cb("stop", {"generation": 1, "collected": 42})
        w._cb("start", {"generation": 0})
        w._cb("stop", {"generation": 0, "collected": 1})          # rapide : rien
        with caplog.at_level(logging.INFO, logger=R.log.name):
            w.flush()
    finally:
        w.close()
    assert "Slow garbage collection: generation 1" in caplog.text and "42 objects freed" in caplog.text
    assert caplog.text.count("Slow garbage collection") == 1


# ------------------------------------------------------------------ piles écrites si l'interface se fige
def test_stall_report_after_a_block(tmp_path, caplog):
    from djsync.ui.stall import StallWatch

    w = StallWatch(tmp_path / "stall.log")
    with caplog.at_level(logging.INFO, logger="djsync.ui.stall"):
        w.tick()
        time.sleep(0.6)                                           # interface « figée »
        w.tick()
        w.stop()
    assert w.reports == 1
    assert "UI blocked for more than 350 ms" in caplog.text and "test_stall_report_after_a_block" in caplog.text


def test_no_report_when_ticks_keep_coming_or_after_stop(tmp_path, caplog):
    from djsync.ui.stall import StallWatch

    w = StallWatch(tmp_path / "stall.log")
    with caplog.at_level(logging.INFO, logger="djsync.ui.stall"):
        for _ in range(8):
            w.tick()
            time.sleep(0.05)
        w.stop()
        time.sleep(0.5)                                           # arrêtée : pas de faux relevé
        w.collect()
    assert w.reports == 0 and "UI blocked" not in caplog.text
