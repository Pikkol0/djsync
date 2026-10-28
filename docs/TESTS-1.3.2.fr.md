# Scénarios de test — DJSync 1.3.2

Confort et prise en main : accueil au premier lancement (**C54**), guide « Premiers pas » (**C68**),
raccourci menu Démarrer / Applications (**C70**), version sur l'Accueil (**C73**), réglages par défaut
(**C57**), sons hors playlist (**C56**), vrais boutons en bout de ligne (**C58**), écoute immédiate
depuis la Recherche (**C74**), page Analyser plus claire (**C76**). Outil Doublons : même titre mais son
différent (**C80**), barre de progression et vérification prioritaire (**C84**), fusion sans fenêtre avec
Annuler (**C82**), aperçu des cues et bouton Cues (**C79**). Les scénarios de `docs/TESTS-1.3.1.fr.md`
restent à faire s'ils ne sont pas cochés.

Numérotation : thème en 3 lettres + n°, propre à la version. Dans le suivi : « 132 · DOU-1 ».

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
