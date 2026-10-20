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

NAMES = {T.TRACKS: "pistes", T.GENRES: "genres", T.ARTISTS: "artistes", T.ALBUMS: "albums", T.LABELS: "labels",
         T.KEYS: "tonalités", T.COLORS: "couleurs", T.PLAYLIST_TREE: "arbre des playlists",
         T.PLAYLIST_ENTRIES: "contenu des playlists"}
WRITABLE = (T.TRACKS, T.ARTISTS, T.ALBUMS, T.PLAYLIST_TREE, T.PLAYLIST_ENTRIES)


def resolve_pdb(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        p = p / "PIONEER" / "rekordbox" / "export.pdb"
    return p


def report(path: Path) -> List[str]:
    lines = [f"Fichier : {path}"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        return lines + [f"ILLISIBLE : {exc}"]
    lines.append(f"Taille  : {len(data)} octets = {len(data) / PAGE_SIZE:g} pages de {PAGE_SIZE}")
    try:
        f = PdbFile(data)
    except PdbFormatError as exc:
        return lines + [f"NON RECONNU : {exc}", "=> DJSync n'écrira PAS dans ce fichier."]
    lines.append(f"Tables  : {len(f.tables)} ; prochaine page libre : {f.next_unused} ; séquence : {f.seq}")
    ok = True
    for ttype in sorted(f.tables):
        tab = f.tables[ttype]
        label = NAMES.get(ttype, f"inconnue {ttype}")
        try:
            chain = f.chain(ttype)
            idx = [p for p in chain if f.page(p).is_index]
            n_rows = sum(1 for _ in f.iter_rows(ttype)) if ttype in WRITABLE else None
            grow = ""
            if ttype in WRITABLE:
                grow = _growth_state(f, ttype)
            lines.append(f"  [{ttype:2d}] {label:22s} pages {len(chain):3d} (index : {len(idx)})"
                         + (f"  lignes {n_rows}" if n_rows is not None else "") + (f"  agrandissement : {grow}" if grow else ""))
        except PdbError as exc:
            if ttype in WRITABLE:
                ok = False
            lines.append(f"  [{ttype:2d}] {label:22s} PROBLÈME : {exc}")
    try:
        db = PdbDatabase(data)
        lines.append(f"Pistes : {db.track_count} ; playlists/dossiers : {db.playlist_count()}")
    except PdbError as exc:
        ok = False
        lines.append(f"Chargement complet : ÉCHEC : {exc}")
    lines.append("")
    lines.append("=> Modèle reconnu : DJSync peut ajouter/retirer des lignes dans les pages existantes."
                 if ok else "=> Modèle NON reconnu pour au moins une table utilisée : DJSync n'écrira pas dans ce fichier.")
    return lines


def _growth_state(f: PdbFile, ttype: int) -> str:
    try:
        tab = f.table(ttype)
        chain = f.chain(ttype)
        if f.page(chain[-1]).next_page != tab.empty_candidate:
            return "non (page vide candidate non reconnue)"
        idx = [p for p in chain if f.page(p).is_index]
        if idx:
            f._locate_index_run(idx[0], [p for p in chain if p != idx[0]])
        return "possible"
    except PdbError as exc:
        return f"non ({exc})"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.db.pdb.check", description=__doc__.split("\n")[0])
    ap.add_argument("target", help="racine de la clé (E:\\) ou chemin de export.pdb")
    args = ap.parse_args(argv)
    lines = report(resolve_pdb(args.target))
    print("\n".join(lines))
    return 0 if lines[-1].startswith("=> Modèle reconnu") else 1


if __name__ == "__main__":
    sys.exit(main())
