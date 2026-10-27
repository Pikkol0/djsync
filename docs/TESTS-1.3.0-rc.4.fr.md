# Scénarios de test — DJSync 1.3.0-rc.4

La rc.4 corrige les six tests KO de la rc.3 (fiches **B18**, **B20**, **C39**, **C31**, **B22**) et deux
bugs relevés le 27/10 (**B23**, **B24**). Rien d'autre ne change par rapport à la rc.3 : les tests OK
de la rc.3 restent valables. Les tests portent la même lettre que leur essai KO de la rc.3 (même test,
nouvel essai) ; B1 et B2 sont nouveaux.

## Nouveaux essais des tests KO de la rc.3
| # | Étapes | Attendu |
|---|---|---|
| Y1 | Accueil ▸ **Uniformiser les infos** ▸ toute la bibliothèque (ou « Seulement les sons à problèmes »), et regarder la liste pendant toute la recherche, en particulier sur l'écran 4K à 200 %. | Les sons s'ajoutent en bas par petits groupes ; aucun bloc ne rétrécit, ne se superpose ni ne « saute » ; ce qui est au-dessus ne bouge pas. (B18) |
| F4 | 1) Ouvrir **Grille et cues** sur un son dont le fichier n'existe plus, cliquer Lecture. 2) Lire un autre son, le mettre en pause, puis ouvrir Grille et cues sur un son présent et cliquer **Lecture dans le lecteur du bas** (puis Espace, puis le bouton de la page). | 1) Bandeau rouge « Fichier audio introuvable… », Lecture ne fait rien. 2) Le lecteur du bas joue le son de la page, depuis le curseur de la page ; pause / lecture et position suivent dans les deux sens. Page fermée : le lecteur du bas reprend son rôle habituel. (B20) |
| P1 | Page Grille et cues, vue de 2 s ou 4 s : lancer la lecture sur un passage avec des kicks nets, puis mettre en pause. | Le curseur passe sur les traits de temps au moment où l'on entend le kick ; **à la pause, le son s'arrête tout de suite** (plus d'une seconde qui continue) ; la reprise repart de ce qu'on a entendu. (C39) |
| P3 | Avec un casque Bluetooth (ou si le curseur reste en avance) : Paramètres ▸ Apparence ▸ **Retard audio en plus pour les curseurs** ▸ **Tester…**. Déplacer le curseur jusqu'à entendre chaque clic pile quand un repère passe la ligne rouge, **Enregistrer**, puis relancer DJSync. | Réglage de −200 à 2000 ms, appliqué en direct pendant le test ; le curseur de Grille et cues tombe ensuite sur ce qu'on entend ; le réglage est gardé. **Annuler** remet la valeur d'avant. (C39) |
| W4 | Lancer DJSync.exe (Windows) et regarder l'écran de démarrage jusqu'à l'ouverture de la fenêtre, à 100 % puis à 200 %. | L'écran de l'exe (violet) apparaît pendant la décompression, puis l'écran de DJSync, **centré et net**, avec **« v1.3.0-rc.4 »** sous « Loading… » (dans la couleur choisie). (C31, B24) |
| X3 | Clé ouverte dans DJSync : la retirer **sans** Éjecter, attendre 10 s, puis la rebrancher. | **Un seul** message : « La clé E:\ a été retirée sans être éjectée : DJSync l'a refermée… » ; aucun « disk I/O error » ni autre erreur ensuite ; rebranchée, elle se rouvre toute seule et export.pdb est vérifié. (B22) Si ce n'est pas le cas : note ce qui s'affiche et envoie le journal (Retours ▸ Envoyer mes logs). |

## Nouveaux tests
| # | Étapes | Attendu |
|---|---|---|
| B1 | Paramètres ▸ changer la couleur, puis passer par Accueil, Bibliothèque, Recherche, Diagnostic et Grille et cues, **sans redémarrer**. | Les icônes (Outils de l'Accueil compris), pastilles, logo et formes d'onde ont la nouvelle couleur tout de suite ; la page Paramètres reste ouverte ; la lecture en cours continue. (B23) |
| B2 | Windows en zoom 200 % (et 100 %, et 150 % si possible ; un et deux écrans) : lancer DJSync.exe. | L'écran de démarrage reste centré du début à la fin et ne glisse plus vers le haut à gauche. (B24) |
