# Scénarios de test — DJSync 1.3.0-rc.3

Version au démarrage (**C31**), fenêtre du lanceur Windows (**C35**), analyse après téléchargement
(**C32**), message d'export.pdb en anglais (**B14**). Les scénarios de `docs/TESTS-1.3.0-rc.2.fr.md` et
`docs/TESTS-1.3.0.fr.md` restent à faire s'ils ne sont pas cochés.

## W. Lancement et version (C31, C35)
| # | Étapes | Attendu |
|---|---|---|
| W1 | Windows : dans DJSync rc.2, Paramètres ▸ DJSync ▸ Vérifier maintenant ▸ Mettre à jour vers la rc.3. | Après le redémarrage, petite fenêtre « Mise à jour de DJSync 1.3.0-rc.2 → 1.3.0-rc.3… » (une seule langue, celle de Windows), titre « DJSync 1.3.0-rc.3 », barre avec pourcentage, rien de coupé, pas de rectangle gris. |
| W2 | Copier `DJSync.exe` rc.3 sur une clé où DJSync n'a jamais été lancé, double-cliquer. | Fenêtre « Installation de DJSync 1.3.0-rc.3 sur cette clé… ». |
| W3 | Refaire W1 ou W2 avec l'affichage Windows à 125 % puis 150 % (Paramètres Windows ▸ Écran ▸ Échelle). Pour revoir la fenêtre, supprimer le dossier caché `.djsync\app` à côté de `DJSync.exe` (sans toucher `.djsync\data`). | Texte et barre à la bonne taille, marges égales, rien de coupé. |
| W4 | Juste après la fenêtre du lanceur : regarder l'écran de démarrage DJSync (logo, « Loading… »). | La version exacte (« v1.3.0-rc.3 ») est écrite sous « Loading… », dans la couleur violette. |
| W5 | macOS / Linux : lancer DJSync. | Écran de démarrage avec le logo à sa taille normale (plus de logo géant) et « v1.3.0-rc.3 » sous « Loading… ». |

## A. Analyse après téléchargement (C32)
| # | Étapes | Attendu |
|---|---|---|
| A1 | Paramètres ▸ Analyse | Deux cases cochées par défaut : « Analyser les titres après téléchargement — clé USB » et « — bibliothèque de l'ordinateur » (aussi après la mise à jour depuis la rc.2). |
| A2 | Clé ouverte : télécharger 3 sons d'affilée. | Les téléchargements s'enchaînent sans attendre l'analyse ; la carte « Analyse » de la barre latérale avance ; à la fin, BPM, tonalité et forme d'onde dans la Bibliothèque. |
| A3 | Décocher « — clé USB », télécharger un son. | Le son arrive sans analyse (section « Non analysés »). |
| A4 | Bibliothèque de l'ordinateur (Rekordbox fermé), case « — bibliothèque de l'ordinateur » cochée : télécharger un son. | Son analysé après le téléchargement ; les sons de Rekordbox ne sont pas touchés. |
| A5 | Pendant l'analyse de A2, passer sur l'autre bibliothèque. | Pas d'erreur ; les sons pas encore analysés le seront à la demande. |

## E. export.pdb (B14)
| # | Étapes | Attendu |
|---|---|---|
| E1 | (Facultatif) App en anglais, clé avec un export.pdb inhabituel. | Tout message d'export.pdb est en anglais. |

## R. Retour
Envoyer les logs depuis l'app (Retours ▸ Envoyer mes logs) après W1 et A2, avec une capture de la
fenêtre du lanceur si elle paraît encore mal réglée.
