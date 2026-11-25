"""1.4.4-rc.1 : outils de build (C230)."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bmr", ROOT / "packaging" / "build_metrics_record.py")
bmr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bmr)


def test_c230_record_sizes_and_duration(tmp_path):
    (tmp_path / "DJSync.exe").write_bytes(b"x" * 2_500_000)
    (tmp_path / "DJSync.exe.sha256").write_text("abc")
    (tmp_path / "DJSync-Linux-x86_64.tar.gz").write_bytes(b"x" * 1_000_000)
    now = datetime(2026, 11, 26, 1, 30, tzinfo=timezone.utc)
    m = bmr.record("v1.4.4-rc.1", tmp_path, "2026-11-26T01:00:00Z", "ok", now=now)
    assert m["exe_mb"] == 2.5 and m["linux_mb"] == 1.0 and "dmg_mb" not in m
    assert m["build_min"] == 30.0 and m["build_ok"] is True and m["tag"] == "v1.4.4-rc.1"


def test_c230_merge_keeps_build_time_of_release_job():
    old = {"tag": "v1", "build_min": 30.0, "exe_mb": 2.5}
    new = {"tag": "v1", "dmg_mb": 90.1, "build_min": 55.0}
    out = bmr.merge(old, new)
    assert out == {"tag": "v1", "build_min": 30.0, "exe_mb": 2.5, "dmg_mb": 90.1}


def test_c230_workflow_writes_metrics_in_release_and_macos_jobs():
    wf = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    assert wf.count("packaging/build_metrics_record.py") == 2
    assert "--started" in wf


def test_c230_dry_run_prints_json(tmp_path, capsys):
    (tmp_path / "DJSync-macOS.dmg").write_bytes(b"x" * 100)
    assert bmr.main(["v9", str(tmp_path), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dmg_mb"] == 0.0


def test_c223_deleted_log_add_search_remove_clear(tmp_path):
    from types import SimpleNamespace as NS

    from djsync.core.deleted_log import DeletedLog, search

    log = DeletedLog(tmp_path / "DJSync_Backups")
    assert log.entries() == []
    n = log.add([NS(title="Umbrella", artist="Rihanna", source_url="https://youtu.be/x"),
                 NS(title="One More Time", artist="Daft Punk", source_url=None), NS(title="", artist="")])
    items = log.entries()
    assert n == 2 and [x.title for x in items] == ["Umbrella", "One More Time"]
    assert items[0].url == "https://youtu.be/x" and items[1].query == "Daft Punk - One More Time"
    assert [x.title for x in search(items, "daft")] == ["One More Time"]
    log.remove([items[0]])
    assert [x.title for x in log.entries()] == ["One More Time"]
    assert len((tmp_path / "DJSync_Backups" / "deleted_tracks.json").read_bytes()) < 400   # ≈ 200 octets par son
    log.clear()
    assert log.entries() == []


def test_c235_backup_levels_migrate_and_prune(tmp_path):
    from djsync.db import backup_levels as bl
    from djsync.settings import Settings

    s = Settings(backup_keep=5)
    s.normalize()
    try:
        assert bl.from_copies(5) == "light" and bl.from_copies(10) == "normal" and bl.from_copies(50) == "full"
        root = tmp_path / "DJSync_Backups"
        for i in range(8):
            (root / f"master-2026112{i}-000000").mkdir(parents=True)
            (root / f"master-2026112{i}-000000" / "master.db").write_bytes(b"x" * 1000)
            (root / f"session-2026112{i}-000000").mkdir()
        for i in range(40):
            (root / "anlz" / f"2026112{i:02d}-1-cues").mkdir(parents=True)
        bl.set_level("light")
        freed = bl.prune_now(root)
        assert freed >= 5000
        assert len(list(root.glob("master-*"))) == 3 and len(list(root.glob("session-*"))) == 1
        assert len(list((root / "anlz").iterdir())) == 30
        bl.set_level("bogus")
        assert bl.level() == "normal" and bl.limit("copies") == 10
    finally:
        bl.set_level("normal")


def test_c235_settings_level_from_old_copies():
    from djsync.db import backup_levels as bl
    from djsync.settings import Settings

    try:
        for keep, level, copies in ((5, "light", 3), (20, "full", 50), (10, "normal", 10)):
            s = Settings(backup_keep=keep)
            out = s.normalize()
            assert (out.backup_level, out.backup_keep) == (level, copies)
    finally:
        bl.set_level("normal")


def test_c222_one_bar_per_disk(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    from djsync.core import space

    a, b = tmp_path / "A", tmp_path / "B"
    (a / "backups").mkdir(parents=True)
    (a / "backups" / "x.db").write_bytes(b"x" * 5000)
    (b / "cache").mkdir(parents=True)
    (b / "cache" / "y").write_bytes(b"y" * 3000)
    monkeypatch.setattr(space, "drive_of", lambda p: "A:" if str(p).startswith(str(a)) else
                        "B:" if str(p).startswith(str(b)) else str(p))
    monkeypatch.setattr(space, "_disk", lambda root: (100_000, 40_000))
    bars = space.computer_disks({"backups": a / "backups", "caches": b / "cache"}, {"C:": 7000}, skip=["A:"])
    assert [x.title for x in bars] == ["B:", "C:"]
    assert bars[0].usage.parts["caches"] == 3000 and bars[1].usage.parts["music"] == 7000
    assert bars[0].usage.parts["free"] == 40_000 and bars[0].usage.parts["other"] == 60_000 - 3000
    key = tmp_path / "KEY"
    (key / "Contents").mkdir(parents=True)
    (key / "Contents" / "s.mp3").write_bytes(b"z" * 2000)
    usb = space.usb_disks([NS(root=key, label="DJ"), NS(root=tmp_path / "OPEN", label="OPEN")],
                          skip=[str(tmp_path / "OPEN")])
    assert [x.title for x in usb] == ["DJ"] and usb[0].kind == "usb" and usb[0].usage.parts["music"] == 2000


def test_b128_a09_memwatch_sample_and_growth(caplog):
    import logging

    from djsync.core.memwatch import MemWatch, top_growth

    w = MemWatch()
    with caplog.at_level(logging.INFO, logger="djsync.memory"):
        first = w.sample(detail=True)
        keep = [[i] for i in range(50_000)]                  # des listes en plus
        second = w.sample(detail=True)
    assert first.startswith("Memory: RSS") and "top:" in first and "peak" in first
    assert "grown:" in second and "list +" in second
    assert any("Memory: RSS" in r.message for r in caplog.records)
    assert top_growth({"a": 1, "b": 5}, {"a": 4, "b": 5, "c": 2}) == [("a", 3), ("c", 2)]
    del keep


def test_a09_workers_limited_by_free_memory(monkeypatch):
    from djsync.analysis import pool

    monkeypatch.delenv("DJSYNC_ANALYSIS_WORKERS", raising=False)
    pool.set_light(False)
    assert pool.worker_count(16, free_mb=None) == 4
    assert pool.worker_count(16, free_mb=1024 + 2 * 250) == 2              # 4 Go, peu de mémoire libre
    assert pool.worker_count(16, free_mb=600) == 1
