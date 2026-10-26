"""Contrôle en LECTURE SEULE d'un export.pdb : correspond-il au modèle sur lequel DJSync écrit ?

    python -m djsync.db.pdb.check E:\\
    python -m djsync.db.pdb.check E:\\PIONEER\\rekordbox\\export.pdb

Ne modifie rien. Sert à savoir, AVANT d'activer la synchronisation, si votre fichier est reconnu,
et — si ce n'est pas le cas — à fournir un rapport précis pour corriger le modèle.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .database import PdbDatabase
from .file import PdbFile
from .format import PAGE_SIZE, PdbError, PdbFormatError, T

NAMES = {T.TRACKS: "tracks", T.GENRES: "genres", T.ARTISTS: "artists", T.ALBUMS: "albums", T.LABELS: "labels",
         T.KEYS: "keys", T.COLORS: "colours", T.PLAYLIST_TREE: "playlist tree",
         T.PLAYLIST_ENTRIES: "playlist entries", T.ARTWORK: "artwork"}
WRITABLE = (T.TRACKS, T.ARTISTS, T.ALBUMS, T.PLAYLIST_TREE, T.PLAYLIST_ENTRIES)


def resolve_pdb(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        p = p / "PIONEER" / "rekordbox" / "export.pdb"
    return p


def report(path: Path) -> List[str]:
    lines = [f"File    : {path}"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        return lines + [f"UNREADABLE: {exc}"]
    lines.append(f"Size    : {len(data)} bytes = {len(data) / PAGE_SIZE:g} pages of {PAGE_SIZE}")
    try:
        f = PdbFile(data)
    except PdbFormatError as exc:
        return lines + [f"NOT RECOGNISED: {exc}", "=> DJSync will NOT write to this file."]
    lines.append(f"Tables  : {len(f.tables)}; next free page: {f.next_unused}; sequence: {f.seq}")
    ok = True
    for ttype in sorted(f.tables):
        tab = f.tables[ttype]
        label = NAMES.get(ttype, f"unknown {ttype}")
        try:
            chain = f.chain(ttype)
            idx = [p for p in chain if f.page(p).is_index]
            n_rows = sum(1 for _ in f.iter_rows(ttype)) if ttype in WRITABLE else None
            grow = ""
            if ttype in WRITABLE:
                grow = _growth_state(f, ttype)
            lines.append(f"  [{ttype:2d}] {label:22s} pages {len(chain):3d} (index: {len(idx)})"
                         + (f"  rows {n_rows}" if n_rows is not None else "") + (f"  growth: {grow}" if grow else ""))
        except PdbError as exc:
            if ttype in WRITABLE:
                ok = False
            lines.append(f"  [{ttype:2d}] {label:22s} PROBLEM: {exc}")
    links = f.index_link_problems()
    for problem in links:
        lines.append(f"  INDEX: {problem} (Rekordbox reports the library as corrupted; DJSync repairs it at its next write)")
    try:
        db = PdbDatabase(data)
        lines.append(f"Tracks: {db.track_count}; playlists/folders: {db.playlist_count()}")
    except PdbError as exc:
        ok = False
        lines.append(f"Full load: FAILED: {exc}")
    lines.append("")
    lines.append("=> Layout recognised: DJSync can add/remove rows in the existing pages."
                 if ok else "=> Layout NOT recognised for at least one table in use: DJSync will not write to this file.")
    return lines


def _growth_state(f: PdbFile, ttype: int) -> str:
    try:
        tab = f.table(ttype)
        chain = f.chain(ttype)
        if f.page(chain[-1]).next_page != tab.empty_candidate:
            return "no (empty candidate page not recognised)"
        new = tab.empty_candidate
        if new < f.n_pages and not f.page(new).is_blank():
            return f"no (page {new} not empty)"
        return "possible"
    except PdbError as exc:
        return f"no ({exc})"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.db.pdb.check", description="Read-only check of export.pdb: can DJSync safely update it?")
    ap.add_argument("target", help="drive root (E:\\) or path of export.pdb")
    args = ap.parse_args(argv)
    lines = report(resolve_pdb(args.target))
    print("\n".join(lines))
    return 0 if lines[-1].startswith("=> Layout recognised") else 1


if __name__ == "__main__":
    sys.exit(main())
