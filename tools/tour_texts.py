"""OUTIL DE DÉVELOPPEMENT : textes de la visite vidéo (tools/tour_video.py).

FR : traduction des textes affichés (clé = texte anglais du scénario).
SPOKEN_EN / SPOKEN_FR : ce que dit la voix off quand il faut autre chose que le texte affiché
(symboles, sigles, phrases plus naturelles à l'oral). Sans entrée, la voix lit le texte affiché.
À relire avant de générer la voix : ces textes sont le script de la vidéo.
"""
from __future__ import annotations

from typing import Dict

FR: Dict[str, str] = {
    # cartons
    "Your music, your Rekordbox USB, any computer.": "Votre musique, votre clé Rekordbox, sur n'importe quel ordinateur.",
    "On your USB.": "Sur votre clé.",
    "Any computer. Any gig.": "Tous les ordinateurs. Toutes les soirées.",
    "Free, open source: djsync on GitHub": "Gratuit et open source : djsync sur GitHub",
    # 1
    "On your USB, any computer": "Sur votre clé, partout",
    "Windows, Mac or Linux. Nothing to install.": "Windows, Mac ou Linux. Rien à installer.",
    "Download the version for your computer": "Téléchargez la version de votre ordinateur",
    "then copy it to your USB drive": "puis copiez-la sur votre clé USB",
    "DJSync folder": "dossier DJSync",
    "Plug the drive in, open DJSync": "Branchez la clé, ouvrez DJSync",
    "same drive, any computer": "la même clé, sur n'importe quel ordinateur",
    "Your USB drive: tracks, playlists, free space": "Votre clé : sons, playlists, espace libre",
    "Tracks not analysed yet, older players supported (export.pdb)":
        "Sons pas encore analysés, anciennes platines prises en charge (export.pdb)",
    "This PC's Rekordbox collection, one click away": "La collection Rekordbox de ce PC, à un clic",
    "Search, or paste a link, from Home": "Cherchez, ou collez un lien, depuis l'Accueil",
    # 2
    "Search": "Recherche",
    "Find any track on YouTube Music.": "Trouvez n'importe quel son sur YouTube Music.",
    "Open Search": "Ouvrir la Recherche",
    "Songs (official audio) or videos": "Titres (audio officiel) ou vidéos",
    "Already in your library? You know before downloading": "Déjà dans votre bibliothèque ? Vous le savez avant de télécharger",
    "Filters: songs only, words to exclude (remix, live…)": "Filtres : titres seulement, mots à exclure (remix, live…)",
    "Preview before downloading": "Écoutez avant de télécharger",
    # 3
    "Download into playlists": "Télécharger dans vos playlists",
    "Create a playlist on the fly, or pick existing ones.": "Créez une playlist à la volée, ou choisissez-en.",
    "Select two tracks, then Download": "Sélectionnez deux sons, puis Télécharger",
    "New playlist: type a name, then Create": "Nouvelle playlist : tapez un nom, puis Créer",
    "A track can go into several playlists": "Un son peut aller dans plusieurs playlists",
    "Download": "Télécharger",
    "Downloads: progress, playlists, then tagged and filed on the drive":
        "Téléchargements : progression, playlists, puis tagué et rangé sur la clé",
    "Your new playlist, in the library": "Votre nouvelle playlist, dans la bibliothèque",
    "Add any track to a playlist: Add to…": "Ajoutez n'importe quel son à une playlist : Ajouter à…",
    # 4
    "Import a playlist": "Importer une playlist",
    "Paste a Spotify link: the right tracks are found for you.": "Collez un lien Spotify : les bons sons sont trouvés pour vous.",
    "Import URL": "Importer un lien",
    "Read the link": "Lire le lien",
    "Each track is matched on YouTube Music, with a score": "Chaque son est retrouvé sur YouTube Music, avec un score",
    "Found: the official audio, same duration": "Trouvé : l'audio officiel, même durée",
    "Not sure? Marked to check: listen, or pick another match":
        "Un doute ? Marqué à vérifier : écoutez, ou choisissez un autre résultat",
    "Download the selection into your playlists": "Téléchargez la sélection dans vos playlists",
    # 5
    "Analyse like Rekordbox": "Analyser comme Rekordbox",
    "BPM, key, beat grid, waveforms. Read by the decks.": "BPM, tonalité, grille, formes d'onde. Lus par les platines.",
    "Tracks not analysed yet": "Sons pas encore analysés",
    "Analyse all: in the background, the library stays usable": "Tout analyser : en arrière-plan, la bibliothèque reste utilisable",
    "Double-click to play: the waveform scrolls in the player": "Double-clic pour écouter : la forme d'onde défile dans le lecteur",
    "Tools menu ▸ Edit beat grid": "Menu Outils ▸ Modifier la grille",
    "Rekordbox-style 3-band waveform, beats and bars": "Forme d'onde 3 bandes façon Rekordbox, temps et mesures",
    "Shift the whole grid, to the millisecond": "Décalez toute la grille, à la milliseconde",
    "Bar starts here: the first beat of the bar": "La mesure commence ici : le premier temps de la mesure",
    "BPM × 2 / ÷ 2, or type the exact BPM": "BPM × 2 / ÷ 2, ou tapez le BPM exact",
    "Save: written to the analysis files read by the decks": "Enregistrer : écrit dans les fichiers d'analyse lus par les platines",
    # 6
    "Organise your library": "Organiser votre bibliothèque",
    "Playlists, order, titles, Camelot keys, clean-up.": "Playlists, ordre, titres, tonalités Camelot, nettoyage.",
    "Keys in Camelot notation, with their colour": "Tonalités en notation Camelot, avec leur couleur",
    "Pick a track, then Harmonic: only compatible tracks remain": "Choisissez un son, puis Harmonique : seuls les sons compatibles restent",
    "Change the order of a playlist, then Save order": "Changez l'ordre d'une playlist, puis Enregistrer l'ordre",
    "Right-click ▸ Edit info: title, artists, album, genre, artwork":
        "Clic droit ▸ Modifier les infos : titre, artistes, album, genre, pochette",
    "Right-click a playlist ▸ Copy to this computer's Rekordbox": "Clic droit sur une playlist ▸ Copier dans le Rekordbox de ce PC",
    "Analyses are reused, not recomputed": "Les analyses sont reprises, pas recalculées",
    "Diagnostic: duplicates, music videos, low bitrate": "Diagnostic : doublons, clips vidéo, faible débit",
    "Sorted by problem: duplicates, bad source, low quality": "Trié par problème : doublons, mauvaise source, faible qualité",
    "Keep one version… or re-download a clean one": "Gardez une version… ou retéléchargez-en une propre",
    "It replaces the old ones in every playlist, at the same position":
        "Elle remplace les anciennes dans chaque playlist, à la même place",
    "A music video in your library? Same thing": "Un clip vidéo dans votre bibliothèque ? Pareil",
    # 7
    "100% Rekordbox": "100 % Rekordbox",
    "Everything stays readable by Rekordbox and the decks.": "Tout reste lisible par Rekordbox et les platines.",
    "Written the Rekordbox way": "Écrit à la manière de Rekordbox",
    "on your USB and on your PC": "sur votre clé et sur votre PC",
    "Rekordbox library": "Bibliothèque Rekordbox",
    "exportLibrary.db (OneLibrary)": "exportLibrary.db (OneLibrary)",
    "Older players": "Anciennes platines",
    "export.pdb kept in sync": "export.pdb tenu à jour",
    "Analysis files": "Fichiers d'analyse",
    "beat grids, waveforms, cues (ANLZ)": "grilles, formes d'onde, cues (ANLZ)",
    "Your computer": "Votre ordinateur",
    "Rekordbox collection (master.db)": "collection Rekordbox (master.db)",
    "Safe by design": "Sûr par conception",
    "your library is never at risk": "votre bibliothèque n'est jamais en danger",
    "Backup first": "Sauvegarde d'abord",
    "the database is saved before every change": "la base est sauvegardée avant chaque modification",
    "Rekordbox open?": "Rekordbox ouvert ?",
    "DJSync warns you and waits": "DJSync vous prévient et attend",
    "Safe eject": "Éjection sûre",
    "library closed cleanly before unplugging": "bibliothèque bien fermée avant de débrancher",
    "Works offline": "Fonctionne hors ligne",
    "only search and downloads need internet": "seules la recherche et les téléchargements demandent internet",
    # 8
    "Settings & eject": "Réglages et éjection",
    "Your format, always up to date, unplug safely.": "Votre format, toujours à jour, débranchez en sécurité.",
    "Settings": "Paramètres",
    "M4A (original quality) or MP3 320, same volume for every track":
        "M4A (qualité d'origine) ou MP3 320, même volume pour tous les sons",
    "YouTube changed? Update the download engine in one click": "YouTube a changé ? Mettez à jour le moteur de téléchargement en un clic",
    "Eject: the library is closed, you can unplug the drive": "Éjecter : la bibliothèque est fermée, vous pouvez débrancher la clé",
    # chapitres
    "Intro": "Intro",
}

