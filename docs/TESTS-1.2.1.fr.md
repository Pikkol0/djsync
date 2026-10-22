# Scénarios de test — DJSync 1.2.1

À faire avec ceux de la rc.4 (`docs/TESTS-1.2.0-rc.4.fr.md`) : la 1.2.1 contient tout ce qu'il y a dans
la rc.4. Notez OK / KO, avec une capture et `djsync.log` en cas de KO… ou testez directement l'onglet
**Retours** (C1) en signalant vos KO avec !

**Mise à jour depuis l'app** : si la 1.2.0-rc.4 est installée, *Paramètres* ▸ *DJSync* ▸ *Vérifier
maintenant* doit proposer la 1.2.1-rc.1. C'est le vrai test de la mise à jour en un clic (scénarios A1.4
à A1.9 de la rc.4).

## C. Nouveautés de la 1.2.1

### C1. Onglet Retours (C18)
| # | Étapes | Attendu |
|---|---|---|
| C1.1 | Barre latérale ▸ **Retours** (Ctrl+7) | Une remarque vide : type, titre, description, *Capturer DJSync*, *Ajouter une image…*. |
| C1.2 | Aller dans la Bibliothèque, revenir dans Retours, *Capturer DJSync* | Vignette de la fenêtre telle qu'elle était dans la Bibliothèque ; on revient sur Retours. |
| C1.3 | *Ajouter une image…* ; glisser une image depuis le bureau sur la remarque | Vignettes ajoutées, 3 au plus ; *Retirer* fonctionne. |
| C1.4 | *Ajouter une autre remarque* : une « Idée » avec un titre | Remarques numérotées 1, 2 ; corbeille pour en retirer une. |
| C1.5 | *Envoyer* **avant** d'avoir installé le script (`docs/FEEDBACK_SETUP.fr.md`) | Message « l'envoi direct n'est pas disponible » et page GitHub préremplie avec les remarques. |
| C1.6 | Installer le script (guide), lancer DJSync avec `DJSYNC_FEEDBACK_URL=<url>` (ou attendre la version qui l'embarque), envoyer 2 remarques dont une avec 2 captures, e-mail renseigné | E-mail reçu : « [DJSync …] 1 Bug, 1 Idée · … », remarques numérotées, captures `1-bug-capture-1.jpg`…, `djsync-log.txt` ; *Répondre* écrit à l'e-mail donné. Le formulaire de DJSync est vidé, « Merci ! ». |
| C1.7 | Décocher « Joindre les informations techniques », envoyer | Pas de `djsync-log.txt`, seulement la version. |
| C1.8 | Ouvrir `djsync-log.txt` reçu | Aucun nom d'utilisateur ni chemin `C:\Users\…` / `/Users/…` (remplacés par `~` et `<user>`). |

### C2. Bibliothèque : colonnes, tri, source (C04, C05, C06)
| # | Étapes | Attendu |
|---|---|---|
| C2.1 | Bibliothèque ▸ playlist de plus de 700 sons | La colonne `#` affiche les numéros en entier. |
| C2.2 | Clic droit sur l'en-tête du tableau | Liste des colonnes à cocher + « Rétablir les colonnes par défaut ». Par défaut : album et format décochés. |
| C2.3 | Cocher *Album*, élargir *Artiste*, changer de playlist, d'onglet, puis relancer DJSync | Album affiché, largeur gardée partout. « Rétablir » revient au défaut. |
| C2.4 | Trier une playlist par *Ajouté le* décroissant, aller dans une autre playlist, revenir ; relancer DJSync | Le tri est retrouvé pour cette playlist ; l'autre playlist garde le sien. |
| C2.5 | Colonne **Source** | YouTube Music / YouTube / SoundCloud pour les sons téléchargés par DJSync ; vide pour les sons venus de Rekordbox. |
| C2.6 | Même chose dans Recherche et Téléchargements | Colonnes choisies et largeurs retenues séparément pour chaque tableau. |

### C3. Choix de playlist (C02)
| # | Étapes | Attendu |
|---|---|---|
| C3.1 | Télécharger un son ▸ « Télécharger dans… » | Arborescence comme dans Rekordbox (dossiers dépliés, playlists dedans), toute la hauteur. |
| C3.2 | Taper le nom d'une playlist dans la recherche, puis le nom d'un **dossier** | Seules les playlists correspondantes restent (avec leurs dossiers) ; le nom du dossier fait apparaître ses playlists. Les cochées restent visibles. |
| C3.3 | Sélectionner un dossier, taper un nom, *Créer* | « Les nouvelles playlists iront dans le dossier … » ; la playlist est créée dans ce dossier et cochée. Vérifier dans Rekordbox. |
| C3.4 | Bibliothèque ▸ sélection ▸ *Ajouter à…* / *Déplacer vers…* | Même fenêtre en arborescence. |

### C4. Recherche (C08, C09)
| # | Étapes | Attendu |
|---|---|---|
| C4.1 | Menu à gauche de la barre : **Artiste**, taper un artiste dont le nom est aussi un titre courant | Seulement des sons de cet artiste. |
| C4.2 | **Titre** | Seulement des sons dont le titre contient les mots tapés. |
| C4.3 | **Album**, taper un album connu | Une ligne par album (type « Album », année). Double-clic (ou flèche) : les titres de l'album, tous sélectionnés ; *Télécharger* propose le nom de l'album comme nouvelle playlist. Bouton « ← Albums » pour revenir. |
| C4.4 | *Filtres* ▸ Durée maximale « moins de 10 min » | Les mixes longs disparaissent ; le bouton Filtres est mis en avant. |
| C4.5 | *Filtres* ▸ « Masquer les titres déjà dans la bibliothèque » | Les sons déjà présents disparaissent ; « N déjà dans la bibliothèque masqués » sous la barre. |
| C4.6 | Relancer DJSync | Champ et filtres retenus. Un ancien réglage « Type : Artistes » devient le champ « Artiste ». |

### C5. Éditeur de grille, doublons, progression (C03, C11, C12, C21)
| # | Étapes | Attendu |
|---|---|---|
| C5.1 | Éditeur de grille : Ctrl/⌘ + molette, pincement du pavé tactile (Mac), boutons − / + | Zoom de 2 à 32 s autour du curseur ; la molette seule fait défiler. |
| C5.2 | Doublons : un groupe | Sous chaque version : « Dans : playlist A, playlist B » ou « Dans aucune playlist ». |
| C5.3 | Doublons : *Début* puis *Milieu* sur deux versions | Lecture depuis le début, puis depuis le milieu du son. |
| C5.4 | Télécharger 5 sons | Barre dans la colonne État de chaque ligne ; barre globale en haut de l'onglet ; carte « Téléchargements 2 / 5 » dans la barre latérale. |
| C5.5 | Pendant les téléchargements, lancer *Tout analyser* | Carte « Activité » avec les deux barres ; dans la liste d'analyse, une barre sur le son en cours. |

## D. Non-régression
Reprendre la partie **B** des scénarios de la rc.4 (B1 à B17), plus :

| # | Étapes | Attendu |
|---|---|---|
| D1 | Copier un son SoundCloud d'une clé vers l'ordinateur (copie de playlist) | Copie OK, la source SoundCloud est gardée. |
| D2 | Recherche « Tout » sans filtre | Mêmes résultats qu'avant (titres puis vidéos). |
| D3 | Raccourcis Ctrl+1 … Ctrl+7, F1 | Ctrl+7 ouvre Retours ; l'aide liste les 7 onglets. |
