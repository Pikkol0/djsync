"""Assemble le DJSync.exe en UN SEUL FICHIER : lanceur + application zippée + bloc de fin.

    python packaging/pack_single_exe.py launcher.exe dist/DJSync 1.0.0 out/DJSync.exe

`dist/DJSync` = dossier PyInstaller (DJSync.exe, _internal, tools). Le lanceur (launcher/launcher.c)
lit le bloc de fin "DJSYNCPK" | début du zip | taille | version, et extrait l'application dans
.djsync/app à côté de lui au premier lancement (ou quand la version change).
"""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

MAGIC = b"DJSYNCPK"


def pack(launcher: Path, app_dir: Path, version: str, out: Path) -> int:
    if not (app_dir / "DJSync.exe").is_file():
        raise SystemExit(f"{app_dir} does not contain DJSync.exe")
    tag = version.encode("ascii")
    if len(tag) > 32:
        raise SystemExit("version longer than 32 characters")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = out.with_suffix(".zip.tmp")
    files = sorted(p for p in app_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            zf.write(f, f.relative_to(app_dir).as_posix())
    head = launcher.read_bytes()
    with open(out, "wb") as fh:
        fh.write(head)
        start = fh.tell()
        with open(payload, "rb") as src:
            while chunk := src.read(1 << 20):
                fh.write(chunk)
        size = fh.tell() - start
        fh.write(MAGIC + struct.pack("<QQ", start, size) + tag.ljust(32, b"\0"))
    payload.unlink()
    print(f"{out}: {len(files)} files, {out.stat().st_size / 1e6:.1f} MB")
    return len(files)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    pack(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
