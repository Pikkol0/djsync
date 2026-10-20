"""Thème Qt (V0.3.0) : fond sombre neutre, UNE couleur d'accent, aucun effet.

Volontairement sobre : style Qt « Fusion », coins à peine arrondis (2 px), bordures de 1 px, pas
d'ombre, pas d'animation, pas de dégradé. Toute l'apparence tient dans UNE feuille de style
générée ici (`stylesheet()`), appliquée à l'application : changer de couleur ou de zoom la
régénère et Qt redessine, sans reconstruire les fenêtres.

Zoom (Paramètres, 80-200 %) : taille de la police de l'application + marges de la feuille de
style. Le facteur DPI de l'écran (Windows 125-150 %) est géré par Qt lui-même. Le zoom ne suit
plus la taille de la fenêtre (V0.3.0 : c'était la cause des redessins pendant un
redimensionnement).
"""
from __future__ import annotations

from typing import Optional, Tuple

from .palettes import DEFAULT_THEME, PALETTES

# ---- couleurs neutres (identiques pour tous les thèmes)
BG = "#0E0E10"
SURFACE = "#151518"
ELEV = "#1C1C21"
BORDER = "#2A2A31"
TEXT = "#E6E6EA"
DIM = "#9A9AA5"
FAINT = "#62626C"
WARN = "#E9A23B"
ERR = "#E5575C"

ACCENT = ON_ACCENT = ACCENT_DIM = ""
CURRENT_THEME = DEFAULT_THEME

ZOOM_MIN, ZOOM_MAX = 80, 200
BASE_PT = 10.0            # taille de police de base (points) à 100 %
_ZOOM = 1.0


def _rgb(color: str) -> Tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, ratio: float) -> str:
    """Mélange de deux couleurs « #RRGGBB » : ratio 0 -> a, 1 -> b."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * ratio) for x, y in zip(ra, rb))


def luminance(color: str) -> float:
    def lin(v: int) -> float:
        v_ = v / 255
        return v_ / 12.92 if v_ <= 0.03928 else ((v_ + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_color(background: str) -> str:
    """Texte (noir du thème ou blanc) le plus lisible posé sur `background`."""
    return BG if contrast(background, BG) >= contrast(background, "#FFFFFF") else "#FFFFFF"


def palette_colors(accent: str) -> dict:
    return {"ACCENT": accent, "ON_ACCENT": on_color(accent), "ACCENT_DIM": mix(SURFACE, accent, 0.22)}


def apply_palette(name: str) -> str:
    """Active une palette (identifiant inconnu -> défaut). Renvoie l'identifiant appliqué."""
    global ACCENT, ON_ACCENT, ACCENT_DIM, CURRENT_THEME
    if name not in PALETTES:
        name = DEFAULT_THEME
    c = palette_colors(PALETTES[name])
    ACCENT, ON_ACCENT, ACCENT_DIM = c["ACCENT"], c["ON_ACCENT"], c["ACCENT_DIM"]
    CURRENT_THEME = name
    return name


apply_palette(DEFAULT_THEME)


# ------------------------------------------------------------------------------ zoom
def set_zoom(percent: float) -> float:
    global _ZOOM
    _ZOOM = max(ZOOM_MIN, min(ZOOM_MAX, float(percent))) / 100.0
    return _ZOOM


def zoom() -> float:
    return _ZOOM


def px(n: float) -> int:
    """Taille en pixels logiques au zoom courant (Qt ajoute lui-même le facteur DPI)."""
    return max(1, int(round(n * _ZOOM)))


def font_pt(rel: float = 0.0) -> float:
    """Taille de police (points) : base x zoom, + `rel` points (titres)."""
    return (BASE_PT + rel) * _ZOOM


# ---- roue Camelot (1 -> 12) : teinte par position, comme Mixed In Key / Rekordbox
CAMELOT_COLORS = ["#4DE3B5", "#6BE36B", "#B6E34D", "#E3D94D", "#F2B24D", "#F2844D",
                  "#F25C6E", "#E35CB4", "#B05CE3", "#7A6BF2", "#4D9CF2", "#4DCFE3"]


def camelot_color(code: Optional[str]) -> str:
    try:
        n = int((code or "")[:-1])
    except ValueError:
        return FAINT
    return CAMELOT_COLORS[(n - 1) % 12]


