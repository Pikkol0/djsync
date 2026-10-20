"""Thème : fond sombre neutre + UNE couleur d'accent choisie parmi ~20 palettes néon / pastel.

L'accent est volontairement rare : onglet actif, bouton principal, curseurs, élément en lecture.
Tout le reste est neutre. Par défaut : « Violet clair » (`DEFAULT_THEME`).

Fonctionnement :
  * `apply_palette("cyan")` recalcule ACCENT, ACCENT_HOVER, ACCENT_DIM, ON_ACCENT (variables de ce
    module, lues partout sous la forme `theme.ACCENT`) ;
  * les widgets déjà créés gardent leurs anciennes couleurs : changer de thème en cours d'exécution
    demande de reconstruire l'interface (prévu à l'étape Paramètres) ;
  * `set_zoom(150)` agit sur customtkinter (widgets + fenêtre) ET sur les mesures Tk brutes.

Deux fonctions de taille, à ne pas confondre :
  * `px(n)`   : taille pour un widget customtkinter. Renvoie n tel quel : customtkinter applique
                déjà DPI × zoom (mettre à l'échelle ici aussi la doublerait) ;
  * `tkpx(n)` : taille pour Tk « brut » (ttk.Treeview, PhotoImage, colonnes, rowheight) : n × DPI × zoom.
"""
from __future__ import annotations

from tkinter import ttk
from typing import Any, Dict, Optional, Tuple

import customtkinter as ctk

# ---- palette neutre (identique pour tous les thèmes)
BG = "#0B0B0D"          # fond de fenêtre
SURFACE = "#121216"     # panneaux, tableaux
ELEV = "#1A1A20"        # éléments surélevés (en-têtes, survol)
BORDER = "#26262E"
TEXT = "#ECECF1"
DIM = "#8D8D99"
FAINT = "#5A5A66"

WARN = "#F5A524"        # doublon / à vérifier
ERR = "#F2555A"
ERR_DIM = "#3A1517"

# ---- accents : identifiant -> couleur (le nom affiché est la clé i18n « theme.<identifiant> »)
DEFAULT_THEME = "violet_light"
PALETTES: Dict[str, str] = {
    "violet_light": "#B79CFF",   # défaut
    "lavender": "#D2B8FF",
    "neon_violet": "#A855FF",
    "electric_blue": "#4D7CFF",
    "sky": "#7CC4FF",
    "cyan": "#36E2FF",
    "turquoise": "#2EE6C5",
    "mint": "#8FF5C8",
    "neon_green": "#39FF88",
    "lime": "#B6F23A",           # accent de la V0.1.0
    "yellow": "#F5FF3D",
    "amber": "#FFB020",
    "orange": "#FF8A2B",
    "coral": "#FF7A7A",
    "red": "#FF3D5A",
    "hot_pink": "#FF3D9A",
    "magenta": "#F03DFF",
    "pastel_pink": "#FFB3D9",
    "pastel_peach": "#FFCBA4",
    "pastel_blue": "#A9CCFF",
}

ACCENT = ACCENT_HOVER = ACCENT_DIM = ON_ACCENT = ""   # renseignés par apply_palette() ci-dessous
CURRENT_THEME = DEFAULT_THEME

FAMILY = "Segoe UI"     # repli automatique si absente (Linux/macOS)
ROW_HEIGHT = 48         # unités de base : pochette 40 + marge
COVER_SIZE = 40


def _rgb(color: str) -> Tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, ratio: float) -> str:
    """Mélange de deux couleurs « #RRGGBB » : ratio 0 -> a, 1 -> b."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * ratio) for x, y in zip(ra, rb))


def luminance(color: str) -> float:
    """Luminance relative (0 noir … 1 blanc), formule WCAG."""
    def lin(v: int) -> float:
        v_ = v / 255
        return v_ / 12.92 if v_ <= 0.03928 else ((v_ + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_color(background: str) -> str:
    """Texte (fond sombre du thème ou blanc) le plus lisible posé sur `background`."""
    return BG if contrast(background, BG) >= contrast(background, "#FFFFFF") else "#FFFFFF"


def palette_colors(accent: str) -> Dict[str, str]:
    """Dérive les 4 couleurs d'un thème à partir de son accent."""
    return {
        "ACCENT": accent,
        "ACCENT_HOVER": mix(accent, "#FFFFFF", 0.28),
        "ACCENT_DIM": mix(SURFACE, accent, 0.20),                # sélection de ligne (accent très atténué)
        "ON_ACCENT": on_color(accent),                          # texte posé sur l'accent
    }


def apply_palette(name: str) -> str:
    """Active une palette (identifiant inconnu -> défaut). Renvoie l'identifiant réellement appliqué."""
    global ACCENT, ACCENT_HOVER, ACCENT_DIM, ON_ACCENT, CURRENT_THEME
    if name not in PALETTES:
        name = DEFAULT_THEME
    colors = palette_colors(PALETTES[name])
    ACCENT, ACCENT_HOVER = colors["ACCENT"], colors["ACCENT_HOVER"]
    ACCENT_DIM, ON_ACCENT = colors["ACCENT_DIM"], colors["ON_ACCENT"]
    CURRENT_THEME = name
    return name


apply_palette(DEFAULT_THEME)

# ---- échelle
_DPI = 1.0       # facteur DPI de l'écran (Windows « 150 % »…)
_ZOOM = 1.0      # option utilisateur 100–200 %


def set_scale(value: float) -> None:
    """`value` = facteur total lu sur la fenêtre customtkinter (DPI × zoom déjà appliqué)."""
    global _DPI
    _DPI = max(0.5, float(value or 1.0)) / _ZOOM


def set_zoom(percent: float, root: Optional[Any] = None) -> float:
    """Zoom utilisateur (100–200 %). Applique customtkinter ; avec `root`, rafraîchit aussi les ttk."""
    global _ZOOM
    _ZOOM = max(1.0, min(2.0, float(percent) / 100.0))
    ctk.set_widget_scaling(_ZOOM)
    ctk.set_window_scaling(_ZOOM)
    if root is not None:
        apply_ttk_style(root)
    return _ZOOM


def zoom_factor() -> float:
    return _ZOOM


def px(n: float) -> int:
    """Taille pour un widget customtkinter (déjà mis à l'échelle par la bibliothèque)."""
    return int(round(n))


def tkpx(n: float) -> int:
    """Taille pour Tk brut (ttk, PhotoImage, colonnes) : DPI × zoom."""
    return int(round(n * _DPI * _ZOOM))


def font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


def tk_font(size: int = 10, weight: str = "") -> Tuple[Any, ...]:
    """Police pour ttk (non gérée par customtkinter) : suit le zoom."""
    size = max(6, int(round(size * _ZOOM)))
    return (FAMILY, size, weight) if weight else (FAMILY, size)


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
        relief="flat", rowheight=tkpx(ROW_HEIGHT), font=tk_font(10),
    )
    style.configure(
        "Treeview.Heading", background=ELEV, foreground=DIM, relief="flat", borderwidth=0,
        font=tk_font(9, "bold"), padding=(tkpx(8), tkpx(7)),
    )
    style.map("Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", BORDER)], foreground=[("active", TEXT)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # supprime le cadre pointillé
    # arbre de navigation (playlists) : lignes plus compactes, sans pochette
    style.configure("Nav.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, borderwidth=0,
                    rowheight=tkpx(30), font=tk_font(10), indent=tkpx(16))
    style.map("Nav.Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", ACCENT)])
    style.layout("Nav.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
