# Scénarios de test — DJSync 1.3.0

## 1.3.0 stable : derniers correctifs (après la rc.9)
- **B32** (Mac, plein écran : ouvrir Doublons ou le Diagnostic affichait le bureau) : cause trouvée grâce aux
  journaux de la rc.9 : la pastille de tonalité de chaque version s'affichait un instant comme une fenêtre
  avant d'être placée dans la page. Corrigé ; un test ouvre toutes les pages et échoue si une fenêtre
  apparaît, même un instant (seule cette pastille était concernée).
- **B33** (Mac : blanc d'environ 1/4 s en écoute à l'ouverture / fermeture de « Télécharger vers… ») : sur
  Mac, ces fenêtres glissaient en « feuille » depuis la fenêtre principale ; l'animation retardait le son.
  Elles s'ouvrent maintenant directement au-dessus, sans feuille.
- **B35** : supprimer le pad dont la boucle tourne, ou lui retirer sa boucle, fait sortir de la boucle tout
  de suite ; changer sa longueur fait suivre la boucle en cours.

| # | Étapes | Attendu |
|---|---|---|
| F-1 | (Testeur Mac) DJSync **en plein écran** ▸ Accueil ▸ **Trouver les doublons**, puis le **Diagnostic**. | Plus de bureau : on reste dans DJSync. |
| F-2 | (Testeur Mac) Recherche ▸ écouter un son ▸ **Télécharger** (choix de playlist), puis fermer le choix ; 2 ou 3 fois. | Plus de blanc dans le son ; la fenêtre s'ouvre sans glisser. |
| F-3 | Grille et cues : pad A en boucle de 4 temps ▸ cliquer A (la boucle tourne) ▸ clic droit ▸ **Supprimer**. | La lecture sort de la boucle et continue, sans coupure. |
| F-4 | Même chose, mais clic droit ▸ **Boucle de 8 temps**, puis **Pas de boucle**. | La boucle en cours passe à 8 temps, puis on en sort. |
| F-5 | (Auteur, Windows) Confirmation (ex. Retour sans enregistrer dans Grille et cues), **Télécharger vers…** | Comme avant. |

Dans le suivi : « 130 · F-1 ».

## Scénarios de la 1.3.0 (rc.1)

Hot cues et boucles sans Rekordbox, Uniformiser v2, doublons décidés par le son, report des hot cues.
À faire sur une **copie** de la clé (ou après un point de restauration : Paramètres ▸ Sauvegardes de la
clé), Rekordbox fermé pendant les écritures. Si ce n'est pas déjà fait, passer aussi
`docs/TESTS-1.2.4.fr.md` (export.pdb, clé non préparée).

## G. Grille et cues (C22)

### G1. Poser, écouter, modifier
| # | Étapes | Attendu |
|---|---|---|
| G1.1 | Bibliothèque ▸ clic droit sur un son analysé ▸ **Grille et cues…** | Page « Grille et cues » : forme d'onde, grille, 8 pads A–H vides aux couleurs Rekordbox, bloc Mémoires. |
| G1.2 | Placer le curseur près d'un kick, cliquer le pad **A** (ou touche 1) | Un cue A apparaît sur le temps le plus proche (lettre en haut de la forme d'onde). Le pad prend sa couleur. « cues modifiés » en bas. |
| G1.3 | Même chose avec **Maj** enfoncée sur le pad B | B est posé exactement au curseur, pas sur le temps. |
| G1.4 | Cliquer le pad A posé | La lecture part de A. |
| G1.5 | Clic droit sur A ▸ **Boucle de 4 temps** ; cliquer A | A devient une boucle (zone colorée sur 4 temps) ; la lecture boucle jusqu'au clic suivant. |
| G1.6 | Clic droit sur B ▸ **Renommer** « Drop », puis **Couleur** ▸ une autre couleur | Nom et couleur affichés sur le pad et la forme d'onde. |
| G1.7 | Glisser la lettre de B sur la forme d'onde | B se déplace (sur les temps ; Maj : librement). |
| G1.8 | **Mémoire au curseur** à deux endroits ; clic sur une mémoire, puis clic droit ▸ supprimer | Aller à la mémoire / suppression. |
| G1.9 | **Proposer des cues** sur un son sans cue | Les pads libres sont remplis (A au premier temps fort, puis toutes les 32 mesures) ; message « N cues proposés ». Les pads déjà posés ne bougent pas. |
| G1.10 | **Retour** sans enregistrer | Demande de confirmation ; rien n'est écrit. Rouvrir : cues d'avant. |
| G1.11 | Refaire G1.2-G1.6, **Enregistrer** | « Cues enregistrés (originaux copiés dans DJSync_Backups/anlz) ». Rouvrir la page : tout est là. |

