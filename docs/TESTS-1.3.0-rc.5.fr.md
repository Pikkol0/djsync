# Scénarios de test — DJSync 1.3.0-rc.5

La rc.5 reprend le seul KO de la rc.4 : le son en retard sous Windows (**C39**, tests rc4 · LEC-1 et
LEC-2). Les autres tests de la rc.4 sont OK et restent valables. Numérotation : thème + n°
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
