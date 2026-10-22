"""CI (macOS / Linux): checks the self-test report written by the built application.

    DJSYNC_SELFTEST=report.json path/to/DJSync ; python packaging/check_selftest.py report.json

Fails (exit 1, with GitHub error annotations) if a module or a bundled tool is missing — same
checks as the Windows smoke test in .github/workflows/windows.yml.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(path: str) -> int:
    report = Path(path)
    if not report.is_file():
        print("::error title=self-test::no self-test report (the application did not start)")
        return 1
    data = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=1)[:4000])
    bad = [f"{name}: {check.get('error')}" for name, check in data.get("checks", {}).items() if not check.get("ok")]
    value = lambda name: (data.get("checks", {}).get(name) or {}).get("value") or {}  # noqa: E731
    if not value("yt_dlp").get("ejs"):
        bad.append("yt_dlp: yt-dlp-ejs (YouTube JavaScript solver) missing")
    if not (value("tools").get("js") or {}).get("quickjs"):
        bad.append("tools: bundled QuickJS not found")
    if not value("tools").get("ffmpeg"):
        bad.append("tools: bundled FFmpeg not found")
    for b in bad:
        print(f"::error title=self-test::{b}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
