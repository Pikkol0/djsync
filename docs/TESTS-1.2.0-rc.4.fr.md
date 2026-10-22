# Scénarios de test — DJSync 1.2.0-rc.4

Deux parties : **A** vérifie que chaque correctif fait bien son travail, **B** vérifie que rien
d'autre n'a cassé. Chaque scénario donne la plateforme concernée, les étapes et le résultat attendu.
Notez pour chacun : OK / KO + capture et `djsync.log` en cas de KO (*Paramètres* ▸ *Sauvegardes* ▸
*Ouvrir le dossier du journal*).

Avant de commencer : gardez une copie de votre clé (ou un point de restauration : *Paramètres* ▸
*Sauvegardes de la clé* ▸ *Créer*).

## A. Correctifs et nouveautés

### A1. Mise à jour depuis l'application (C20) — Windows, Mac, Linux
La rc.4 est la dernière version à installer à la main. Le vrai test se fera à la sortie de la rc.5 ;
d'ici là, A1.1 à A1.3 vérifient l'affichage.

| # | Étapes | Attendu |
|---|---|---|
| A1.1 | *Paramètres* ▸ carte **DJSync** | « Version 1.2.0-rc.4 » (et non « 1.2.0 ») ; même numéro dans l'aide (F1) et l'écran de démarrage. |
| A1.2 | *Vérifier maintenant* | « DJSync est à jour (1.2.0-rc.4) » tant qu'aucune version plus récente n'est publiée. |
| A1.3 | *Versions proposées* : choisir « Versions stables seulement », *Enregistrer*, relancer DJSync | Le choix est conservé. Remettre « Automatique ». |
| A1.4 *(à la rc.5)* | Au démarrage, ou *Vérifier maintenant* | Proposition « DJSync 1.2.0-rc.5 est disponible » avec **Mettre à jour**. |
| A1.5 *(à la rc.5)* | *Mettre à jour* | Barre de progression et « Téléchargement… x / y Mo », bouton *Annuler* ; puis « Mise à jour prête » ▸ *Redémarrer maintenant*. |
| A1.6 *(à la rc.5)* | *Redémarrer maintenant* | DJSync se ferme, se rouvre en quelques secondes en rc.5 (A1.1). Réglages, langue, clé active, historique : identiques. |
| A1.7 *(à la rc.5)* | Pendant le téléchargement : *Annuler*, puis couper Internet et réessayer | Annulation sans message d'erreur ; hors ligne : message clair, la version installée n'a pas bougé. |
| A1.8 *(à la rc.5, Windows)* | Après la mise à jour, regarder la clé | Seul `DJSync.exe` est visible (un `DJSync.exe.update-old` peut exister jusqu'au lancement suivant, puis disparaît). |
| A1.9 *(à la rc.5, Mac)* | Mise à jour avec DJSync sur la clé, puis relancer | Pas de message « Ouvrir quand même » ni de copie en quarantaine ; DJSync voit la clé. |

### A2. Grille des m4a (B01) — toutes plateformes
| # | Étapes | Attendu |
|---|---|---|
| A2.1 | Bibliothèque : sélectionner les m4a déjà analysés par DJSync ▸ *Outils* ▸ **Analyser la sélection**, cocher « Réanalyser aussi les titres déjà analysés par DJSync » (ou, pour un son : lecteur ▸ menu ▸ *Analyser à nouveau*) | Analyse sans erreur. |
| A2.2 | Rekordbox fermé, refaire la mesure sur les 52 sons de référence : `python -m djsync.analysis --compare local --under "E:\Contents" --csv m4a-rc4.csv --ffmpeg "E:\.djsync\tools"` | Ligne `.m4a : median offset` proche de **0 ms** (avant : −32,5 ms) ; « Grid: beats within 20 ms » autour de 32/45 au lieu de 1/45. Envoyer le CSV. |
| A2.3 | Dans Rekordbox, ouvrir 3 m4a réanalysés (dont un des 52), mode GRID, zoom fort | Les traits de grille tombent sur les kicks, plus décalés à gauche. |
| A2.4 | Sur platine (si possible) : caler deux m4a réanalysés en SYNC | Les kicks restent ensemble. |
| A2.5 | Éditeur de grille d'un m4a puis d'un mp3 : lancer l'écoute, regarder le curseur passer sur un kick | Le curseur passe sur le kick en même temps qu'on l'entend (plus d'avance d'environ 30 ms). |

### A3. Contretemps (B11) — toutes plateformes
| # | Étapes | Attendu |
|---|---|---|
| A3.1 | Éditeur de grille de « The Underground » (ou « BMW », « Tu sais ») ▸ bouton **½ temps** | Toute la grille avance d'un demi-temps : les traits passent des claps/charleys aux kicks. *Enregistrer*. |
| A3.2 | Appuyer deux fois sur **½ temps** | Un temps entier de décalage (le « 1 » de la mesure change de temps). |
| A3.3 | Mesure A2.2 | Nouvelle ligne « Grid: shifted by half a beat » (environ 10/45 attendu : la détection automatique arrive plus tard). |

### A4. Sons invisibles après avoir rouvert Rekordbox (B03) — bibliothèque de l'ordinateur, Mac et Windows
| # | Étapes | Attendu |
|---|---|---|
| A4.1 | DJSync ouvert sur « Cet ordinateur » : télécharger 2 sons dans une playlist | Ils apparaissent dans DJSync. |
| A4.2 | Ouvrir Rekordbox, vérifier les 2 sons, fermer Rekordbox (DJSync reste ouvert) | Les 2 sons étaient là. |
| A4.3 | Sans relancer DJSync : télécharger 2 autres sons dans la même playlist, puis créer une playlist | Pas d'erreur. |
| A4.4 | Rouvrir Rekordbox | Les **4** sons et la nouvelle playlist sont là. Si KO : envoyer `djsync.log` (lignes « change saved to master.db »). |
| A4.5 | Recommencer A4.2–A4.4 en créant une playlist **dans Rekordbox** à l'étape A4.2 | Elle apparaît dans DJSync ; les ajouts suivants de DJSync apparaissent dans Rekordbox. |

### A5. Petits correctifs d'interface
| # | Plateforme | Étapes | Attendu |
|---|---|---|---|
| A5.1 (B05) | Mac | DJSync en plein écran : Accueil ▸ *Trouver les doublons*, puis *Diagnostic* | La fenêtre s'ouvre devant DJSync, dans le même écran, sans revenir au bureau ; elle se déplace et se redimensionne. |
| A5.2 (B05) | Mac | DJSync en fenêtre : ouvrir Doublons, cliquer dans la fenêtre principale | La fenêtre Doublons reste visible au-dessus. |
| A5.3 (B06) | Toutes | Langue Français | Onglet « Importer un lien » ; en bas à gauche « Cet ordinateur ». Repasser en anglais : « Import URL », « This computer ». |
| A5.4 (B07) | Toutes, surtout Mac | Recherche : taper un titre, sélectionner un résultat, *Écouter*, puis **Espace** | Pause / reprise (plus d'espace tapé dans la recherche). |
| A5.5 (B07) | Toutes | Pendant l'écoute, touches multimédia du clavier (lecture/pause, suivant, précédent) avec DJSync au premier plan | Elles agissent sur le lecteur de DJSync. (Mac : si une autre app joue du son, macOS peut garder ces touches.) |
| A5.6 (B08) | Toutes | Écouter un son **pas encore téléchargé**, cliquer aux trois quarts de la barre d'avancement | La lecture saute à cet endroit (sans attraper le rond). Glisser fonctionne toujours. |
| A5.7 (B09) | Toutes | Fenêtre étroite (barre en icônes) : bouton flèche en bas de la barre latérale | La barre se déplie avec les libellés ; le bouton « Réduire » la replie. Le choix reste après redémarrage. |
| A5.8 (B10) | Toutes | Télécharger un son ▸ fenêtre « Télécharger dans… » | La liste occupe toute la hauteur ; le champ « Rechercher une playlist… » filtre la liste ; les playlists cochées restent visibles. |
| A5.9 (C01) | Toutes | Cliquer *Écouter* sur un résultat de recherche | Titre et pochette s'affichent tout de suite dans le lecteur, le bouton lecture tourne pendant le chargement. |
| A5.10 (C19) | Toutes | *Paramètres* ▸ DJSync ▸ *Licence*, *Composants tiers*, *DJSync sur GitHub* | Les deux textes s'ouvrent ; le lien ouvre le dépôt. |

## B. Non-régression

À faire au moins une fois sur Windows et une fois sur Mac.

| # | Domaine | Étapes | Attendu |
|---|---|---|---|
| B1 | Démarrage | Lancer DJSync depuis la clé (premier lancement de la rc.4) | Démarre ; réglages et langue d'avant conservés. |
| B2 | Recherche | Recherche pendant la frappe, filtres, ↓ en bout de ligne | Comme avant. |
| B3 | Téléchargement | Télécharger 3 sons (m4a par défaut) dans une playlist de la clé | Fichiers `.m4a`, pochette, tags, playlist mise à jour. |
| B4 | Format MP3 | *Paramètres* ▸ Format MP3 320, télécharger 1 son, revenir en M4A | Fichier `.mp3`, analyse OK ; puis retour au m4a. |
| B5 | Analyse | *Non analysés* ▸ *Tout analyser*, puis arrêter au milieu | Progression, arrêt propre, reprise possible. |
| B6 | Grille MP3 | Éditeur de grille d'un MP3 analysé par DJSync : décaler ±10 ms, enregistrer, revoir dans Rekordbox | Grille enregistrée, toujours alignée comme en rc.3 (pas de nouveau décalage sur les MP3). |
| B7 | Clé USB dans Rekordbox | Après B3–B6 : ouvrir la clé dans Rekordbox (Device Library et OneLibrary) | Sons, BPM, tonalité, formes d'onde, playlists, mémoire cue. |
| B8 | Platines | Lire la clé sur les platines (si dispo) | Playlists et sons visibles ; grilles des m4a réanalysés justes. |
| B9 | Bibliothèque du PC | Ajouter un son à « Cet ordinateur », ouvrir Rekordbox | Visible, analysé, dans sa playlist. |
| B10 | Doublons | *Trouver les doublons*, écouter une version, fusionner un groupe sûr | Le son gardé prend la place des autres dans les playlists. |
| B11 | Diagnostic | *Diagnostic* sur la clé | S'ouvre, liste les problèmes, *Ignorer* est retenu. |
| B12 | Copie de playlist | Copier une playlist clé → ordinateur | Sons copiés, analyse reprise. |
| B13 | Sauvegardes | *Paramètres* ▸ *Sauvegardes de la clé* : créer un point, restaurer le précédent | Restauration OK, « avant restauration » créé. |
| B14 | Lecteur | Précédent / Suivant, enchaînement, volume, mini forme d'onde cliquable | Comme avant. |
| B15 | Interface | Zoom 80 % et 150 %, changement de couleur d'accent, de langue | S'applique sans redémarrer ; aucune fenêtre coupée. |
| B16 | Éjection | Bouton Éjecter | Clé éjectée proprement. |
| B17 | Rekordbox ouvert | Rekordbox ouvert : essayer d'ajouter un son à « Cet ordinateur » | Message « Fermez Rekordbox d'abord », rien d'écrit. |

## Tests automatiques
`python -m pytest -q` : 345 tests (dont `tests/test_rc4.py` : décalage m4a sur un fichier réel, ½ temps,
version exacte et canal, téléchargement vérifié par SHA-256, échange complet d'une installation Linux
avec reprise des réglages, archive dangereuse refusée, carte DJSync des Paramètres, barre d'avancement,
barre latérale, recherche de playlist ; `tests/test_local_library.py` : master.db enregistré sur place
par Rekordbox avant une écriture de DJSync).
