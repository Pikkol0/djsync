"""Écran de démarrage : s'affiche dès le double-clic, pendant le chargement des modules et la
construction de la fenêtre (environ 1 s depuis les sources, davantage pour l'exécutable).

Volontairement minimal : Tkinter seul (pas de customtkinter, pas de Pillow), logo dessiné sur un
Canvas à la couleur du thème choisi, nom, « Loading… ». Aucune barre de progression.

Exécutable PyInstaller : l'écran de démarrage natif de PyInstaller (packaging/DJSync.spec) couvre
déjà la décompression ; celui-ci n'est alors pas affiché et `close_native()` ferme le natif.
"""
from __future__ import annotations

import json
import tkinter as tk
from typing import Optional

from .. import __version__
from .logo import LogoCanvas
from .palettes import DEFAULT_THEME, DIM, ELEV, PALETTES, SURFACE, TEXT

WIDTH, HEIGHT = 340, 210      # unités logiques (x facteur DPI de l'écran)


def native_splash_active() -> bool:
    try:
        import pyi_splash  # noqa: F401  (n'existe que dans l'exécutable PyInstaller)
        return True
    except ImportError:
        return False


def close_native() -> None:
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:  # noqa: BLE001 - pas d'écran natif (lancement depuis les sources)
        pass


def _saved_accent() -> str:
    """Couleur choisie dans les Paramètres, lue sans charger toute l'application."""
    try:
        from ..settings import Settings

        theme = json.loads(Settings.path().read_text(encoding="utf-8")).get("theme", DEFAULT_THEME)
    except Exception:  # noqa: BLE001 - pas encore de réglages : couleur par défaut
        theme = DEFAULT_THEME
    return PALETTES.get(theme, PALETTES[DEFAULT_THEME])


class Splash:
    """Fenêtre sans bordure, centrée. `close()` la détruit (idempotent)."""

    def __init__(self) -> None:
        root = tk.Tk()
        self.root: Optional[tk.Tk] = root
        # Ce Tk temporaire ne doit pas devenir la racine par défaut de l'application (images,
        # polices de customtkinter) : la vraie fenêtre la remplace dès sa création.
        tk._default_root = None  # type: ignore[attr-defined]
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg=SURFACE)
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        k = max(1.0, root.winfo_fpixels("1i") / 96.0)          # facteur DPI de l'écran
        w, h = int(WIDTH * k), int(HEIGHT * k)
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        accent = _saved_accent()
        border = tk.Frame(root, bg=ELEV, padx=1, pady=1)
        border.pack(fill="both", expand=True)
        box = tk.Frame(border, bg=SURFACE)
        box.pack(fill="both", expand=True)
        logo = LogoCanvas(box, int(64 * k), accent, SURFACE, ELEV)
        logo.pack(pady=(int(34 * k), int(12 * k)))
        tk.Label(box, text="DJSync", bg=SURFACE, fg=TEXT, font=("Segoe UI", -int(24 * k), "bold")).pack()
        tk.Label(box, text=f"Loading…   v{__version__}", bg=SURFACE, fg=DIM,
                 font=("Segoe UI", -int(12 * k))).pack(pady=(int(6 * k), 0))
        root.deiconify()
        root.update()

    def close(self) -> None:
        root, self.root = self.root, None
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass


def show() -> Optional[Splash]:
    """Affiche l'écran de démarrage (sauf si celui de l'exécutable est déjà visible ou sans écran)."""
    if native_splash_active():
        return None
    try:
        return Splash()
    except tk.TclError:
        return None
