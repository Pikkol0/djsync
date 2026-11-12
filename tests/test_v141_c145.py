"""1.4.1 (C145) : registre des tâches longues et bandeau du volet gauche (TaskStrip)."""
from __future__ import annotations

import threading

import pytest

from djsync.ui import tasks as T


# ------------------------------------------------------------------ registre seul (sans Qt)
class _Later:
    def __init__(self):
        self.calls = []

    def __call__(self, ms, fn):
        self.calls.append((ms, fn))

    def run(self):
        calls, self.calls = self.calls, []
        for _ms, fn in calls:
            fn()


def _reg(**kw):
    seen = []
    later = _Later()
    reg = T.TaskRegistry(later=later, notify=lambda: seen.append(1), **kw)
    return reg, later, seen


def test_c145_order_and_one_task_per_key():
    reg, _later, seen = _reg()
    a = reg.start("b", "x.b")
    c = reg.start("c", "x.c", order=20)
    first = reg.start("a", "x.a", order=0)
    assert [x.key for x in reg.tasks()] == ["a", "b", "c"]         # rang, puis ordre d'inscription
    again = reg.start("b", "x.b", total=9)
    assert again is a and len(reg.tasks()) == 3 and a.total == 9   # même clé : même ligne
    assert first.state == T.RUNNING and c.active and seen


def test_c145_pause_resume_stop_are_relayed_only_when_allowed():
    reg, _later, _seen = _reg()
    log = []
    task = reg.start("dup", "x", total=4, can_pause=True, pause=lambda: log.append("p"),
                     resume=lambda: log.append("r"), can_stop=True, stop=lambda: log.append("s"))
    assert reg.pause("dup") and task.state == T.PAUSED
    assert not reg.pause("dup")                                    # déjà en pause
    assert reg.resume("dup") and task.state == T.RUNNING
    assert reg.stop("dup") and task.state == T.STOPPING and not task.stoppable
    assert not reg.pause("dup") and not reg.stop("dup")
    assert log == ["p", "r", "s"]
    task.finish()
    assert task.state == T.DONE


def test_c145_a_write_has_no_stop_and_no_pause():
    reg, _later, _seen = _reg()
    task = reg.start("pdb", "x", total=3)                           # écriture : progression seule
    assert not task.can_stop and not task.can_pause
    assert not reg.stop("pdb") and not reg.pause("pdb") and task.state == T.RUNNING
    # « can_stop » sans fonction d'arrêt : refusé aussi
    assert not reg.start("w", "x", can_stop=True).can_stop


def test_c145_done_lingers_then_disappears_failed_stays_until_dismissed():
    reg, later, _seen = _reg()
    ok = reg.start("ok", "x", total=2)
    ok.progress(2, 2)
    ok.finish()
    assert ok.state == T.DONE and ok.fraction == 1.0 and reg.get("ok") is ok
    assert later.calls and later.calls[0][0] == int(T.DONE_LINGER_S * 1000)
    later.run()
    assert reg.get("ok") is None                                    # « ✓ fini » 4 s, puis la ligne part
    gone = reg.start("now", "x", linger=0)
    gone.finish()
    assert reg.get("now") is None                                   # sans délai (analyse, téléchargements)
    bad = reg.start("bad", "x")
    bad.fail("disk full")
    later.run()
    assert reg.get("bad") is bad and bad.state == T.FAILED and bad.error == "disk full"
    assert reg.dismiss("bad") and reg.get("bad") is None
    assert not reg.dismiss("missing")


def test_c145_restart_before_the_end_of_the_linger_keeps_the_line():
    reg, later, _seen = _reg()
    task = reg.start("k", "x", total=5)
    task.progress(5, 5)
    task.finish()
    again = reg.start("k", "x", total=3)
    later.run()                                                    # ancien retrait différé : ignoré
    assert again is task and task.active and task.done == 0 and reg.get("k") is task
    assert not reg.dismiss("k")                                     # une tâche en cours ne se masque pas


