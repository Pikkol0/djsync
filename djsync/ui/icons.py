"""Icônes vectorielles dessinées en code (Pillow), à la couleur demandée.

Aucune police d'icônes à installer et aucun glyphe Unicode « au petit bonheur » (certains manquent
sous Windows) : chaque icône est tracée sur une grille 24 x 24, suréchantillonnée x6 puis réduite
(bords lisses). `ctk_icon("search", 18, theme.TEXT)` -> CTkImage mise en cache.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Dict, Tuple

from PIL import Image, ImageDraw

SS = 6          # suréchantillonnage
GRID = 24       # unités de dessin


def _rgba(color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha


class _Pen:
    def __init__(self, size: int, color: str, stroke: float = 2.0) -> None:
        self.k = size * SS / GRID
        self.img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.c = _rgba(color)
        self.w = max(1, int(round(stroke * self.k)))

    def p(self, *xy: float) -> list:
        return [v * self.k for v in xy]

    def line(self, *xy: float, w: float = 0) -> None:
        width = int(round(w * self.k)) if w else self.w
        self.d.line(self.p(*xy), fill=self.c, width=width, joint="curve")
        r = width / 2
        for x, y in zip(xy[0::2], xy[1::2]):  # extrémités arrondies
            self.d.ellipse((x * self.k - r, y * self.k - r, x * self.k + r, y * self.k + r), fill=self.c)

    def circle(self, cx: float, cy: float, r: float, fill: bool = False) -> None:
        box = self.p(cx - r, cy - r, cx + r, cy + r)
        if fill:
            self.d.ellipse(box, fill=self.c)
        else:
            self.d.ellipse(box, outline=self.c, width=self.w)

    def rect(self, x0: float, y0: float, x1: float, y1: float, r: float = 2, fill: bool = False) -> None:
        box = self.p(x0, y0, x1, y1)
        if fill:
            self.d.rounded_rectangle(box, radius=r * self.k, fill=self.c)
        else:
            self.d.rounded_rectangle(box, radius=r * self.k, outline=self.c, width=self.w)

    def poly(self, *xy: float) -> None:
        self.d.polygon(self.p(*xy), fill=self.c)

    def arc(self, cx: float, cy: float, r: float, start: float, end: float) -> None:
        self.d.arc(self.p(cx - r, cy - r, cx + r, cy + r), start, end, fill=self.c, width=self.w)


def _home(p: _Pen) -> None:
    p.line(3, 11, 12, 3.5, 21, 11)
    p.line(5.5, 9.5, 5.5, 20, 18.5, 20, 18.5, 9.5)
    p.line(10, 20, 10, 14, 14, 14, 14, 20)


def _search(p: _Pen) -> None:
    p.circle(10.5, 10.5, 6.5)
    p.line(15.5, 15.5, 20.5, 20.5, w=2.4)


def _library(p: _Pen) -> None:
    p.line(4, 4, 4, 20)
    p.line(8.5, 4, 8.5, 20)
    p.line(13, 5, 18.5, 19.5)


def _downloads(p: _Pen) -> None:
    p.line(12, 3.5, 12, 14.5)
    p.line(7.5, 10, 12, 14.5, 16.5, 10)
    p.line(4, 15.5, 4, 20, 20, 20, 20, 15.5)


def _link(p: _Pen) -> None:
    p.arc(8, 16, 4.6, 90, 315)
    p.arc(16, 8, 4.6, 270, 135)
    p.line(9.5, 14.5, 14.5, 9.5)


def _settings(p: _Pen) -> None:
    import math

    p.circle(12, 12, 3.2)
    for i in range(8):
        a = i * math.pi / 4
        p.line(12 + 6 * math.cos(a), 12 + 6 * math.sin(a), 12 + 8.8 * math.cos(a), 12 + 8.8 * math.sin(a), w=2.6)
    p.circle(12, 12, 6.4)


def _help(p: _Pen) -> None:
    p.circle(12, 12, 9)
    p.arc(12, 9.6, 3.2, 180, 410)
    p.line(12, 13, 12, 14.2)
    p.circle(12, 17.4, 1.2, fill=True)


def _filter(p: _Pen) -> None:
    p.line(4, 7, 20, 7)
    p.line(7, 12, 17, 12)
    p.line(10, 17, 14, 17)


def _download(p: _Pen) -> None:
    p.line(12, 4, 12, 16)
    p.line(7, 11.5, 12, 16.5, 17, 11.5)
    p.line(6, 20, 18, 20)


def _play(p: _Pen) -> None:
    p.poly(7, 4.5, 19.5, 12, 7, 19.5)


def _pause(p: _Pen) -> None:
    p.rect(6, 4.5, 10, 19.5, 1.2, fill=True)
    p.rect(14, 4.5, 18, 19.5, 1.2, fill=True)


def _stop(p: _Pen) -> None:
    p.rect(6, 6, 18, 18, 2, fill=True)


def _next(p: _Pen) -> None:
    p.poly(5, 5, 15, 12, 5, 19)
    p.rect(16, 5, 19, 19, 1, fill=True)


def _prev(p: _Pen) -> None:
    p.poly(19, 5, 9, 12, 19, 19)
    p.rect(5, 5, 8, 19, 1, fill=True)


def _volume(p: _Pen) -> None:
    p.poly(3, 9.5, 7, 9.5, 12, 5, 12, 19, 7, 14.5, 3, 14.5)
    p.arc(13, 12, 4, -50, 50)
    p.arc(13, 12, 8, -50, 50)


def _wave(p: _Pen) -> None:
    for x, h in ((4, 3), (8, 7), (12, 10), (16, 6), (20, 3.5)):
        p.line(x, 12 - h, x, 12 + h)


def _duplicates(p: _Pen) -> None:
    p.rect(3.5, 3.5, 14.5, 14.5, 2)
    p.rect(9.5, 9.5, 20.5, 20.5, 2)


def _menu(p: _Pen) -> None:
    for y in (6.5, 12, 17.5):
        p.line(4, y, 20, y)


def _close(p: _Pen) -> None:
    p.line(6, 6, 18, 18)
    p.line(18, 6, 6, 18)


def _plus(p: _Pen) -> None:
    p.line(12, 5, 12, 19)
    p.line(5, 12, 19, 12)


def _usb(p: _Pen) -> None:
    p.rect(7, 9, 17, 21, 2)
    p.rect(9, 3, 15, 9, 1)
    p.line(10.5, 5.5, 10.5, 6.5)
    p.line(13.5, 5.5, 13.5, 6.5)


def _grid(p: _Pen) -> None:
    for x in (5, 10, 15, 20):
        p.line(x, 4, x, 20, w=1.6 if x != 5 else 2.6)


def _arrow_right(p: _Pen) -> None:
    p.line(4, 12, 19, 12)
    p.line(13, 6, 19, 12, 13, 18)


def _edit(p: _Pen) -> None:
    p.line(5, 19, 6, 14.5, 15.5, 5, 19, 8.5, 9.5, 18, 5, 19)


def _music(p: _Pen) -> None:
    p.line(9, 17, 9, 5, 19, 3.5, 19, 15)
    p.circle(6.6, 17, 2.6, fill=True)
    p.circle(16.6, 15, 2.6, fill=True)


def _up(p: _Pen) -> None:
    p.line(12, 19, 12, 5)
    p.line(6, 11, 12, 5, 18, 11)


def _down(p: _Pen) -> None:
    p.line(12, 5, 12, 19)
    p.line(6, 13, 12, 19, 18, 13)


def _trash(p: _Pen) -> None:
    p.line(4, 6.5, 20, 6.5)
    p.line(9.5, 6.5, 9.5, 4, 14.5, 4, 14.5, 6.5)
    p.line(6.5, 6.5, 7.5, 20, 16.5, 20, 17.5, 6.5)
    p.line(10.5, 10, 10.5, 16.5, w=1.6)
    p.line(13.5, 10, 13.5, 16.5, w=1.6)


def _key(p: _Pen) -> None:
    """Roue harmonique (Camelot) : cercle et 4 rayons."""
    p.circle(12, 12, 8.5)
    p.circle(12, 12, 3.2, fill=True)
    for x0, y0, x1, y1 in ((12, 3.5, 12, 7), (12, 17, 12, 20.5), (3.5, 12, 7, 12), (17, 12, 20.5, 12)):
        p.line(x0, y0, x1, y1, w=1.8)


def _check(p: _Pen) -> None:
    p.line(5, 12.5, 10, 17.5, 19, 7)


def _keyboard(p: _Pen) -> None:
    p.rect(2.5, 6, 21.5, 18, 2.5)
    for x in (6.5, 10, 13.5, 17):
        p.line(x, 10, x + 0.5, 10, w=1.8)
    p.line(7.5, 14.5, 16.5, 14.5, w=1.8)


DRAW: Dict[str, Callable[[_Pen], None]] = {
    "home": _home, "search": _search, "library": _library, "downloads": _downloads, "import": _link,
    "settings": _settings, "help": _help, "filter": _filter, "download": _download, "play": _play,
    "pause": _pause, "stop": _stop, "next": _next, "prev": _prev, "volume": _volume, "wave": _wave,
    "duplicates": _duplicates, "menu": _menu, "close": _close, "plus": _plus, "usb": _usb, "grid": _grid,
    "go": _arrow_right, "edit": _edit, "music": _music, "up": _up, "down": _down, "trash": _trash,
    "key": _key, "check": _check, "keyboard": _keyboard,
}


@lru_cache(maxsize=512)
def pil_icon(name: str, size: int, color: str, stroke: float = 2.0) -> Image.Image:
    pen = _Pen(max(8, int(size)), color, stroke)
    DRAW[name](pen)
    return pen.img.resize((max(8, int(size)), max(8, int(size))), Image.LANCZOS)


_ctk_cache: Dict[Tuple[str, int, str], Any] = {}


def reset_icons() -> None:
    """Nouvelle fenêtre racine : les images Tk de l'ancienne ne sont plus valables."""
    _ctk_cache.clear()


def ctk_icon(name: str, size: int, color: str) -> Any:
    """CTkImage (mise à l'échelle par customtkinter avec le zoom). Rendue en x2 pour rester nette
    jusqu'à 200 % de zoom."""
    import customtkinter as ctk

    key = (name, size, color)
    if key not in _ctk_cache:
        img = pil_icon(name, size * 2, color)
        _ctk_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _ctk_cache[key]
