"""1.4.0-rc.2 (C139) : « Afficher dans l'explorateur » (Finder sur Mac) pour le fichier d'un son."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional


def reveal_command(path: Path, platform: Optional[str] = None) -> Optional[List[str]]:
    """Commande qui ouvre le dossier avec le fichier sélectionné ; None : ouvrir simplement le dossier."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        return ["explorer", f"/select,{path}"]
    if platform == "darwin":
        return ["open", "-R", str(path)]
    return None


def reveal(path: Any) -> bool:
    """Montre le fichier ; False s'il n'existe pas."""
    p = Path(str(path))
    if not p.is_file():
        return False
    cmd = reveal_command(p)
    if cmd is not None:
        subprocess.Popen(cmd)  # noqa: S603 - chemin du son, pas de shell
        return True
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
    return True


def reveal_entry(ctrl: Any, track: Any) -> tuple:
    """Entrée de menu pour un son de la bibliothèque (message clair si le fichier est introuvable)."""
    from ..i18n import t

    def go() -> None:
        try:
            path = ctrl.library.absolute_path(track)
        except Exception:  # noqa: BLE001
            path = None
        if path is None or not reveal(path):
            ctrl.message("error", ctrl.missing_file_text(path or getattr(track, "path", "")))

    key = "reveal.finder" if sys.platform == "darwin" else "reveal.explorer"
    return (t(key), go, "folder")