def test_c145_progress_and_unknown_total():
    reg, _later, seen = _reg()
    task = reg.start("k", "x")
    assert task.total == 0 and task.fraction == 0.0                 # durée inconnue
    n = len(seen)
    task.progress(3, 10, detail="song")
    assert (task.done, task.total, task.detail, task.fraction) == (3, 10, "song", 0.3) and len(seen) == n + 1
    task.progress(3, 10, detail="song")
    assert len(seen) == n + 1                                       # rien de nouveau : pas de rafraîchissement
    task.progress(1, 4, fraction=0.9)
    assert task.fraction == 0.9                                     # avancement donné par l'outil
    task.finish()
    task.progress(4, 4)
    assert task.done == 1                                           # finie : plus de mise à jour


def test_c145_updates_from_a_worker_thread_go_through_post():
    posted = []
    reg = T.TaskRegistry(post=lambda fn, *a: posted.append((fn, a)))
    task = reg.start("k", "x", total=2)
    th = threading.Thread(target=lambda: (task.progress(1, 2), task.finish()))
    th.start()
    th.join()
    assert task.done == 0 and task.active and len(posted) == 2     # rien n'a touché l'état hors du fil UI
    for fn, a in posted:
        fn(*a)
    assert task.done == 1 and task.state == T.DONE


def test_c145_a_failing_tool_command_does_not_break_the_registry():
    reg, _later, _seen = _reg()

    def boom():
        raise RuntimeError("x")

    reg.start("k", "x", can_pause=True, pause=boom, resume=boom)
    assert reg.pause("k") and reg.get("k").state == T.PAUSED


# ------------------------------------------------------------------ bandeau du volet
qt = pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


def _clear(reg):
    for x in list(reg.tasks()):
        if x.active:
            reg._finish(x, False, "")
        reg._tasks.pop(x.key, None)
    reg._changed()


def test_c145_strip_with_0_1_and_4_tasks(demo):  # noqa: F811
    from djsync.ui.task_strip import MAX_ROWS

    reg, strip = demo.ctrl.tasks, demo.task_strip
    demo.ctrl.settings.sidebar_compact = "off"
    demo._compact = None
    demo._update_compact()
    _clear(reg)
    assert strip.isHidden()                                         # 0 tâche : rien

    log = []
    a = reg.start("dup", "task.duplicates", total=40, can_pause=True, pause=lambda: log.append("p"),
                  resume=lambda: log.append("r"), can_stop=True, stop=lambda: log.append("s"), open="dup")
    a.progress(12, 40)
    pump(demo, 0.1)
    assert strip.isVisible() and strip.title.text() == "CHECKING DUPLICATES"
    row = strip.rows["dup"]
    assert row.label.text() == "12 / 40" and row.bar.value() == 300
    hb = strip.head_buttons                                         # une seule tâche : boutons dans l'en-tête
    assert hb.open.isVisible() and hb.pause.isVisible() and hb.stop.isVisible()
    assert not row.buttons.pause.isVisible()
    hb.pause.click()
    assert a.state == T.PAUSED and "Paused" in row.label.text() and hb.pause.toolTip() == "Resume"
    hb.pause.click()
    assert a.state == T.RUNNING and log == ["p", "r"]

    others = [reg.start(k, "task.uniformize", total=10, can_stop=True, stop=lambda: None) for k in ("u1", "u2", "u3")]
    pump(demo, 0.2)
    assert strip.title.text() == "ACTIVITY" and len(reg.tasks()) == 4
    assert strip._scrolling and strip.area.isVisible()               # au-delà de 3 lignes : défilement
    assert strip.area.height() < strip.inner.sizeHint().height()
    assert strip.rows["dup"].label.text().startswith("Checking duplicates 12 / 40")
    assert all(strip.rows[x.key].buttons.stop.isVisible() for x in others)   # suivantes : boutons dans la ligne
    assert hb.task is a and hb.pause.isVisible()                    # première : dans l'en-tête
    strip.rows["u1"].buttons.stop.click()
    assert others[0].state == T.STOPPING and not strip.rows["u1"].buttons.stop.isEnabled()

    for x in others:
        x.finish()
    pump(demo, 0.1)
    assert all(strip.rows[x.key].label.text().endswith("✓ Done") for x in others)   # « ✓ fini » reste un moment
    for x in others:
        reg._expire(x, x._token)
    pump(demo, 0.1)
    assert len(reg.tasks()) == 1 and not strip._scrolling and strip.area.isHidden()
    assert MAX_ROWS == 3

    b = reg.start("bad", "task.uniformize")
    b.fail("Disk full")
    pump(demo, 0.1)
    bad = strip.rows["bad"]
    assert bad.label.text().endswith("Disk full") and bad.label.property("role") == "err"
    bad._clicked()                                                  # clic sur la ligne rouge : masquée
    assert reg.get("bad") is None

    opened = []
    demo._open_task_page = opened.append
    strip._opener = opened.append
    strip.open_task(a)
    strip.open_task(None)
    assert opened == ["dup", "downloads"]
    _clear(reg)
    pump(demo, 0.1)
    assert strip.isHidden() and not demo.errors