# Clé = texte anglais (celui du scénario). Le texte des panneaux est « titre. sous-titre ».
SPOKEN_EN: Dict[str, str] = {
    "DJSync Your music, your Rekordbox USB, any computer.":
        "This is DJSync: your music, on your Rekordbox USB drive, on any computer.",
    "Tracks not analysed yet, older players supported (export.pdb)":
        "Tracks not analysed yet, and older players are supported too.",
    "Tools menu ▸ Edit beat grid": "In the Tools menu, open Edit beat grid.",
    "BPM × 2 / ÷ 2, or type the exact BPM": "Double or halve the BPM, or type the exact value.",
    "Right-click ▸ Edit info: title, artists, album, genre, artwork":
        "Right-click, Edit info: title, artists, album, genre and artwork.",
    "Right-click a playlist ▸ Copy to this computer's Rekordbox":
        "Right-click a playlist to copy it to this computer's Rekordbox.",
    "M4A (original quality) or MP3 320, same volume for every track":
        "M4A in original quality, or MP3 at 320, with the same volume for every track.",
    "Written the Rekordbox way. on your USB and on your PC. Rekordbox library. Older players. Analysis files. Your computer":
        "Everything is written the Rekordbox way, on your USB and on your PC: the library, the older players' "
        "database, the analysis files, and your computer's collection.",
    "Safe by design. your library is never at risk. Backup first. Rekordbox open?. Safe eject. Works offline":
        "Safe by design: a backup before every change, a warning if Rekordbox is open, a clean eject, "
        "and it works offline.",
    "On your USB. Any computer. Any gig.": "On your USB. Any computer. Any gig. DJSync is free: get it on GitHub.",
}

