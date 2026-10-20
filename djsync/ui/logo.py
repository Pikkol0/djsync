"""Logo DJSync : des ondes audio (barres symétriques) dans un carré arrondi, À LA COULEUR D'ACCENT.

`logo_image(size, accent)` : image Pillow (icône de fenêtre / de l'exécutable, PNG exportés pour
chaque couleur par `tools/export_logos.py`) ; `logo_pixmap` : la même en QPixmap pour l'interface.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Tuple

if TYPE_CHECKING:  # Pillow n'est importé qu'à l'usage (démarrage plus rapide)
    from PIL import Image


# barres : (position x relative 0-1, demi-hauteur relative 0-1) -> « pulsation » symétrique
BARS: List[Tuple[float, float]] = [(0.20, 0.16), (0.32, 0.34), (0.44, 0.24), (0.56, 0.44),
                                   (0.68, 0.24), (0.80, 0.34)]
BAR_W = 0.075
TILE_RADIUS = 0.26


def _mix(a: str, b: str, ratio: float) -> str:
    ca = [int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * ratio):02X}" for x, y in zip(ca, cb))


def geometry(size: float) -> Tuple[Tuple[float, float, float, float], List[Tuple[float, float, float, float]]]:
    """(carré, [barres (x0, y0, x1, y1)]) pour un logo de `size` px. Barres décalées de 0,6 % vers
    la gauche : l'ensemble paraît centré (la dernière barre est plus basse)."""
    tile = (0.0, 0.0, size, size)
    bars = []
    for x, h in BARS:
        cx = (x - 0.006) * size
        bars.append((cx - BAR_W * size / 2, (0.5 - h) * size, cx + BAR_W * size / 2, (0.5 + h) * size))
    return tile, bars


def logo_image(size: int, accent: str, background: str = "#1A1A20", transparent: bool = False) -> "Image.Image":
    """Logo en image (suréchantillonné x4). Pillow importé ici : l'écran de démarrage n'en a pas besoin."""
    from PIL import Image, ImageDraw

    k = 4
    big = size * k
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tile, bars = geometry(big)
    if not transparent:
        d.rounded_rectangle(tile, radius=TILE_RADIUS * big, fill=background)
    glow = _mix(accent, background, 0.55)
    for i, (x0, y0, x1, y1) in enumerate(bars):
        color = accent if i % 2 == 1 else _mix(accent, "#FFFFFF", 0.18)
        r = (x1 - x0) / 2
        d.rounded_rectangle((x0 - r * 0.6, y0 - r * 0.6, x1 + r * 0.6, y1 + r * 0.6), radius=r * 1.6, fill=glow)
        d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=color)
    return img.resize((size, size), Image.LANCZOS)


def logo_pixmap(size: int, accent: str, background: str = "#1A1A20") -> Any:
    """Logo en QPixmap (barre latérale, icône de fenêtre, écran de démarrage), net en x2."""
    from .icons import to_qpixmap

    pm = to_qpixmap(logo_image(size * 2, accent, background))
    pm.setDevicePixelRatio(2.0)
    return pm
