# Scénarios de test — DJSync 1.3.2

Confort et prise en main : accueil au premier lancement (**C54**), guide « Premiers pas » (**C68**),
raccourci menu Démarrer / Applications (**C70**), version sur l'Accueil (**C73**), réglages par défaut
(**C57**), sons hors playlist (**C56**), vrais boutons en bout de ligne (**C58**), écoute immédiate
depuis la Recherche (**C74**), page Analyser plus claire (**C76**). Outil Doublons : même titre mais son
différent (**C80**), barre de progression et vérification prioritaire (**C84**), fusion sans fenêtre avec
Annuler (**C82**), aperçu des cues et bouton Cues (**C79**). Les scénarios de `docs/TESTS-1.3.1.fr.md`
restent à faire s'ils ne sont pas cochés.

1.3.2-rc.6 à rc.2 : correctifs des tests KO et des signalements de testeurs (sections en tête).

Numérotation : thème en 3 lettres + n°, propre à la version. Dans le suivi : « 132 · DOU-1 ».

## 1.3.2-rc.6 : forme d'onde de Grille et cues, playlists en chargement (04/11)
Le relevé de la rc.5 a montré la vraie cause du blocage toutes les ~8 s : le redessin de la forme d'onde 3 bandes (un point Qt par pixel), maintenant fait en bloc (~40 fois plus rapide).

**Sous Windows** (et sur Mac par le testeur Mac) : GRI-6, BIB-9.

| # | Refait | Étapes | Attendu |
|---|---|---|---|
| GRI-6 | GRI-5 | (**B50**) Grille et cues : lire un son 2 min ; zoomer, dézoomer pendant la lecture ; puis Retours ▸ Envoyer mes logs. | Plus aucun freeze périodique ; forme d'onde identique (bleu, orange, blanc), nette à 200 %. Journal : pas de « UI blocked » ni d'« Audio late » réguliers. |
| BIB-9 | — | (**B52**) Bibliothèque de l'ordinateur : télécharger et analyser une dizaine de sons, puis ouvrir plusieurs playlists ; Envoyer mes logs. | Les playlists s'ouvrent, jamais de chargement sans fin. Si la bibliothèque a été refermée entre-temps, le journal dit par quoi (« Computer library closed by … ») et « reopening it ». |

## 1.3.2-rc.5 : blocage toutes les ~8 s pendant la lecture (04/11)
Refait le test KO de la rc.4 (GRI-4). La rc.4 a supprimé les saccades (vérification de Rekordbox) ; il restait un blocage de 250 à 780 ms toutes les ~8 s, image et son ensemble. La rc.5 fait le nettoyage de la mémoire de Python par petits passages réguliers, sans passage complet pendant la lecture, et écrit dans le journal ce qui bloque si un blocage reste.

**Sous Windows** (et sur Mac par le testeur Mac) : GRI-5.

| # | Refait | Étapes | Attendu |
|---|---|---|---|
| GRI-5 | GRI-4 | (**B50**) Grille et cues : lire un son 2 min juste après avoir lancé DJSync ; puis ouvrir Doublons, revenir dans Grille et cues et relire 1 min ; puis Retours ▸ Envoyer mes logs (pas besoin de joindre le fichier : il est lu dans le mail). | Plus de freeze toutes les ~8 s. Journal : plus de « Audio late » réguliers ; « worst gap » sous ~100 ms. S'il reste un blocage : des lignes « Slow garbage collection » et/ou « UI blocked for more than 350 ms during playback » disent ce qui bloque. |

## 1.3.2-rc.4 : freezes de la lecture (04/11)
Refait le test KO de la rc.3 (GRI-3). Le journal de la rc.3 montrait l'affichage rapide (~65 images/s) mais des blocages de 120 à 700 ms toutes les ~8 s, le son en même temps : c'était la détection de Rekordbox (contrôle des clés, toutes les 4 s), très lente sous Windows. Les autres tests de la rc.3 restent valables (DEM-14 encore à faire, et la partie Mac).