SPOKEN_FR: Dict[str, str] = {
    "DJSync Your music, your Rekordbox USB, any computer.":
        "Voici DJSync : votre musique, sur votre clé Rekordbox, sur n'importe quel ordinateur.",
    "Tracks not analysed yet, older players supported (export.pdb)":
        "Les sons pas encore analysés, et les anciennes platines sont prises en charge.",
    "Tools menu ▸ Edit beat grid": "Dans le menu Outils, ouvrez Modifier la grille.",
    "BPM × 2 / ÷ 2, or type the exact BPM": "Doublez ou divisez le BPM par deux, ou tapez la valeur exacte.",
    "Right-click ▸ Edit info: title, artists, album, genre, artwork":
        "Clic droit, Modifier les infos : titre, artistes, album, genre et pochette.",
    "Right-click a playlist ▸ Copy to this computer's Rekordbox":
        "Clic droit sur une playlist pour la copier dans le Rekordbox de ce PC.",
    "M4A (original quality) or MP3 320, same volume for every track":
        "M4A en qualité d'origine, ou MP3 320, avec le même volume pour tous les sons.",
    "Written the Rekordbox way. on your USB and on your PC. Rekordbox library. Older players. Analysis files. Your computer":
        "Tout est écrit à la manière de Rekordbox, sur votre clé et sur votre PC : la bibliothèque, la base des "
        "anciennes platines, les fichiers d'analyse et la collection de votre ordinateur.",
    "Safe by design. your library is never at risk. Backup first. Rekordbox open?. Safe eject. Works offline":
        "Sûr par conception : une sauvegarde avant chaque modification, un avertissement si Rekordbox est ouvert, "
        "une éjection propre, et ça marche hors ligne.",
    "On your USB. Any computer. Any gig.":
        "Sur votre clé. Tous les ordinateurs. Toutes les soirées. DJSync est gratuit : retrouvez-le sur GitHub.",
    "Read the link": "Lire le lien.",
}

# Mots que les voix lisent mal : remplacés à l'oral seulement.
SAY_FIX = {
    "en": {"▸": ",", "×": "times", "÷": "divided by", "…": ".", "DJSync": "D J Sync", "M4A": "M 4 A",
           "MP3": "M P 3", "BPM": "B P M", "USB": "U S B", "PC": "P C"},
    "fr": {"▸": ",", "×": "fois", "÷": "divisé par", "…": ".", "DJSync": "D J Sync", "M4A": "M 4 A",
           "MP3": "M P 3", "BPM": "B P M", "USB": "U S B", "PC": "P C", "100 %": "100 pour cent"},
}
