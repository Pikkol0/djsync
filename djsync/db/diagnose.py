"""Diagnostic d'une clé : pourquoi un son ajouté par DJSync n'apparaît pas dans Rekordbox ?

Usage (en ligne de commande, Rekordbox FERMÉ) :
    python -m djsync.db.diagnose E:\\            # lecture seule, affiche le rapport
    python -m djsync.db.diagnose E:\\ --inspect  # + convention des sons natifs (NULL / 0 / valide)

Le rapport vérifie, pour la base OneLibrary (exportLibrary.db) :
  * la présence de l'ancien format (export.pdb), que DJSync ne met pas à jour ;
  * l'intégrité SQLite et le mode WAL ;
  * les fichiers référencés mais absents de la clé, les chemins mal formés ;
  * les clés étrangères pendantes (artiste/album/couleur… qui désignent une ligne inexistante) ;
  * les lignes de playlist_content orphelines et le compteur property.numberOfContents.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Sequence

from .usb import drive_from_letter
from .usb_library import _CONTENT_FKS, LEGACY_DB_NAMES, RekordboxUsbLibrary


@dataclass
class DiagnosticReport:
    drive: str = ""
    journal_mode: str = ""
    integrity: str = ""
    track_count: int = 0
    playlist_count: int = 0
    legacy_files: List[str] = field(default_factory=list)
    legacy_newer_than_onelibrary: Optional[bool] = None
    missing_files: List[str] = field(default_factory=list)
    bad_paths: List[str] = field(default_factory=list)
    dangling_fks: List[str] = field(default_factory=list)
    orphan_playlist_rows: int = 0
    counter_mismatch: Optional[str] = None
    pdb_state: str = ""
    pdb_detail: str = ""

    @property
    def problems(self) -> List[str]:
        out: List[str] = []
        if self.legacy_files:
            if self.pdb_state == "ok":
                pass   # export.pdb reconnu et à jour : rien à signaler
            else:
                why = {"unsupported": "format non reconnu par DJSync, il n'est pas mis à jour",
                       "stale": "il ne contient pas tous les sons/playlists (Paramètres > Synchroniser)",
                       "off": "synchronisation désactivée"}.get(self.pdb_state, "état inconnu")
                out.append(
                    f"Ancien format présent ({', '.join(self.legacy_files)}) : {why}. Les platines qui le lisent "
                    "ne voient pas les ajouts faits dans exportLibrary.db." + (f" [{self.pdb_detail}]" if self.pdb_detail else ""))
        if self.integrity and self.integrity.lower() != "ok":
            out.append(f"Intégrité SQLite : {self.integrity}")
        if self.missing_files:
            out.append(f"{len(self.missing_files)} son(s) référencé(s) dont le fichier est absent de la clé.")
        if self.bad_paths:
            out.append(f"{len(self.bad_paths)} chemin(s) mal formé(s) (attendu : « /Contents/… », sans « \\\\ »).")
        if self.orphan_playlist_rows:
            out.append(f"{self.orphan_playlist_rows} ligne(s) de playlist pointent vers un son/une playlist inexistant(e).")
        if self.counter_mismatch:
            out.append(self.counter_mismatch)
        return out

    def lines(self) -> List[str]:
        rows = [
            f"Clé                : {self.drive}",
            f"Sons / playlists   : {self.track_count} / {self.playlist_count}",
            f"Mode journal       : {self.journal_mode}",
            f"Format ancien      : {', '.join(self.legacy_files) or 'absent (OneLibrary seul)'}",
        ]
        if self.legacy_newer_than_onelibrary is not None:
            rows.append("export.pdb         : " + (
                "plus récent que exportLibrary.db" if self.legacy_newer_than_onelibrary
                else "plus ancien que exportLibrary.db"))
        if self.dangling_fks:  # information : Rekordbox lui-même en laisse (0 = « aucun »)
            rows.append("Réf. sans ligne cible : " + "; ".join(self.dangling_fks) + "  (info, pas une erreur)")
        if self.legacy_files:
            rows.append(f"Synchro export.pdb : {self.pdb_state or '?'}" + (f" ({self.pdb_detail})" if self.pdb_detail else ""))
        rows.append("")
        problems = self.problems
        rows += ["Aucun problème détecté dans la base OneLibrary."] if not problems else (
            ["Problèmes :"] + [f"  - {p}" for p in problems])
        for title, items in (("Fichiers absents", self.missing_files), ("Chemins mal formés", self.bad_paths)):
            if items:
                rows += ["", f"{title} (20 premiers) :"] + [f"  {i}" for i in items[:20]]
        return rows


def diagnose(library: RekordboxUsbLibrary, sample: int = 20) -> DiagnosticReport:
    """Rapport complet. La bibliothèque doit être connectée (lecture seule suffit)."""
    rep = DiagnosticReport(drive=str(library.drive), journal_mode=library.journal_mode)
    q = library._read

    rep.integrity = str(q("PRAGMA quick_check")[0][0])
    rep.track_count = q("SELECT COUNT(*) FROM content")[0][0]
    rep.playlist_count = q("SELECT COUNT(*) FROM playlist")[0][0]

    folder = library.db_path.parent
    present = [n for n in LEGACY_DB_NAMES if (folder / n).is_file()]
    rep.legacy_files = present
    if "export.pdb" in present:
        st = library.pdb_status()
        rep.pdb_state = st.state
        rep.pdb_detail = st.detail or (f"{st.missing_tracks} son(s) absent(s)" if st.missing_tracks else "")
    if present:
        rep.legacy_newer_than_onelibrary = (folder / present[0]).stat().st_mtime > library.db_path.stat().st_mtime

    for path in (r[0] for r in q("SELECT path FROM content")):
        path = path or ""
        if not path.startswith("/") or "\\" in path:
            rep.bad_paths.append(path)
            continue
        if not library.absolute_path(path).is_file():
            rep.missing_files.append(path)

    for col, table, id_col in _CONTENT_FKS:
        if not any(c[1] == col for c in q('PRAGMA table_info("content")')):
            continue
        if table in library._tables:
            n = q(f'SELECT COUNT(*) FROM content WHERE {col} IS NOT NULL AND {col} NOT IN '
                  f'(SELECT {id_col} FROM "{table}")')[0][0]
        else:
            n = q(f"SELECT COUNT(*) FROM content WHERE {col} = 0")[0][0]
        if n:
            rep.dangling_fks.append(f"content.{col} ({n})")

    rep.orphan_playlist_rows = q(
        "SELECT COUNT(*) FROM playlist_content pc WHERE pc.content_id NOT IN (SELECT content_id FROM content) "
        "OR pc.playlist_id NOT IN (SELECT playlist_id FROM playlist)")[0][0]

    prop = q("SELECT numberOfContents FROM property LIMIT 1")
    if prop and prop[0][0] != rep.track_count:
        rep.counter_mismatch = (
            f"property.numberOfContents = {prop[0][0]} mais la base contient {rep.track_count} son(s).")

    return rep


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djsync.db.diagnose", description=__doc__.split("\n")[0])
    ap.add_argument("drive", help='lettre ou dossier racine de la clé (ex. "E:" ou "/media/usb")')
    ap.add_argument("--inspect", action="store_true", help="affiche comment Rekordbox renseigne les colonnes optionnelles")
    args = ap.parse_args(argv)

    try:
        drive = drive_from_letter(args.drive)
        with RekordboxUsbLibrary(drive, read_only=True) as lib:   # jamais d'écriture ici
            report = diagnose(lib)
            conventions = lib.inspect_conventions() if args.inspect else {}
    except Exception as exc:  # noqa: BLE001 - affichage lisible en ligne de commande
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    print(f"=== DJSync – diagnostic {datetime.now():%Y-%m-%d %H:%M} ===")
    print("\n".join(report.lines()))
    for name, counts in conventions.items():
        print(f"  {name:28s} " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
