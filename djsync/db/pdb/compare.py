"""Comparaison en LECTURE SEULE de deux export.pdb (1.3.0, T01).

    python -m djsync.db.pdb.compare REFERENCE.pdb AUTRE.pdb [--playlist NOM] [-o rapport.txt]

Usage type (retour platine « la playlist créée par DJSync n'apparaît pas ») : REFERENCE = export.pdb
d'une clé où Rekordbox a créé une playlist, AUTRE = le même export après que DJSync a créé sa playlist
(ou une copie de la clé du testeur). Le rapport liste, table par table, l'en-tête du fichier, la chaîne
de pages et l'en-tête de chaque page (drapeaux, compteurs, octets bruts), puis les lignes de l'arbre
des playlists et les entrées de la playlist demandée, et signale les incohérences qu'une platine peut
refuser : entrée qui pointe vers un son ou une playlist absents, numéros d'entrée non continus,
playlist sans parent, ordres de tri en double.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import rows as _rows
from .check import NAMES, resolve_pdb
from .file import PdbFile
from .format import HEADER, PdbError, T


def _hex(b: bytes) -> str:
    return b.hex(" ")


def _load(path: Path) -> PdbFile:
    return PdbFile(path.read_bytes())


def tree_rows(f: PdbFile) -> List[Dict[str, object]]:
    out = []
    for p, i, off in f.iter_rows(T.PLAYLIST_TREE):
        pos = f.page(p).base + off
        end = _rows.row_end(T.PLAYLIST_TREE, f.data, pos)
        row = dict(_rows.read_tree(f.data, pos))
        row.update(page=p, slot=i, raw=bytes(f.data[pos:end]))
        out.append(row)
    return out


def entries(f: PdbFile) -> Dict[int, List[Dict[str, int]]]:
    by: Dict[int, List[Dict[str, int]]] = defaultdict(list)
    for p, i, off in f.iter_rows(T.PLAYLIST_ENTRIES):
        e = dict(_rows.read_entry(f.data, f.page(p).base + off))
        e.update(page=p, slot=i)
        by[e["playlist"]].append(e)
    return by


def track_ids(f: PdbFile) -> set:
    ids = set()
    for p, _i, off in f.iter_rows(T.TRACKS):
        ids.add(int(_rows.read_track(f.data, f.page(p).base + off)["id"]))
    return ids


def anomalies(f: PdbFile) -> List[str]:
    """Incohérences de contenu qu'une platine peut refuser."""
    out: List[str] = []
    trees = tree_rows(f)
    ids = {int(t["id"]) for t in trees}
    tracks = track_ids(f)
    for t in trees:
        if int(t["parent"]) and int(t["parent"]) not in ids:
            out.append(f"playlist {t['id']} '{t['name']}': parent {t['parent']} missing")
    dup = Counter((int(t["parent"]), int(t["sort"])) for t in trees)
    for (parent, sort), n in dup.items():
        if n > 1:
            out.append(f"folder {parent}: sort order {sort} used {n} times")
    for pl, es in entries(f).items():
        if pl not in ids:
            out.append(f"{len(es)} entries point to missing playlist {pl}")
        missing = [e["track"] for e in es if e["track"] not in tracks]
        if missing:
            out.append(f"playlist {pl}: {len(missing)} entries point to missing tracks (e.g. {missing[:5]})")
        idx = sorted(e["index"] for e in es)
        if idx != list(range(1, len(idx) + 1)):
            out.append(f"playlist {pl}: entry numbers are not 1..{len(idx)} (got {idx[:10]}{'…' if len(idx) > 10 else ''})")
    return out


