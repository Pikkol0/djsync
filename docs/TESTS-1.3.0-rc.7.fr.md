# Scénarios de test — DJSync 1.3.0-rc.7

La rc.7 reprend les KO de la rc.5 et un bug vu pendant le test Mixxx :
- **C63** (rc5 · DOU-1 KO) : un seul outil Doublons. Le Diagnostic n'a plus sa propre liste de doublons :
  sa ligne « Doublons (n groupes) » ouvre l'outil Doublons, qui sait maintenant aussi remplacer toutes
  les versions par une version propre téléchargée.
- **C39** (rc5 · LEC-2 KO) : un saut pendant la lecture s'entend tout de suite. Le son en cours est gardé
  décodé en mémoire (jusqu'à 12 min, ~10 Mo par minute) et la carte son n'est plus rouverte (Windows, Linux).
- **B28** : clé retirée puis rebranchée avant que DJSync le voie : rouverte toute seule, un seul message,
  plus de « disk I/O error » ni de proposition de rapport.
- Build : 2 tests automatiques qui ne peuvent pas tourner sous Windows y sont sautés (le contrôle
  « tests (windows-latest) » repasse au vert).

Les tests de la rc.6 et ceux de la rc.5 non faits restent valables. Numérotation : thème + n° ;
dans le suivi : « rc7 · DOU-1 ».

## DOU — Un seul outil Doublons (C63)
| # | Étapes | Attendu |
|---|---|---|
| DOU-1 | Accueil ▸ **Diagnostic**. | Une seule ligne « Doublons (n groupes) » en haut de la liste ; à droite, un bouton **Ouvrir les doublons**. Plus de liste de doublons propre au Diagnostic. |
| DOU-2 | Cliquer **Ouvrir les doublons** ; puis, depuis l'Accueil, ouvrir l'outil **Doublons** directement. | La même interface dans les deux cas, avec les mêmes groupes. |
| DOU-3 | Dans un groupe : **Chercher une version propre à télécharger**. | Les versions trouvées s'affichent sous le groupe (écoute possible) ; le choix de la version à garder et le titre saisi ne bougent pas. |
| DOU-4 | Sur une version trouvée : **Télécharger et remplacer** ▸ confirmer. | Le son propre est téléchargé et remplace toutes les versions du groupe dans leurs playlists, hot cues recalés (comme rc1 · D5) ; le groupe quitte la liste. |
| DOU-5 | Refaire les tests rc5 · DOU-2 à DOU-8 s'ils ne sont pas faits. | Comme décrit en rc.5. |

## LEC — Saut pendant la lecture (C39)
| # | Étapes | Attendu |
|---|---|---|
| LEC-1 | Page **Grille et cues**, un m4a en lecture : attendre 2 s, puis cliquer ailleurs sur la forme d'onde, appuyer sur un hot cue, cliquer dans la barre du lecteur du bas. | Chaque nouvel endroit s'entend tout de suite, sans trou ni bout de l'ancien passage ; le curseur y est déjà. |
| LEC-2 | Même chose sur un MP3 et sur un son long (plus de 12 min). | Pareil pour le MP3 ; le son long marche comme en rc.6 (pas gardé en mémoire). |
| LEC-3 | (Testeur Mac) Refaire LEC-1 sur macOS. | Saut immédiat (le son est en mémoire ; sur Mac la carte son est encore rouverte, comme avant). |

## CLE — Clé retirée puis rebranchée (B28)
| # | Étapes | Attendu |
|---|---|---|
| CLE-1 | Clé ouverte dans DJSync : la retirer **et la rebrancher tout de suite** (en moins de 4 s), puis cliquer sur une playlist. | Un seul message « La clé … a été retirée puis rebranchée : DJSync l'a rouverte » ; la bibliothèque se recharge ; pas de « disk I/O error », pas de proposition de rapport. |
| CLE-2 | Retirer la clé et attendre 10 s avant de la rebrancher. | Comme en rc.4 : « retirée sans être éjectée », puis réouverture au rebranchement. |

## DEM — Build
| # | Étapes | Attendu |
|---|---|---|
| DEM-1 | (Auteur) Après le tag : Actions ▸ Build. | Tous les contrôles verts, y compris « tests (windows-latest) ». |