**Sous Windows** (et sur Mac par le testeur Mac) : GRI-4, RKB-1.

| # | Refait | Étapes | Attendu |
|---|---|---|---|
| GRI-4 | GRI-3 | (**B50**) Grille et cues : lire un son 2 min juste après avoir lancé DJSync ; puis ouvrir Doublons, revenir dans Grille et cues et relire 1 min ; puis Retours ▸ Envoyer mes logs. | Curseur et son fluides, plus de petits freezes réguliers. Journal : plus de « Audio late » toutes les ~8 s ; « worst gap » sous ~100 ms la plupart du temps ; aucune ligne « Slow drive check » (si elle apparaît, elle dit quelle partie du contrôle des clés est lente). |
| RKB-1 | — | (**B50**) Ouvrir Rekordbox, attendre ~10 s, regarder l'Accueil ; fermer Rekordbox, attendre ~10 s. | L'Accueil affiche « Rekordbox ouvert » puis repasse à fermé, comme avant (la détection a changé de méthode sous Windows). Écrire dans la bibliothèque de l'ordinateur reste refusé tant que Rekordbox est ouvert. |

## 1.3.2-rc.3 : correctifs après les tests de la rc.2 (04/11)
Refont le test KO de la rc.2 (colonne « Refait ») et couvrent les signalements du 04/11. Les tests de la rc.2 encore à faire (ANA-3, ANA-4, MAJ-4, DOU-11/12/14, Mac) restent valables.

**Sous Windows et sur Mac** (le testeur Mac fait la partie Mac) : ANA-5, BIB-7, BIB-8, DOU-17, GRI-3, PAR-6, DIA-2, DIA-3, DEM-13, DEM-14.

