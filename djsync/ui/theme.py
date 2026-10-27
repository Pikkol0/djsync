"""Thème Qt (V0.3.1) : fond sombre neutre, UNE couleur d'accent, icônes, coins arrondis.

Style Qt « Fusion », coins arrondis (6 px boutons et champs, 8 px listes, 10 px cartes), bordures de 1 px, pas
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
# 1.3.1 (C29) : échelle de qualité commune, indépendante de la couleur d'accent, toujours doublée d'un mot
GOOD = "#4CC38A"          # bon
FAIR = "#D2BE4E"          # moyen
GOLD, SILVER = "#E2B84A", "#C9D1DB"     # 1.4.0 (C10) : sans perte (doré), 320 kbps (argenté)
LEVELS = {"good": GOOD, "fair": FAIR, "warn": WARN, "bad": ERR, "neutral": DIM, "gold": GOLD, "silver": SILVER}

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
    r6, r8, r10 = p(6), p(8), p(10)      # coins arrondis : boutons et champs / listes / cartes
    hover = mix(ELEV, TEXT, 0.07)
    row_hover = mix(SURFACE, TEXT, 0.045)
    accent_hover = mix(ACCENT, "#FFFFFF", 0.15)
    return f"""
* {{ outline: 0; }}
QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {ELEV}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: {r6}px; padding: {p(4)}px {p(6)}px; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: {font_pt(7):.1f}pt; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: {font_pt(2):.1f}pt; font-weight: 600; }}
QLabel[role="dim"] {{ color: {DIM}; }}
QLabel[role="faint"] {{ color: {FAINT}; }}
QLabel[role="section"] {{ color: {FAINT}; font-size: {font_pt(-1.5):.1f}pt; font-weight: 700; }}
QLabel[role="warn"] {{ color: {WARN}; }}
QLabel[role="err"] {{ color: {ERR}; }}
QLabel[role="accent"] {{ color: {ACCENT}; }}
QLabel[role="chip"], QFrame[role="panel"] QLabel[role="chip"] {{ background: {ELEV}; color: {DIM}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_warn"], QFrame[role="panel"] QLabel[role="chip_warn"] {{ background: {mix(SURFACE, WARN, 0.18)}; color: {WARN}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_ok"], QFrame[role="panel"] QLabel[role="chip_ok"] {{ background: {ACCENT_DIM}; color: {ACCENT}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_good"], QFrame[role="panel"] QLabel[role="chip_good"] {{ background: {mix(SURFACE, GOOD, 0.16)}; color: {GOOD}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_gold"], QFrame[role="panel"] QLabel[role="chip_gold"] {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8C6A1C, stop:0.45 #F3D27A, stop:0.55 #FFF1BF, stop:1 #B8862B); color: #2B1E05; font-weight: 700; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_silver"], QFrame[role="panel"] QLabel[role="chip_silver"] {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7D8792, stop:0.45 #DDE3EA, stop:0.55 #FFFFFF, stop:1 #98A2AD); color: #1C2128; font-weight: 700; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_fair"], QFrame[role="panel"] QLabel[role="chip_fair"] {{ background: {mix(SURFACE, FAIR, 0.16)}; color: {FAIR}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="chip_bad"], QFrame[role="panel"] QLabel[role="chip_bad"] {{ background: {mix(SURFACE, ERR, 0.16)}; color: {ERR}; border-radius: {p(9)}px; padding: {p(2)}px {p(9)}px; }}
QLabel[role="good"] {{ color: {GOOD}; }}
QLabel[role="fair"] {{ color: {FAIR}; }}
QFrame[role="panel"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {r10}px; }}
QFrame[role="panel"] QLabel, QFrame[role="panel"] QCheckBox, QFrame[role="panel"] QRadioButton {{ background: transparent; }}
QFrame[role="sidebar"] {{ background: {SURFACE}; border: 0; border-right: 1px solid {BORDER}; }}
QFrame[role="sidebar"] QWidget {{ background: {SURFACE}; }}
QFrame[role="sidebar"] QFrame[role="panel"] {{ background: {ELEV}; border: 0; }}
QFrame[role="sidebar"] QFrame[role="panel"] QWidget {{ background: transparent; }}
QFrame[role="bar"] {{ background: {SURFACE}; border: 0; border-top: 1px solid {BORDER}; }}
QFrame[role="bar"] QWidget {{ background: {SURFACE}; }}
QFrame[role="banner"] {{ background: {ACCENT_DIM}; border: 1px solid {ACCENT}; border-radius: {r8}px; }}
QFrame[role="banner"] QWidget {{ background: transparent; }}
QFrame[role="toast"] {{ background: {ELEV}; border: 1px solid {mix(BORDER, TEXT, 0.12)}; border-radius: {r10}px; }}
QFrame[role="toast"] QLabel {{ background: transparent; }}
QFrame[role="tile"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {r10}px; }}

QPushButton {{ background: {ELEV}; border: 1px solid {BORDER}; border-radius: {r6}px;
              padding: {p(5)}px {p(12)}px; min-height: {p(18)}px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; background: {mix(BG, ELEV, 0.6)}; border-color: {ELEV}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton[kind="primary"]:disabled {{ background: {ELEV}; color: {FAINT}; border-color: {ELEV}; }}
QPushButton[kind="danger"] {{ color: {ERR}; }}
QPushButton[kind="danger"]:hover {{ background: {mix(ELEV, ERR, 0.18)}; }}
QPushButton[kind="flat"] {{ background: transparent; border: 0; color: {DIM}; }}
QPushButton[kind="flat"]:hover {{ color: {TEXT}; background: {ELEV}; }}
QPushButton[kind="nav"] {{ background: transparent; border: 0; border-radius: {r8}px;
              text-align: left; padding: {p(8)}px {p(10)}px; color: {DIM}; }}
QPushButton[kind="nav"]:hover {{ color: {TEXT}; background: {ELEV}; }}
QPushButton[kind="nav"]:checked {{ color: {TEXT}; background: {ACCENT_DIM}; font-weight: 600; }}
QPushButton[kind="tab"] {{ background: transparent; border: 0; border-bottom: 2px solid transparent; border-radius: 0;
              padding: {p(6)}px {p(12)}px; color: {DIM}; }}
QPushButton[kind="tab"]:hover {{ color: {TEXT}; }}
QPushButton[kind="tab"]:checked {{ color: {TEXT}; border-bottom-color: {ACCENT}; font-weight: 600; }}
QPushButton[kind="tile"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {r10}px;
              padding: {p(12)}px {p(14)}px; text-align: left; font-weight: 600; }}
QPushButton[kind="tile"]:hover {{ border-color: {ACCENT}; background: {mix(SURFACE, ACCENT, 0.06)}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r6}px; padding: {p(4)}px; }}
QToolButton:hover {{ background: {ELEV}; }}
QToolButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton::menu-indicator {{ image: none; }}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER};
              border-radius: {r6}px; padding: {p(5)}px {p(8)}px; selection-background-color: {ACCENT_DIM}; }}
