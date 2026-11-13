# Scénarios de test — DJSync 1.4.2

Lot 1 de la 1.4.2, « prête pour la vidéo » : tout ce qui change l'interface. Numérotation : thème en 3 lettres + n°
(voir `revues/numerotation-tests.md`) ; dans le suivi : « 142 · NAV-1 ». Rangés par bloc, pour tester en plusieurs fois.
Le lot 2 (C23 transferts clé ↔ ordinateur, C24 clé vierge) aura ses scénarios quand il sera codé.

## Volet, Rechercher, menus (C182, reste d'A06)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| NAV-1 | Tous | Windows, macOS, Linux | (**C182**) Regarder le volet, déplié puis replié. | 6 entrées : Accueil, Rechercher, Bibliothèque, Téléchargements, Diagnostic, Paramètres. En bas, sur une ligne : Retours, Aide, Réduire (l'un sous l'autre en volet replié). Aucun texte coupé. |
| NAV-2 | Tous | Windows, macOS, Linux | (**C182**) Rechercher : passer d'un onglet à l'autre (Recherche, Haute qualité, Lien ou playlist), avec un texte déjà tapé dans Recherche. | Les trois pages ont la même barre d'onglets ; l'entrée « Rechercher » du volet reste cochée. Le texte tapé suit dans Haute qualité et la recherche part. Plus de menu « Classique / Haute qualité ». |
| NAV-3 | Tous | Windows, macOS, Linux | (**C182**) Raccourcis Ctrl (Cmd sur Mac) + 1 à 9. | 1 Accueil, 2 Rechercher, 3 Bibliothèque, 4 Téléchargements, 5 Diagnostic, 6 Paramètres, 7 Haute qualité, 8 Lien ou playlist, 9 Retours. Même liste dans Aide ▸ Raccourcis. |
| NAV-4 | Tous | Windows, macOS, Linux | (**C182**) Clic droit sur un son : dans la Bibliothèque, dans Téléchargements (liste du bas, et un téléchargement fini), dans Diagnostic ▸ Qualité ; puis ☰ du lecteur. | Partout le même bloc, dans le même ordre : Diagnostic de ce son, Grille et cues, Modifier les infos ; Analyser (ou Analyser à nouveau), Qualité, Compléter les infos ; Sons compatibles, Afficher dans la bibliothèque (pas dans la Bibliothèque), Afficher dans l'Explorateur / le Finder, Acheter. |
| NAV-5 | Tous | Windows, macOS, Linux | (**C182**) « Diagnostic de ce son » depuis le lecteur. | Le Diagnostic s'ouvre sur l'onglet « Un son », ce son déjà choisi ; l'entrée Diagnostic du volet est cochée. |
| NAV-6 | Tous | Windows, macOS, Linux | (**C182**) Bibliothèque ▸ ☰. | Seulement les outils de liste : Uniformiser la portée affichée, Playlists par genre, Compléter les infos (+ les boutons repliés faute de place). |
| NAV-7 | Tous | Windows, macOS, Linux | (**C182**) Cliquer la carte « Bibliothèque active » du volet (puis l'anneau, volet replié). | Petit menu : Espace occupé, Sauvegardes…, Prêt pour le set ?, Éjecter (clé USB). « Espace occupé » ouvre Paramètres ▸ Bibliothèques sur la carte Espace ; Sauvegardes s'ouvre en 1 clic. |
| NAV-8 | Tous | Windows, macOS, Linux | (**C182**) Ouvrir Grille et cues depuis la Bibliothèque, puis Uniformiser depuis la Bibliothèque. | L'entrée Bibliothèque reste cochée dans le volet. |
| NAV-9 | Testeur Windows | Windows | (**C182**) Écran de 768 px (ou fenêtre basse), zoom 125 %, volet replié, deux tâches en cours. | Les icônes du volet replié rapetissent quand la hauteur manque ; rien n'est écrasé. Volet déplié : cartes entières à 100 % sur un écran de 768 px. |

## Accueil et visite guidée (C178, C182)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ACC-1 | Tous | Windows, macOS, Linux | (**C178**, maquette A) Ouvrir l'Accueil avec une clé branchée. | En haut les cartes des bibliothèques ; dessous « Que voulez-vous faire ? » avec 4 grandes actions : Télécharger, Analyser, Préparer une clé, Uniformiser ; dessous « À régler » (C182). |
| ACC-2 | Tous | Windows, macOS, Linux | (**C178**) Cliquer chacune des 4 actions. | Télécharger ouvre Rechercher ; Analyser ouvre Bibliothèque ▸ Non analysés et lance l'analyse ; Préparer une clé ouvre « Prêt pour le set ? » (sans clé : message et Paramètres ▸ Bibliothèques) ; Uniformiser demande la portée. |
| ACC-3 | Tous | Windows, macOS, Linux | (**C182**) « À régler » de l'Accueil. | Une tuile par onglet du Diagnostic (Fichiers introuvables, Doublons, Qualité, Uniformiser) avec son nombre (« — » tant qu'il n'est pas compté) ; un clic ouvre l'onglet. Sans bibliothèque : une phrase à la place. |
| ACC-4 | Tous | Windows, macOS, Linux | (**C178**) Premier lancement de la 1.4.2 (ou réglage `tour_state` vidé). | Après l'accueil éventuel, une fenêtre propose la visite : Commencer la visite, Plus tard, Ne plus montrer. « Plus tard » : proposée au lancement suivant. « Ne plus montrer » : plus jamais au lancement. |
| ACC-5 | Tous | Windows, macOS, Linux | (**C178**) Faire la visite (Suivant, Précédent, Échap), puis la relancer depuis Aide ▸ Premiers pas ▸ « Visite guidée ». | Un projecteur éclaire tour à tour chaque entrée du volet, la carte de la bibliothèque, le lecteur, l'Aide ; une bulle explique chaque partie. Rien n'est cliquable sous le voile. Échap ou Passer arrête la visite. La fenêtre peut être redimensionnée pendant la visite. |

## « Prêt pour le set ? » (C67)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| SET-1 | Tous | Windows, macOS, Linux | (**C67**) Clé ouverte : Accueil ▸ carte de la clé ▸ « Prêt pour le set ? ». | En quelques secondes : système de fichiers, export.pdb, fichiers audio, analyse, formats, cues, playlists, place libre, sauvegarde ; chaque ligne verte (✓), orange (!) ou rouge (✕), et un verdict en haut. Rien n'est modifié. |
| SET-2 | Tous | Windows, macOS, Linux | (**C67**) Changer « Platines du club » (Je ne sais pas, Récentes, NXS2, Anciennes) sur une clé qui a des FLAC ; fermer et rouvrir. | Avec Anciennes ou « Je ne sais pas », les FLAC et les fichiers au-delà de 48 kHz passent en rouge ; avec Récentes ou NXS2, la ligne Formats est verte. Le choix est retenu. Clé en exFAT : rouge sauf pour Récentes. |
| SET-3 | Tous | Windows, macOS, Linux | (**C67**) Sur une clé avec des sons non analysés, un export.pdb pas à jour et un fichier introuvable : cliquer le bouton de chaque ligne orange ou rouge. | « Analyser les n sons » lance l'analyse ; « Mettre à jour export.pdb » le met à jour puis relance la vérification ; « Voir les fichiers introuvables » ouvre l'onglet du Diagnostic ; « Voir ces sons » ouvre Bibliothèque ▸ Sans hot cue ; Sauvegardes ouvre les sauvegardes. |
| SET-4 | Tous | Windows, macOS, Linux | (**C67**) « Copier le rapport », puis « Enregistrer le rapport… ». | Un texte court (clé, date, platines, verdict, une ligne par contrôle) dans le presse-papiers, puis dans un fichier .txt. |
| SET-5 | Testeur platines | Platines | (**C67**) Clé déclarée « prête » (tout vert) pour les platines du club : la brancher. | Playlists, grilles, formes d'onde et cues présents sur les platines ; tous les sons se chargent. |

## Bibliothèque : nouvelles colonnes (C113)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| BIB-1 | Tous | Windows, macOS, Linux | (**C113**) Bibliothèque ▸ Colonnes : afficher My Tags, Dernière lecture, Analyse, Doublon. | Nouvelles colonnes masquées par défaut. My Tags : les My Tags de Rekordbox, dans leur ordre ; si la bibliothèque en a, la colonne s'affiche d'elle-même la première fois. La recherche trouve un son par son My Tag. |
| BIB-2 | Tous | Windows, macOS, Linux | (**C113**) Bibliothèque de l'ordinateur, puis clé jouée sur des platines (historiques) : colonne Dernière lecture, triée. | Date du plus récent historique qui contient le son ; vide si jamais joué. |
| BIB-3 | Tous | Windows, macOS, Linux | (**C113**) Colonne Analyse ; enregistrer une grille dans Grille et cues ; revenir. | « Pas analysé » (orange), « Analysé », puis « Grille vérifiée » (couleur d'accent) pour le son enregistré, gardé après redémarrage et sur un autre PC (même clé). |
| BIB-4 | Tous | Windows, macOS, Linux | (**C113**) Colonne Doublon : cliquer l'icône d'un son qui a un doublon. | Bulle « 1 doublon possible » ; le clic ouvre Diagnostic ▸ Doublons sur ce groupe. |

## Couleurs, playlists, recherche, mode léger (C144, C149, C169, C172, C174)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| COU-1 | Tous | Windows, macOS, Linux | (**C144**) Paramètres ▸ Apparence ▸ Couleur. | 24 couleurs en trois familles (Vives, Profondes, Douces), dont un vrai vert (« Vert franc »). Chaque couleur reste lisible (textes en couleur, boutons). Le changement s'applique sans redémarrer. |
| REC-1 | Tous | Windows, macOS, Linux | (**C149**) Télécharger un son vers des playlists avec beaucoup de playlists (30 et plus), dont une cochée par défaut tout en bas. | Bandeau « Sélectionnées » en haut avec une pastille par playlist cochée (✕ pour la retirer), même celle du bas ; « Aucune playlist : bibliothèque seulement » sinon. La fenêtre est plus haute (jusqu'à 80 % de l'écran) et la liste défile jusqu'à la première playlist cochée. |
| REC-2 | Tous | Windows, macOS, Linux | (**C169**) Rechercher ▸ Haute qualité ▸ bouton « ? ». | Un petit panneau explique place libre, file d'attente, vitesse, fiabilité, qualité annoncée et l'absence d'écoute Soulseek. Les en-têtes de colonnes gardent leurs bulles. |
| REC-3 | Tous | Windows, macOS, Linux | (**C172**) Lien ou playlist : une playlist YouTube ou SoundCloud de plus de 200 titres. | Bandeau « Seuls les 200 premiers titres sur 534 sont affichés » et « Charger les 200 suivants » ; chaque clic ajoute la suite, les cases déjà décochées le restent ; le bandeau disparaît quand tout est chargé. |
| DEM-1 | Testeur Windows | Windows | (**C174**) PC modeste (ou Paramètres ▸ Général ▸ Mode léger : Activé), lancer DJSync deux fois ; puis la version portable sur un autre PC modeste. | Sur chaque PC, la fenêtre d'explication du mode léger ne s'ouvre qu'une fois. Ensuite, à chaque lancement, une bulle discrète « Mode léger actif sur ce PC (…) » avec « Réglages ». |

## Tests automatiques (C183)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| CI-1 | Claude | Windows, Linux | (**C183**) Passe complète `ci/full` sur la branche de la rc. | Plus aucun test d'au moins 5 min : les fenêtres des tests sont vraiment détruites (elles s'accumulaient : ~940 widgets par test). Les gros fichiers d'interface sont découpés, sans retirer de test. Rekordbox ouvert sur la machine ne fait plus échouer de test. |