| # | Refait | Étapes | Attendu |
|---|---|---|---|
| ANA-5 | — | (**B49**) Bibliothèque de l'ordinateur avec des sons sur une clé débranchée (E:) : Téléchargements & analyse ▸ **Tout analyser** ; puis Bibliothèque ▸ bouton **Analyser** (sans sélection) ; puis une sélection qui contient un son introuvable. | « Tout analyser (n) » ne compte pas les sons introuvables. Pendant l'analyse, ces sons sont marqués « fichier sur E:, pas branché » (orange), jamais « Échec ». Message de fin : « … 0 en échec. n fichiers introuvables (écartés) : n sur E: (pas branché). » avec **Voir dans le Diagnostic**. |
| BIB-7 | — | (**C124**) Même bibliothèque ▸ Tous les titres. | Les sons introuvables ont une petite icône ⚠ rouge devant le titre et le titre grisé ; au survol, la bulle dit pourquoi (« Fichier sur E:, pas branché… » ou « Fichier introuvable… »). « Non analysés » ne les compte plus. |
| BIB-8 | — | (**C124**) Arbre de la Bibliothèque ▸ **Introuvables (n)** ; clic droit dessus. | L'entrée (icône ⚠, rouge quand n > 0) liste ces sons ; en haut, le bouton **Voir dans le Diagnostic** ouvre Fichiers introuvables ; le clic droit propose la même chose. Sur une clé sans fichier manquant : « Tous les fichiers sont là ». |
| DOU-17 | DOU-15 | (**B41**) Doublons ▸ groupe « Chargé » (ou un groupe où la meilleure version est introuvable). | Les versions dont le fichier existe sont **comparées entre elles** (« Référence », « Même son » ou « Variante ») ; « file not found » sur les introuvables ; un fichier présent mais illisible : pastille orange « Illisible » ; s'il ne reste qu'une version lisible : « Non comparé : seule version lisible » (bulle explicative). |
| GRI-3 | — | (**B50**) Grille et cues : lire un son 1 min, juste après avoir lancé DJSync, puis avec Doublons ouvert ; puis Retours ▸ Envoyer mes logs. | Curseur fluide, plus de petits freezes réguliers ni de craquements. Journal : « Playback frames (beat grid): … fps, … ms per drawing, … ms other drawings, … ms work per frame, worst gap … ms, n gap(s) over 50 ms » : à joindre (il dira ce qui bloque si des freezes restent). |
| PAR-6 | — | (**B51**) Paramètres : faire défiler la page à la molette ou au pavé tactile en passant sur les listes (langue, couleur…) et les compteurs. | La page défile, aucune valeur ne change. Après un clic dans une liste, la molette change sa valeur comme avant. |
| DIA-2 | — | (**C127**) Accueil ▸ **Diagnostic** ▸ onglet Doublons ▸ revenir à l'Accueil ▸ **Diagnostic**. | Le Diagnostic rouvre sur **Doublons** (le dernier onglet), aussi après avoir relancé DJSync. Un lien précis (Accueil ▸ Doublons, « Voir dans le Diagnostic ») ouvre toujours son onglet. |
| DIA-3 | — | (**C126**) Diagnostic ▸ Fichiers introuvables (bibliothèque de l'ordinateur, clé E: débranchée) ▸ **Cocher ceux de E:** ▸ **Retirer les n cochés**. | Chaque son a une case ; « Tout cocher » et « Cocher ceux de E: » cochent ; le bouton dit le nombre. La confirmation prévient que rebrancher E: ne les fera pas revenir et que les fichiers ne sont pas touchés ; après, ils ne sont plus dans la liste ni dans la Bibliothèque. |
| DEM-13 | — | (**C123**) Tout premier lancement (dossier neuf sans `.djsync`). | La fenêtre s'ouvre **agrandie** (barre des tâches visible). Ensuite, DJSync rouvre comme on l'a laissée. |
| DEM-14 | — | (**C128**) Premier lancement ▸ étape Bienvenue, en français puis en anglais, à 100 % puis 200 %. | Titre en grand, une phrase d'accroche plus grande que le texte, trois points avec une icône chacun ; remerciements en petit, **centrés**. Aucun texte coupé. |

## 1.3.2-rc.2 : correctifs après les tests de la rc.1 (02/11)
Refont les tests KO de la rc.1 (colonne « Refait ») et couvrent les signalements de testeurs du 02/11.

**Sous Windows et sur Mac** (le testeur Mac fait la partie Mac) : DEM-11, PAR-3, PAR-4, PAR-5, BIB-4, BIB-5, BIB-6, REC-1, ANA-3 (clé débranchée = `/Volumes/…`), DIA-1, DOU-15, DOU-16, LEC-5, MAJ-5. Windows seulement : DEM-10.

| # | Refait | Étapes | Attendu |
|---|---|---|---|
| DEM-8 | DEM-3 | (**C68**) Aide ▸ onglet **Premiers pas** ; README. | Les six étapes seulement : plus de « Questions fréquentes », ni dans l'app ni dans le README. |
| DEM-9 | DEM-4 | (**C70**) Paramètres ▸ section **DJSync**. | La case « Retrouver DJSync dans le menu Démarrer / Applications », GitHub / Licence / Composants tiers et « Revoir l'accueil » sont dans la carte DJSync, plus dans « Retours et confidentialité ». |
| DEM-10 | — | (**B36**, B43) Windows : double-clic sur DJSync.exe dans l'Explorateur (depuis la clé, puis depuis le disque). | Après l'écran de chargement, la fenêtre de DJSync est **devant** l'Explorateur. Journal : « Window brought to the front » (avec la méthode) ; plus « taskbar icon flashing ». |
| DEM-11 | — | (**B44**) Premier lancement (dossier neuf sans `.djsync`), à 100 % puis à 200 %. | Fenêtre plus grande, aucun texte coupé. Langue : deux grandes cartes, un clic choisit, **Valider** passe à la suite. Bienvenue : gros bouton **⭐ Mettre une étoile sur GitHub** en couleur, avec une ligne d'explication ; « Commencer » à côté. |
| DEM-12 | — | (**C119**) README (haut), accueil, Paramètres ▸ DJSync. | « Un grand merci à Tazyh pour son aide aux tests. » (et en anglais), seul nom cité. |
| PAR-3 | PAR-2 | (**C57**, B42) Paramètres ▸ **Réglages par défaut** ▸ confirmer. | Après la remise à zéro (fenêtre reconstruite), la notification « Réglages par défaut rétablis » s'affiche bien en bas à droite, avec **Annuler** ; Annuler remet les réglages d'avant. |
| PAR-4 | — | (**C121**) Paramètres : faire défiler ; cliquer les sections du volet de gauche ; chercher « mp3 ». | Toutes les sections sur une seule page, chacune sous son titre ; un clic dans le volet fait défiler jusqu'à la section ; en défilant à la main, la section surlignée suit. La recherche n'affiche que les cartes trouvées, sous leur titre. Lien « export.pdb » de l'Accueil : défile jusqu'à Bibliothèques. |
| PAR-5 | — | (**B45**, **B46**) Paramètres en français ; puis zoom à 180 % (et 150 %, 200 %). | « Couleur du thème et du logo » entier (passe à la ligne au besoin). Bouton lecture du lecteur et de Grille et cues, poignées des curseurs et boutons radio restent **ronds** à tout zoom, aussi juste après avoir changé le zoom. |
| BIB-4 | BIB-1 | (**C56**) Bibliothèque de l'ordinateur et clé. | « Hors playlist » a sa propre icône (rond barré) en bleu quand il y a des sons ; « Tous les titres » rappelle « n hors playlist » ; sur l'ordinateur, le rappel parle de la Collection de Rekordbox. |
| BIB-5 | BIB-2 | (**C56**) Hors playlist ▸ **glisser** un son sur une playlist de l'arbre. | Survoler une playlist la surligne sans l'ouvrir ; au lâcher, le son est ajouté et sort de « Hors playlist ». Même chose depuis « Tous les titres ». |
| BIB-6 | BIB-3 | (**C58**) Bibliothèque (son analysé), Recherche, page Analyser. | Les boutons en bout de ligne sont **visibles** : petit bouton avec fond, bordure et icône (Grille et cues, Télécharger, Analyser), survol marqué. |
| REC-1 | — | (**B39**) Recherche « sls », fenêtre agrandie. | Pas de grand vide à droite : le Titre prend la place, la colonne du bouton Télécharger garde sa petite largeur, tout à droite. |
| ANA-3 | ANA-1 | (**C76**) Bibliothèque de l'ordinateur avec des sons sur une clé débranchée (E:) ▸ Analyser. | Ces sons sont marqués « ⚠ fichier sur E:, pas branché » et écartés (« n fichiers introuvables (écartés) ») ; la durée estimée s'affiche ; pendant l'analyse, « encore environ n min ». Plus de « 11 en échec ». |
| ANA-4 | ANA-2 | (**C76**) Réanalyser des sons déjà analysés par DJSync (case cochée). | Ils sont analysés ; un éventuel échec a sa raison dans le journal (« Analysis failed for track … »), à joindre si besoin. Les sons analysés par Rekordbox restent « déjà analysé ». |
| DIA-1 | — | (**B40**) Bibliothèque de l'ordinateur ▸ Diagnostic ▸ Fichiers manquants, avec une clé débranchée. | En haut : « n sur E: (pas branché) » ; sur chaque son : « sur E:, pas branché » ; le détail explique que c'est une clé ou un disque débranché (souvent un son ajouté à Rekordbox depuis une clé). |
| DOU-15 | — | (**B41**) Doublons ▸ groupe avec un fichier introuvable et un fichier abîmé. | Pastilles à leur taille, centrées (plus de grands blocs) ; pas de « Non comparé » sur un fichier introuvable ; écouter le fichier abîmé : « Impossible de lire « … » : fichier abîmé, incomplet… », la cause brute entre parenthèses. |
| DOU-16 | — | (**B47**) Doublons pendant la vérification ▸ **Retour** ▸ rouvrir Doublons. | Retour ramène à la page d'avant **sans fermer** l'outil : à la réouverture, même groupe et la vérification a continué. Seul **Fermer** ferme l'outil. |
| LEC-5 | — | (**C85**) Lire un son analysé depuis la Bibliothèque ; Paramètres ▸ Général. | Plus de forme d'onde défilante au-dessus du lecteur (elle n'est que dans Grille et cues) ; la case « Forme d'onde défilante » a disparu. |
| MAJ-5 | MAJ-1 | (**C96**) Paramètres ▸ DJSync. | Sur une ligne : « Version : » et la liste déroulante des versions, la case « Afficher les versions de test (rc) », puis le bouton d'installation à droite (« Mettre à jour vers … » / « Revenir à la … »). Cocher / décocher la case relit la liste. |

