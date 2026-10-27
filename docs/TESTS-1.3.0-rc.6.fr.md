# Scénarios de test — DJSync 1.3.0-rc.6

La rc.6 prépare les tests sur platines (**B27**) et accélère les builds (**C64**). Les tests de la rc.5
restent valables : ceux qui n'ont pas encore été faits peuvent l'être sur la rc.6. Numérotation :
thème + n° (`revues/numerotation-tests.md`) ; dans le suivi : « rc6 · CLE-1 ».

Ce qui change :
- **Dossiers d'analyse comme Rekordbox.** Les fichiers d'analyse (forme d'onde, grille, cues) des sons
  ajoutés par DJSync vont maintenant dans le même dossier que Rekordbox choisirait
  (`PIONEER/USBANLZ/Pxxx/xxxxxxxx`, calculé à partir du chemin du son ; vérifié sur les 213 sons d'un
  vrai export). Avant, DJSync choisissait son propre nom : les platines suivent le chemin écrit dans la
  base, mais certaines pourraient recalculer ce dossier, et ne rien trouver.
- **Clés déjà remplies : rangées toutes seules.** À l'ouverture d'une clé, les analyses des sons de
  DJSync sont copiées au bon endroit, les deux bases (exportLibrary.db et export.pdb) mises à jour
  (sauvegarde avant, comme toute écriture), puis les anciens fichiers effacés, seulement une fois
  export.pdb à jour. Les sons de Rekordbox ne sont jamais touchés. Si Rekordbox est ouvert, rien n'est
  changé : ce sera fait à l'ouverture suivante.
- **Lignes d'export.pdb comme Rekordbox** pour les sons de DJSync (champ propre à chaque son, champs
  constants, pas de débit pour les m4a, durée tronquée).

**Avant de tester : garde une copie de ta clé** (au moins le dossier `PIONEER`).

## CLE — Clé et export.pdb (B27)
| # | Étapes | Attendu |
|---|---|---|
| CLE-1 | Ouvrir dans DJSync une clé déjà remplie avec la rc.5 (ou avant) : des sons ajoutés **et analysés** par DJSync. Attendre ~10 s, puis Paramètres ▸ Anciennes platines (export.pdb). | Aucun message d'erreur ; « export.pdb reconnu et à jour ». Facultatif : `djsync.log` (dossier des réglages de DJSync) contient « Analysis files moved to the Rekordbox folders: n track(s) ». |
| CLE-2 | Après CLE-1 : ouvrir 2 ou 3 sons de DJSync dans **Grille et cues**. | Forme d'onde, grille, hot cues et mémoires toujours là. |
| CLE-3 | Éjecter, ouvrir la clé dans **Rekordbox** (appareil, pas la collection) : les sons de DJSync. | Pas de message « bibliothèque corrompue » ; forme d'onde, grille et hot cues des sons de DJSync affichés ; playlists complètes. |
| CLE-4 | Ajouter un son (téléchargé ou fichier), le laisser s'analyser, éjecter ; refaire CLE-3 avec lui. | Pareil pour le nouveau son. |
| CLE-5 | Rekordbox **ouvert sur la même clé** : ouvrir la clé dans DJSync (avant CLE-1, sur une autre clé de la rc.5 si possible). Puis fermer Rekordbox, éjecter et rouvrir la clé dans DJSync. | Pas d'erreur bloquante pendant que Rekordbox est ouvert ; après réouverture, comme CLE-1. |
| CLE-6 | Supprimer un son ajouté par DJSync (clic droit ▸ Supprimer, fichier compris). | Son dossier d'analyse disparaît de `PIONEER/USBANLZ` (s'il ne contient rien d'autre). |

## PLA — Platines (B27, P05)
| # | Étapes | Attendu |
|---|---|---|
| PLA-1 | Dès maintenant, sans platine : ouvrir la clé dans **Mixxx** (bibliothèque ▸ Rekordbox ▸ la clé). Charger 3 sons de DJSync et 1 son de Rekordbox. | Les sons de DJSync ont leur grille et leurs hot cues, comme celui de Rekordbox (Mixxx les lit dans export.pdb et dans les fichiers d'analyse de la clé) ; playlists visibles. |
| PLA-2 | (Testeur platines) Brancher la clé sur une platine récente (CDJ-3000, XDJ…) : playlists, charger des sons de DJSync. | Playlists visibles ; forme d'onde (aperçu et zoomée), grille, BPM, tonalité, hot cues et mémoires des sons de DJSync. |
| PLA-3 | (Testeur platines) Même chose sur une ancienne platine (CDJ-2000NXS2 ou plus ancienne : export.pdb). | Pareil ; pas d'erreur E-8307 (T01). |

## DEM — Build (C64)
| # | Étapes | Attendu |
|---|---|---|
| DEM-1 | (Auteur) Après le tag : onglet Actions ▸ Build. | Windows et Linux prêts en **~8 à 10 min** (avant : ~17 min) ; les tests tournent à côté (job « tests ») sans bloquer la release ; dès la 2ᵉ release, FFmpeg n'est plus recompilé (workflow « FFmpeg cache » lancé une fois sur main). |
