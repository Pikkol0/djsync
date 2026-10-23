# Scénarios de test — DJSync 1.2.4

Correctif export.pdb (anciennes platines : XDJ-XZ, XDJ-1000, CDJ-2000NXS2…), suite aux logs du 23/10, et clé vierge expliquée (T02).

| # | Étapes | Attendu |
|---|---|---|
| F1 | Clé de l'ami (XDJ-XZ, export Rekordbox ancien, erreur « page 18: inconsistent counters ») : brancher, ouvrir avec la 1.2.4 | Message « export.pdb rattrapé : 9 sons, 2 playlists ». La pastille orange « export.pdb pas à jour » disparaît de l'Accueil. |
| F2 | Brancher cette clé sur la XDJ-XZ | Les playlists « Trance Oldskool » et « RNS/NDOLE » apparaissent avec leurs sons ; les autres playlists sont **identiques** à avant (aucun son en double, « dBs » et « dbs » restent deux playlists). |
| F3 | Clé exportée par Rekordbox 7 (erreur « next free page outside the file ») : télécharger 2 sons dans une nouvelle playlist | Pas d'avertissement orange ; sur une ancienne platine, la playlist et les sons sont là. |
| F4 | `Retours ▸ Envoyer les logs` après F1-F3 | Le contrôle d'export.pdb du rapport dit « Layout recognised ». |
| F5 | Brancher une clé fraîchement formatée en FAT32 (aucun dossier PIONEER) | Sur l'Accueil : carte « Pas encore préparée » avec la marche à suivre (Rekordbox, ajouter une playlist ou un son). |
| F6 | Sans débrancher, ajouter une playlist sur cette clé dans Rekordbox (n'importe quel mode), fermer Rekordbox | En quelques secondes la carte devient une bibliothèque normale et DJSync l'ouvre. |
| F7 | Clé formatée en NTFS (ou clé avec seulement un vieux dossier PIONEER) | Pastille « NTFS ⚠ » et phrase « reformatez en FAT32 » / texte « ancienne version de Rekordbox ». |