## Ajouts du 28/10 (soir) : B34, C95, C96
| # | Étapes | Attendu |
|---|---|---|
| DOU-11 | (**B34**) Doublons ▸ un groupe avec beaucoup de versions (ou la fenêtre réduite) | Le détail du groupe défile ; les lignes ne sont jamais tassées ; Fusionner / Plus tard / Fermer restent visibles en bas. Un autre groupe s'affiche en haut. |
| DOU-12 | (**C95**) Doublons pendant la vérification (« Vérification du son… x / N ») ▸ cliquer l'Accueil (ou Grille et cues d'un son) ▸ revenir par Accueil ▸ **Trouver les doublons** | La même page revient, sur le même groupe ; la vérification a continué pendant ce temps (le compteur a avancé), elle ne repart pas de zéro. |
| DOU-13 | Doublons ▸ **Fermer**, puis le rouvrir | Nouvelle recherche (normal) ; la vérification va vite pour les sons déjà vérifiés (empreintes en cache). |
| MAJ-1 | (**C96**) Paramètres ▸ DJSync : case **Afficher les versions de test (rc)** et bouton **Choisir une version…** | La case remplace l'ancien menu « Versions proposées » ; elle est cochée sur une version de test. |
| MAJ-2 | **Choisir une version…** | Liste des versions publiées pour ce système, la plus récente en haut, avec la date ; « installée » sur la tienne ; décocher la case retire les rc. **Nouveautés** ouvre la page de la version. |
| MAJ-3 | Choisir une version **plus récente** ▸ **Mettre à jour vers …** | Même installation que la mise à jour habituelle (progression, Redémarrer). |
| MAJ-4 | Choisir une version **plus ancienne** (ex. 1.2.4) ▸ **Revenir à la …** | Avertissement d'abord (réglages et bibliothèques gardés ; une version ancienne peut ne pas relire ce qu'une plus récente a écrit) ; après confirmation, installation puis redémarrage dans cette version. Revenir ensuite à la version de test par le même chemin. |

