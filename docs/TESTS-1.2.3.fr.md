# Scénarios de test — DJSync 1.2.3

Petite version pour les retours de test : envoyer ses logs, rapports d'erreur, format de la clé. À faire
avec ceux de la 1.2.2 (`docs/TESTS-1.2.2.fr.md`) si ce n'est pas déjà fait.

## E. Nouveautés de la 1.2.3

### E1. Envoyer mes logs (onglet Retours)
| # | Étapes | Attendu |
|---|---|---|
| E1.1 | Clé ouverte ▸ Retours ▸ bloc **Envoyer mes logs** : écrire « test XDJ-1000 », laisser « Joindre les fichiers de la bibliothèque » coché, **Envoyer les logs** | « Logs envoyés. Merci ! ». E-mail reçu : « [DJSync 1.2.3] 1 Logs · test XDJ-1000 » (ou « 1 Remarque » si le script n'a pas été mis à jour), avec `djsync-log.txt`, `djsync-report.txt`, `rekordbox-library.zip`. |
| E1.2 | Ouvrir `djsync-report.txt` | Format de la clé (FAT32, exFAT…), espace, fichiers de PIONEER/rekordbox avec taille et date, contrôle d'export.pdb s'il existe. |
| E1.3 | Ouvrir `rekordbox-library.zip` | `PIONEER/rekordbox/exportLibrary.db`, `export.pdb`… ; pas de musique. |
| E1.4 | Décocher « Joindre les fichiers », envoyer | Pas de zip dans l'e-mail. |
| E1.5 | Bibliothèque de l'ordinateur ouverte, envoyer | Logs envoyés, sans zip (ce n'est pas une clé). |
| E1.6 | `djsync-log.txt` reçu | Aucun nom d'utilisateur ni chemin `C:\Users\…` / `/Users/…`. |

### E2. Rapports d'erreur
| # | Étapes | Attendu |
|---|---|---|
| E2.1 | Paramètres ▸ carte DJSync ▸ **Rapports d'erreur** | « Demander à chaque fois » par défaut ; « Toujours envoyer », « Ne jamais envoyer ». |
| E2.2 | Provoquer une erreur normale : couper Internet et lancer une recherche | Message « pas d'Internet », **aucune** proposition de rapport (situation normale). |
| E2.3 | Une erreur inattendue (si vous en rencontrez une) | Fenêtre « Envoyer un rapport d'erreur ? » avec le résumé ; *Envoyer le rapport* → e-mail « [DJSync 1.2.3] 1 Erreur · … » avec la trace et la fin du journal ; *Ne pas envoyer* → rien. |
| E2.4 | Cocher « Toujours envoyer… » dans la fenêtre | Le réglage passe à « Toujours envoyer » ; les rapports suivants partent sans demander. |
| E2.5 | Même erreur plusieurs fois dans la journée | Un seul rapport proposé par jour pour un même problème (5 rapports par jour au plus). |

### E3. Format de la clé et export.pdb (Accueil)
| # | Étapes | Attendu |
|---|---|---|
| E3.1 | Carte de la clé sur l'Accueil | Pastille du format : « FAT32 » (normale) ou « exFAT ⚠ » / « NTFS ⚠ » (orange) avec l'explication au survol. |
| E3.2 | Clé sans export.pdb (exportée en OneLibrary seulement) | Pastille orange « OneLibrary seul » : au survol, explication pour les anciennes platines et comment exporter aussi la « Device Library » dans Rekordbox. |
| E3.3 | Clé dont l'export.pdb n'a pas pu être mis à jour | Pastille orange « export.pdb pas à jour » avec le détail et « Paramètres ▸ Anciennes platines ▸ Synchroniser maintenant ». |
| E3.4 | `djsync.log` après ouverture d'une clé | Ligne « Drive …: file system FAT32, export.pdb present (… bytes) ». |

### E5. Retours Mac de la 1.2.1-rc.1
| # | Étapes | Attendu |
|---|---|---|
| E5.1 | Télécharger un son ▸ « Télécharger dans… » : **un clic** sur le nom d'une playlist, puis un 2e clic | 1er clic : cochée ; 2e clic : décochée. Cliquer sur la case marche toujours (pas de double bascule). Un clic sur un dossier le sélectionne (création dedans). |
| E5.2 | Écouter un son de la recherche, puis ouvrir / fermer « Télécharger dans… », Annuler, lancer un téléchargement | Plus de « rollback » (son qui recule ou se répète) à l'ouverture / fermeture des fenêtres. |
| E5.3 | **Mac** : pendant l'écoute, touches lecture/pause, suivant, précédent du clavier (F7-F9) ou du casque, DJSync au premier plan puis en arrière-plan | Elles agissent sur le lecteur de DJSync ; le widget « À l'écoute » de macOS affiche le titre et l'artiste. |
| E5.4 | Accueil ▸ *Trouver les doublons*, *Diagnostic* ; Bibliothèque ▸ *Outils* ▸ *Analyser…* | S'ouvrent **dans la fenêtre principale** (comme l'éditeur de grille), bouton *Retour* en haut ou Échap pour revenir là où on était. Plus de fenêtre séparée (plein écran Mac compris). |
| E5.5 | Lire un son **analysé** de la bibliothèque | Au-dessus du lecteur : forme d'onde détaillée qui **défile** sous une tête de lecture fixe au centre, avec les temps et les débuts de mesure (traits rouges) ; l'aperçu du morceau entier reste en bas pour se déplacer. En pause : elle s'arrête. Son pas analysé ou préécoute : pas de bande. |
| E5.6 | Paramètres ▸ décocher « Forme d'onde défilante… », lire un autre son | Plus de bande défilante. |

### E4. Outil développeur
| # | Étapes | Attendu |
|---|---|---|
| E4.1 | `python -m djsync.db.pdb.compare ref.pdb autre.pdb --playlist "Ma playlist" -o rapport.txt` | Rapport : en-têtes, pages, arbre des playlists, entrées de la playlist, anomalies (entrées vers un son absent…). |
