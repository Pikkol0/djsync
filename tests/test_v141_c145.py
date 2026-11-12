"""1.4.1 (C145) : registre des tâches longues et cartes du volet gauche (TaskStrip) : une carte par tâche en
cours, réduite à son anneau en volet replié, disparue dès la fin ; pause de l'analyse et des téléchargements."""
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


def test_c145_done_disappears_at_once_failed_stays_until_dismissed():
    reg, later, _seen = _reg()
    ok = reg.start("ok", "x", total=2)
    ok.progress(2, 2)
    ok.finish()
    assert ok.state == T.DONE and reg.get("ok") is None and not later.calls   # 12/11 : la carte part tout de suite
    slow = reg.start("slow", "x", linger=4.0)                       # délai encore possible pour un outil
    slow.finish()
    assert reg.get("slow") is slow and later.calls[0][0] == 4000
    later.run()
    assert reg.get("slow") is None
    bad = reg.start("bad", "x")
    bad.fail("disk full")
    assert reg.get("bad") is bad and bad.state == T.FAILED and bad.error == "disk full"
    assert reg.dismiss("bad") and reg.get("bad") is None
    assert not reg.dismiss("missing")


def test_c145_restart_before_the_end_of_the_linger_keeps_the_line():
    reg, later, _seen = _reg()
    task = reg.start("k", "x", total=5, linger=4.0)
    task.progress(5, 5)
    task.finish()
    again = reg.start("k", "x", total=3, linger=4.0)
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


def _expand(demo, compact="off"):
    demo.ctrl.settings.sidebar_compact = compact
    demo._compact = None
    demo._update_compact()


def test_c145_one_card_per_task_with_0_1_and_4_tasks(demo):  # noqa: F811
    from djsync.ui.task_strip import MAX_CARDS

    reg, strip = demo.ctrl.tasks, demo.task_strip
    _expand(demo)
    _clear(reg)
    assert strip.isHidden()                                         # 0 tâche : rien

    log = []
    a = reg.start("dup", "task.duplicates", total=40, can_pause=True, pause=lambda: log.append("p"),
                  resume=lambda: log.append("r"), can_stop=True, stop=lambda: log.append("s"), open="dup")
    a.progress(12, 40)
    pump(demo, 0.1)
    card = strip.cards["dup"]
    assert strip.isVisible() and card.isVisible() and card.title.text() == "DUPLICATES"
    assert card.label.text() == "12 / 40" and card.bar.value() == 300
    assert card.open.isVisible() and card.pause.isVisible() and card.stop.isVisible()
    card.pause.click()
    assert a.state == T.PAUSED and card.label.text() == "12 / 40  ·  Paused" and card.pause.toolTip() == "Resume"
    card.pause.click()
    assert a.state == T.RUNNING and log == ["p", "r"]

    others = [reg.start(k, "task.uniformize", total=10, can_stop=True, stop=lambda: None) for k in ("u1", "u2", "u3")]
    pump(demo, 0.2)
    assert all(strip.cards[x.key].isVisible() is not None for x in others) and len(reg.tasks()) == 4
    assert all(strip.cards[k].title.text() == "UNIFORMISE" for k in ("u1", "u2", "u3"))   # une carte chacune
    assert card.title.text() == "DUPLICATES"
    assert strip._scrolling and strip.area.isVisible()               # au-delà de 3 cartes : défilement
    assert strip.area.height() < strip.inner.sizeHint().height()
    strip.cards["u1"].stop.click()
    assert others[0].state == T.STOPPING and strip.cards["u1"].title.text() == "STOPPING…"
    assert not strip.cards["u1"].stop.isEnabled()

    for x in others:
        x.finish()
    pump(demo, 0.1)
    assert len(reg.tasks()) == 1 and not strip._scrolling and strip.area.isHidden()   # finies : cartes parties
    assert all(strip.cards[k].isHidden() for k in ("u1", "u2", "u3")) and MAX_CARDS == 3

    b = reg.start("bad", "task.uniformize")
    b.fail("Disk full")
    pump(demo, 0.1)
    bad = strip.cards["bad"]
    assert bad.label.text() == "Disk full" and bad.label.property("role") == "err" and bad.bar.isHidden()
    bad._clicked()                                                  # clic sur la carte rouge : masquée
    assert reg.get("bad") is None and bad.isHidden()

    opened = []
    strip._opener = opened.append
    strip.open_task(a)
    strip.open_task(None)
    assert opened == ["dup", "downloads"]
    _clear(reg)
    pump(demo, 0.1)
    assert strip.isHidden() and not demo.errors


def test_c145_collapsed_sidebar_one_small_card_per_task(demo):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.app import SIDEBAR_COMPACT

    reg, strip = demo.ctrl.tasks, demo.task_strip
    _clear(reg)
    _expand(demo, "on")
    try:
        a = reg.start("a", "task.duplicates", total=10, order=0)
        a.progress(5, 10)
        b = reg.start("b", "task.uniformize", total=4, icon="tag")
        b.progress(1, 4)
        c = reg.start("c", "task.uniformize", total=4)
        c.progress(3, 4)
        pump(demo, 0.2)
        rings = [strip.cards[k].ring for k in ("a", "b", "c")]
        assert all(r.isVisible() for r in rings)                    # un anneau par tâche
        assert [r.value for r in rings] == [0.5, 0.25, 0.75]
        assert rings[0].toolTip() == "Duplicates 5 / 10" and rings[1].icon == "tag"
        assert all(strip.cards[k].title.isHidden() and strip.cards[k].bar.isHidden() for k in ("a", "b", "c"))
        inner = demo.sidebar.width() - 2 * theme.px(10)
        for k in ("a", "b", "c"):                                   # jamais coupé (B94)
            m = strip.cards[k].layout().contentsMargins()
            assert strip.cards[k].ring.width() + m.left() + m.right() <= inner
        assert demo.sidebar.width() >= SIDEBAR_COMPACT
    finally:
        _clear(reg)
        _expand(demo, "auto")
    assert not demo.errors