QLineEdit:hover, QComboBox:hover {{ border-color: {mix(BORDER, TEXT, 0.15)}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit[role="big"] {{ padding: {p(9)}px {p(10)}px; font-size: {font_pt(1.5):.1f}pt; border-radius: {r8}px; }}
QComboBox::drop-down {{ border: 0; width: {p(20)}px; }}
QComboBox QAbstractItemView {{ background: {ELEV}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM}; padding: {p(4)}px; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: {p(8)}px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: {p(15)}px; height: {p(15)}px; border: 1px solid {FAINT};
              background: {SURFACE}; border-radius: {p(4)}px; }}
QRadioButton::indicator {{ border-radius: {p(8)}px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTableView, QTreeWidget, QListWidget {{ background: {SURFACE}; alternate-background-color: {mix(SURFACE, BG, 0.35)};
              border: 1px solid {BORDER}; border-radius: {r8}px; gridline-color: transparent;
              selection-background-color: {ACCENT_DIM}; selection-color: {TEXT}; }}
QTableView::item {{ padding: 0 {p(6)}px; border: 0; }}
QTableView::item:hover, QTreeWidget::item:hover, QListWidget::item:hover {{ background: {row_hover}; }}
QTableView::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QTreeWidget::item, QListWidget::item {{ padding: {p(4)}px {p(4)}px; border-radius: {r6}px; }}
QTreeWidget, QListWidget {{ padding: {p(4)}px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE}; color: {FAINT}; border: 0; border-bottom: 1px solid {BORDER};
              padding: {p(6)}px {p(8)}px; font-weight: 600; font-size: {font_pt(-1):.1f}pt; }}
QHeaderView::section:hover {{ color: {TEXT}; }}
QTableCornerButton::section {{ background: {SURFACE}; border: 0; }}

QProgressBar {{ background: {BORDER}; border: 0; border-radius: {p(3)}px; max-height: {p(6)}px; min-height: {p(6)}px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: {p(3)}px; }}
QSlider::groove:horizontal {{ height: {p(4)}px; background: {BORDER}; border-radius: {p(2)}px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: {p(2)}px; }}
QSlider::handle:horizontal {{ width: {p(12)}px; margin: -{p(4)}px 0; background: {TEXT}; border-radius: {p(6)}px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar:vertical {{ background: transparent; width: {p(10)}px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: {p(10)}px; margin: 0; }}
QScrollBar::handle {{ background: {BORDER}; min-height: {p(24)}px; min-width: {p(24)}px; border-radius: {p(3)}px; margin: {p(2)}px; }}
QScrollBar::handle:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
QScrollArea {{ border: 0; background: transparent; }}
QMenu {{ background: {ELEV}; border: 1px solid {BORDER}; border-radius: {r8}px; padding: {p(4)}px; }}
QMenu::item {{ padding: {p(6)}px {p(18)}px {p(6)}px {p(10)}px; background: transparent; border-radius: {r6}px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::icon {{ padding-left: {p(8)}px; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: {p(4)}px {p(6)}px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: {r8}px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {DIM}; padding: {p(6)}px {p(14)}px; border: 0;
              border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QSplitter::handle {{ background: transparent; }}
QDialog {{ background: {BG}; }}
QToolButton[kind="primary"], QFrame[role="bar"] QToolButton[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT};
              border-radius: {p(16)}px; }}
QToolButton[kind="primary"]:hover, QFrame[role="bar"] QToolButton[kind="primary"]:hover {{ background: {accent_hover}; }}
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
