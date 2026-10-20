"""Catalogue français (mêmes clés que en.py ; une clé absente retombe sur l'anglais)."""

STRINGS = {
    # ---- navigation
    "tab.home": "Accueil",
    "tab.search": "Recherche",
    "tab.library": "Bibliothèque",
    "tab.downloads": "Téléchargements",
    "tab.import": "Import",
    "tab.settings": "Paramètres",
    "nav.active_drive": "CLÉ ACTIVE",
    "nav.no_drive": "Aucune clé détectée",
    "nav.drive_not_connected": "Clé détectée, non connectée",

    # ---- actions génériques
    "action.download": "Télécharger",
    "action.play": "Lecture",
    "action.pause": "Pause",
    "action.next": "Suivant",
    "action.previous": "Précédent",
    "action.search": "Rechercher",
    "action.cancel": "Annuler",
    "action.ok": "OK",
    "action.close": "Fermer",
    "action.save": "Enregistrer",
    "action.delete": "Supprimer",
    "action.rename": "Renommer",
    "action.paste": "Coller",
    "action.analyse": "Analyser",
    "action.apply": "Appliquer",
    "action.retry": "Réessayer",
    "action.skip": "Ignorer",
    "action.keep_both": "Garder les deux",
    "action.replace": "Remplacer",
    "action.edit_metadata": "Modifier les métadonnées",

    # ---- vocabulaire titres / playlists
    "track.song": "Titre",
    "track.video": "Vidéo",
    "track.title": "Titre",
    "track.artist": "Artiste",
    "track.album": "Album",
    "track.duration": "Durée",
    "track.key": "Tonalité",
    "track.bpm": "BPM",
    "track.views": "Vues",
    "lib.all_tracks": "Tous les titres",
    "lib.tracks_one": "{n} titre",
    "lib.tracks_many": "{n} titres",

    # ---- modes de recherche
    "mode.all": "Tout",
    "mode.songs": "Titres",
    "mode.videos": "Vidéos",
    "mode.artists": "Artistes",

    # ---- correspondance Spotify -> YouTube Music
    "match.auto": "Automatique",
    "match.song": "Titre prioritaire",
    "match.video": "Vidéo prioritaire",

    # ---- état des téléchargements
    "job.queued": "En attente",
    "job.downloading": "Téléchargement",
    "job.converting": "Conversion…",
    "job.tagging": "Tags…",
    "job.adding": "Ajout à la clé…",
    "job.done": "✓ Terminé",
    "job.error": "✗ Erreur",

    # ---- paramètres
    "settings.title": "Paramètres",
    "settings.language": "Langue",
    "settings.theme": "Couleur du thème",
    "settings.zoom": "Zoom de l'interface",
    "settings.zoom_hint": "De 100 % à 200 %. Appliqué immédiatement.",
    "settings.restart_hint": "Certains changements ne sont complets qu'après redémarrage de DJSync.",

    # ---- thèmes
    "theme.violet_light": "Violet clair",
    "theme.lavender": "Lavande",
    "theme.neon_violet": "Violet néon",
    "theme.electric_blue": "Bleu électrique",
    "theme.sky": "Bleu ciel",
    "theme.cyan": "Cyan néon",
    "theme.turquoise": "Turquoise",
    "theme.mint": "Menthe",
    "theme.neon_green": "Vert néon",
    "theme.lime": "Lime acide",
    "theme.yellow": "Jaune néon",
    "theme.amber": "Ambre",
    "theme.orange": "Orange néon",
    "theme.coral": "Corail",
    "theme.red": "Rouge laser",
    "theme.hot_pink": "Rose vif",
    "theme.magenta": "Magenta",
    "theme.pastel_pink": "Rose pastel",
    "theme.pastel_peach": "Pêche pastel",
    "theme.pastel_blue": "Bleu pastel",

    # ---- diagnostic de la base Rekordbox
    "db.legacy_format": (
        "Cette clé contient aussi l'ancien format Rekordbox (export.pdb). DJSync le met à jour en même temps que la base OneLibrary (exportLibrary.db) s'il le reconnaît ; sinon il n'y touche pas et les platines qui le lisent ne verront pas les nouveaux titres."
    ),
    "db.no_legacy_format": "Base OneLibrary uniquement : les titres ajoutés par DJSync sont visibles des lecteurs compatibles.",
    "db.diagnose_title": "Diagnostic de la clé",
}
