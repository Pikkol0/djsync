"""OUTIL DE DÉVELOPPEMENT : exporte le logo DJSync dans chaque couleur des Paramètres.

    python tools/export_logos.py            -> docs/logos/djsync-<couleur>.png (512 px) + aperçu
                                               + packaging/djsync.ico (icône de l'exe, couleur par défaut)
                                               + packaging/splash.png (écran de démarrage de l'exe)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def make_splash(path: Path, accent: str) -> None:
    """Image de l'écran de démarrage natif de l'exécutable (PyInstaller), même dessin que
    djsync/ui/splash.py : logo, nom, « Loading… »."""
    from PIL import Image, ImageDraw, ImageFont

    from djsync.ui.logo import logo_image
    from djsync.ui.palettes import DIM, ELEV, SURFACE, TEXT

    w, h = 340, 210
    img = Image.new("RGB", (w, h), ELEV)
    d = ImageDraw.Draw(img)
    d.rectangle((1, 1, w - 2, h - 2), fill=SURFACE)
    logo = logo_image(64, accent, ELEV)
    img.paste(logo, ((w - 64) // 2, 34), logo)

    def font(size: int, bold: bool) -> ImageFont.ImageFont:
        names = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    for text, y, size, bold, color in (("DJSync", 112, 24, True, TEXT), ("Loading…", 152, 12, False, DIM)):
        f = font(size, bold)
        box = d.textbbox((0, 0), text, font=f)
        d.text(((w - (box[2] - box[0])) / 2 - box[0], y), text, font=f, fill=color)
    img.save(path)


def main() -> int:
    from PIL import Image

    from djsync.ui.logo import logo_image
    from djsync.ui.theme import DEFAULT_THEME, PALETTES

    out = ROOT / "docs" / "logos"
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, accent in PALETTES.items():
        img = logo_image(512, accent)
        img.save(out / f"djsync-{name}.png")
        tiles.append(logo_image(96, accent))
    cols = 10
    sheet = Image.new("RGBA", (cols * 104 + 8, ((len(tiles) + cols - 1) // cols) * 104 + 8), (11, 11, 13, 255))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (8 + (i % cols) * 104, 8 + (i // cols) * 104), tile)
    sheet.save(out / "apercu-toutes-couleurs.png")
    logo_image(256, PALETTES[DEFAULT_THEME]).save(
        ROOT / "packaging" / "djsync.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    make_splash(ROOT / "packaging" / "splash.png", PALETTES[DEFAULT_THEME])
    print(f"{len(tiles)} logos -> {out}; icon -> packaging/djsync.ico; splash -> packaging/splash.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
