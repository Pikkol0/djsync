# DJSync V0.2.0 — Interface, analyse à la demande, doublons, grille

## Ce qui change pour l'utilisateur

| | Avant (V0.1.6) | V0.2.0 |
|---|---|---|
| Langue | français | **anglais par défaut**, français dans Paramètres ▸ Apparence (appliqué sans redémarrer) |
| Fenêtre | minimum 1020 × 640, zoom = fenêtre géante | minimum **760 × 500** ; l'interface suit la taille de la fenêtre (réf. 1280 × 800, × 0,85 à × 1,45) **et** le zoom 80-200 % (curseur en direct) |
| Onglets | 5 | **Accueil**, Recherche, Bibliothèque, Téléchargements récents, Import URL, Paramètres (Ctrl+1…6) |
| Barre latérale | fixe | icônes seules quand la fenêtre est étroite (réglable) ; remplissage de la clé |
| Recherche | bouton + Entrée | **pendant la frappe** (0,45 s de pause) ; Filtres / Rechercher en icônes ; **↓ en bout de ligne** = télécharger ce son |
| Bibliothèque | « Collection » | **« Tous les titres »**, nombre de sons, durée totale, dernier ajout ; **pastille Camelot colorée** (tri par clé) ; **glisser des sons sur une playlist** ; **filtre Harmonique** ; dossiers |
| Lecteur | lecture / stop | **Précédent / Suivant**, enchaînement automatique, **tonalité + BPM**, **mini forme d'onde** cliquable |
| Analyse | automatique à chaque ajout | **à la demande** (menu Outils, Accueil, Paramètres) ; option « Analyser chaque titre à son téléchargement » (désactivée par défaut) |
| Grille de temps | — | **éditeur** : décaler (±1 / ±10 ms), choisir le 1er temps, imposer le BPM, écouter, enregistrer |
| Doublons | — | **outil Doublons** : choisir la version gardée, corriger titre / artiste, playlists fusionnées |
| Aide | — | bouton **Raccourcis et aide** (F1) |

## Raccourcis
Ctrl+K omnibar · Ctrl+1…6 onglets · Ctrl+F champ de filtre · Espace lecture/pause · Ctrl+→ / Ctrl+← suivant /
précédent · Entrée écouter · Suppr supprimer (Bibliothèque) · Ctrl+A tout sélectionner · Ctrl+, Paramètres · F1 aide.

## Grille de temps : ce qui est écrit
* `ANLZ0000.DAT` : la balise **PQTZ** est remplacée, toutes les autres balises sont recopiées à l'octet près ;
* `.EXT` / `.2EX` : la balise **PQT2** (grille étendue des platines récentes) est retirée si elle existe, pour
  que les platines ne gardent pas l'ancienne grille ; rien d'autre ne change ;
* `exportLibrary.db` : `bpmx100` (médiane des tempos), `analysisDataUpdateCount` + 1 ;
* `export.pdb` : la ligne du son est reconstruite **avec le même id** (seul le BPM change, tous les autres octets
  de la ligne sont conservés) ;
* les fichiers d'origine sont copiés dans `DJSync_Backups/anlz/<date>-<id>/` avant toute écriture ; en cas
  d'échec ils sont restaurés.
Un son analysé par Rekordbox peut être corrigé (confirmation demandée) ; un nouvel export Rekordbox écrasera la
correction.

## Doublons : règles de regroupement
Titres normalisés (accents, casse, « (Clip Officiel) », « [Lyrics] », « feat. … », ponctuation retirés) ;
« Artiste - Titre » découpé quand l'artiste est vide/inconnu ou identique à la partie gauche ; suffixes de chaîne
(« VEVO », « - Topic ») ignorés. Deux sons sont regroupés si les titres se ressemblent à ≥ 90 %, si les artistes
sont compatibles (un artiste inconnu est compatible avec tout) et si les durées diffèrent de moins de 90 s (une
version longue reste à part). Version proposée par défaut : analysée > avec pochette > avec artiste > titre propre.
Le son gardé **prend la place** des doublons dans chaque playlist (même position).

## Architecture (point 16 : découpage)
* `djsync/db/usb_library.py` (1 344 lignes) → `djsync/db/library/` : `base.py` (connexion, transactions,
  sauvegardes), `pdb_mirror.py`, `tracks.py`, `playlists.py`, `ingest.py` (ajout + analyse),
  `metadata.py` (métadonnées, doublons, statistiques, grille). `usb_library.py` assemble la classe et garde
  les noms publics.
* `djsync/ui/controller.py` → + `ui/ctrl/library_ops.py`, `ui/ctrl/downloads.py`, `ui/ctrl/playback.py`
  (**file d'écoute dans le contrôleur**).
* Nouveaux modules d'interface : `icons.py` (icônes vectorielles dessinées en code), `logo.py`,
  `views/home_view.py`, `help_dialog.py`, `analysis_dialog.py`, `duplicates_dialog.py`, `grid_editor.py`.
* `analysis/grid.py` (édition de grille, fonctions pures), `analysis/anlz.py` (relecture PQTZ / formes d'onde,
  réécriture sans perte), `db/pdb/rows.patch_track` + `PdbDatabase.update_track`.

## Robustesse
* **Ramasse-miettes** : Python pouvait libérer des objets Tk (polices, images) depuis un thread de
  téléchargement, ce qui bloquait le téléchargement (constaté en test). Le ramassage automatique est désormais
  fait dans le thread de l'interface (`ui/runner.py`) ; polices et icônes sont partagées.
* Les erreurs fréquentes (base verrouillée, nom de playlist en double…) sont traduites ; le détail technique des
  erreurs rares reste en français (messages de la couche base de données).

## Outils de développement (non livrés dans l'exe)
* `tools/ui_screenshots.py` : captures de chaque onglet à plusieurs tailles, en anglais ou français, sur une
  fausse clé de démonstration (`--dialogs` : Aide, Doublons, Analyse, Grille, forme d'onde du lecteur).
* `tools/export_logos.py` : logo dans les 20 couleurs (`docs/logos/`) + icône de l'exe (`packaging/djsync.ico`).

## Tests
`python -m pytest -q` (sans écran : les tests d'interface sont ignorés) ; `xvfb-run -a python -m pytest -q`
sous Linux ou simplement `python -m pytest -q` sous Windows pour tout lancer. Nouveaux : `test_v020_library.py`
(base + export.pdb), `test_ui_v020.py` (interface), `test_i18n_ui.py` (aucun texte français en dur dans
`djsync/ui`, clés présentes dans les deux langues avec les mêmes paramètres).

## Non fait / limites
* Analyse et grille : toujours pas de mesure sur m4a (décalage d'amorçage AAC, voir `analyse_audio.md`).
* Pas de « tap tempo » ni de métronome dans l'éditeur de grille.
* Le fichier audio n'est pas renommé quand on corrige titre / artiste (seules les bases changent).
* Testé sous Linux (Xvfb) ; à valider sous Windows (polices Segoe UI, DPI 125-150 %).
