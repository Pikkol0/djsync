"""Thème : noir/gris très foncé + une couleur signature « acid lime ».

Le lime est volontairement rare : onglet actif, bouton principal, curseurs, élément en
lecture. Tout le reste est neutre. Pour changer d'ambiance, modifiez seulement ACCENT*
(ex. "#FF3D81" magenta laser, "#36E2FF" cyan, "#FFB020" ambre VU-mètre).
"""
from __future__ import annotations

from tkinter import ttk
from typing import Any, Optional

import customtkinter as ctk

# ---- palette
BG = "#0B0B0D"          # fond de fenêtre
SURFACE = "#121216"     # panneaux, tableaux
ELEV = "#1A1A20"        # éléments surélevés (en-têtes, survol)
BORDER = "#26262E"
TEXT = "#ECECF1"
DIM = "#8D8D99"
FAINT = "#5A5A66"

ACCENT = "#B6F23A"          # signature : acid lime
ACCENT_HOVER = "#CBFA5E"
ACCENT_DIM = "#27330F"      # sélection de ligne (lime très atténué)
ON_ACCENT = "#0B0B0D"       # texte posé sur le lime

WARN = "#F5A524"        # doublon / à vérifier
ERR = "#F2555A"
ERR_DIM = "#3A1517"

FAMILY = "Segoe UI"     # repli automatique si absente (Linux/macOS)
ROW_HEIGHT = 48         # px à 100 % : pochette 40 px + marge
COVER_SIZE = 40

SCALE = 1.0


def set_scale(value: float) -> None:
    global SCALE
    SCALE = max(0.75, float(value or 1.0))


def px(n: float) -> int:
    """Pixels mis à l'échelle de l'écran (Tk ne scale pas ttk tout seul)."""
    return int(round(n * SCALE))


def font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


# ------------------------------------------------------------------- fabriques de widgets
def label(parent: Any, text: str = "", size: int = 12, color: str = TEXT, weight: str = "normal", **kw: Any) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, text_color=color, font=font(size, weight), **kw)


def button(parent: Any, text: str, command: Any = None, kind: str = "ghost", width: Optional[int] = None, **kw: Any) -> ctk.CTkButton:
    """kind : primary (lime plein) · ghost (contour discret) · danger · flat (sans cadre)."""
    styles = {
        "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT, border_width=0),
        "ghost": dict(fg_color="transparent", hover_color=ELEV, text_color=TEXT, border_width=1, border_color=BORDER),
        "danger": dict(fg_color="transparent", hover_color=ERR_DIM, text_color=ERR, border_width=1, border_color=ERR_DIM),
        "flat": dict(fg_color="transparent", hover_color=ELEV, text_color=DIM, border_width=0),
    }[kind]
    return ctk.CTkButton(
        parent, text=text, command=command, width=width or px(96), height=px(32), corner_radius=6,
        font=font(12, "bold" if kind == "primary" else "normal"), text_color_disabled=FAINT, **styles, **kw,
    )


def entry(parent: Any, placeholder: str = "", **kw: Any) -> ctk.CTkEntry:
    return ctk.CTkEntry(
        parent, placeholder_text=placeholder, fg_color=SURFACE, border_color=BORDER, text_color=TEXT,
        placeholder_text_color=FAINT, corner_radius=6, border_width=1, height=px(34), font=font(12), **kw,
    )


def option_menu(parent: Any, values: list, command: Any = None, width: Optional[int] = None, **kw: Any) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(
        parent, values=values, command=command, width=width or px(150), height=px(32), corner_radius=6,
        fg_color=SURFACE, button_color=ELEV, button_hover_color=BORDER, text_color=TEXT,
        dropdown_fg_color=ELEV, dropdown_hover_color=ACCENT_DIM, dropdown_text_color=TEXT,
        font=font(12), dropdown_font=font(12), **kw,
    )


def checkbox(parent: Any, text: str, **kw: Any) -> ctk.CTkCheckBox:
    return ctk.CTkCheckBox(
        parent, text=text, text_color=TEXT, font=font(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
        checkmark_color=ON_ACCENT, border_color=FAINT, border_width=2, corner_radius=4,
        checkbox_width=px(18), checkbox_height=px(18), **kw,
    )


def slider(parent: Any, **kw: Any) -> ctk.CTkSlider:
    return ctk.CTkSlider(
        parent, fg_color=BORDER, progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
        height=px(14), **kw,
    )


# ------------------------------------------------------------------------- style ttk
def apply_ttk_style(root: Any) -> None:
    """Tableaux (ttk.Treeview) assortis au thème sombre : légers, rapides, avec images."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, borderwidth=0,
        relief="flat", rowheight=px(ROW_HEIGHT), font=(FAMILY, 10),
    )
    style.configure(
        "Treeview.Heading", background=ELEV, foreground=DIM, relief="flat", borderwidth=0,
        font=(FAMILY, 9, "bold"), padding=(px(8), px(7)),
    )
    style.map("Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", BORDER)], foreground=[("active", TEXT)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # supprime le cadre pointillé
    # arbre de navigation (playlists) : lignes plus compactes, sans pochette
    style.configure("Nav.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, borderwidth=0,
                    rowheight=px(30), font=(FAMILY, 10), indent=px(16))
    style.map("Nav.Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", ACCENT)])
    style.layout("Nav.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
