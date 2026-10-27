"""1.3.0-rc.5 (C62) : mémoire des « pas un doublon ».

Chaque choix est une paire de sons (identifiés par le chemin de leur fichier) qui ne doivent plus être
regroupés : « Afro Trap Pt. 7 n'est pas un doublon de Afro Trap Pt. 3 ». Gardée dans le dossier des
réglages (`duplicates_ignored.json`), lisible et réversible : liste des choix, « Annuler » sur chacun,
« Tout rétablir ».
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .duplicates import ignore_key, ignored_pair

log = logging.getLogger(__name__)
FILE_NAME = "duplicates_ignored.json"


class DuplicateIgnores:
    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            from ..settings import settings_dir

            path = settings_dir() / FILE_NAME
        self.path = Path(path)
        self.entries: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = [e for e in data.get("pairs", []) if isinstance(e, dict) and e.get("a") and e.get("b")]
        except FileNotFoundError:
            self.entries = []
        except Exception as exc:  # noqa: BLE001 - fichier abîmé : on repart de zéro sans planter
            log.warning("Duplicate choices unreadable (%s): starting again", exc)
            self.entries = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pairs": self.entries}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def pairs(self) -> set:
        return {frozenset((e["a"], e["b"])) for e in self.entries}

    def add(self, track: Any, others: Iterable[Any]) -> List[Dict[str, Any]]:
        """`track` n'est un doublon d'aucun des `others`. Renvoie les entrées ajoutées (pour annuler)."""
        known = self.pairs()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        added = []
        for o in others:
            if o is track or ignored_pair(track, o) in known:
                continue
            e = {"a": ignore_key(track), "b": ignore_key(o), "ta": track.title or "", "tb": o.title or "", "at": now}
            self.entries.append(e)
            added.append(e)
        if added:
            self.save()
        return added

    def add_group(self, group: List[Any]) -> List[Dict[str, Any]]:
        """Tout le groupe : aucun de ces sons n'est un doublon d'un autre."""
        added = []
        for i, x in enumerate(group):
            added += self.add(x, group[i + 1:])
        return added

    def remove(self, entries: Iterable[Dict[str, Any]]) -> None:
        drop = {(e["a"], e["b"]) for e in entries}
        self.entries = [e for e in self.entries if (e["a"], e["b"]) not in drop]
        self.save()

    def clear(self) -> None:
        self.entries = []
        self.save()
