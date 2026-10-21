"""Release notes for a GitHub release, built from the README (single source of truth).

    python packaging/release_notes.py v1.0.0 > notes.md      # also checks the tag against djsync.__version__

Takes the version's row of the README "Version history" table, adds the installation steps for the
Windows exe. Exit code 1 if the tag does not match the version written in djsync/__init__.py
(a "-rc.1" / "-beta" suffix is allowed: it marks a pre-release of that version).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTALL = """## Installation (Windows)
1. Download **DJSync.exe** below.
2. Put it on your USB drive (or anywhere on the computer) and **double-click it**. That's all:
   nothing to unzip, nothing installed on the computer.
3. The first launch takes a moment: DJSync prepares its files in a hidden folder next to itself
   (once, and again after an update). Your settings are kept across updates.

If Windows SmartScreen warns about an unknown publisher (unsigned app): *More info* ▸ *Run anyway*.
To update: replace DJSync.exe with the new one.

Close Rekordbox while DJSync writes to a library, and keep a copy of your drive.
SHA-256: see `DJSync.exe.sha256`.

Quick installation guide: [English](https://github.com/Pikkol0/djsync/blob/main/docs/INSTALL.md) ·
[français](https://github.com/Pikkol0/djsync/blob/main/docs/INSTALL.fr.md)
"""


def package_version() -> str:
    text = (ROOT / "djsync" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def history_row(version: str) -> str:
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].strip("*") == version:
            return cells[1]
    return ""


def main(tag: str) -> int:
    wanted = tag.lstrip("v")
    base = wanted.split("-", 1)[0]
    current = package_version()
    if base != current:
        print(f"Tag {tag} does not match djsync.__version__ = {current}", file=sys.stderr)
        return 1
    changes = history_row(current) or "See the README version history."
    title = "Pre-release" if "-" in wanted else "Release"
    print(f"**{title} {wanted}**\n\n## What's new\n{changes}\n\n{INSTALL}")
    return 0


if __name__ == "__main__":
    # Windows writes redirected output in the ANSI code page (cp1252), which has no "▸" or "·":
    # always UTF-8, which is also what GitHub expects for the notes file.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else f"v{package_version()}"))