## A. Démarrage (C54, C68, C70, C73)
| # | Étapes | Attendu |
|---|---|---|
| DEM-1 | Version portable dans un dossier neuf (sans dossier `.djsync`) : lancer DJSync. | Accueil en deux étapes : choix English / Français (langue du système présélectionnée, le texte change tout de suite), puis Bienvenue avec « Mettre une étoile au projet sur GitHub », la case du raccourci, « Premiers pas » et « Commencer ». « Passer » partout. |
| DEM-2 | Fermer et relancer ; puis remplacer DJSync.exe par une autre version et relancer. | L'accueil ne revient pas. Paramètres ▸ DJSync ▸ **Revoir l'accueil** le rouvre. |
| DEM-3 | Aide ▸ onglet **Premiers pas**. | Six étapes (préparer la clé, télécharger, analyser, cues, vérifier, éjecter) et la FAQ ; même contenu dans le README (FR et EN). |
| DEM-4 | Paramètres ▸ DJSync : cocher « Retrouver DJSync dans le menu Démarrer / Applications ». Taper « DJSync » dans la recherche Windows (Spotlight sur Mac, menu des applications sous Linux). | DJSync est trouvé, avec son icône, et se lance. Décocher : le raccourci disparaît. Depuis le code source, la case est grisée avec une explication. |
| DEM-5 | Version sur clé : cocher le raccourci, changer la clé de port (autre lettre), relancer DJSync depuis la clé, puis utiliser le raccourci. | Le raccourci suit la nouvelle lettre. |
| DEM-6 | Regarder le bas de l'Accueil. | « DJSync 1.3.2 » discret (« version de test » pour une -rc) ; clic = Paramètres ▸ DJSync. Si une mise à jour existe : « x.y.z disponible » à côté. |