def test_c145_collapsed_sidebar_one_ring_then_a_second_that_adds_up_the_rest(demo):  # noqa: F811
    reg, strip = demo.ctrl.tasks, demo.task_strip
    _clear(reg)
    demo.ctrl.settings.sidebar_compact = "on"
    demo._compact = None
    demo._update_compact()
    try:
        a = reg.start("a", "task.duplicates", total=10, order=0)
        a.progress(5, 10)
        pump(demo, 0.1)
        assert strip.ring_a.isVisible() and not strip.ring_b.isVisible() and strip.inner.isHidden()
        assert strip.ring_a.value == 0.5 and strip.ring_a.toolTip() == "Checking duplicates 5 / 10"
        b = reg.start("b", "task.uniformize", total=4)
        b.progress(1, 4)
        pump(demo, 0.1)
        assert strip.ring_b.isVisible() and strip.ring_b.value == 0.25
        c = reg.start("c", "task.uniformize", total=4)
        c.progress(3, 4)
        pump(demo, 0.1)
        assert strip.ring_b.value == 0.5 and strip.ring_b.toolTip().count("\n") == 1   # cumul des suivantes
    finally:
        _clear(reg)
        demo.ctrl.settings.sidebar_compact = "auto"
        demo._compact = None
        demo._update_compact()
    assert not demo.errors


def test_c145_analysis_goes_through_the_registry_and_stops_from_the_strip(demo):  # noqa: F811
    ctrl = demo.ctrl
    q = ctrl.analysis
    _clear(ctrl.tasks)
    demo.ctrl.settings.sidebar_compact = "off"
    demo._compact = None
    demo._update_compact()
    q.finished, q.total, q.done, q.current, q.cancelled = False, 10, 3, "Song", False
    try:
        ctrl._emit("analysis")
        task = ctrl.tasks.get("analysis")
        assert task is not None and task.can_stop and not task.can_pause and task.open == "downloads"
        assert demo.an_title.text() == "ANALYSING" and demo.an_label.text() == "3 / 10  ·  Song"
        assert demo.an_stop.isVisible() and demo.an_stop.toolTip() == "Stop analysis"
        demo.an_stop.click()                                        # arrêt depuis le volet : la file s'arrête
        assert q.cancelled and task.state == T.STOPPING and demo.an_title.text() == "STOPPING…"
        assert not demo.an_stop.isEnabled()
    finally:
        q.finished, q.cancelled = True, False
        ctrl._emit("analysis")
    assert ctrl.tasks.get("analysis") is None and not demo.an_box.isVisible()   # disparaît aussitôt (comme avant)
    assert not demo.errors


