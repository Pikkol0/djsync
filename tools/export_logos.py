"""OUTIL DE DÉVELOPPEMENT : exporte le logo DJSync dans chaque couleur des Paramètres.

    python tools/export_logos.py            -> docs/logos/djsync-<couleur>.png (512 px) + aperçu
                                               + packaging/djsync.ico (icône de l'exe, couleur par défaut)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
    print(f"{len(tiles)} logos -> {out} ; icône -> packaging/djsync.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
