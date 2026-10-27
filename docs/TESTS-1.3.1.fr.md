# Scénarios de test — DJSync 1.3.1

Interface et confort : code couleur commun (**C29**), lecteur centré (**C34**), un seul bouton de
filtres dans la Recherche (**C33**), toutes les colonnes de métadonnées dans la Bibliothèque (**C37**),
volet des Paramètres (**C28**), espace occupé (**C27**), Diagnostic en onglets (**C41**) avec les
fichiers introuvables (**C43**), format et débit des doublons (**C42**), Suggestions pour enchaîner
(**C30**). Sur la clé : genre et label dans export.pdb (**C38**). Les scénarios de
`docs/TESTS-1.3.0-rc.3.fr.md` restent à faire s'ils ne sont pas cochés.

## J. Lecteur, recherche, couleurs (C34, C33, C29)
| # | Étapes | Attendu |
|---|---|---|
| J1 | Agrandir la fenêtre en plein écran, puis la réduire à environ 1100 px de large. | Le bouton lecture et la barre de progression restent au centre de la fenêtre ; la barre ne s'étire pas sans fin sur grand écran. |
| J2 | Onglet Recherche : regarder à gauche de la barre de recherche. | Plus de liste « Tout / Titre / Artiste / Album » à gauche : un seul bouton **Filtres** à droite. |
| J3 | Ouvrir **Filtres**, choisir « Artiste » dans « Chercher dans » et une durée maximale de 10 min. | Le bouton affiche « Artiste · ≤ 10 min » ; les résultats suivent. |
| J4 | Doublons : un groupe où le son a été comparé. | « Même son » en vert, quelle que soit la couleur d'accent choisie ; « Variante x % » en jaune / orange / rouge selon x. |