### G2. Lecture par Rekordbox et les platines
| # | Étapes | Attendu |
|---|---|---|
| G2.1 | Ouvrir la clé dans Rekordbox (mode Export) ▸ le son de G1.11 | Hot cues A et B (nom « Drop », couleurs), boucle sur A, mémoires : identiques à DJSync. |
| G2.2 | Sur une platine récente (CDJ-3000, XDJ-XZ…) | Hot cues A–H, boucle, noms et couleurs. |
| G2.3 | Sur une ancienne platine (CDJ-2000NXS2, XDJ-1000) | Hot cues A–C et mémoires (les anciennes platines n'affichent pas D–H). |
| G2.4 | Bibliothèque du PC (Rekordbox fermé) : poser 3 cues sur un son, Enregistrer, ouvrir Rekordbox | Les cues sont dans la collection de l'ordinateur. Sauvegarde de master.db faite avant. |
| G2.5 | Son déjà préparé dans Rekordbox avec des cues : ouvrir dans DJSync | Ses cues sont lus et affichés ; modifier un pad, Enregistrer, vérifier dans Rekordbox que les autres sont intacts. |
| G2.6 | Réanalyser un son qui a des cues (Analyse ▸ « Réanalyser ») | Les cues restent. |

## U. Uniformiser les infos (C25)
| # | Étapes | Attendu |
|---|---|---|
| U1 | Accueil ▸ Outils ▸ **Uniformiser les infos** | Choix : sons à problèmes, toute la bibliothèque, 50 derniers, une playlist. |
| U2 | « Sons à problèmes » ▸ Ouvrir | Liste continue : chaque son sur deux lignes **Actuellement** / **Après**, les sûrs en premier. Ce qui change est écrit en couleur, l'incertain en orange. |
| U3 | Un titre avec un identifiant YouTube (« Titre [AbCdEfGhIjK] ») ou « (Official Video) » | Ligne Après sans l'identifiant ni le bruit ; les invités du « feat. » passent dans les artistes. |
| U4 | Cliquer un champ de la ligne Après, le modifier, Entrée ; puis ↺ | La valeur change ; ↺ remet la valeur actuelle. |
| U5 | Survoler la pochette Après ▸ croix ; puis cliquer la zone vide ▸ choisir une image ; puis glisser une autre image | Pochette retirée, puis remplacée par l'image choisie, puis par l'image glissée. |
| U6 | Son mal reconnu : **Chercher autrement**, taper « artiste titre », Entrée | Ligne Après remplie par le meilleur résultat ; les autres résultats dessous, un clic pour en prendre un. |
| U7 | Clavier : Entrée, I, F, Espace, Ctrl+Z | Valider et passer au suivant / ignorer / aller à « Chercher autrement » / écouter / annuler la dernière validation. |
| U8 | Valider quelques sons ▸ **Enregistrer** | Infos changées dans la bibliothèque (et dans Rekordbox / sur la platine pour la clé) ; fichiers audio, grilles et cues intacts. |
| U9 | Fermer, rouvrir Uniformiser | Les sons validés ou ignorés ne reviennent pas dans « à revoir ». |

## D. Doublons par le son (B02) et report des cues (C13)
| # | Étapes | Attendu |
|---|---|---|
| D1 | Télécharger deux fois le même son (deux sources différentes) ; Accueil ▸ **Trouver les doublons** | Groupe affiché ; « Comparaison du son… » puis chaque version marquée **Référence** / **Même son**. |
| D2 | Deux versions différentes d'un même titre (clip et version album, remix…) | Marquées **Variante (N % en commun)** avec un avertissement « écoutez avant de fusionner ». |
| D3 | Deux sons au titre proche mais différents (ex. « … pt 3 » et « … pt 7 ») | Ils ne sont plus regroupés (sortis du groupe), ou marqués non identiques. **À noter si ce n'est pas le cas** (sert à régler les seuils). |
| D4 | Poser des hot cues sur la version qui sera supprimée ; dans Doublons, **Hot cues à garder** ▸ cette version ▸ **Garder celui-ci, supprimer les autres** | « N hot cues reportés sur la version gardée » ; ouvrir Grille et cues de la version gardée : les cues sont au même endroit musical. |
| D5 | Diagnostic ▸ remplacer un son qui a des cues par un nouveau téléchargement | Après analyse du nouveau fichier, les cues sont recalés dessus (message si certains tombent hors du fichier). |
| D6 | Facultatif, pour régler les seuils : `python tools/dup_audio_report.py E:` (depuis les sources) | Rapport des verdicts par groupe ; l'envoyer avec Retours ▸ Envoyer les logs ou par mail. |

## R. Retour
Après les tests : **Retours ▸ Envoyer les logs** (fichiers de la bibliothèque joints), en précisant les
numéros de scénario qui ne donnent pas le résultat attendu et le modèle de platine utilisé.
