# DJSync — consignes pour Claude Code

Python + PySide6 (épinglé, packaging/constraints.txt : ne pas changer). GPL-3.0.
Réponses en français, courtes : résultat d'abord, puis ce que l'auteur doit faire.

## Règles
- Anonymat : aucun prénom nulle part (code, commits, PR, docs). Auteur : « Pikkol0 ».
  Testeurs désignés par leur rôle (testeur Mac, testeur platines).
- Fichiers des testeurs (clés, logs, captures) : jamais dans le dépôt.
- Interface en anglais, traduction française complète : chaque nouveau texte est traduit en FR.
- Ne coder que les fiches demandées ; lire seulement les fichiers qu'elles touchent.
- Jamais de push sur main ni de tag : l'auteur fusionne et pousse vX.Y.Z-rc.N.

## Flux d'une rc
1. Branche depuis main (même convention que les PR précédentes).
2. Code + tests ciblés en local (pytest sur les fichiers touchés).
3. docs/TESTS-<version>.fr.md (scénarios : id, qui, plateformes, comment, attendu) + README si besoin.
4. Pousser la branche, puis la même en ci/full/<branche> (Windows ×2 + Linux, ≈ 30 min) ;
   ne rapporter que les échecs, en résumé.
5. PR vers main : fiches traitées, tests, risques.
