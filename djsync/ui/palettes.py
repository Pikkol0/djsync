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
    # 1.4.4 (C226) : 16 couleurs par famille (vives, profondes, pastel), teintes bien espacées
    "fuchsia": "#E040FB",
    "aqua": "#22D3EE",
    "vermilion": "#FF5A36",
    "grass": "#5BE34A",
    "petrol": "#2B9AB5",
    "indigo": "#7666E0",
    "raspberry": "#D2477F",
    "brick": "#C95A3C",
    "olive": "#A3A132",
    "moss": "#7FA83F",
    "steel": "#5E8DBA",
    "amethyst": "#9563DD",
    "lilac": "#C9B3F5",
    "pistachio": "#B8E6A0",
    "peach": "#F7B99A",
    "butter": "#F2E394",
    "powder_blue": "#A8D4F2",
    "seafoam": "#9EE3D2",
    "salmon": "#F4A09A",
    "orchid": "#E3A6E8",
    "mauve": "#D4A5C9",
    "ice": "#B5E8F0",
    "celery": "#D6EDA0",
    "spearmint": "#A8E8C0",
}
# 1.4.2 (C144) : familles présentées dans Paramètres ▸ Apparence (dans cet ordre)
FAMILIES = {
    # 1.4.4 (C226) : rangées par teinte (du rouge au rose), 16 par famille
    "vivid": ("red", "vermilion", "orange", "amber", "yellow", "lime", "grass", "neon_green", "turquoise", "aqua",
              "sky", "electric_blue", "violet_light", "neon_violet", "fuchsia", "hot_pink"),
    "deep": ("brick", "copper", "ochre", "olive", "moss", "forest", "green", "teal", "petrol", "steel", "royal_blue",
             "indigo", "amethyst", "plum", "raspberry", "bordeaux"),
    "soft": ("salmon", "peach", "sand", "butter", "celery", "pistachio", "sage", "spearmint", "seafoam", "ice",
             "powder_blue", "periwinkle", "lilac", "orchid", "mauve", "rose"),
}
# 1.4.4 (C226) : couleurs montrées directement dans Paramètres (« Toutes… » ouvre la grille des familles)
FEATURED = ("violet_light", "electric_blue", "turquoise", "neon_green", "amber", "red", "hot_pink")
# 1.4.4 (C226) : thèmes prêts à choisir (fond + couleur) ; les 6 premiers sont proposés à l'accueil
THEMES = {
    "club": ("default", "violet_light"),
    "night": ("navy", "sky"),
    "forest": ("fir", "sage"),
    "coffee": ("brown", "amber"),
    "prune": ("prune", "rose"),
    "neon": ("oled", "neon_green"),
    "daylight": ("bright", "royal_blue"),
    "contrast": ("high_contrast", "yellow"),
}
MIN_CONTRAST = 3.0            # accent lisible sur le fond des cartes (vérifié par les tests, C144)
# couleurs retirées -> la plus proche gardée (réglages des versions précédentes)
RETIRED = {"lavender": "violet_light", "cyan": "turquoise", "mint": "turquoise", "coral": "red",
           "magenta": "hot_pink", "pastel_pink": "hot_pink", "pastel_peach": "orange", "pastel_blue": "sky"}

