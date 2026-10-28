# Scénarios de test — DJSync 1.3.0-rc.8

La rc.8 corrige les bugs remontés sur la rc.7 avant la 1.3.0 stable, et complète le dépôt :
- **B29** : **Retour** depuis Grille et cues revient à la page d'où l'on vient (Doublons, Diagnostic,
  Analyser), dans l'état où on l'a laissée ; sinon à l'onglet, comme avant.
- **B30** : les sons réanalysés depuis la Bibliothèque (ou une autre page) apparaissent dans la liste
  Analyse de Téléchargements & analyse pendant l'analyse.
- **B31** : Pause puis Lecture ne relance plus le son de Grille et cues quand cette page est restée
  ouverte derrière un autre onglet ; le lecteur du bas ne suit la page que lorsqu'elle est affichée.
- **B32** (Mac, plein écran : ouvrir Doublons renvoyait au bureau) et **B33** (Mac : petit saut du son en
  écoute en ouvrant / fermant le choix de playlist) : cause pas encore reproduite hors Mac ; la rc.8
  **note dans le journal** les fenêtres en trop à l'ouverture d'une page et les retards du son
  (« Audio late by… »). Le testeur Mac refait le test et **envoie le journal**.
- **C78** : code de conduite, guide de contribution, politique de sécurité, modèle de pull request.

Les tests rc.5, rc.6 et rc.7 encore à faire (Mac, platines) restent valables. Dans le suivi : « rc8 · NAV-1 ».

## NAV — Retour vers la page d'origine (B29)
| # | Étapes | Attendu |
|---|---|---|
| NAV-1 | Accueil ▸ **Doublons**, ouvrir un groupe ; puis ouvrir **Grille et cues** sur un son, puis **Retour**. | Retour dans l'outil Doublons, sur le même groupe (pas à l'Accueil). Un deuxième **Retour** ramène à l'Accueil. |
| NAV-2 | Même chose depuis le **Diagnostic** et depuis la page **Analyser**. | Retour sur la page d'origine à chaque fois. |

## ANA — Liste Analyse (B30)
| # | Étapes | Attendu |
|---|---|---|
| ANA-1 | Ouvrir **Téléchargements & analyse** ; dans la Bibliothèque, sélectionner des sons **déjà analysés** ▸ clic droit ▸ Analyser ▸ **Réanalyser** ; revenir sur Téléchargements & analyse. | Les sons apparaissent en haut de la liste Analyse (« En file », « Analyse… », « Analysé »), en même temps que la barre de progression. |

## LEC — Lecture après Grille et cues (B31)
| # | Étapes | Attendu |
|---|---|---|
| LEC-1 | Lancer un son A depuis la Bibliothèque ; ouvrir **Grille et cues** sur A ; cliquer l'onglet **Bibliothèque** ; lancer un son B ; **Pause** puis **Lecture** (barre du bas ou Espace). | C'est B qui reprend, pas A. La forme d'onde défilante du bas montre B. |
| LEC-2 | Revenir sur la page Grille et cues de A (rouvrir A) ; **Lecture**. | La page reprend la main : Lecture joue A depuis son curseur (comme en rc.4). |
| LEC-3 | (Testeur Mac) Même chose que LEC-1 sur Mac. | B reprend. |

## MAC — Diagnostic des deux bugs Mac (B32, B33)
| # | Étapes | Attendu |
|---|---|---|
| MAC-1 | (Testeur Mac) DJSync **en plein écran** ▸ ouvrir **Doublons**, puis **Diagnostic**, puis **Analyser**. | Idéalement plus de retour au bureau. Sinon : **Retours ▸ Envoyer les logs** juste après (le journal dit quelle fenêtre s'est ouverte en trop). |
| MAC-2 | (Testeur Mac) Recherche ▸ écouter un son ▸ **Télécharger** (choix de playlist), puis fermer le choix. | Idéalement aucun saut. Sinon : envoyer les logs (lignes « Audio late by… » ou « Audio stream short… »). |

## COM — Dépôt prêt pour la communication (C78)
| # | Étapes | Attendu |
|---|---|---|
| COM-1 | Après la fusion : GitHub ▸ dépôt ▸ *Insights* ▸ *Community standards*. | Tout est coché (code de conduite, contribution, licence, politique de sécurité, modèles d'issues et de PR). |
| COM-2 | Onglet *Security* ▸ *Report a vulnerability*. | Le formulaire de signalement privé s'ouvre. |
| COM-3 | Ouvrir une pull request de test vers main (sans la fusionner), puis la fermer. | Description pré-remplie par le modèle. |

## R. Retour
Après les tests : **Retours ▸ Envoyer les logs**, en précisant les numéros qui ne donnent pas le résultat attendu.
