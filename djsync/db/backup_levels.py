"""1.4.4 (C235) : quantité de sauvegardes en un seul réglage : Légères / Normales / Complètes.

Toujours au moins une copie de master.db et le point d'origine de la clé (ce qui évite de perdre une
bibliothèque). Le niveau est posé par l'application (réglage `backup_level`) ; les modules des bases lisent
les limites ici, au moment de faire le ménage.
"""
from __future__ import annotations

from typing import Dict

LEVELS: Dict[str, Dict[str, int]] = {
    # copies de master.db / de la clé « avant modification », copies « début de session » de master.db,
    # points automatiques et « avant restauration » de la clé, grilles et cues d'origine (ANLZ)
    "light": {"copies": 3, "sessions": 1, "key_recent": 2, "key_restore": 1, "anlz": 30},
    "normal": {"copies": 10, "sessions": 5, "key_recent": 5, "key_restore": 3, "anlz": 200},
    "full": {"copies": 50, "sessions": 10, "key_recent": 10, "key_restore": 5, "anlz": 1000},
}
DEFAULT = "normal"
_current = DEFAULT


def set_level(level: str) -> str:
    global _current
    _current = level if level in LEVELS else DEFAULT
    return _current


def level() -> str:
    return _current


def limit(name: str) -> int:
    """Limite du niveau en cours (au moins 1)."""
    return max(1, LEVELS[_current][name])


def from_copies(copies: int) -> str:
    """Reprise d'un ancien réglage « copies conservées » (5 / 10 / 20 / 50)."""
    return "light" if copies <= 5 else "full" if copies >= 20 else "normal"


def _size(p) -> int:
    from pathlib import Path

    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0


def prune_now(backup_dir) -> int:
    """« Supprimer les anciennes » : applique tout de suite le niveau choisi au dossier de sauvegardes d'une
    bibliothèque (copies de master.db et « début de session », points automatiques de la clé, grilles d'origine).
    Le point d'origine, les points manuels et la dernière copie restent toujours. Renvoie les octets libérés."""
    import shutil
    from pathlib import Path

    root = Path(backup_dir)
    if not root.is_dir():
        return 0
    before = _size(root)
    for pattern, keep in (("master-*", limit("copies")), ("session-*", limit("sessions"))):
        olds = sorted(p for p in root.glob(pattern) if p.is_dir())
        for old in olds[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
    from . import backups

    if (root / backups.POINTS_DIR).is_dir():
        backups.prune(root)
    anlz = root / "anlz"
    if anlz.is_dir():
        from .library.metadata import prune_folders

        prune_folders(anlz, limit("anlz"))
    return max(0, before - _size(root))
