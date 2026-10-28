# Scénarios de test — DJSync 1.3.1

Interface et confort : code couleur commun (**C29**), lecteur centré (**C34**), un seul bouton de
filtres dans la Recherche (**C33**), toutes les colonnes de métadonnées dans la Bibliothèque (**C37**),
volet des Paramètres (**C28**), espace occupé (**C27**), Diagnostic en onglets (**C41**) avec les
fichiers introuvables (**C43**), format et débit des doublons (**C42**), Suggestions pour enchaîner
(**C30**). Sur la clé : genre et label dans export.pdb (**C38**). Les scénarios de
`docs/TESTS-1.3.0-rc.3.fr.md` restent à faire s'ils ne sont pas cochés.

Numérotation (27/10) : **thème en 3 lettres + n°**, propre à chaque version (CLE clé et export.pdb, DEM démarrage, LEC lecteur, GRI grille et cues, UNI uniformiser, DOU doublons, DIA diagnostic, BIB bibliothèque, REC recherche, PAR paramètres, COU couleurs, ESP espace, SUG suggestions, IMP fichiers de l'ordinateur, SRC sources, QUA qualité, RET retours, PLA platines, ANA analyse, MAC macOS). Dans le suivi : « 131 · LEC-1 ».

## J. Lecteur, recherche, couleurs (C34, C33, C29)
| # | Étapes | Attendu |
|---|---|---|
| LEC-1 | Agrandir la fenêtre en plein écran, puis la réduire à environ 1100 px de large. | Le bouton lecture et la barre de progression restent au centre de la fenêtre ; la barre ne s'étire pas sans fin sur grand écran. |
| REC-1 | Onglet Recherche : regarder à gauche de la barre de recherche. | Plus de liste « Tout / Titre / Artiste / Album » à gauche : un seul bouton **Filtres** à droite. |
| REC-2 | Ouvrir **Filtres**, choisir « Artiste » dans « Chercher dans » et une durée maximale de 10 min. | Le bouton affiche « Artiste · ≤ 10 min » ; les résultats suivent. |
| COU-1 | Doublons : un groupe où le son a été comparé. | « Même son » en vert, quelle que soit la couleur d'accent choisie ; « Variante x % » en jaune / orange / rouge selon x. |

## C. Colonnes de la Bibliothèque (C37)
| # | Étapes | Attendu |
|---|---|---|
| BIB-1 | Bibliothèque ▸ bouton **Colonnes** (à côté de Harmonique). | Menu avec toutes les colonnes, dont Genre, Année, Label, Débit, Fréquence, Note, Couleur, Lectures, Créé, Taille, Commentaire, Emplacement ; il reste ouvert pendant qu'on coche. |
| BIB-2 | Cocher Genre, Année, Débit et Emplacement, réduire la fenêtre. | Les colonnes cochées restent affichées ; le tableau défile horizontalement au lieu d'en masquer. |
| BIB-3 | Glisser l'en-tête « Genre » à gauche de « Titre » ; cliquer sur l'en-tête « Débit ». | La colonne se déplace ; tri par débit. |
| BIB-4 | Fermer DJSync, le rouvrir. | Mêmes colonnes, même ordre, mêmes largeurs. **Réinitialiser les colonnes** (clic droit sur l'en-tête) revient à l'affichage d'origine. |
| BIB-5 | Bibliothèque de l'ordinateur (Rekordbox fermé) : afficher Genre, Note et Couleur. | Valeurs de Rekordbox (étoiles, pastille de couleur). |

## E. Genre et label dans export.pdb (C38) — clé avec export.pdb
| # | Étapes | Attendu |
|---|---|---|
| CLE-1 | Télécharger un son dont le genre est trouvé (colonne Genre remplie). Éjecter, ouvrir la clé dans Rekordbox (Device Library, colonne Genre). | Le genre (et le label s'il y en a un) s'affiche dans Rekordbox. |
| CLE-2 | Clé déjà utilisée avec la 1.3.0 : l'ouvrir dans DJSync 1.3.1. | Accueil : export.pdb « pas à jour » le temps du rattrapage, puis à jour ; dans Rekordbox, les genres des sons ajoutés avant apparaissent. |
| CLE-3 | Modifier le genre d'un son (clic droit ▸ Infos), éjecter, ouvrir dans Rekordbox. | Nouveau genre dans Rekordbox. |
| CLE-4 | (Platines, si possible) Parcourir par genre sur une ancienne platine. | Le genre est proposé. |

## I. Volet des Paramètres (C28)
| # | Étapes | Attendu |
|---|---|---|
| PAR-1 | Ouvrir Paramètres. | Volet à gauche : Général · Bibliothèques · Téléchargement · Analyse · Retours et confidentialité · DJSync ; à droite, seulement les cartes de la section. Aucun réglage n'a changé. |
| PAR-2 | Taper « mp3 » puis « sauvegarde » dans **Chercher un réglage**. | Les cartes concernées de toutes les sections s'affichent ; un mot absent affiche « Aucun réglage ne correspond… ». |
| PAR-3 | Choisir « Analyse », fermer DJSync, le rouvrir, aller dans Paramètres. | La section Analyse est rouverte. |
| PAR-4 | Réduire la fenêtre à moins de 800 px de large. | Le volet devient une liste déroulante en haut. |
| PAR-5 | Accueil : cliquer la pastille « export.pdb » de la carte de la clé. | Paramètres ▸ Bibliothèques s'ouvre (carte Anciennes platines). |

## O. Espace occupé (C27)
| # | Étapes | Attendu |
|---|---|---|
| ESP-1 | Accueil : cliquer « xx Go libres sur yy Go » (ou la barre) de la clé. | Paramètres ▸ Bibliothèques, carte **Espace occupé** : « Mesure en cours… » puis une barre en couleurs et le détail : Musique, Analyses et pochettes, Bases Rekordbox, Sauvegardes DJSync, Application DJSync, Caches, Autres fichiers, Libre. |
| ESP-2 | Comparer « Musique » à la taille du dossier `Contents` dans l'Explorateur / le Finder. | Même ordre de grandeur. |
| ESP-3 | **Vider les caches** (version sur la clé). | Message « Caches vidés : x libérés » ; la barre se met à jour ; DJSync fonctionne normalement (formes d'onde recalculées au besoin). |
| ESP-4 | **Garder les 5 derniers points de restauration**, puis Paramètres ▸ Sauvegardes de la clé ▸ Sauvegardes et restauration. | Le point « origine » et vos points manuels sont toujours là ; seuls les automatiques au-delà des 5 derniers ont disparu. |
| ESP-5 | Bibliothèque de l'ordinateur : ouvrir la carte. | Musique (dossier de téléchargement DJSync), Sauvegardes (master.db), Caches, Libre. |

## T. Diagnostic en onglets et fichiers introuvables (C41, C43, C42)
| # | Étapes | Attendu |
|---|---|---|
| DIA-1 | Accueil ▸ bouton **Diagnostic** de la carte. | Page avec quatre onglets : **Fichiers introuvables** (ouvert), **Doublons**, **Mauvaise qualité**, **Uniformiser**, chacun avec son nombre de sons quand il est connu. |
| DIA-2 | Passer d'un onglet à l'autre, puis **Retour**. | Un seul onglet ouvert à la fois ; Retour ramène à l'Accueil. Outils ▸ Doublons (Accueil ou Bibliothèque) ouvre directement l'onglet Doublons. |
| DIA-3 | Bibliothèque de l'ordinateur avec le son B.M.S (by my side) dont le fichier a disparu. | Il est listé avec le chemin attendu et ses playlists ; s'il existe ailleurs dans la bibliothèque, « Remplacer par … » est proposé. |
| DIA-4 | Clé : déplacer un fichier de `Contents` dans un autre sous-dossier de `Contents` (Explorateur), ouvrir l'onglet. | « Utiliser le fichier trouvé ici : … » proposé par défaut ; **Appliquer** : le son se relit, garde playlists, grille et cues ; après éjection, Rekordbox le lit aussi. |
| DIA-5 | Supprimer le fichier d'un son qui a une autre version dans la bibliothèque, **Remplacer par**. | La version gardée prend sa place dans les playlists ; ses hot cues viennent de l'ancienne si elle n'en avait pas. |
| DIA-6 | **Retirer l'entrée** sur un son introuvable, puis **Retirer toutes les entrées introuvables**. | Les sons quittent la bibliothèque et leurs playlists (sauvegarde avant) ; les sons d'un disque non branché ne sont pas touchés. |
| DIA-7 | Lire un son dont le fichier manque. | Message d'erreur avec un bouton **Voir dans le Diagnostic** qui ouvre l'onglet Fichiers introuvables. |
| DIA-8 | Onglet **Doublons** : un groupe avec des versions MP3 et AAC. | Chaque version affiche format · débit · fréquence (« AAC · 256 kbps · 44,1 kHz »), en couleur selon la qualité ; « meilleure qualité » sur la meilleure ; « ? » si le fichier manque. |
| DIA-9 | Onglet Doublons : **Chercher une version propre**. | Versions à retélécharger avec la qualité attendue (« m4a · ~256 kbps » ou « MP3 320 ») ; en choisir une et appliquer : elle remplace toutes les versions du groupe dans leurs playlists. |
| DIA-10 | Onglet **Mauvaise qualité**. | Seulement les sons de faible débit ou de mauvaise source (clip, live, lyrics…), avec « Retélécharger » ; les doublons n'y sont plus. |

## Z. Suggestions pour enchaîner (C30)
| # | Étapes | Attendu |
|---|---|---|
| SUG-1 | Bibliothèque ▸ **Suggestions**, sélectionner un son analysé. | Panneau à droite : « Après « … » · 8A · 124 BPM », puis jusqu'à 20 sons classés : pastille Camelot, BPM avec l'écart en couleur, raison (« même clé », « ±1 sur la roue », « clé relative »). |
| SUG-2 | Lancer la lecture d'un autre son. | Les suggestions suivent le son en lecture. |
| SUG-3 | Régler **BPM ± %** sur 2 puis 10 ; choisir « Playlist ouverte ». | La liste se resserre / s'élargit ; seulement les sons de la playlist ouverte. Un son à 70 BPM est proposé pour une référence à 140 (×½). |
| SUG-4 | Dans une playlist : **+** sur une suggestion ; glisser une autre suggestion sur une playlist de l'arbre. | Ajout en fin de playlist ; « ✓ » pour les sons déjà dedans. |
| SUG-5 | Double-cliquer une suggestion. | Lecture du son (la liste des suggestions devient la file de lecture). |
| SUG-6 | Filtre **Harmonique** : choisir « BPM ±6 % » dans le bandeau. | Ne restent que les sons de clé compatible et de BPM proche. |
| SUG-7 | Fermer DJSync avec le panneau ouvert, le rouvrir. | Le panneau est rouvert, avec le même réglage de BPM. |

## Ajouts du 28/10 : mémoires de boucle (C75), remerciements (C55), erreurs (C61), exe plus léger (C66)
| # | Étapes | Attendu |
|---|---|---|
| GRI-1 | **Grille et cues** : bouton **Mémoire de boucle** ▸ « Boucle de 4 temps », au curseur. | Une mémoire « ⟳ 4  m:ss » apparaît dans la rangée des mémoires, calée sur le temps le plus proche. |
| GRI-2 | Clic droit sur une mémoire simple ▸ « Boucle de 8 temps » ; puis ▸ « Retirer la boucle ». | Elle devient « ⟳ 8 … », puis redevient « ▼ … ». |
| GRI-3 | Enregistrer, éjecter, ouvrir la clé dans Rekordbox (et sur platine si possible). | La mémoire de boucle est dans la liste des mémoires avec sa longueur ; l'appeler puis Reloop la joue en boucle. (La « boucle active » qui s'enclenche toute seule n'est pas encore gérée : à relever sur un son de Rekordbox.) |
| RET-1 | Haut du README sur GitHub ; Paramètres ▸ DJSync ; onglet **Retours**. | Le remerciement à Tazyh, Vogue, Paf et Kuss, en anglais et en français dans le README, dans la langue de l'app ailleurs. |
| CLE-5 | Rekordbox ouvert sur la clé : dans DJSync, faire une modification (renommer une playlist). | Si une erreur arrive, elle se termine par « 💡 Rekordbox est ouvert et utilise probablement ce fichier : fermez Rekordbox, puis réessayez. » |
| CLE-6 | Lire une erreur longue. | La bulle d'erreur est large (jusqu'à ~70 % de la fenêtre), le texte entier se lit, **Copier** met le message dans le presse-papiers ; elle reste jusqu'à **Fermer** (×). Les messages d'info disparaissent seuls comme avant. |
| DEM-1 | (Auteur) Build de la 1.3.1 : taille de DJSync.exe (::notice du build) et premier lancement depuis une clé. | Plus petit qu'en 1.3.0 (fichiers Qt inutiles retirés : OpenGL logiciel, QML, clavier virtuel, traductions autres que FR/EN…) ; l'autotest du build passe ; DJSync démarre et tout s'affiche. |