## B. Paramètres (C57)
| # | Étapes | Attendu |
|---|---|---|
| PAR-1 | Changer le thème, le zoom et un réglage du lecteur, puis Paramètres ▸ **Réglages par défaut**. | Confirmation qui dit ce qui est remis à zéro, case « Garder la langue et les dossiers et bibliothèques choisis » cochée. Après « Rétablir » : thème et zoom d'origine tout de suite, sans redémarrer ; langue et bibliothèques gardées. |
| PAR-2 | Juste après, cliquer **Annuler** dans le message. | Les réglages précédents reviennent. |

## C. Bibliothèque (C56, C58)
| # | Étapes | Attendu |
|---|---|---|
| BIB-1 | Bibliothèque ▸ arbre de gauche : entrée **Hors playlist**. | Compteur et liste des sons qui ne sont dans aucune playlist, avec le rappel qu'ils ne se voient sur platine que dans la liste de tous les morceaux. |
| BIB-2 | Glisser un de ces sons sur une playlist. | Il quitte la liste « Hors playlist », le compteur baisse. Quand il n'en reste plus : « Chaque son est dans au moins une playlist ✓ ». |
| BIB-3 | Bibliothèque : colonne **Grille et cues** en bout de ligne ; Recherche : colonne **Télécharger** ; page Analyser : bouton par son. | De vrais petits boutons (fond, bordure, survol, info-bulle). Un clic agit sans sélectionner la ligne. |

## D. Recherche et lecteur (C74)
| # | Étapes | Attendu |
|---|---|---|
| LEC-1 | Recherche : écouter un résultat. | Le lecteur affiche tout de suite le titre, l'artiste et la pochette, avec une animation de chargement, puis la lecture démarre. |
| LEC-2 | Cliquer très vite sur Écouter pour deux résultats différents. | Seul le second est joué. |
| LEC-3 | Couper le réseau, écouter un résultat. | Message « Impossible d'écouter « … » », pas de lecteur figé. |

## E. Page Analyser (C76)
| # | Étapes | Attendu |
|---|---|---|
| ANA-1 | Bibliothèque : sélectionner quelques sons ▸ clic droit ▸ Analyser. | En haut : résumé (n sons, durée estimée) et bouton **Analyser** bien visible. Liste des sons avec leur état (à analyser, déjà analysé, Rekordbox) et une case pour en retirer. |
| ANA-2 | Cocher « Réanalyser aussi les titres déjà analysés par DJSync », lire l'explication, lancer. | La page reste ouverte et suit l'avancement son par son (en attente, fait, échec). « Continuer en arrière-plan » la quitte sans arrêter l'analyse. |