# ------------------------------------------------------------------ Doublons
def test_c145_duplicates_pause_resume_stop_between_groups(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    ctrl = demo.ctrl
    _clear(ctrl.tasks)
    pending = []
    ctrl.refine_duplicate_group = lambda g, ok: pending.append((g, ok))
    ctrl.find_duplicates = lambda ok, progress=None, full=False: None   # groupes fournis par le test
    dup = DuplicatesDialog(demo.views["home"], ctrl)
    tracks = ctrl.library.list_tracks()
    groups = [tracks[0:2], tracks[2:4], tracks[4:6], tracks[6:8]]
    dup._loaded([list(g) for g in groups])
    task = ctrl.tasks.get("dup")
    assert task is not None and task.active and (task.done, task.total) == (0, 4) and len(pending) == 1
    assert task.can_pause and task.can_stop and task.open == "dup"

    assert ctrl.tasks.pause("dup")
    g, ok = pending.pop()
    ok([g])                                                         # le groupe en cours finit…
    assert not pending and task.state == T.PAUSED and task.done == 1   # … le suivant n'est pas commencé
    dup.verify_now(3)                                               # une demande explicite passe quand même
    assert len(pending) == 1
    g, ok = pending.pop()
    ok([g])
    assert not pending and task.done == 2
    assert ctrl.tasks.resume("dup") and len(pending) == 1           # reprise : groupe suivant

    assert ctrl.tasks.stop("dup") and task.state == T.STOPPING
    g, ok = pending.pop()
    ok([g])
    assert not pending and task.state == T.DONE                      # arrêt : fin propre après le groupe en cours
    assert dup.verified.count(False) == 1                           # le reste n'est pas vérifié, rien n'est perdu
    dup.verify_now(dup.verified.index(False))
    assert len(pending) == 1 and ctrl.tasks.get("dup").state == T.DONE   # sans relancer la tâche
    dup.close()
    assert not demo.errors


def test_c145_duplicates_task_ends_with_the_page(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    ctrl = demo.ctrl
    _clear(ctrl.tasks)
    ctrl.refine_duplicate_group = lambda g, ok: None
    ctrl.find_duplicates = lambda ok, progress=None, full=False: None
    dup = DuplicatesDialog(demo.views["home"], ctrl)
    tracks = ctrl.library.list_tracks()
    dup._loaded([tracks[0:2], tracks[2:4]])
    task = ctrl.tasks.get("dup")
    assert task.active
    dup.close()
    assert task.state == T.DONE and not demo.errors


# ------------------------------------------------------------------ Uniformiser
def test_c145_uniformize_pause_and_stop_never_start_the_next_track(demo, monkeypatch):  # noqa: F811
    from djsync.core import metadata

    calls = []
    sem = threading.Semaphore(0)

    def gated(title, artist, duration=0, cleaned=False):
        calls.append(title)
        sem.acquire(timeout=10)
        return {}

    monkeypatch.setattr(metadata, "match", gated)
    ctrl = demo.ctrl
    _clear(ctrl.tasks)
    ctrl._emit("open_uniformize", list(ctrl.library.list_tracks()), "All")
    page = demo.uniformize_page
    try:
        task = ctrl.tasks.get("uniformize")
        assert task is not None and task.active and task.total == page._to_scan > 3
        assert task.can_pause and task.can_stop and task.open == "uniformize"
        assert pump(demo, 5, lambda: len(calls) == 1)
        assert ctrl.tasks.pause("uniformize")
        sem.release()                                               # le son en cours finit…
        assert pump(demo, 5, lambda: page._scanned == 1)
        pump(demo, 0.8)
        assert len(calls) == 1 and task.state == T.PAUSED and task.done == 1   # … le suivant attend
        assert ctrl.tasks.resume("uniformize")
        assert pump(demo, 5, lambda: len(calls) == 2)
        assert ctrl.tasks.stop("uniformize") and task.state == T.STOPPING
        sem.release()
        assert pump(demo, 5, lambda: task.state == T.DONE)
        pump(demo, 0.8)
        assert len(calls) == 2                                      # arrêt : plus aucun son commencé
        assert page.scan_bar.isHidden()
        demo.show_view("home")
        demo._open_task_page("uniformize")                          # → revient sur la page en cours
        assert demo.stack.currentWidget() is page
    finally:
        for _ in range(50):
            sem.release()
        page._leaving = True
        page.close()
    assert pump(demo, 2, lambda: demo.uniformize_page is None) and not demo.errors
