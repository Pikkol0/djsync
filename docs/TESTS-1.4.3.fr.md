# Scénarios de test — DJSync 1.4.3

Numérotation : thème en 3 lettres + n° (voir `revues/numerotation-tests.md`) ; dans le suivi : « 143 · REC-1 ».
Règle : un test OK sous Windows est validé ; Mac et Linux seulement pour un point qui leur est propre.

## rc.1, lot 1 — rapidité et sûreté des données

Fiches : A3-6, B98, A1-2, A1-4, A1-5, A1-8, A1-10, A1-12, A1-13 (rapidité) ; A6-1, A6-2, A6-4, A6-5, A6-9, A6-10, A6-11 (données) ;
A3-5, A3-10 (code) ; C202, C206. Specs : `claude/spec-1.4.3.md` (A1-2, A6-1, A6-2, A6-9).

### Rapidité pendant les téléchargements

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| REC-1 | Tous | Windows | (**B98**, **A3-6**) Clé USB ouverte : lancer 10 téléchargements, puis faire 3 recherches pendant qu'ils tournent. | Les résultats s'affichent en moins de 2 s, comme sans téléchargement ; « déjà dans la bibliothèque » apparaît juste après (une fraction de seconde) et reste juste. |
| REC-2 | Tous | Windows | (**B98**) Même chose sur la bibliothèque de l'ordinateur (Rekordbox fermé). | Même résultat. |
| REC-3 | Tous | Windows | (**B98**) Paramètres ▸ Recherche ▸ masquer ce qui est déjà dans la bibliothèque, puis chercher un son déjà téléchargé. | Il n'apparaît pas (le marquage est fait avant l'affichage dans ce cas). |
| PDB-1 | Tous | Windows | (**A1-2**) Clé USB : 10 téléchargements de suite, puis Paramètres ▸ Bibliothèques ▸ état d'export.pdb. Envoyer le journal. | État « à jour ». Dans le journal, « export.pdb reconciled » une fois par rafale (quelques secondes après la dernière écriture), pas une fois par son. |
| PDB-2 | Tous | Windows | (**A1-2**) Télécharger un son, puis **tout de suite** (moins de 3 s) Éjecter depuis DJSync ; rebrancher la clé dans Rekordbox (Appareil) ou sur une ancienne platine. | Le son est dans export.pdb (visible côté Rekordbox / ancienne platine). |
| PDB-3 | Tous | Windows | (**A1-2**) Télécharger un son puis ouvrir tout de suite « Prêt pour le set ? ». | La ligne export.pdb est verte. |
| LIB-1 | Tous | Windows | (**A1-5**) Bibliothèque de plus de 500 sons : Ctrl+A, puis Maj+clic sur une grande plage. | Pas de gel ; le menu du clic droit compte bien les sons choisis. |
| LIB-2 | Tous | Windows | (**A1-8**) Bibliothèque ▸ Doublons, fermer, rouvrir ; télécharger un son puis rouvrir. | Mêmes groupes qu'en 1.4.2 ; la 2e ouverture est immédiate. |
| GRI-1 | Tous | Windows | (**A1-10**) Grille et cues sur un son de Rekordbox, forme d'onde Bleu puis RGB : lecture, défilement, zoom. | Image fluide, mêmes couleurs qu'avant. |
| IMP-1 | Tous | Windows | (**A1-12**) Glisser un dossier sur la liste de la Bibliothèque ; envoyer le journal. | Une ligne « Import finished: n files (…) in x s; y MB copied, z MB/s ». |
| DL-1 | Tous | Windows | (**A1-13**) 10 téléchargements avec pochettes. | Comme avant, un peu plus rapides ; pochettes présentes. |
| ORD-1 | Tous | Windows | (**A1-4**) Bibliothèque de l'ordinateur : importer 200 sons, puis ouvrir des playlists et chercher. | Pas de ralentissement au fil de la session. |

