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
    # 1.4.2 (C144) : profondes (ni néon ni pastel), dont un vrai vert franc
    "green": "#2FBF5B",
    "forest": "#4E9F63",
    "teal": "#2A9D8F",
    "royal_blue": "#4F74E3",
    "plum": "#A066C8",
    "bordeaux": "#C8465E",
    "copper": "#CD7A3C",
    "ochre": "#D19A2A",
    # 1.4.2 (C144) : douces
    "sage": "#9CC5A1",
    "periwinkle": "#A6B4F0",
    "rose": "#E8A0B4",
    "sand": "#E0C79A",
}
# 1.4.2 (C144) : familles présentées dans Paramètres ▸ Apparence (dans cet ordre)
FAMILIES = {
    "vivid": ("violet_light", "neon_violet", "electric_blue", "sky", "turquoise", "neon_green", "lime", "yellow",
              "amber", "orange", "red", "hot_pink"),
    "deep": ("green", "forest", "teal", "royal_blue", "plum", "bordeaux", "copper", "ochre"),
    "soft": ("sage", "periwinkle", "rose", "sand"),
}
MIN_CONTRAST = 3.0            # accent lisible sur le fond des cartes (vérifié par les tests, C144)
# couleurs retirées -> la plus proche gardée (réglages des versions précédentes)
RETIRED = {"lavender": "violet_light", "cyan": "turquoise", "mint": "turquoise", "coral": "red",
           "magenta": "hot_pink", "pastel_pink": "hot_pink", "pastel_peach": "orange", "pastel_blue": "sky"}