# ----------------------------------------------------------------------- feuille de style
def stylesheet() -> str:
    """Feuille de style de toute l'application (couleurs + marges au zoom courant)."""
    p = px
    return f"""
* {{ outline: 0; }}
QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {ELEV}; color: {TEXT}; border: 1px solid {BORDER}; padding: {p(3)}px; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: {font_pt(6):.1f}pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: {font_pt(2):.1f}pt; font-weight: 600; }}
QLabel[role="dim"] {{ color: {DIM}; }}
QLabel[role="faint"] {{ color: {FAINT}; }}
QLabel[role="section"] {{ color: {FAINT}; font-size: {font_pt(-1.5):.1f}pt; font-weight: 600; }}
QLabel[role="warn"] {{ color: {WARN}; }}
QLabel[role="err"] {{ color: {ERR}; }}
QLabel[role="accent"] {{ color: {ACCENT}; }}
QFrame[role="panel"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 2px; }}
QFrame[role="panel"] QLabel, QFrame[role="panel"] QCheckBox {{ background: transparent; }}
QFrame[role="sidebar"] {{ background: {SURFACE}; border: 0; border-right: 1px solid {BORDER}; }}
QFrame[role="sidebar"] QWidget {{ background: {SURFACE}; }}
QFrame[role="bar"] {{ background: {SURFACE}; border: 0; border-top: 1px solid {BORDER}; }}
QFrame[role="bar"] QWidget {{ background: {SURFACE}; }}
QFrame[role="banner"] {{ background: {ACCENT_DIM}; border: 1px solid {ACCENT}; border-radius: 2px; }}
QFrame[role="banner"] QWidget {{ background: transparent; }}

QPushButton {{ background: {ELEV}; border: 1px solid {BORDER}; border-radius: 2px;
              padding: {p(4)}px {p(10)}px; min-height: {p(18)}px; }}
QPushButton:hover {{ border-color: {DIM}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {ELEV}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
QPushButton[kind="primary"]:disabled {{ background: {ELEV}; color: {FAINT}; border-color: {ELEV}; }}
QPushButton[kind="danger"] {{ color: {ERR}; }}
QPushButton[kind="flat"] {{ background: transparent; border: 0; color: {DIM}; }}
QPushButton[kind="flat"]:hover {{ color: {TEXT}; }}
QPushButton[kind="nav"] {{ background: transparent; border: 0; border-left: 2px solid transparent;
              text-align: left; padding: {p(7)}px {p(10)}px; color: {DIM}; }}
QPushButton[kind="nav"]:hover {{ color: {TEXT}; }}
QPushButton[kind="nav"]:checked {{ color: {TEXT}; border-left: 2px solid {ACCENT}; background: {ELEV}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 2px; padding: {p(3)}px; }}
QToolButton:hover {{ border-color: {BORDER}; }}
QToolButton:checked {{ border-color: {ACCENT}; }}
QToolButton::menu-indicator {{ image: none; }}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER};
              border-radius: 2px; padding: {p(4)}px {p(6)}px; selection-background-color: {ACCENT_DIM}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {ELEV}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM}; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: {p(6)}px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: {p(13)}px; height: {p(13)}px; border: 1px solid {DIM};
              background: {SURFACE}; }}
QRadioButton::indicator {{ border-radius: {p(7)}px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTableView, QTreeWidget, QListWidget {{ background: {SURFACE}; alternate-background-color: {mix(SURFACE, BG, 0.5)};
              border: 1px solid {BORDER}; gridline-color: {BORDER};
              selection-background-color: {ACCENT_DIM}; selection-color: {TEXT}; }}
QTableView::item, QTreeWidget::item {{ padding: 0 {p(4)}px; }}
QHeaderView::section {{ background: {ELEV}; color: {DIM}; border: 0; border-right: 1px solid {BORDER};
              border-bottom: 1px solid {BORDER}; padding: {p(3)}px {p(6)}px; font-weight: 600; }}
QTableCornerButton::section {{ background: {ELEV}; border: 0; }}

QProgressBar {{ background: {BORDER}; border: 0; border-radius: 0; max-height: {p(4)}px; min-height: {p(4)}px; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QSlider::groove:horizontal {{ height: {p(3)}px; background: {BORDER}; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; }}
QSlider::handle:horizontal {{ width: {p(9)}px; margin: -{p(4)}px 0; background: {TEXT}; border-radius: 0; }}
QScrollBar:vertical {{ background: {SURFACE}; width: {p(10)}px; margin: 0; }}
QScrollBar:horizontal {{ background: {SURFACE}; height: {p(10)}px; margin: 0; }}
QScrollBar::handle {{ background: {BORDER}; min-height: {p(20)}px; min-width: {p(20)}px; }}
QScrollBar::handle:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
QMenu {{ background: {ELEV}; border: 1px solid {BORDER}; padding: {p(3)}px 0; }}
QMenu::item {{ padding: {p(4)}px {p(18)}px; background: transparent; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: {p(3)}px 0; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; }}
QTabBar::tab {{ background: {SURFACE}; color: {DIM}; padding: {p(5)}px {p(12)}px; border: 1px solid {BORDER}; border-bottom: 0; }}
QTabBar::tab:selected {{ color: {TEXT}; border-top: 2px solid {ACCENT}; }}
QStatusBar {{ background: {BG}; color: {DIM}; }}
QDialog {{ background: {BG}; }}
QToolButton[kind="primary"], QFrame[role="bar"] QToolButton[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; }}
QToolButton[kind="primary"]:hover, QFrame[role="bar"] QToolButton[kind="primary"]:hover {{ border-color: {TEXT}; }}
"""


def apply(app: object, zoom_percent: Optional[float] = None) -> None:
    """Applique police + feuille de style à l'application Qt (à chaud)."""
    from PySide6.QtGui import QFont

    if zoom_percent is not None:
        set_zoom(zoom_percent)
    f = QFont(app.font())                       # type: ignore[attr-defined]
    f.setPointSizeF(font_pt())
    app.setFont(f)                              # type: ignore[attr-defined]
    app.setStyleSheet(stylesheet())             # type: ignore[attr-defined]