### Sûreté des données

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| DON-1 | Auteur | Windows | (**A6-1**) Sur une clé de test : copier `export.pdb` en `export.pdb.djsync-tmp` à côté, supprimer `export.pdb`, ouvrir la clé dans DJSync. | Message « DJSync a réparé export.pdb… » ; export.pdb de retour, état « à jour ». |
| DON-2 | Auteur | Windows | (**A6-1**) Même chose avec `exportLibrary.db` (renommée en `exportLibrary.db.djsync-tmp`). | La clé est reconnue et s'ouvre normalement. |
| DON-3 | Auteur | Windows | (**A6-1**) Clé de test avec au moins un point de restauration : remplacer `exportLibrary.db` par un fichier tronqué nommé `exportLibrary.db.djsync-tmp` (supprimer l'original). | Accueil : carte « Bibliothèque perdue », rien de supprimé ; « Restaurer la dernière sauvegarde » remet la clé dans l'état du dernier point et l'ouvre ; la copie illisible est dans DJSync_Backups. « Ouvrir le dossier des sauvegardes » ouvre DJSync_Backups. |
| DON-4 | Auteur | Windows | (**A6-2**) Paramètres ▸ Sauvegardes de la clé ▸ Restaurer un point, avec export.pdb ouvert dans un autre programme (Rekordbox, ou un éditeur qui garde le fichier). | Message « Restauration non faite… fermez-le » ; rien n'a changé sur la clé. Programme fermé : la restauration passe. |
| DON-5 | Tous | Windows | (**A6-4**) Bibliothèque de l'ordinateur : 12 changements (playlists, téléchargements), puis regarder le dossier des sauvegardes de master.db. | Un dossier `session-…` pour la session, en plus des 10 dernières copies `master-…`. L'aide des sauvegardes explique comment revenir en arrière. |
| DON-6 | Auteur | Windows | (**A6-5**) Rekordbox fermé : vider `masterPlaylists6.xml` (fichier de 0 octet), ouvrir la bibliothèque de l'ordinateur dans DJSync. | Elle s'ouvre ; le fichier est repris de la dernière sauvegarde, la copie illisible gardée à côté des sauvegardes. |
| DON-7 | Auteur | Windows | (**A6-10**) DJSync fermé : abîmer `settings.json` (couper le fichier au milieu), relancer. | Les réglages d'avant le dernier enregistrement reviennent (dossiers, langue…) ; une copie `settings-unreadable-…json` est gardée. |
| DON-8 | Tous | Windows | (**A6-9**, **A6-11**) Supprimer un son, renommer une playlist, modifier des grilles sur plusieurs sons, puis « Prêt pour le set ? ». | export.pdb « à jour » ; rien d'autre de visible (sécurité interne). |

### Divers

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| REC-4 | Tous | Windows | (**C202**) Rechercher ▸ onglet Haute qualité ; aller dans la Bibliothèque ; revenir par « Rechercher » ; quitter et relancer DJSync, cliquer « Rechercher ». | Haute qualité se rouvre les deux fois. |
| IMP-2 | Tous | Windows | (**C206**) Lien ou playlist ▸ une playlist Spotify publique de plus de 100 titres. | « Spotify ne donne que les 100 premiers sons sur n. » et la marche à suivre pour le reste (découper la playlist, ou « Coller une liste… »). |

### Reporté au lot 2

Fait au lot 2 (voir plus bas), sauf A7-3 (reporté au lot 3). Sautées et signalées : B105 (spec non validée), C114
(échantillon de cues manquant), A07 (à décider), A1-11 (reportée).

## rc.1, lot 2 — reste de la 1.4.3

Fiches : A1-9, B103 (option A), A3-2, A3-3, A3-4, A3-7, A3-8, A3-9 (code) ; A2-18 (option A), A2-19, A2-20, A2-21,
A2-23 (UX) ; C199, C200, C203, C210 ; A7-4, A7-5 (repris de Sleeve). A2-22 : déjà livrée en 1.4.2 (option A).
Tests automatiques : `tests/test_v143_rc2.py`.

### Rapidité et Diagnostic

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| LIB-3 | Tous | Windows | (**A1-9**) Clé de ≈ 500 sons, Bibliothèque ouverte (colonne « Playlists » affichée) : lancer 10 téléchargements, puis une analyse de 20 sons ; faire défiler et trier pendant ce temps. | Pas d'à-coup à chaque son ; la liste se met à jour au plus 2 fois par seconde ; colonne « Playlists » et œil du dossier surveillé justes. |
| DIA-1 | Tous | Windows | (**B103**) Diagnostic ▸ Mauvaise qualité ▸ Analyser maintenant, puis relancer une 2e fois ; pendant la 2e, lancer la lecture d'un son. | 2e passage beaucoup plus court (sons déjà lus gardés) ; pendant la lecture, le calcul attend (pas de saccade du son). Un son remplacé ou modifié est relu. |

### Paramètres, clavier, accessibilité

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| PAR-1 | Tous | Windows | (**A2-18**) Paramètres : cocher / décocher une case, changer une liste, taper un dossier puis Tab ; quitter la page ; relancer DJSync. | Plus de bouton « Enregistrer » ; « ✓ Enregistré » s'affiche brièvement ; plus de question en quittant ; tout est gardé après relance. |
| PAR-2 | Tous | Windows | (**A3-8**) Parcourir toutes les sections des Paramètres en français puis en anglais. | Mêmes cartes, même ordre, mêmes textes qu'en rc.1 (captures avant/après identiques en test). |
| CLA-1 | Tous | Windows | (**A2-19**) Pendant la lecture d'un son : Tab jusqu'à un bouton puis Espace ; Tab jusqu'à une case puis Espace ; Espace ailleurs. | Le bouton et la case sont activés (la lecture continue) ; ailleurs, Espace met en pause / relance. Le bouton qui a le focus clavier a un contour coloré ; un clic à la souris ne laisse pas de contour. |
| ACC-1 | Testeur Mac | macOS | (**A2-20**) VoiceOver : parcourir le volet et le lecteur. | Chaque bouton à icône est annoncé par son nom (celui de sa bulle). |
| PLA-6 | Tous | Windows | (**A2-21**) Dans une playlist, choisir 3 sons, Retirer, puis « Annuler » dans la bulle. | Les 3 sons reviennent, à leur place d'avant. |
| AID-1 | Tous | Windows | (**A2-23**) Aide ▸ Raccourcis. | Sections « Grille et cues » (1 à 8, 0, ← / →, Échap) et « Uniformiser » (Entrée, I, F, Espace, ↑ / ↓, Ctrl + Z). |

### Fonctions

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| TRA-11 | Tous | Windows | (**C203**) Clé et bibliothèque de l'ordinateur branchées : Accueil. Cliquer la tuile « Transférer et synchroniser », revenir, puis le bouton « Transférer et synchroniser » de la carte de la clé. | Tuile présente dans « Que voulez-vous faire ? » ; nom partout (menu, titre, tuile, bouton) ; sous-titre « Gardez la même musique… » ; depuis la tuile ou le menu : sens unique ; depuis la carte : « Synchroniser les deux », la clé d'un côté et l'ordinateur de l'autre. |
| TRA-12 | Tous | Windows | (**A7-5**) Transférer vers une clé exFAT : revue. | « ≈ x nécessaires » un peu au-dessus de la taille des fichiers (arrondi aux blocs de la clé, analyses comprises) ; refus clair si la place manque. |
| TAC-1 | Tous | Windows | (**C210**) Bibliothèque ▸ playlist ▸ Copier vers une clé ; puis « Prêt pour le set ? ». | Une ligne « Copier vers » dans le volet gauche (progression, ⏹ arrête après le son en cours), au lieu d'un message réécrit à chaque son ; « Prêt pour le set ? » apparaît aussi dans le volet pendant le contrôle. |
| ESP-1 | Tous | Windows | (**C200**) Paramètres ▸ Bibliothèques ▸ Espace occupé. | En tête : « DJSync sur cet ordinateur : x au total », puis le détail (application, caches, sauvegardes, réglages et journaux, sons sur l'ordinateur). |
| FUS-1 | Tous | Windows | (**C199**) Diagnostic ▸ Doublons : un groupe dont les versions sont dans des playlists différentes et ont des hot cues ; changer la version gardée, la version des cues, le titre. | « Ce que la fusion va faire » : playlists « = » gardées et « + » où la version gardée prend la place ; cues « = / + / − » ; versions retirées en rouge ; mis à jour à chaque choix. |
| FUS-2 | Tous | Windows | (**C199**) Diagnostic ▸ Fichiers introuvables ▸ Fusionner avec une version présente. | La confirmation montre le même aperçu (fichier introuvable : « retiré de la bibliothèque », pas « effacé »). |

### Clé : écriture sûre et éjection (A7-4, repris de Sleeve)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| CLE-7 | Tous | Windows | (**A7-4**) Ouvrir la clé dans l'Explorateur (une fenêtre sur la clé), puis Éjecter depuis DJSync ; refaire après avoir fermé la fenêtre. | 1er essai : DJSync dit que la clé est fermée et peut être débranchée, et nomme ce qui la tient si Windows le dit (« explorer.exe ») ; 2e essai : « éjectée » et la clé disparaît de « Retirer le périphérique en toute sécurité ». Journal : « Drive … ejected (Plug and Play request) ». |
| CLE-8 | Testeur Mac | macOS | (**A7-4**) Clé **exFAT** : télécharger 5 sons, modifier une grille, Éjecter ; ouvrir la clé dans Rekordbox puis sur platine. | Aucune erreur à l'écriture ; tout est sur la clé. |
| PDB-4 | Testeur platines | Platines | (**A7-4**) Après CLE-8 (ou une clé écrite sous Windows) : ancienne platine. | export.pdb lu comme avant (contenu inchangé : seul le vidage sur disque change). |

### Code (rien de visible)

A3-2 (code mort retiré), A3-3 (identité de la bibliothèque, `is_offline_error` dans core, analyse passée en paramètre
au transfert), A3-4 (≈ 160 erreurs avalées notées au journal ; cues ou grille illisibles montrées comme
« différentes » dans le transfert), A3-7 (boucle d'analyse, grille et reprise d'analyse communes à la clé et à
master.db, `db/analysis_flow.py`), A3-9 (tests du plan d'export.pdb, code non touché) : couverts par la suite complète
et `tests/test_v143_rc2.py`. Signe d'une régression : analyse, grille ou transfert qui se comporte différemment entre
la clé et l'ordinateur.

### Reporté au lot 3

A7-3 (formes d'onde calculées comme Rekordbox, portage des formules de Sleeve, à valider sur l'échantillon) ; A1-6,
A1-7 ; liste longue de `00-etat-du-projet.md`.

## rc.1, lot 3 — fiches sans action de l'auteur

Fiches : A7-3 (formes d'onde comme Rekordbox, repris de Sleeve), A1-6 (plusieurs cœurs), A1-7 (un seul décodage),
C185, B89, C53, S05, C109, C176, C72, C94. Tests automatiques : `tests/test_v143_rc3.py`.
Sautées (attendent l'auteur) : B105, C114, A07 ; C83 et C156 : spec courte `claude/spec-c83-c156.md` à valider ;
C16, C69, A01 : mesures sur le PC portable.

### Analyse

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ODE-4 | Tous | Windows | (**A7-3**) Analyser dans DJSync 10 sons de l'échantillon « Échantillon DJSync » (déjà analysés par Rekordbox), sur une clé ; ouvrir la clé dans Rekordbox, comparer chaque son avec sa version analysée par Rekordbox (Bleu, RGB, 3 bandes ; forme d'onde zoomée et aperçu). | Formes d'onde semblables à celles de Rekordbox (hauteurs, couleurs, aperçu bleu) ; en 1.4.2, elles étaient nettement différentes. |
| ODE-5 | Testeur platines | Platines | (**A7-3**) Même clé sur les platines : forme d'onde du son chargé et aperçu, en Bleu, RGB et 3 bandes. | Comme un son analysé par Rekordbox ; aucune forme d'onde vide ou décalée. |
| ANA-6 | Tous | Windows | (**A1-6**) Analyser 30 sons non analysés, mode léger coupé ; regarder le Gestionnaire des tâches et la durée par son au journal ; refaire en mode léger. | Plusieurs processus DJSync (cœurs − 1, 4 au plus) pendant l'analyse, puis plus rien une minute après ; analyse nettement plus rapide (journal : « Analysis on N processes ») ; en mode léger, un seul processus comme avant. Résultats (BPM, tonalité, grille) identiques. |
| ANA-7 | Testeur Mac | macOS | (**A1-6**) Analyser 10 sons. | Pas de second DJSync dans le Dock, analyse faite ; aucune erreur. |
| ANA-8 | Tous | Windows | (**A1-7**) Bibliothèque ▸ colonne Vraie qualité sur 10 sons non encore mesurés, puis analyse. | Même vraie qualité qu'en 1.4.2 pour un son déjà mesuré en 1.4.2 (registre) ; mesure faite pendant l'analyse, sans second décodage. |

### Import et recherche

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| IMP-16 | Tous | Windows | (**C185**) Importer une playlist YouTube de plus de 600 titres, puis une playlist Deezer de 1 500 titres. | Les 200 premiers s'affichent, puis la suite se charge seule (« Chargement de la playlist… n sons sur N »), sans bouton ; le tableau défile ; arrêt à 2 000 avec « Seuls les 2 000 premiers… ». |
| IMP-17 | Tous | Windows | (**C94**) Importer une playlist publique **Apple Music**, une **Tidal**, une **Amazon Music**. | Liste lue (titre, artiste, durée), puis correspondance YouTube Music comme pour Spotify ; pour Amazon, si la page ne donne pas la liste : message clair (playlist publique, lien de partage). Noter le service qui ne marche pas. |
| SRC-14 | Tous | Windows | (**B89**) Recherche Haute qualité : « jul », puis un album connu sur Audius. | archive.org : plus de bulletins radio ni de podcasts, seulement de la musique dont le titre ou l'artiste contient les mots ; albums d'archive.org et d'Audius en lignes d'album (titres numérotés). |

### Fichiers, lecture, apparence

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| TAG-1 | Tous | Windows | (**S05**) Paramètres ▸ Analyse ▸ cocher « Écrire le BPM et la tonalité dans les fichiers audio » ; analyser 3 sons (MP3, M4A, FLAC) ; ouvrir leurs propriétés (Explorateur ou un autre logiciel). | BPM et tonalité dans les tags ; le son se lit toujours ; Rekordbox et les platines lisent la clé comme avant (taille du fichier mise à jour). Réglage décoché : fichiers non modifiés. |
| LEC-6 | Tous | Windows | (**C109**) Analyser un son très fort et un son calme, les écouter l'un après l'autre dans DJSync ; décocher « Même volume pour tous les sons » et réécouter. | Coché : volume proche entre les deux, jamais de saturation ; décoché : comme avant. Sur l'ordinateur : Rekordbox montre un Auto Gain pour les sons analysés par DJSync (valeur à comparer avec celle de Rekordbox sur l'échantillon). |
| AFF-8 | Tous | Windows | (**C53**) Paramètres ▸ Apparence ▸ Fond : Haut contraste, Lumineux, OLED, puis Sombre ; parcourir Accueil, Bibliothèque, Rechercher, Grille et cues. | Changement immédiat ; textes et couleur d'accent lisibles partout (le Lumineux assombrit l'accent si besoin) ; noter les zones restées sombres ou illisibles. |

### Application

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| MAJ-6 | Tous | Windows | (**C72**) Depuis la 1.4.3-rc.1, mettre à jour vers la rc suivante depuis Paramètres. | Téléchargement bien plus court que la taille de DJSync.exe (journal : « Delta update: x MB downloaded instead of y MB ») ; DJSync redémarre dans la nouvelle version. Depuis une version d'avant la 1.4.3 : téléchargement complet comme avant. |
| ESP-6 | Tous | Windows | (**C176**) Taille de DJSync.exe et du dossier `.djsync\app` après extraction, comparées à la 1.4.2. | Plus petit (modules jamais utilisés retirés) ; tout fonctionne (recherche, téléchargement YouTube, pochettes). Détail dans l'annotation « App size (C176) » du build. |
| CLE-9 | Tous | Windows | Après ANA-6 et TAG-1 : la clé dans Rekordbox puis sur platines. | Tous les sons se lisent ; grilles, cues et playlists inchangés. |

## rc.1, lot 4 — clé illisible, mêmes règles pour tous les sons, « Prêt pour le set ? », vues de colonnes

Fiches : B105, A07 (avec C156), C213, C214. Décisions : `claude/spec-c83-c156.md`. Tests automatiques :
`tests/test_v143_lot4.py`. Sautées (attendent l'auteur) : C16, C69, A01 (accès au PC portable).

Inventaire A07 (protections « son de Rekordbox » sur l'ordinateur) : **suppression** : remplacée (corbeille du
système, réglage de protection désactivé par défaut) ; **réanalyse** : déjà un choix et une confirmation (D20,
C131), inchangée ; **grille** : déjà une confirmation « Cette grille vient de Rekordbox » avant d'enregistrer,
inchangée ; **cues** : aucune protection ; **Uniformiser** : propositions décochées (orange) pour un son pas
téléchargé par DJSync (S06) : c'est déjà un avertissement, inchangé. La fusion de doublons (Doublons, Introuvables)
suit la même règle que « Supprimer ».

### Clé et données

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| CLE-10 | Auteur | Windows | (**B105**) Une clé passée par Rekordbox sur le Mac et retirée sans éjecter (cas de CLE-1), ou la clé du 14/11 si elle est encore dans cet état ; l'ouvrir dans DJSync, puis envoyer le journal. | La clé s'ouvre, rien n'est perdu (sons et playlists ajoutés en dernier sur le Mac présents). Journal : « Drive database open failed: … (code …) », « reopening once in exclusive mode », « repaired in exclusive mode ». Aucun fichier supprimé dans PIONEER/rekordbox. |
| CLE-11 | Auteur | Windows | (**B105**) Même clé, Rekordbox ouvert sur cette clé (Appareil), puis ouvrir la clé dans DJSync. | Message clair qui nomme la clé (« fermez Rekordbox, vérifiez que la clé n'est pas en lecture seule ») ; rien de changé. Rekordbox fermé : la clé s'ouvre. |
| CLE-12 | Testeur platines | Platines | (**B105**) Après CLE-10 : la clé sur les platines puis dans Rekordbox. | Tout se lit comme avant. |

### Supprimer (ordinateur et clé)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| SUP-1 | Tous | Windows | (**A07**, **C156**) Bibliothèque de l'ordinateur, Rekordbox fermé : supprimer un son que DJSync n'a **pas** téléchargé (ajouté par Rekordbox). | Bouton « Supprimer de l'ordinateur » ; confirmation : le fichier va dans la corbeille. Après : son retiré de Rekordbox, fichier dans la Corbeille de Windows (« Restaurer » le remet à sa place) ; message « 1 fichier mis à la corbeille ». |
| SUP-2 | Tous | Windows | (**C156**) Paramètres ▸ Bibliothèques ▸ cocher « Protéger les sons qui ne viennent pas de DJSync », refaire SUP-1 avec un autre son. | Bouton « Retirer de la collection Rekordbox » ; le fichier reste où il est. Un son téléchargé par DJSync va toujours à la corbeille. |
| SUP-3 | Tous | Windows | (**C156**) Deux entrées Rekordbox qui pointent vers le même fichier (même chemin) : en supprimer une. | Le fichier reste (encore utilisé par l'autre son). |
| SUP-4 | Tous | Windows | (**A07**) Supprimer une playlist (clé, puis ordinateur) : garder « La playlist seule » ; puis une autre avec « La playlist et ses sons ». | Seule : les sons restent dans « Tous les sons ». Avec ses sons : sons supprimés (clé : effacés ; ordinateur : corbeille) ; la confirmation dit combien sont aussi dans d'autres playlists. Pour un dossier : les sons de toutes ses playlists (listes intelligentes exclues). |
| SUP-5 | Tous | Windows | (**A07**, à la place de C83) Supprimer des sons dont certains ont été importés depuis des fichiers (pas de lien YouTube ou SoundCloud). | Ligne rouge dans la confirmation : « n sons n'ont pas de lien d'origine : DJSync ne pourra pas les retélécharger (titres…) ». |
| SUP-6 | Testeur Mac | macOS | (**C156**) SUP-1 sur le Mac. | Fichier dans la Corbeille du Finder (« Remettre » fonctionne). |

### « Prêt pour le set ? » et Bibliothèque

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| SET-6 | Tous | Windows | (**C213**) Clé avec des sons analysés dont certaines grilles ont été marquées « Grille juste » ; ouvrir « Prêt pour le set ? ». | Ligne orange « Grilles : n grilles pas encore vérifiées » juste après Analyse ; le verdict ne change pas à cause d'elle (reste « Prête » si tout le reste est vert). « Voir » ouvre la Bibliothèque sur ces sons seuls (bandeau, ✕ pour tout revoir), vue « Préparer un set » avec la colonne Analyse. |
| VUE-1 | Tous | Windows | (**C214**) Bibliothèque ▸ « Vue : Découvrir / ranger ▾ » : essayer Préparer un set, Mixer, Vérifier la qualité, Tout voir. | Les colonnes changent d'un coup ; largeurs et ordre gardés. Après mise à jour, les colonnes choisies avant restent (vue « Mes colonnes » si elles ne correspondent à aucune vue). |
| VUE-2 | Tous | Windows | (**C214**) Dans une vue, cocher une colonne de plus (bouton Colonnes ou clic droit sur l'en-tête). | « (modifiée) » avec Enregistrer et Revenir ; Revenir remet la vue ; Enregistrer la garde (vue d'origine : « Rétablir la vue d'origine » dans le menu). |
| VUE-3 | Tous | Windows | (**C214**) « Nouvelle vue… », la nommer ; la renommer puis la supprimer. Choisir une vue différente pour deux playlists, passer de l'une à l'autre, relancer DJSync. | Chaque playlist retrouve sa vue ; textes en anglais et en français. |


## rc.1, lot 5 — mesures sur le PC fixe : tempo qui change, volume calé sur Rekordbox

Fiches : **C69** (tempo qui change), **C109** (référence de volume). Mesures : `claude/mesures-1.4.3.md` (docs du projet).

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ANA-9 | Auteur | Windows | (**C69**) Analyser la playlist « testlivesetbeatswitchetcccc » (19 sons) avec DJSync, puis Bibliothèque ▸ Listes automatiques ▸ « Tempo qui change ». | Une douzaine de sons listés (les deux sets, les beatswitchs, la plupart des lives) ; pastille bleue sur le BPM ; bulle « Version live détectée · grille variable », « Beatswitch détecté (122 → 140 BPM) · grille fixe : à vérifier dans Grille et cues »… Les lives sans batterie nette ne sont pas signalés (rien d'affirmé). |
| ANA-10 | Auteur | Windows | (**C69**) Analyser des sons de club à tempo fixe (house, techno, hardstyle). | Aucun dans « Tempo qui change » ; grille fixe partout (« tempo constant » dans Grille et cues). |
| GRI-8 | Auteur | Windows | (**C69**) Grille et cues sur un son signalé « grille variable » (live, accélération, set), puis sur un beatswitch. | La ligne d'infos dit le type détecté (« Version live détectée ») ; la grille variable suit les temps, sur le temps et pas le contretemps. Beatswitch : grille fixe, juste sur un des deux passages (une grille par passage : C16). |
| LEC-7 | Auteur | Windows | (**C109**) Bibliothèque de l'ordinateur : analyser avec DJSync un son déjà analysé par Rekordbox (Auto Gain), comparer le gain dans Rekordbox avant et après. | Écart de 1 dB au plus (référence −10,7 LUFS, calée sur 147 sons de Rekordbox). |

## rc.1, lot 6 — grille par passage, qualité lue dans l'en-tête

Fiches : **C16** (sons au tempo qui change : grille par passage, validation, grille fixe, réglage), **A04** (encodeur lu dans l'en-tête, confiance, spectrogramme). Tests automatiques : `tests/test_v143_lot6.py` (beatswitchs synthétiques : chaque temps à moins de 5 ms).

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ANA-11 | Auteur | Windows | (**C16**) Analyser à nouveau les beatswitchs de la playlist « testlivesetbeatswitchetcccc », puis Grille et cues sur chacun. | Bulle du BPM : « Beatswitch détecté (122 → 140 BPM) · grille par passage » ; dans Grille et cues, « tempo par passage », un trait orange « 122.0 → 140.0 » au changement, et la grille juste sur les deux passages (1er temps de mesure au changement). |
| GRI-9 | Auteur | Windows | (**C16**) Sur un son signalé : lire le bandeau orange, cliquer « Grille fixe », enregistrer ; puis « Analyser à nouveau ». Revenir et cliquer « Grille par passage », enregistrer. | Bandeau « … : vérifiez la grille passage par passage… » ; « Grille fixe » donne un seul tempo calé sur le temps sélectionné, et la réanalyse garde la grille fixe ; « Grille par passage » rend la grille de l'analyse. |
| GRI-10 | Auteur | Windows | (**C16**) Liste « Tempo qui change » : cliquer « Grille juste » dans Grille et cues pour un des sons. | Avant : pastille orange sur le BPM, colonne Analyse « Tempo qui change : à vérifier », sous-titre « N à valider ». Après : pastille bleue, « Grille vérifiée », bandeau vert « grille vérifiée ». |
| PAR-14 | Auteur | Windows | (**C16**) Paramètres ▸ Analyse ▸ « Grille des sons dont le tempo change » : « Jamais », puis analyser à nouveau un live et un beatswitch ; remettre « Automatique ». | Avec « Jamais » : grille fixe pour les deux (« tempo constant »), sons toujours signalés dans « Tempo qui change » (bulle « grille fixe : à vérifier »). |
| PLA-7 | Testeur platines | Platines | (**C16**) Clé avec un beatswitch analysé par DJSync (grille par passage) : charger le son, laisser passer le changement, synchroniser avec un autre son. | Le BPM affiché change au passage ; la grille reste sur les temps après le changement ; la synchro suit le nouveau tempo. |
| QUA-9 | Auteur | Windows | (**A04**) Mauvaise qualité ▸ « Recalculer la qualité supposée », puis passer la souris sur la colonne « Qualité réelle » d'un MP3 encodé par LAME et d'un m4a. | « ≈ 320 kbps (sûr) » quand le spectre monte jusqu'au passe-bas réglé par LAME ; « (probable) » sinon ; bulle : « spectre coupé vers … kHz · encodé par LAME 3.100 (CBR, 320 kbps, passe-bas 20.5 kHz) · … ». Un faux 320 (MP3 ré-encodé depuis un 128) : « ≈ 128 kbps (sûr) ». |
| QUA-10 | Auteur | Windows, macOS | (**A04**) Clic droit sur un son ▸ « Spectre ». | Fenêtre avec le spectrogramme du son entier (noir → bleu → rouge → jaune), graduations en kHz, pointillés à 16, 19 et 20 kHz, temps en bas ; la qualité et ses indices en haut. Fichier absent : message clair. |

## rc.2 — corrections après les tests de la rc.1

Fiches : **A01** (tonalité, profils à moitié appris sur Rekordbox), **B123**, **C224**, **C206** (IMP-2 KO), **C207** (REC-11 KO,
1.4.2), **C212** (GRI-7 KO, 1.4.2), **B120** (avec B116, B121), **B117**, **B119**, **B122**, **B124**, **B114**, **C217**, **C218**,
**C228**. Spec : `claude/spec-1.4.3-rc2.md` (docs du projet). Tests automatiques : `tests/test_v143_rc2_fiches.py`.
Sautées (mesure sur la tour impossible depuis la session) : **B115**, **B118** → 1.4.4.

### Bibliothèque

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| SUP-7 | Tous | Windows | (**B120**) Bibliothèque de l'ordinateur (la plus grosse possible), Rekordbox fermé : supprimer 1 son, puis 10 ; retirer 5 sons d'une playlist, un par un. Envoyer le journal. | Plus de gel : les lignes disparaissent tout de suite ; message « n sons supprimés · n fichiers mis à la corbeille » un peu après. Journal : « master.db backed up in x s » une fois pour toute la rafale (pas à chaque suppression). Les fichiers sont dans la corbeille. |
| SUP-8 | Tous | Windows | (**B121**) Playlist triée par BPM, défilée vers le bas, un son choisi : retirer un autre son de la playlist. | La playlist n'est pas rechargée : tri, défilement et sélection restent ; « # » renuméroté ; « Annuler » remet le son. |
| SUP-9 | Auteur | Windows | (**B120**) Supprimer un son, ouvrir Rekordbox, y changer une playlist, le fermer, puis supprimer un autre son dans DJSync dans la minute. | Deux copies `master-…` dans le dossier des sauvegardes (l'écriture de Rekordbox entre les deux relance une copie). |
| VUE-4 | Tous | Windows | (**C218**) Bibliothèque : le bouton de la vue est juste à droite de « Colonnes » et n'affiche que son nom (« Essentiel ▾ »). Essayer les 4 vues. | Essentiel : #, Titre, Artiste, BPM, Tonalité, Durée, Playlists, Ajouté le. Préparer un set : … Analyse, Cues, Note, Couleur, My Tags, Dernière lecture, Playlists. Qualité et fichiers : … Qualité supposée, Format, Débit, Fréquence, Source, Doublon, Taille, Chemin. Tout voir : toutes, dans cet ordre puis le reste. |
| VUE-5 | Tous | Windows | (**C218**) Après la mise à jour : une playlist qui était sur « Mixer », une sur « Découvrir / ranger » modifiée (Enregistrer en rc.1). Puis glisser une colonne à une autre place. | « Mixer » devient « Préparer un set » ; la vue modifiée est gardée telle quelle sous le nom « Découvrir / ranger » (vue personnelle). Colonne déplacée : « (modifiée) » ; Revenir remet l'ordre, Enregistrer le garde. |
| LIB-4 | Tous | Windows | (**C224**) Barre de la Bibliothèque : « Importer » ; menu ☰ ▸ « Harmonique » (un son choisi), puis ☰ de nouveau. | Plus de bouton « Harmonique » dans la barre ; dans ☰ il active le filtre (bandeau), coché « ✓ Harmonique » tant qu'il est actif ; un nouveau clic l'enlève. |
| LIB-5 | Tous | Windows | (**C217**) Accueil avec la clé et l'ordinateur ; puis Bibliothèque ▸ ☰, et clic droit sur une playlist. | Plus de bouton « Transférer et synchroniser » sur les cartes (la tuile reste) ; l'entrée est dans ☰ et dans le menu de la playlist (playlist précochée). |
| LIB-6 | Tous | Windows | (**B114**) Choisir une playlist dans le volet de gauche (un dossier avec flèche), une ligne de la fenêtre « Ajouter à une playlist », un filtre. | Un surlignage rectangulaire d'un seul tenant sur toute la ligne, zone de la flèche comprise ; plus de morceaux arrondis. Les sections des Paramètres gardent leurs coins arrondis. |
| QUA-11 | Auteur | Windows | (**B123**) Les MP3 vus à 32 kbps (Obito, STUNTMEN, Prêt à partir, Heads Will Roll) : Mauvaise qualité ▸ « Recalculer la qualité supposée », puis colonnes Débit et Qualité supposée. Importer un de ces fichiers à nouveau. | Débit ≈ 117 à 131 kbps (débit moyen) ; « ≈ 128 kbps » en orange comme les vrais 128 kbps, plus en rouge. Un son importé ensuite a d'emblée le bon débit. |

### Fenêtres et pages

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| IMP-18 | Tous | Windows | (**C206**, IMP-2 KO) Lien ou playlist ▸ playlist Spotify de plus de 100 titres, fenêtre de largeur moyenne. | Le message Spotify est sur sa propre ligne au-dessus de « Correspondance » et « Coller une liste… », sur plusieurs lignes si besoin, jamais coupé. |
| REC-12 | Tous | Windows | (**C207**, REC-11 KO) Téléchargements et analyse : replier Analyse, puis Téléchargements, puis déplier Téléchargements, puis Analyse. | Chaque panneau garde son contenu juste sous son en-tête ; Téléchargements toujours au-dessus ; tout replié : les deux en-têtes en haut, rien dessous. |
| GRI-11 | Tous | Windows | (**C212**, GRI-7 KO) Grille et cues, fenêtre étroite (≈ 700 px) puis basse. | Une barre de défilement horizontale (et verticale si basse) apparaît ; rien ne se superpose ni n'est coupé. |
| GRI-12 | Tous | Windows | (**B117**) Grille et cues, forme d'onde Bleu puis RGB, zoom au maximum. | Contour lisse comme les 3 bandes, plus d'escalier ni de pixels ; mêmes couleurs ; défilement fluide. |
| SUP-10 | Tous | Windows | (**B119**) Supprimer une playlist (choix « La playlist seule » / « La playlist et ses sons »), en anglais puis en français. | Fenêtre assez large ; les textes des choix passent à la ligne au besoin, rien de coupé. |
| FUS-3 | Tous | Windows | (**B122**) Doublons pendant la vérification du son (beaucoup de groupes), un groupe choisi en bas de la liste. | La liste ne bouge pas (ni largeur, ni défilement) quand les compteurs changent. |
| FUS-4 | Tous | Windows | (**B124**) Doublons ▸ un groupe ▸ « Ce que la fusion va faire », dans les 4 thèmes. | Lignes « = » lisibles (couleur du texte) ; une ligne longue finit par « … », texte entier dans la bulle. |
| ESP-7 | Tous | Windows | (**C228**, ESP-1) Paramètres ▸ Bibliothèques ▸ Espace. | « DJSync sur cet ordinateur » ne compte plus les sons téléchargés ; ligne à part « Sons téléchargés par DJSync sur cet ordinateur : … ». |

### Analyse

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ANA-12 | Auteur | Windows | (**A01**) Analyser à nouveau la playlist d'échantillon (sons déjà analysés par Rekordbox), puis `python -m djsync.analysis --compare local --playlist "<nom>" --csv x.csv`. | Accord sur la tonalité au moins égal à celui de la rc.1 ; pas plus de tonalités mineures données à tort. |

## rc.3 — gel de l'exe à l'ouverture et après une suppression

Fiche : **B126** (régression de la rc.1, exe seulement). Cause (relevé py-spy du 21/11) : la colonne « Doublon »,
masquée par défaut, relançait la recherche des doublons à chaque chargement de la bibliothèque, et rapidfuzz tournait
dans l'exe avec son code Python pur (partie compilée absente). Correctifs : A (partie compilée incluse dans l'exe,
vérifiée au démarrage et par l'autotest du build) et D (doublons calculés seulement si la colonne Doublon est affichée).
Tests automatiques : `tests/test_v143_rc3_b126.py`.

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| GEL-1 | Auteur | Windows | (**B126**) Exe rc.3 : lancer DJSync, ouvrir la bibliothèque de l'ordinateur, passer tout de suite la souris sur la liste ; puis supprimer 3 sons et repasser la souris. Envoyer le journal. | Le surlignage suit la souris dès l'ouverture et après la suppression (plus de vingtaine de secondes de lenteur). Journal : « Fuzzy matching (rapidfuzz): compiled » au démarrage ; plus de « Slow drive check » de plusieurs secondes. |
| GEL-2 | Tous | Windows | (**B126**) Bibliothèque ▸ Colonnes ▸ cocher « Doublon ». | La colonne se remplit en une ou deux secondes (⧉ sur les sons qui ont un doublon) ; un clic sur ⧉ ouvre Doublons. |
