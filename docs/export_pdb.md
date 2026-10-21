# export.pdb (V1.1-A4) — état du module, calibré sur un export réel

## Ce que fait DJSync
À chaque écriture dans `exportLibrary.db` (ajout/suppression de son, playlists, ordre), la même
opération est appliquée à `PIONEER/rekordbox/export.pdb` **après** le commit de la base OneLibrary.
export.pdb n'est jamais créé ; il est chargé strictement, modifié en mémoire, contrôlé (relisible,
seules les pages touchées diffèrent), sauvegardé (`DJSync_Backups/export-*.pdb`), écrit via un
fichier temporaire puis remplacé atomiquement, relu. Au moindre écart avec le modèle : fichier
intact, ajout OneLibrary conservé, état « à rattraper ».

## Calibrage sur un vrai export Rekordbox (83 pages, 213 pistes, 4 playlists)
Le fichier réel est conservé dans `tests/data/real_export.pdb` (supprimable : les tests le sautent s'il manque).
Confirmé : en-tête et table des tables ; lignes de pistes (0x88 octets, 21 offsets de chaînes,
champs BPM/durée/type/chemin…), artistes, albums, arbre des playlists, contenu des playlists ;
chaînes ASCII courtes et UTF-16 ; pages « vides candidates » nulles.
Corrigé grâce à ce fichier (le premier modèle était faux sur ces points) :
* `next_unused_page` = nombre de pages + 1 : la dernière page vide candidate n'existe pas encore dans le fichier ;
* les compteurs à 0x18 forment un champ de 24 bits (13 bits d'emplacements + 11 bits de lignes valides) ;
* drapeau de page 0x24 (normale) / 0x34 (contient des lignes supprimées) ; marqueur « dernière ligne touchée »
  (u2 0x20 = 1, u2 0x22 = n° de ligne, bit dans le 2e mot du groupe d'index) ;
* `libre + utilisé + 0x28 + index = 4096` sur toutes les pages (désormais exigé) ;
* la page d'index d'une table ne liste PAS les pages de données (uniquement certaines pages avec lignes
  supprimées) : l'ancien code qui y enregistrait les nouvelles pages a été supprimé ;
* champs « inconnus » d'une piste : seuls `kuvo_public`/`autoload_hot_cues` (« ON ») sont repris d'une piste existante.

## V1.0.0 : agrandissement activé par défaut
Sans ajout de pages, une clé fraîchement exportée par Rekordbox est **pleine en une quinzaine de sons**
(table des albums d'abord : Rekordbox laisse peu de place dans chaque page). Validation faite sur le vrai
`export.pdb` d'une clé (236 pistes, 20 tables) :
* les 20 tables s'agrandissent (page vide candidate -> dernière page, nouvelle candidate réservée), contrôle
  d'intégrité passé à chaque fois ;
* 400 pistes (artistes et albums neufs) et 40 playlists ajoutées : fichier de 84 -> 116 pages, relu par
  DJSync **et par un lecteur indépendant** (`rekordcrate` 0.3.0, Rust : `dump-pdb`, `list-playlists`) qui
  retrouve les 400 pistes, artistes, albums et les 40 playlists ;
* Rekordbox 7 affiche la Device Library d'une clé modifiée par DJSync.
L'option reste désactivable (Paramètres ▸ Anciennes platines). Les réglages existants passent à « activé »
une fois (migration `settings_version` 1). À l'ouverture d'une clé, les sons et playlists absents
d'export.pdb (par exemple après une réécriture par Rekordbox ouvert en même temps) sont rajoutés.

Revalider avec rekordcrate : `cargo install rekordcrate --features cli`, puis
`rekordcrate dump-pdb PIONEER/rekordbox/export.pdb`.

## Ce qui reste NON validé
* Aucune platine (CDJ) n'a encore lu un fichier écrit par DJSync. Les tests (fichier réel + fichier synthétique)
  prouvent la cohérence structurelle, pas l'acceptation matérielle.
* Les pages touchées par une suppression passent en 0x34 mais DJSync n'ajoute pas ces pages à la page
  d'index (Rekordbox le fait). Sans effet probable en lecture ; non prouvé.
* Un champ 4 octets à 0x14 de chaque piste (valeur variable, signification inconnue) est repris du modèle.
* ~~Pistes ajoutées non analysées~~ — V1.1-A4 : BPM, tonalité (table 5, lignes `id, id, nom`),
  pochette (table 13, lignes `id, chemin`), `analyze_path`/`analyze_date` et `date_added` sont
  renseignés (voir docs/analyse_audio.md). Une tonalité ou une pochette qui ne tient plus dans sa
  table est simplement omise (la piste est ajoutée quand même). Une piste ajoutée SANS analyse par
  une version précédente est réécrite avec le même id quand on l'analyse.
* Marge réelle de ce fichier : tonalités ≈ 300 lignes, pochettes ≈ 80 ; dernière page des pistes ≈ 12 ajouts, des playlists ≈ 70 entrées ; au-delà,
  l'ajout de pages est nécessaire (Paramètres, désactivé par défaut) sinon la synchro passe à « à rattraper ».

## V0.2.4 : les mises à jour ne consomment plus la marge
Avant, chaque mise à jour d'une piste (analyse d'un son déjà présent, BPM corrigé dans l'éditeur de grille,
titre / artiste) ajoutait une NOUVELLE ligne et marquait l'ancienne supprimée (ses octets restent dans la
page) : analyser 7 sons pouvait remplir la dernière page et donner « table 0: last page full ».
* `PdbFile.replace_row` : réécriture **sur place** (même numéro, même offset) quand la ligne ne grandit pas
  (cas du BPM) ; sinon la page est **réorganisée** avec la nouvelle ligne au même numéro si elle tient ;
  sinon nouvelle ligne + suppression de l'ancienne (comme avant).
* `Page.compact` : avant de déclarer une table pleine, la place des lignes supprimées est récupérée (dernière
  page d'abord, puis les autres). Les lignes valides gardent leur numéro (l'index de la page ne change pas),
  seul leur offset change ; les emplacements supprimés gardent leur bit à 0.
* `index_shift` (u16 à +2 des pistes / artistes / albums) recalculé une fois la place de la ligne connue.
* Message clair quand la table est vraiment pleine : autoriser l'ajout de pages (Paramètres ▸ Anciennes
  platines) puis « Synchroniser maintenant ».
Non validé sur platine, comme le reste du module : une page compactée n'est pas une forme que Rekordbox
produit lui-même, mais les platines ne lisent que les offsets de l'index de la page.

## Validation à faire (clé de test)
1. `python -m djsync.db.pdb.check E:\` : doit afficher « Modèle reconnu ».
2. Ajouter 1 son avec DJSync, le charger sur la platine la plus ancienne.
3. Retour arrière : copier `DJSync_Backups/export-…-session.pdb` sur `export.pdb`.
