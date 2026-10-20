# export.pdb (V1.1-A3) — ce qui est fait, ce qui est vérifié, ce qui ne l'est pas

## Ce que fait DJSync
À chaque écriture dans `exportLibrary.db` (ajout/suppression de son, playlists, ordre), la même
opération est appliquée à `PIONEER/rekordbox/export.pdb` **après** le commit de la base OneLibrary.

Sécurité : export.pdb n'est jamais créé ; il est chargé strictement, modifié en mémoire, contrôlé
(fichier relisible, seules les pages touchées diffèrent), sauvegardé (`DJSync_Backups/export-*.pdb`),
écrit via un fichier temporaire puis remplacé atomiquement, relu. Au moindre écart avec le modèle :
le fichier n'est pas touché, l'ajout dans exportLibrary.db reste valide, l'état passe à « à rattraper ».

## Honnêteté technique
* pyrekordbox n'est pas utilisé : à ma connaissance il ne sait pas écrire export.pdb (et il n'était pas
  installable dans l'environnement de développement, sans réseau). Le format est implémenté d'après
  l'analyse publique de Deep Symmetry, **de mémoire, sans vrai fichier de référence**.
* Les tests (`tests/test_pdb*.py`) utilisent un fichier synthétique construit selon ce même modèle :
  ils prouvent la cohérence interne, **pas** qu'une platine accepte le résultat.
* Une piste ajoutée n'est pas analysée (pas de BPM/tonalité/forme d'onde/ANLZ) : à vérifier sur platine.
* L'ajout de pages à une table pleine est désactivé par défaut (Paramètres), car la mise à jour de la
  page d'index est la partie la moins sûre. Sans lui, une table dont la dernière page est pleine
  refuse l'écriture (message clair) ; `Synchroniser maintenant` rattrape ensuite.
* Si une table ne contient aucune page de données, rien ne peut y être ajouté sans cet agrandissement.

## Validation à faire (dans cet ordre, sur une clé de test)
1. `python -m djsync.db.pdb.check E:\`  → lecture seule, dit si votre vrai fichier est reconnu.
   Envoyez-en le rapport (et idéalement le export.pdb) : c'est ce qui permet de corriger le modèle.
2. Ajoutez un son avec DJSync, mettez la clé dans la platine la plus ancienne que vous avez.
3. Pour revenir en arrière : copiez la sauvegarde `DJSync_Backups/export-…-session.pdb` sur export.pdb.

## Mode portable
`DJSync.exe` sur la clé : réglages dans `DJSync_Data/`, clé connectée d'office, `tools/` ajouté au PATH.
