# Scénarios de test — DJSync 1.4.3

Numérotation : thème en 3 lettres + n° (voir `revues/numerotation-tests.md`) ; dans le suivi : « 143 · REC-1 ».
Règle : un test OK sous Windows est validé ; Mac et Linux seulement pour un point qui leur est propre.

## rc.1 — rapidité et sûreté des données

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

### Reporté à la rc.2

Fait en rc.2 (voir plus bas), sauf A7-3 (reporté à la rc.3). Sautées et signalées : B105 (spec non validée), C114
(échantillon de cues manquant), A07 (à décider), A1-11 (reportée).

## rc.2 — reste de la 1.4.3

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

### Reporté à la rc.3

A7-3 (formes d'onde calculées comme Rekordbox, portage des formules de Sleeve, à valider sur l'échantillon) ; A1-6,
A1-7 ; liste longue de `00-etat-du-projet.md`.
