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
