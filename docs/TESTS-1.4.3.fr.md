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
| IMP-2 | Tous | Windows | (**C206**) Lien ou playlist ▸ une playlist Spotify publique de plus de 100 titres. | « Spotify ne donne que les 100 premiers morceaux sur n. » et la marche à suivre pour le reste (découper la playlist, ou « Coller une liste… »). |

### Reporté à la rc.2

A1-9, A3-2, A3-3, A3-4, A3-7, A3-8, A3-9, A2-18 à A2-23, B103, A7-3 à A7-5, C199, C200, C203, C210. Sautées et signalées : B105 (spec non validée), C114 (échantillon de cues manquant), A07 (à décider), A1-11 (reportée).
