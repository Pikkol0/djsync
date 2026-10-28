# Scénarios de test — DJSync 1.3.0-rc.9

La rc.9 est une version de **diagnostic pour le Mac**, après les tests de la rc.8 :
- **B32** (Mac, plein écran : ouvrir Doublons affiche le bureau) : l'enregistrement d'écran du testeur
  montre une fenêtre ouverte ~0,4 s après la page, puis refermée ~0,3 s plus tard (écran noir « DJSync »,
  puis bureau). Pendant 3 s après l'ouverture d'une page, le journal note maintenant **chaque fenêtre qui
  apparaît et disparaît** (type, nom, taille, textes, délais en ms), ainsi que la perte de premier plan
  de DJSync et la sortie du plein écran.
- **B33** (Mac : blanc d'environ 1/4 s en ouvrant le choix de playlist en écoute) : la mesure des retards
  du son est corrigée (plus de faux retards de plusieurs minutes après un arrêt de la carte son) et le
  journal donne le pire retard. Le correctif du blanc lui-même viendra ensuite.
- Journal plus lisible : les sons sans empreinte audio (sons Apple Music, clé absente) ne sont plus notés
  un par un (5 premiers, puis un compte).

Tests sur Mac : le .dmg et la suite de tests automatique se font sur la machine du testeur Mac
(`DJSYNC_VERSION=1.3.0-rc.9 packaging/build_macos.sh`, voir `revues/tests-mac-par-mail.md`).
Dans le suivi : « rc9 · MAC-1 ».

## MAC — Diagnostic (B32, B33)
| # | Étapes | Attendu |
|---|---|---|
| MAC-1 | (Testeur Mac) DJSync **en plein écran** ▸ Accueil ▸ **Trouver les doublons** ; si le bureau s'affiche, revenir dans DJSync ; puis **Retours ▸ Envoyer les logs** tout de suite. | Le journal contient des lignes « window shown after … ms » / « window gone after … ms » et « App state: inactive » qui désignent la fenêtre en cause. |
| MAC-2 | (Testeur Mac) Recherche ▸ écouter un son ▸ **Télécharger** (choix de playlist), puis fermer le choix ; refaire 2 ou 3 fois ; **Envoyer les logs**. | Plus de « Audio late by » de plusieurs minutes ; les retards réels donnent leur valeur et le pire (« worst since last note »). |
| MAC-3 | (Testeur Mac) Construire le .dmg et lancer la suite de tests sur le Mac. | « self-test OK » et aucun test en échec. |

## W — Rien n'a changé ailleurs
| # | Étapes | Attendu |
|---|---|---|
| W-1 | (Auteur, Windows) Ouvrir Doublons, Diagnostic, Analyser ; écouter un son, Pause / Lecture. | Comme en rc.8. |

## R. Retour
Après les tests : **Retours ▸ Envoyer les logs**, en précisant les numéros qui ne donnent pas le résultat attendu.