## L. Colonnes de la Bibliothèque (C37)
| # | Étapes | Attendu |
|---|---|---|
| L1 | Bibliothèque ▸ bouton **Colonnes** (à côté de Harmonique). | Menu avec toutes les colonnes, dont Genre, Année, Label, Débit, Fréquence, Note, Couleur, Lectures, Créé, Taille, Commentaire, Emplacement ; il reste ouvert pendant qu'on coche. |
| L2 | Cocher Genre, Année, Débit et Emplacement, réduire la fenêtre. | Les colonnes cochées restent affichées ; le tableau défile horizontalement au lieu d'en masquer. |
| L3 | Glisser l'en-tête « Genre » à gauche de « Titre » ; cliquer sur l'en-tête « Débit ». | La colonne se déplace ; tri par débit. |
| L4 | Fermer DJSync, le rouvrir. | Mêmes colonnes, même ordre, mêmes largeurs. **Réinitialiser les colonnes** (clic droit sur l'en-tête) revient à l'affichage d'origine. |
| L5 | Bibliothèque de l'ordinateur (Rekordbox fermé) : afficher Genre, Note et Couleur. | Valeurs de Rekordbox (étoiles, pastille de couleur). |

## G. Genre et label dans export.pdb (C38) — clé avec export.pdb
| # | Étapes | Attendu |
|---|---|---|
| G1 | Télécharger un son dont le genre est trouvé (colonne Genre remplie). Éjecter, ouvrir la clé dans Rekordbox (Device Library, colonne Genre). | Le genre (et le label s'il y en a un) s'affiche dans Rekordbox. |
| G2 | Clé déjà utilisée avec la 1.3.0 : l'ouvrir dans DJSync 1.3.1. | Accueil : export.pdb « pas à jour » le temps du rattrapage, puis à jour ; dans Rekordbox, les genres des sons ajoutés avant apparaissent. |
| G3 | Modifier le genre d'un son (clic droit ▸ Infos), éjecter, ouvrir dans Rekordbox. | Nouveau genre dans Rekordbox. |
| G4 | (Platines, si possible) Parcourir par genre sur une ancienne platine. | Le genre est proposé. |

## R. Volet des Paramètres (C28)
| # | Étapes | Attendu |
|---|---|---|
| R1 | Ouvrir Paramètres. | Volet à gauche : Général · Bibliothèques · Téléchargement · Analyse · Retours et confidentialité · DJSync ; à droite, seulement les cartes de la section. Aucun réglage n'a changé. |
| R2 | Taper « mp3 » puis « sauvegarde » dans **Chercher un réglage**. | Les cartes concernées de toutes les sections s'affichent ; un mot absent affiche « Aucun réglage ne correspond… ». |
| R3 | Choisir « Analyse », fermer DJSync, le rouvrir, aller dans Paramètres. | La section Analyse est rouverte. |
| R4 | Réduire la fenêtre à moins de 800 px de large. | Le volet devient une liste déroulante en haut. |
| R5 | Accueil : cliquer la pastille « export.pdb » de la carte de la clé. | Paramètres ▸ Bibliothèques s'ouvre (carte Anciennes platines). |

## O. Espace occupé (C27)
| # | Étapes | Attendu |
|---|---|---|
| O1 | Accueil : cliquer « xx Go libres sur yy Go » (ou la barre) de la clé. | Paramètres ▸ Bibliothèques, carte **Espace occupé** : « Mesure en cours… » puis une barre en couleurs et le détail : Musique, Analyses et pochettes, Bases Rekordbox, Sauvegardes DJSync, Application DJSync, Caches, Autres fichiers, Libre. |
| O2 | Comparer « Musique » à la taille du dossier `Contents` dans l'Explorateur / le Finder. | Même ordre de grandeur. |
| O3 | **Vider les caches** (version sur la clé). | Message « Caches vidés : x libérés » ; la barre se met à jour ; DJSync fonctionne normalement (formes d'onde recalculées au besoin). |
| O4 | **Garder les 5 derniers points de restauration**, puis Paramètres ▸ Sauvegardes de la clé ▸ Sauvegardes et restauration. | Le point « origine » et vos points manuels sont toujours là ; seuls les automatiques au-delà des 5 derniers ont disparu. |
| O5 | Bibliothèque de l'ordinateur : ouvrir la carte. | Musique (dossier de téléchargement DJSync), Sauvegardes (master.db), Caches, Libre. |

## M. Diagnostic en onglets et fichiers introuvables (C41, C43, C42)
| # | Étapes | Attendu |
|---|---|---|
| M1 | Accueil ▸ bouton **Diagnostic** de la carte. | Page avec quatre onglets : **Fichiers introuvables** (ouvert), **Doublons**, **Mauvaise qualité**, **Uniformiser**, chacun avec son nombre de sons quand il est connu. |
| M2 | Passer d'un onglet à l'autre, puis **Retour**. | Un seul onglet ouvert à la fois ; Retour ramène à l'Accueil. Outils ▸ Doublons (Accueil ou Bibliothèque) ouvre directement l'onglet Doublons. |
| M3 | Bibliothèque de l'ordinateur avec le son B.M.S (by my side) dont le fichier a disparu. | Il est listé avec le chemin attendu et ses playlists ; s'il existe ailleurs dans la bibliothèque, « Remplacer par … » est proposé. |
| M4 | Clé : déplacer un fichier de `Contents` dans un autre sous-dossier de `Contents` (Explorateur), ouvrir l'onglet. | « Utiliser le fichier trouvé ici : … » proposé par défaut ; **Appliquer** : le son se relit, garde playlists, grille et cues ; après éjection, Rekordbox le lit aussi. |
| M5 | Supprimer le fichier d'un son qui a une autre version dans la bibliothèque, **Remplacer par**. | La version gardée prend sa place dans les playlists ; ses hot cues viennent de l'ancienne si elle n'en avait pas. |
| M6 | **Retirer l'entrée** sur un son introuvable, puis **Retirer toutes les entrées introuvables**. | Les sons quittent la bibliothèque et leurs playlists (sauvegarde avant) ; les sons d'un disque non branché ne sont pas touchés. |
| M7 | Lire un son dont le fichier manque. | Message d'erreur avec un bouton **Voir dans le Diagnostic** qui ouvre l'onglet Fichiers introuvables. |
| M8 | Onglet **Doublons** : un groupe avec des versions MP3 et AAC. | Chaque version affiche format · débit · fréquence (« AAC · 256 kbps · 44,1 kHz »), en couleur selon la qualité ; « meilleure qualité » sur la meilleure ; « ? » si le fichier manque. |
| M9 | Onglet Doublons : **Chercher une version propre**. | Versions à retélécharger avec la qualité attendue (« m4a · ~256 kbps » ou « MP3 320 ») ; en choisir une et appliquer : elle remplace toutes les versions du groupe dans leurs playlists. |
| M10 | Onglet **Mauvaise qualité**. | Seulement les sons de faible débit ou de mauvaise source (clip, live, lyrics…), avec « Retélécharger » ; les doublons n'y sont plus. |

## Z. Suggestions pour enchaîner (C30)
| # | Étapes | Attendu |
|---|---|---|
| Z1 | Bibliothèque ▸ **Suggestions**, sélectionner un son analysé. | Panneau à droite : « Après « … » · 8A · 124 BPM », puis jusqu'à 20 sons classés : pastille Camelot, BPM avec l'écart en couleur, raison (« même clé », « ±1 sur la roue », « clé relative »). |
| Z2 | Lancer la lecture d'un autre son. | Les suggestions suivent le son en lecture. |
| Z3 | Régler **BPM ± %** sur 2 puis 10 ; choisir « Playlist ouverte ». | La liste se resserre / s'élargit ; seulement les sons de la playlist ouverte. Un son à 70 BPM est proposé pour une référence à 140 (×½). |
| Z4 | Dans une playlist : **+** sur une suggestion ; glisser une autre suggestion sur une playlist de l'arbre. | Ajout en fin de playlist ; « ✓ » pour les sons déjà dedans. |
| Z5 | Double-cliquer une suggestion. | Lecture du son (la liste des suggestions devient la file de lecture). |
| Z6 | Filtre **Harmonique** : choisir « BPM ±6 % » dans le bandeau. | Ne restent que les sons de clé compatible et de BPM proche. |
| Z7 | Fermer DJSync avec le panneau ouvert, le rouvrir. | Le panneau est rouvert, avec le même réglage de BPM. |
