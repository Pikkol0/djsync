"""Couleurs du thème sans dépendance (lues aussi par l'écran de démarrage, avant Qt)."""

BG = "#0B0B0D"
SURFACE = "#121216"
ELEV = "#1A1A20"
TEXT = "#ECECF1"
DIM = "#8D8D99"

# ---- accents : identifiant -> couleur (le nom affiché est la clé i18n « theme.<identifiant> »)
DEFAULT_THEME = "violet_light"
# 1.4.0 (C50) : 12 couleurs nettement différentes (il y en avait 20, dont plusieurs presque identiques)
PALETTES = {
    "violet_light": "#B79CFF",   # défaut
    "neon_violet": "#A855FF",
    "electric_blue": "#4D7CFF",
    "sky": "#7CC4FF",
    "turquoise": "#2EE6C5",
    "neon_green": "#39FF88",
    "lime": "#B6F23A",           # accent de la V0.1.0
    "yellow": "#F5FF3D",
    "amber": "#FFB020",
    "orange": "#FF8A2B",
    "red": "#FF3D5A",
    "hot_pink": "#FF3D9A",
}
# couleurs retirées -> la plus proche gardée (réglages des versions précédentes)
RETIRED = {"lavender": "violet_light", "cyan": "turquoise", "mint": "turquoise", "coral": "red",
           "magenta": "hot_pink", "pastel_pink": "hot_pink", "pastel_peach": "orange", "pastel_blue": "sky"}

