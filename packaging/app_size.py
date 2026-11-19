"""Taille de l'application (1.4.3, C176) : ce que pèse chaque partie de DJSync.exe une fois extrait.

    python packaging/app_size.py out/DJSync.exe      (ou un dossier : dist/DJSync)

Écrit le total extrait, la taille de l'exe, puis les 25 plus gros dossiers et fichiers (annotation de la CI).
"""
from __future__ import annotations

import sys
import zipfile
from collections import Counter
from pathlib import Path


def sizes(target: Path) -> dict:
    if target.is_dir():
        return {p.relative_to(target).as_posix(): p.stat().st_size for p in target.rglob("*") if p.is_file()}
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from djsync.core.delta_update import _trailer, _Window

    with open(target, "rb") as fh:
        start, size = _trailer(fh, target.stat().st_size)
        with zipfile.ZipFile(_Window(fh, start, size)) as zf:
            return {i.filename: i.file_size for i in zf.infolist()}


def report(target: Path) -> str:
    files = sizes(target)
    total = sum(files.values())
    groups: Counter = Counter()
    for name, n in files.items():
        parts = name.split("/")
        key = "/".join(parts[:3]) if parts[0] == "_internal" and len(parts) > 2 else "/".join(parts[:2])
        groups[key] += n
    lines = [f"{target.name}: {total / 1e6:.1f} MB extracted, {len(files)} files"
             + (f", {target.stat().st_size / 1e6:.1f} MB packed" if target.is_file() else "")]
    lines += [f"  {n / 1e6:7.1f} MB  {k}" for k, n in groups.most_common(25)]
    lines += ["  largest files:"] + [f"  {n / 1e6:7.1f} MB  {k}" for k, n in Counter(files).most_common(15)]
    return "\n".join(lines)


if __name__ == "__main__":
    text = report(Path(sys.argv[1]))
    print(text)
    print("::notice title=App size (C176)::" + text.splitlines()[0])
