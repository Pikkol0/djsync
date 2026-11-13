"""Grilles vérifiées à la main (1.4.2, C113) : sons dont la grille a été enregistrée depuis « Grille et cues ».

Petit fichier JSON dans le dossier de sauvegarde de la bibliothèque (DJSync_Backups de la clé, ou celui de
l'ordinateur) : il suit la clé d'un PC à l'autre, sans toucher à exportLibrary.db ni à export.pdb.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Set

log = logging.getLogger(__name__)
FILE = "grids_checked.json"


def load(backup_dir: Any) -> Set[int]:
    try:
        data = json.loads((Path(backup_dir) / FILE).read_text(encoding="utf-8"))
        return {int(i) for i in data.get("ids", [])}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


def mark(backup_dir: Any, content_id: int) -> None:
    ids = load(backup_dir)
    if int(content_id) in ids:
        return
    ids.add(int(content_id))
    try:
        p = Path(backup_dir) / FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ids": sorted(ids)}), encoding="utf-8")
        tmp.replace(p)
    except OSError as exc:                      # clé en lecture seule : sans gravité (simple pastille)
        log.info("Grid mark not saved: %s", exc)