def test_c145_analysis_and_downloads_cards_pause_and_stop(demo):  # noqa: F811
    from djsync.core.downloader import TrackResult
    from djsync.models import DownloadJob

    ctrl = demo.ctrl
    q = ctrl.analysis
    _clear(ctrl.tasks)
    _expand(demo)
    q.finished, q.total, q.done, q.current, q.cancelled = False, 10, 3, "Song", False
    ctrl.jobs.append(DownloadJob(99, TrackResult("abcdefghijk", "T", "A"), status="downloading", percent=30))
    try:
        ctrl._emit("analysis")
        ctrl._emit("downloads")
        task = ctrl.tasks.get("analysis")
        assert task.can_stop and task.can_pause and task.open == "downloads"
        assert demo.an_title.text() == "ANALYSING" and demo.an_label.text() == "3 / 10  ·  Song"
        assert demo.an_box.isVisible() and demo.dl_bar.isVisible()          # deux cartes
        assert demo.task_strip.cards["downloads"].title.text() == "DOWNLOADING"
        demo.an_pause.click()
        assert q.paused and task.state == T.PAUSED and demo.an_label.text() == "3 / 10  ·  Paused  ·  Song"
        demo.an_pause.click()
        assert not q.paused and task.state == T.RUNNING
        dl = demo.task_strip.cards["downloads"]
        assert dl.pause.isVisible() and not dl.stop.isVisible()
        dl.pause.click()
        assert ctrl.downloads_paused and ctrl.tasks.get("downloads").state == T.PAUSED
        dl.pause.click()
        assert not ctrl.downloads_paused
        demo.an_stop.click()                                        # arrêt depuis la carte : la file s'arrête
        assert q.cancelled and task.state == T.STOPPING and demo.an_title.text() == "STOPPING…"
    finally:
        q.finished, q.cancelled, q.paused = True, False, False
        ctrl.jobs[-1].status = "done"
        ctrl._emit("analysis")
        ctrl._emit("downloads")
    assert ctrl.tasks.get("analysis") is None and not demo.an_box.isVisible()   # disparaît aussitôt
    assert not demo.errors


def test_c145_analysis_pause_finishes_the_current_track_and_loses_none(demo):  # noqa: F811
    ctrl = demo.ctrl
    _clear(ctrl.tasks)
    started, processed = [], []
    sem = threading.Semaphore(0)

    def fake(ids, force=False, on_progress=None, should_stop=None, chunk=8):
        n = 0
        for i, cid in enumerate(ids, start=1):
            if should_stop and should_stop():
                break
            started.append(cid)
            sem.acquire(timeout=10)
            processed.append(cid)
            n += 1
            if on_progress:
                on_progress(i, len(ids), None, "")
        return n, 0, 0

    ctrl.library.analyze_tracks = fake
    ids = [x.content_id for x in ctrl.library.list_tracks()]
    q = ctrl.analyze(ids, force=True)
    try:
        assert pump(demo, 5, lambda: len(started) == 1)
        assert ctrl.tasks.pause("analysis") and q.paused
        sem.release()                                               # le son en cours finit…
        assert pump(demo, 5, lambda: len(processed) == 1)
        pump(demo, 0.8)
        assert len(started) == 1 and q.running                      # … le suivant attend
        assert ctrl.tasks.get("analysis").state == T.PAUSED and "Paused" in demo.an_label.text()
        assert ctrl.tasks.resume("analysis") and not q.paused
        for _ in ids:
            sem.release()
        assert pump(demo, 10, lambda: not q.running)
        assert processed == ids and q.done == len(ids)              # aucun son perdu ni analysé deux fois
    finally:
        for _ in range(30):
            sem.release()
        q.cancel()
        pump(demo, 1, lambda: not q.running)
    assert ctrl.tasks.get("analysis") is None and not demo.errors


def test_c145_downloads_pause_waits_before_the_next_file(demo):  # noqa: F811
    from djsync.core.downloader import TrackResult
    from djsync.models import DownloadJob

    ctrl = demo.ctrl
    ctrl.pause_downloads(True)
    job = DownloadJob(77, TrackResult("abcdefghijm", "T", "A"))
    th = threading.Thread(target=ctrl._run_job, args=(job,), daemon=True)
    try:
        th.start()
        th.join(0.8)
        assert th.is_alive() and job.status == "queued"            # pas commencé pendant la pause
        job.status = "error"                                        # retiré entre-temps : rien n'est lancé
        ctrl.pause_downloads(False)
        th.join(3)
        assert not th.is_alive() and job.status == "error"
    finally:
        ctrl.pause_downloads(False)
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
    assert not pending and task.state == T.DONE and ctrl.tasks.get("dup") is None   # arrêt : fin propre
    assert dup.verified.count(False) == 1                           # le reste n'est pas vérifié, rien n'est perdu
    dup.verify_now(dup.verified.index(False))
    assert len(pending) == 1 and ctrl.tasks.get("dup") is None      # sans relancer la tâche
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
    assert task.state == T.DONE and ctrl.tasks.get("dup") is None and not demo.errors


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
