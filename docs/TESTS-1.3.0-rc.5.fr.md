# Scénarios de test — DJSync 1.3.0-rc.5

La rc.5 reprend le seul KO de la rc.4 : le son en retard sous Windows (**C39**, tests rc4 · LEC-1 et
LEC-2), les formes d'onde différentes de celles de Rekordbox (**B25**, **B01**, test rc1 · L5), et
ajoute : un seul outil Doublons, rapide, où l'on peut écarter un son (**C63**, **C62**, tests rc1 · D4 / D5),
et la fin des « Rekordbox ouvert » à tort (**B26**). Les autres tests de la rc.4 sont OK et restent valables. Numérotation : thème + n°
(`revues/numerotation-tests.md`) ; dans le suivi : « rc5 · LEC-1 ».

Ce qui change : la carte son gardait environ **600 ms** d'avance sous Windows (miniaudio lisait « 200 ms »
comme la taille d'un paquet et en gardait trois). Elle en garde maintenant **environ 80 ms**
(2 × 40 ms ; macOS ne change pas), le retard réel est **mesuré** pour placer les curseurs, et un saut
(clic sur la forme d'onde, hot cue, barre de lecture) vide la réserve pour être entendu tout de suite.

**Avant de tester : remets « Retard audio en plus pour les curseurs » à 0** (Paramètres ▸ Apparence),
sauf avec un casque Bluetooth.

## LEC — Lecteur, son (C39)
| # | Étapes | Attendu |
|---|---|---|
| LEC-1 | Page **Grille et cues**, vue de 2 s ou 4 s : lancer la lecture sur un passage avec des kicks nets, puis mettre en pause, reprendre. Comparer avec Rekordbox sur le même PC, mêmes enceintes ou casque. | Le son démarre aussi vite que dans Rekordbox ; le curseur passe sur les traits de temps au moment où l'on entend le kick ; la pause coupe tout de suite ; la reprise repart de ce qu'on a entendu. |
| LEC-2 | Pendant la lecture : cliquer ailleurs sur la forme d'onde, puis appuyer sur un hot cue posé, puis cliquer dans la barre du lecteur du bas. | Le nouvel endroit s'entend tout de suite (plus d'une demi-seconde de l'ancien passage) ; le curseur y est déjà. |
| LEC-3 | Poser une boucle de 4 temps et la laisser tourner 30 s ; ouvrir et fermer une fenêtre (Paramètres) pendant ce temps. | Le retour au début de la boucle tombe pile, sans trou ni craquement ; pas de coupure en ouvrant une fenêtre (sinon : noter, et dire si l'ordinateur est chargé). |
| LEC-4 | Avec un casque Bluetooth (si tu en as un) : Paramètres ▸ Apparence ▸ Retard audio en plus ▸ **Tester…**, régler à l'oreille, Enregistrer, puis refaire LEC-1. | Le curseur tombe sur ce qu'on entend ; la valeur à régler est bien plus petite qu'en rc.4 (seulement le retard du casque). |
| LEC-5 | (Testeur Mac) Refaire LEC-1 et LEC-3 sur macOS. | Comme en rc.4 : pas de changement sur Mac. |

## ANA — Formes d'onde comme Rekordbox (B25, B01)
Mesure sur ton échantillon du 27/10 (7 m4a analysés par DJSync et par Rekordbox 7 sur la même clé) :
- **grille** : à 2–5 ms de celle de Rekordbox sur 6 sons sur 7 (12 ms sur un), donc rien à changer
  pour B01 ; deux autres écarts relèvent de l'analyse (1.4.1) : un BPM faux (87,7 au lieu de 92, A02)
  et un premier temps de la mesure décalé d'un temps (B12) ;
- **formes d'onde** : DJSync étirait chaque son jusqu'en haut (hauteur deux fois trop grande, saturée)
  alors que Rekordbox suit le niveau réel, et les dessinait 6,7 ms trop tôt. Recalées : hauteur à
  ~1,3 / 31 de Rekordbox au lieu de ~3,1, couleurs, aperçus (PWAV, PWV2, PWV4) et 3 bandes rapprochés.

Les fichiers déjà analysés gardent leurs anciennes formes d'onde : **réanalyse** les sons à comparer
(clic droit ▸ Analyser la sélection ▸ Réanalyser).

| # | Étapes | Attendu |
|---|---|---|
| ANA-1 | Réanalyser dans DJSync les sons de ton échantillon (ceux sans « -1 »), éjecter, ouvrir la clé dans Rekordbox et comparer chaque son à sa copie « -1 » analysée par Rekordbox (forme d'onde zoomée et aperçu). | Même hauteur et même allure ; un son masterisé moins fort a une forme d'onde plus basse dans les deux ; les kicks tombent au même endroit sur la grille. |
| ANA-2 | Même comparaison sur 2 ou 3 MP3. | Pareil (le recalage ne dépend pas du format). |
| ANA-3 | (Platines) Charger un son réanalysé sur une platine. | Forme d'onde lisible, ni écrasée ni saturée. |

## DOU — Doublons (C63, C62)
| # | Étapes | Attendu |
|---|---|---|
| DOU-1 | Bibliothèque ▸ Outils ▸ **Doublons** (ou Accueil) sur ta clé. | La liste des groupes s'affiche **tout de suite** ; en haut à droite « Vérification du son… i / n groupes » avance, le groupe affiché d'abord ; les groupes pas encore vérifiés sont en gris. Ouvrir une 2e fois : bien plus rapide (empreintes en cache). |
| DOU-2 | Groupe avec deux « Afro Trap Pt. 3 » (et d'autres parties). | Pt. 7 (ou toute autre partie, un remix, un live) n'est plus dans le groupe des Pt. 3. |
| DOU-3 | Dans un groupe de 3 sons, cliquer **Pas un doublon** sur l'un d'eux, puis **Garder celle-ci, supprimer les autres**. | Le son écarté sort du groupe (message) ; seuls les deux autres sont fusionnés, hot cues reportés comme avant. |
| DOU-4 | Fermer puis rouvrir Doublons. | Le son écarté ne revient pas avec ce groupe. |
| DOU-5 | **Écartés (n)** en bas à gauche : sélectionner la ligne, **Annuler** (ou **Tout rétablir**), fermer. | La liste se relance ; le groupe revient avec le son. |
| DOU-6 | **Détection complète**. | Tous les groupes reviennent, même écartés, mais les choix restent dans « Écartés ». |
| DOU-7 | Bouton **Pas des doublons** sur un groupe ; **Plus tard** sur un autre ; rouvrir. | Le premier ne revient plus (dans « Écartés ») ; le second revient. |
| DOU-8 | Accueil ▸ **Diagnostic** ▸ un groupe de doublons ▸ choisir la version à garder ▸ **Fusionner dans Doublons…** | L'outil Doublons s'ouvre sur ce groupe avec cette version cochée ; fusion avec choix des hot cues (rc1 · D4 refait ici). Retélécharger une meilleure version reste dans le Diagnostic (rc1 · D5, cues recalés). |

## REC — « Rekordbox ouvert » (B26)
| # | Étapes | Attendu |
|---|---|---|
| REC-1 | Rekordbox fermé (vérifier dans le Gestionnaire des tâches qu'aucun « rekordbox.exe » ne reste) : regarder l'Accueil pendant 1 min. | Pas de pastille « Rekordbox ouvert ». |
| REC-2 | Ouvrir Rekordbox, attendre ~10 s ; puis le fermer. | La pastille apparaît après quelques secondes, puis disparaît dès la fermeture. |