## F. Doublons (C80, C84, C82, C79)
| # | Étapes | Attendu |
|---|---|---|
| DOU-1 | Diagnostic ▸ Doublons sur une grosse bibliothèque. | Fine barre en haut : « Recherche des titres proches… » puis vérification par le son groupe par groupe (n / total) ; elle disparaît à la fin. La liste reste utilisable. |
| DOU-2 | Clic droit sur un groupe pas encore vérifié ▸ **Vérifier ce groupe maintenant** (ou le bouton dans le détail). | Le groupe est vérifié juste après celui en cours. |
| DOU-3 | Un groupe où un son a le même titre mais un son différent (remix, autre morceau). | Ce son reste en bas, grisé, « Même titre, son différent (jamais supprimés) » : on peut l'écouter, **Modifier le titre** ou dire « Ce n'est pas un doublon ». Il n'est jamais supprimé par la fusion. |
| DOU-4 | Groupe sans aucun vrai doublon. | Il est rangé dans la section « Mêmes titres, sons différents (n) » en bas de la liste ; le compteur de l'Accueil ne le compte pas. |
| DOU-5 | **Garder celle-ci** sur un groupe. | Pas de fenêtre de confirmation : le groupe disparaît, le suivant s'affiche ; message « n version(s) de « … » seront supprimées dans 10 s » avec **Annuler**. |
| DOU-6 | Refaire une fusion et cliquer **Annuler** (message, ou bouton « Annuler la dernière fusion » de l'outil) avant 10 s. | Le groupe revient tel quel ; rien n'a changé sur la clé (ouvrir dans Rekordbox si besoin). |
| DOU-7 | Fusionner puis attendre 10 s. | Les autres versions sont supprimées, cues reprises ; la clé est à jour. Paramètres ▸ Bibliothèques : délai réglable à 5, 10 ou 30 s. |
| DOU-8 | Fusionner, puis fermer DJSync (ou éjecter) avant la fin du délai. | La fusion est appliquée avant de fermer ; au relancement, le groupe n'existe plus. |
| DOU-9 | Groupe dont une version a des hot cues, une boucle et des mémoires. | Sous chaque version, une fine barre : lettres en couleur, boucle en segment, mémoires en petit triangle ; au survol, position et longueur de boucle. La version dont on garde les cues est surlignée et une ligne dit « Après la fusion : … ». |
| DOU-10 | Bouton **Cues** d'une version, puis **Retour**. | Grille et cues de ce son s'ouvre directement (sans passer par le lecteur) ; Retour revient aux Doublons sur le même groupe. |

## G. Fin de la 1.3.2 : vue d'ensemble (C51), lecture fluide (C52), Windows (B36), Doublons (C98), Import (C101)
| # | Étapes | Attendu |
|---|---|---|
| GRI-1 | Ouvrir **Grille et cues** sur un son analysé. | La vue d'ensemble du son est dans la page, entre la forme d'onde zoomée et les hot cues ; le lecteur du bas n'en a plus. Fond noir, forme d'onde posée en bas (bleu dessous, orange puis blanc par-dessus), étiquette carrée de la couleur de chaque hot cue avec sa lettre en haut, triangle rouge (orange pour une boucle) pour chaque mémoire en bas, zone affichée en grand juste cadrée. Clic ou glissé : la vue et la lecture suivent. |
| GRI-2 | Lancer la lecture dans Grille et cues, curseur volant puis fixe. | Défilement fluide ; curseur rouge vif, plein, avec un léger halo ; jamais de petit retour en arrière. |
| LEC-4 | (Mac surtout) Lecteur du bas : forme d'onde défilante pendant la lecture. | Défilement régulier (~60 images/s), sans retour en arrière ni artefact ; le journal contient toutes les 10 s « Playback frames (player): … fps ». |
| DEM-7 | (Windows) Lancer DJSync.exe depuis l'Explorateur (double-clic), puis depuis le menu Démarrer et depuis une clé. | La fenêtre de DJSync s'ouvre devant l'Explorateur ; à défaut, son icône clignote dans la barre des tâches. |
| DOU-14 | Doublons : choisir un groupe, puis « Vérifier ce groupe maintenant » ou fusionner un autre groupe. | Le groupe affiché est en surbrillance (fond d'accent et barre à gauche), même quand on clique ailleurs ; la sélection et la position de la liste restent après sa mise à jour. |
| IMP-1 | Onglet **Importer**. | Sous le champ : « Sources acceptées : » et une pastille par source (Spotify, YouTube, YouTube Music, SoundCloud) ; la bulle dit ce qui est lu, la limite (100 / 200) et un exemple ; rappel « Coller une liste… ». Le champ et l'écran vide citent les mêmes sources. |
| IMP-2 | Coller un lien d'un autre site (Deezer, Apple Music…) et **Lire le lien**. | Message : « Lien non reconnu. Sources acceptées : Spotify, YouTube, YouTube Music, SoundCloud (ou « Coller une liste… »). » |