def describe(f: PdbFile, name: str, playlist: Optional[str]) -> List[str]:
    lines = [f"== {name}", f"pages {f.n_pages}, next free page {f.next_unused}, sequence {f.seq}, tables {len(f.tables)}",
             "header page 0: " + _hex(bytes(f.data[0:0x1C]))]
    for ttype in sorted(f.tables):
        tab = f.tables[ttype]
        label = NAMES.get(ttype, f"unknown {ttype}")
        lines.append(f"-- [{ttype:2d}] {label}: first {tab.first_page}, last {tab.last_page}, "
                     f"empty candidate {tab.empty_candidate}")
        try:
            chain = f.chain(ttype)
        except PdbError as exc:
            lines.append(f"   chain PROBLEM: {exc}")
            continue
        for p in chain:
            pg = f.page(p)
            lines.append(f"   page {p:4d} flags {pg.flags:#04x}{' index' if pg.is_index else ''} slots {pg.num_slots} "
                         f"valid {pg.num_valid} free {pg.free} used {pg.used} next {pg.next_page}")
            if ttype in (T.PLAYLIST_TREE, T.PLAYLIST_ENTRIES):
                lines.append("        header " + _hex(pg.raw()[:HEADER]))
    trees = tree_rows(f)
    lines.append(f"-- playlist tree ({len(trees)} rows)")
    for t in sorted(trees, key=lambda r: (int(r["parent"]), int(r["sort"]))):
        lines.append(f"   id {t['id']:4d} parent {t['parent']:4d} sort {t['sort']:3d} "
                     f"{'folder ' if t['folder'] else ''}'{t['name']}'  page {t['page']} slot {t['slot']}  raw {_hex(t['raw'])}")
    by = entries(f)
    wanted = [t for t in trees if playlist and str(t["name"]).casefold() == playlist.casefold()]
    for t in wanted:
        es = sorted(by.get(int(t["id"]), []), key=lambda e: e["index"])
        lines.append(f"-- entries of '{t['name']}' (id {t['id']}): {len(es)}")
        for e in es:
            lines.append(f"   #{e['index']:3d} track {e['track']:5d}  page {e['page']} slot {e['slot']}")
    bad = anomalies(f)
    lines.append("-- anomalies: " + ("none" if not bad else ""))
    lines += [f"   ! {b}" for b in bad]
    return lines


def compare(ref: Path, other: Path, playlist: Optional[str] = None) -> List[str]:
    out = [f"Reference : {ref}", f"Compared  : {other}", ""]
    files = {}
    for label, path in (("reference", ref), ("compared", other)):
        try:
            files[label] = _load(path)
        except (OSError, PdbError) as exc:
            out.append(f"{label}: NOT READABLE ({exc})")
    if len(files) < 2:
        return out
    a, b = files["reference"], files["compared"]
    out.append("== differences")
    if (a.data[0:0x1C] != b.data[0:0x1C]):
        out.append(f"header page 0 differs:\n   ref {_hex(bytes(a.data[0:0x1C]))}\n   cmp {_hex(bytes(b.data[0:0x1C]))}")
    for ttype in sorted(set(a.tables) | set(b.tables)):
        ta, tb = a.tables.get(ttype), b.tables.get(ttype)
        if ta is None or tb is None:
            out.append(f"table {ttype}: present in only one file")
            continue
        if (ta.first_page, ta.last_page, ta.empty_candidate) != (tb.first_page, tb.last_page, tb.empty_candidate):
            out.append(f"table {ttype} ({NAMES.get(ttype, '?')}): first/last/empty "
                       f"{ta.first_page}/{ta.last_page}/{ta.empty_candidate} -> {tb.first_page}/{tb.last_page}/{tb.empty_candidate}")
    na = {(t["parent"], t["name"]) for t in tree_rows(a)}
    for t in tree_rows(b):
        if (t["parent"], t["name"]) not in na:
            out.append(f"playlist only in compared file: id {t['id']} '{t['name']}' (parent {t['parent']}, sort {t['sort']}, "
                       f"page {t['page']} slot {t['slot']})")
    out.append("")
    out += describe(a, "reference", playlist) + [""] + describe(b, "compared", playlist)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.db.pdb.compare",
                                 description="Read-only comparison of two export.pdb files (player troubleshooting).")
    ap.add_argument("reference", help="export.pdb (or drive root) used as reference, e.g. written by Rekordbox")
    ap.add_argument("compared", help="export.pdb (or drive root) to compare, e.g. after DJSync")
    ap.add_argument("--playlist", help="playlist whose entries are listed in both files")
    ap.add_argument("-o", "--out", type=Path, help="write the report to this file")
    args = ap.parse_args(argv)
    lines = compare(resolve_pdb(args.reference), resolve_pdb(args.compared), args.playlist)
    text = "\n".join(lines)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"report: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
