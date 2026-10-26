# Scénarios de test — DJSync 1.3.0-rc.2

Correctifs d'export.pdb (anciennes platines : CDJ-2000NXS2, XDJ-1000…) : **B13** (Rekordbox « La
bibliothèque dans le dispositif est corrompue » après des ajouts sur une clé vide) et **P02**
(export.pdb réconcilié avec exportLibrary.db). Les scénarios de `docs/TESTS-1.3.0.fr.md` restent à faire.

À faire Rekordbox fermé pendant les écritures. Ne plus ouvrir la clé de test avec la 1.3.0-rc.1.

## K. Clé vide préparée par Rekordbox (B13)
| # | Étapes | Attendu |
|---|---|---|
| K1 | Clé du test K2 (celle que Rekordbox dit « corrompue ») : dans Rekordbox, répondre **Non** à « Voulez-vous la supprimer ? », fermer Rekordbox. Ouvrir la clé dans DJSync rc.2. | Le journal (`djsync.log`) indique « index page repaired » ; l'Accueil dit export.pdb à jour. |
| K2 | Rouvrir la clé dans Rekordbox | Plus de message « corrompue ». La playlist « test » et ses 2 sons apparaissent dans **Device Library** et dans **OneLibrary**. |
| K3 | Clé vidée puis préparée à nouveau par Rekordbox (aucun son). DJSync rc.2 : télécharger 2 sons dans une nouvelle playlist, éjecter. | Rekordbox : pas de message « corrompue » ; playlist et sons dans Device Library et OneLibrary ; dates d'ajout = date du jour ; tonalités en notation Rekordbox (Am, F#m…). |
| K4 | `python -m djsync.db.pdb.check E:` (ou Retours ▸ Envoyer mes logs) | Aucune ligne `INDEX:`. |
| K5 | Ancienne platine (CDJ-2000NXS2, XDJ-1000), clé de K3 | La playlist et les sons sont lus. |

## S. Réconciliation d'export.pdb (P02)
| # | Étapes | Attendu |
|---|---|---|
| S1 | Clé avec quelques sons. Ouvrir Rekordbox **sur la clé** (il verrouille export.pdb), puis dans DJSync : réordonner une playlist, retirer un son d'une playlist, renommer une playlist, supprimer un son, changer un titre. | Les changements passent dans DJSync ; l'état d'export.pdb devient « pas à jour » avec le détail (playlists différentes, suppressions en attente…). |
| S2 | Fermer Rekordbox, puis **Synchroniser maintenant** (ou faire n'importe quelle modification) | État « à jour ». `DJSync_Backups/pdb-journal.json` a disparu. |
| S3 | Rekordbox : Device Library de la clé | Ordre, retrait, nouveau nom (pas de doublon avec l'ancien), son supprimé absent, nouveau titre : comme dans DJSync. |
| S4 | Refaire S1, puis **retirer la clé sans éjecter** et la rebrancher dans DJSync | Le rattrapage se fait à l'ouverture ; même résultat qu'en S3. |
| S5 | Refaire S1 puis **Éjecter** alors que Rekordbox verrouille encore la clé | Message « export.pdb n'est pas à jour (…). Rebranchez la clé dans DJSync pour terminer la mise à jour. » |
| S6 | Clé avec des sons ajoutés par Rekordbox (inconnus de DJSync seulement si ancien export) | Rien n'est retiré de Device Library par DJSync. |

## R. Retour
Envoyer les logs depuis l'app (Retours ▸ Envoyer mes logs, case « fichiers de la clé » cochée) après K2/K3,
avec une capture de Rekordbox si un message apparaît.
