# Scénarios de test — DJSync 1.3.0-rc.3

Version au démarrage (**C31**), fenêtre du lanceur Windows (**C35**), analyse après téléchargement
(**C32**), bouton « Mettre à jour export.pdb » sur l'Accueil (**C36**), affichage de la page Grille et cues (**B16**, **B17**), curseur de lecture précis (**C39**),
message d'export.pdb en anglais (**B14**). Les scénarios de `docs/TESTS-1.3.0-rc.2.fr.md` et
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

## H. Accueil : mettre à jour export.pdb (C36)
| # | Étapes | Attendu |
|---|---|---|
| H1 | Ouvrir la clé dans Rekordbox et le laisser ouvert ; dans DJSync, renommer une playlist. Revenir à l'Accueil. | Pastille orange « export.pdb pas à jour », une ligne « Pas encore sur les anciennes platines : … » et un bouton **Mettre à jour export.pdb**. |
| H2 | Cliquer **Mettre à jour export.pdb** avec Rekordbox toujours ouvert sur la clé. | Le bouton affiche « Mise à jour… », puis message « export.pdb est utilisé par un autre programme (Rekordbox ouvert sur la clé ?)… » ; la carte reste « pas à jour ». |
| H3 | Fermer Rekordbox, cliquer de nouveau **Mettre à jour export.pdb**. | Message « export.pdb est à jour » ; la pastille orange, la ligne de détail et le bouton disparaissent. Dans Rekordbox (Device Library), la playlist porte le nouveau nom. |

## Q. Page Grille et cues (B16, B17)
| # | Étapes | Attendu |
|---|---|---|
| Q1 | Windows à 125 % ou 150 %. Ouvrir Grille et cues sur un son, poser A en boucle de 4 temps et B. | Pads A et B : les deux lignes (lettre, puis « ⟳ 4 0:03.3 » / temps) sont entières. |
| Q2 | Regarder la bande du haut de la forme d'onde. | Numéros de mesure sur une ligne, étiquettes A / B juste en dessous : plus de « B73 ». Le temps en haut à droite n'est jamais recouvert par un numéro de mesure. |
| Q3 | Réduire la hauteur de la fenêtre. | La forme d'onde rétrécit ; pads, mémoires, boutons et lecteur restent visibles. |
| Q4 | Lancer la lecture depuis la page. | En bas, le lecteur montre le son entier en 3 bandes (mêmes couleurs que l'éditeur), avec la zone affichée encadrée, les hot cues et le curseur ; plus de forme d'onde rose / verte. Cliquer ou glisser dessus déplace l'éditeur et la lecture. |
| Q5 | Quitter la page (Retour), lecture en cours. | Le lecteur reprend sa forme d'onde habituelle. |
| Q6 | Cocher **Curseur fixe au centre**. Glisser la forme d'onde, tourner la molette. | Le curseur reste au milieu, le son défile dessous ; en lecture, le son défile sous le curseur. Un simple clic amène ce point sous le curseur. |
| Q7 | Fermer DJSync, le rouvrir, rouvrir Grille et cues. | La case est toujours cochée. La décocher : retour au curseur volant (défaut). |

## P. Curseur de lecture précis (C39)
| # | Étapes | Attendu |
|---|---|---|
| P1 | Page Grille et cues, vue 2 s ou 4 s, lancer la lecture sur un passage avec des kicks nets. | Le curseur défile sans à-coups et passe sur chaque trait de temps au moment où l'on entend le kick (plus d'avance d'environ 0,2 s). |
| P2 | Pause, puis reprise ; cliquer ailleurs dans la forme d'onde pendant la lecture. | Le curseur s'arrête là où le son s'arrête, repart avec lui, et ne part jamais avant le point cliqué. |
| P3 | (Casque Bluetooth ou carte son avec du retard) Paramètres ▸ Retard audio en plus pour les curseurs : augmenter par pas de 10 ms. | Le curseur se recale sur ce qu'on entend ; le réglage est gardé au prochain lancement. |

## E. export.pdb (B14)
| # | Étapes | Attendu |
|---|---|---|
| E1 | (Facultatif) App en anglais, clé avec un export.pdb inhabituel. | Tout message d'export.pdb est en anglais. |

## R. Retour
Envoyer les logs depuis l'app (Retours ▸ Envoyer mes logs) après W1 et A2, avec une capture de la
fenêtre du lanceur si elle paraît encore mal réglée.
