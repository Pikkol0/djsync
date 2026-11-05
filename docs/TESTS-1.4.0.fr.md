# Scénarios de test — DJSync 1.4.0

Sources de meilleure qualité (**C10**, **C26**, **C45**, **C46**, **C47**, **C48**) et confort de lecture
(**C50**, **C51**, **C52**). Numérotation : thème en 3 lettres + n° (voir `revues/numerotation-tests.md`) ;
dans le suivi : « 140 · IMP-1 ».

## IMP — Fichiers de l'ordinateur et dossier surveillé (C26, C10.3)
| # | Étapes | Attendu |
|---|---|---|
| IMP-1 | Bibliothèque (clé) ▸ **Ajouter des fichiers…** : choisir un WAV, un FLAC et un MP3. | Les trois sont copiés dans `Contents/Artiste/Album/` (les originaux ne bougent pas), titre et artiste lus dans les tags (sinon dans le nom « Artiste - Titre »), analysés ensuite si l'analyse après téléchargement est cochée. |
| IMP-2 | Glisser un dossier de l'Explorateur / du Finder sur une playlist de l'arbre. | Tous les fichiers audio du dossier sont ajoutés à cette playlist ; un son déjà présent est signalé (« voir les doublons »). |
| IMP-3 | Bibliothèque de l'ordinateur : ajouter un fichier. | Le son est référencé là où il est (pas de copie) ; le supprimer de la bibliothèque ne supprime pas le fichier. |
| IMP-4 | Paramètres ▸ **Dossier surveillé** : choisir un dossier, garder « Les ranger dans la playlist Importés ». Y copier un WAV (ou y faire arriver un téléchargement de navigateur). | Quelques secondes après la fin de la copie : « Dossier surveillé : 1 nouveau fichier », le son est dans la playlist **Importés** ; le fichier est déplacé dans le sous-dossier `DJSync imported` (jamais supprimé, jamais pris deux fois). Un téléchargement en cours (`.crdownload`, `.part`) n'est pas pris. |

## PLA — FLAC pour les anciennes platines (C26 sens C)
| # | Étapes | Attendu |
|---|---|---|
| PLA-1 | Paramètres ▸ Anciennes platines ▸ **Fichiers FLAC sur la clé** : « Enregistrer en AIFF ». Ajouter un FLAC 24 bit. | Sur la clé, un `.aiff` 24 bit (44,1 ou 48 kHz) avec ses tags ; le FLAC d'origine n'a pas bougé. |
| PLA-2 | (Platines) Lire ce son sur une CDJ-2000NXS ou une XDJ-1000. | Le son se lit. |

## SRC — Sources (C10.1, C10.3, C45, C10.2)
| # | Étapes | Attendu |
|---|---|---|
| SRC-1 | Paramètres ▸ **SoundCloud** : choisir le navigateur où tu es connecté à SoundCloud (ou coller le jeton). Importer un lien SoundCloud dont l'artiste autorise le téléchargement. | La ligne affiche « SoundCloud · original » en doré ; le fichier téléchargé est celui de l'artiste (souvent WAV), jamais converti ; badge doré dans la Bibliothèque. Clic droit : « le flux » ou « le fichier d'origine » au choix. |
| SRC-2 | Importer un lien SoundCloud avec un « Free Download » (Hypeddit, ToneDen…). | « téléchargement gratuit » en argenté ; clic droit ▸ **Ouvrir le téléchargement gratuit de l'artiste** ouvre la page. |
| SRC-3 | Recherche ou Bibliothèque : clic droit sur un son ▸ **Acheter (WAV / FLAC)**. | Sous-menu Beatport, Bandcamp, Traxsource, Juno Download, Qobuz, recherche déjà remplie (artiste + titre, sans « Official Video »). |
| SRC-4 | Recherche ▸ liste **Haute qualité**, taper « artiste titre » puis Entrée. | Résultats d'Internet Archive (souvent FLAC, licence affichée) et d'Audius (MP3 320) ; source, qualité et licence sur chaque ligne, doré pour le sans perte ; **Écouter** fonctionne ; Télécharger ajoute le son. Un FLAC téléchargé reste en FLAC. |
| SRC-5 | Paramètres ▸ **Soulseek** : cocher « Utiliser Soulseek ». | Avertissement (VPN fortement recommandé, droits et fiabilité à ta charge, rien partagé par défaut) ; **Annuler** décoche ; **J'ai compris** l'active. |
| SRC-6 | Nom d'utilisateur nouveau + mot de passe, Enregistrer. Recherche ▸ Haute qualité ▸ « artiste titre » + Entrée. | « Connecté à Soulseek… » ; résultats Soulseek en plus (« Soulseek · FLAC · 16 bit · 44,1 kHz », place libre ou file) ; pas d'écoute avant téléchargement. |
| SRC-7 | Télécharger un FLAC Soulseek, puis ouvrir Téléchargements. | Le son arrive dans la file (« en attente chez l'autre utilisateur » puis %), est ajouté et analysé ; panneau **Soulseek** : graphe des vitesses reçue / envoyée, pairs, file, octets, « ne partage rien ». |
| SRC-8 | Télécharger un « FLAC » qui est en fait un MP3 réencodé (s'il en passe un). | Message « … annoncé en FLAC mais sa vraie qualité est ≈ 128 kbps. Chercher une autre source ? » qui relance la recherche. |
| SRC-9 | Paramètres ▸ Téléchargement ▸ **Meilleur flux YouTube** (décoché par défaut) : cocher, télécharger 3 sons, puis décocher et retélécharger les mêmes. | Avec : AAC 256 ; sans : AAC ~128. Noter la taille des fichiers (Mo par minute) dans la remarque. |

## QUA — Vraie qualité (C46)
| # | Étapes | Attendu |
|---|---|---|
| QUA-1 | Analyser un vrai FLAC et un « FLAC » tiré d'un MP3 128. Bibliothèque ▸ Colonnes ▸ **Qualité réelle**. | Vrai FLAC : « Sans perte », badge doré ; faux : « ≈ 128 kbps » en orange, pas de doré. |
| QUA-2 | Diagnostic ▸ Mauvaise qualité ▸ **Mesurer la qualité réelle (n)**. | Les sons pas encore mesurés le sont (« Qualité réelle : i / n ») ; les faux FLAC et faux 320 apparaissent dans la liste. |

## DIA — Améliorer ma bibliothèque (C47)
| # | Étapes | Attendu |
|---|---|---|
| DIA-1 | Diagnostic ▸ onglet **Améliorer**. | Les sons sous 256 kbps (qualité réelle si mesurée), du plus faible au meilleur ; « Sans perte seulement » élargit la liste. |
| DIA-2 | **Tout chercher**, attendre. | Pour chaque son : meilleure version trouvée (source, artiste, titre) et gain (« AAC 128 → FLAC ») ; « rien de mieux trouvé » sinon. |
| DIA-3 | **Remplacer tous les sûrs**, confirmer. | Rien ne se passe avant la confirmation ; puis les versions sans perte de même durée se téléchargent et remplacent les anciennes (playlists gardées, hot cues recalés). |
| DIA-4 | Clic droit sur un son sans version gratuite ▸ **Acheter**. | Liens vers les magasins. |

## GRI / LEC — Éditeur des cues et du BPM, lecture (C51, C52)
Livrés en **1.3.2** (décision de l'auteur, 28/10) : scénarios dans `docs/TESTS-1.3.2.fr.md` § G (GRI-1, GRI-2, LEC-4).

## COU — Couleur (C50)
| # | Étapes | Attendu |
|---|---|---|
| COU-1 | Paramètres ▸ Apparence ▸ **Couleur**. | Un seul bouton (pastille + nom) ; un menu avec 12 couleurs ; choisir : appliqué partout tout de suite. Une ancienne couleur retirée (ex. Lavande) devient la plus proche. |

## Ajouts du 29/10 : zoom (C102), colonne Playlists (C103), Deezer (C86), mode léger (C65)
| # | Étapes | Attendu |
|---|---|---|
| COU-2 | N'importe où dans DJSync : **Ctrl +** (⌘ + sur Mac) trois fois, puis **Ctrl −**, puis **Ctrl 0**. Puis Ctrl + molette sur la Bibliothèque. | Badge « 110 % », « 120 % »… au centre ; l'interface grandit après une courte pause ; Ctrl 0 revient à 100 % ; la molette avec Ctrl zoome aussi. Paramètres ▸ Général : boutons − / + / 100 % et rappel des raccourcis, plus de curseur. |
| COU-3 | Grille et cues : Ctrl + molette sur la forme d'onde. | C'est la forme d'onde qui zoome (comme avant), pas l'interface. |
| BIB-1 | Bibliothèque : colonne **Playlists**. | Affichée par défaut : « Rap, Warm-up » ou « — » ; la bulle donne le chemin (« Soirées ▸ Club ») ; la recherche trouve les sons par nom de playlist. Clic droit sur un son ▸ « Ouvrir la playlist « … » ». Ajouter le son à une playlist : la colonne se met à jour. |
| IMP-5 | Importer : coller un lien de playlist **Deezer publique** (puis un album, puis un lien court link.deezer.com). | Liste lue, correspondances YouTube Music comme pour Spotify, nom de la playlist proposé. Deezer figure dans « Sources acceptées ». |
| IMP-6 | Importer : lien d'une playlist Deezer **privée**. | « Cette playlist Deezer est privée ou introuvable. Rends-la publique dans Deezer (… ▸ Rendre publique), puis réessaie. » |
| LEC-2 | Paramètres ▸ Général ▸ **Mode léger** : Activé. Lire un son, ouvrir Grille et cues, lancer une analyse pendant la lecture. | Pas de forme d'onde défilante dans le lecteur ; lecture fluide à 30 images/s dans Grille et cues ; l'analyse attend la fin de la lecture. Le journal indique « Machine: … light mode on ». |
| DEM-1 | (PC modeste, ou mode Auto sur un PC à 2 cœurs / 4 Go) Premier lancement. | Fenêtre « Mode léger activé » : Garder / Désactiver, « Ne plus me le rappeler ». |

## ESP — Espace occupé sur l'ordinateur (C27, C129)
| # | Étapes | Attendu |
|---|---|---|
| ESP-1 | (**C27**) Bibliothèque de l'ordinateur ▸ Paramètres ▸ Bibliothèques ▸ Espace occupé ▸ Mesurer à nouveau. | Pendant la mesure, une petite barre d'attente. Ensuite **Musique** = taille de tous les sons de la collection Rekordbox (plusieurs Go, plus 0 B) ; Analyses et pochettes, Bases Rekordbox, Sauvegardes DJSync, Caches comme avant. |
| ESP-2 | (**C129**) Même carte. | La barre couvre **tout le disque** : postes de la bibliothèque en couleur, « Autres fichiers » (gris foncé), Libre. Au-dessus : « Bibliothèque Rekordbox : x Go (y % du disque) · autres fichiers : … · libre : … sur … ». Si des sons sont sur un autre disque (ex. E:) : ligne « Et x Go de musique sur E:\ ». |
| ESP-3 | Même chose sur une clé. | Inchangé (la clé avait déjà « Autres fichiers »). |

## DOW — Barre des téléchargements (B55)
| # | Étapes | Attendu |
|---|---|---|
| DOW-2 | (**B55**) Lancer une dizaine de téléchargements d'un coup, regarder la barre à côté de « Downloads ». | La barre avance d'un son à l'autre jusqu'au bout, sans retomber à 0 quand un son se termine ; elle repart de 0 seulement pour une nouvelle série lancée après la fin de la précédente. |

## rc.2 — retours de tests de la rc.1
| # | Étapes | Attendu |
|---|---|---|
| SCP-1 | (**B64**) Importer une adresse ▸ une playlist SoundCloud d'au moins 100 sons (ex. une playlist de rap). | Chaque ligne a son titre, son artiste et sa durée (plus de « Untitled · Inconnu · 0:00 ») ; les sons protégés sont marqués « protégé : version YouTube Music » en orange, avec leur nombre en haut. |
| SCP-2 | (**B64**) Écouter puis télécharger un son marqué protégé. | La version YouTube Music est lue puis téléchargée (même titre, même durée à peu près) ; plus d'erreur « DRM protected ». Si aucune version n'est trouvée : message clair. |
| SLK-1 | (**B60**) Paramètres ▸ Téléchargement ▸ Soulseek, sur un nouveau profil ou après avoir coché le partage. | Le partage est coché par défaut ; s'il est décoché, le panneau Soulseek dit « ne partage rien : certains pairs vous refuseront ». |
| SLK-2 | (**B60**) Recherche Haute qualité. | La colonne Type affiche, pour chaque pair, « place libre » ou « file N » et sa vitesse (« 1.2 Mo/s »). |
| SLK-3 | (**B60**) Télécharger un fichier proposé par plusieurs pairs, dont un lent ou en file d'attente. | Si rien n'arrive en 60 s (ou refus / « Banned »), la ligne dit « … : essai chez un autre pair » et le téléchargement repart chez un autre ; le son finit par arriver. |
| SLK-4 | (**B59**) Juste après la connexion à Soulseek, lancer une recherche Haute qualité. | Pendant la recherche : squelette et « 0 fichier pour l'instant », jamais « Aucun résultat » ; sans réponse, la recherche est renvoyée une fois toute seule. |
| YTB-1 | (**B66**) Avec un VPN qui déclenche « Sign in to confirm you're not a bot », télécharger un son YouTube. | Message clair (VPN, navigateur) et bouton **Choisir le navigateur** qui ouvre Paramètres ▸ Téléchargement ; après 3 refus, les autres sons YouTube passent en erreur avec le même message (pause). Choisir le navigateur et Enregistrer : les sons refusés repartent. |
| QLT-1 | (**C137**) Paramètres ▸ Téléchargement. | Tableau « Quelle qualité j'obtiens vraiment ? » (équivalent MP3, aigus coupés) ; le format MP3 ne dit plus « 320 » ; choisir MP3 affiche l'avertissement orange, M4A le cache. |
| DIA-5 | (**B58**) Diagnostic ▸ onglet **Améliorer**. | La page Améliorer s'ouvre (plus « Fichiers introuvables ») ; rouvrir le Diagnostic la ramène si c'était le dernier onglet. |
| DIA-6 | (**B63**) Diagnostic ▸ Mauvaise qualité : lancer la mesure, aller dans la Bibliothèque, revenir par le bouton Diagnostic. | La même page revient avec sa mesure en cours ou finie, sans tout recharger. |
| COL-1 | (**B65**) Importer une adresse : glisser le bord d'une colonne, changer de page et revenir. | Seule la colonne glissée change, sa largeur est gardée ; clic droit sur l'en-tête : choix des colonnes. |
| COL-2 | (**B61**) Téléchargements & analyse avec quelques téléchargements. | Le Titre est lisible (jamais 3 lettres) ; l'Heure reste étroite à droite, sans grande colonne vide. |
| ESP-4 | (**C132**) Paramètres ▸ Espace occupé. | « Autres fichiers » à gauche de la barre ; les caches en vert, plus en gris. |
| REG-1 | (**B57**) Aller dans Paramètres ▸ DJSync, quitter, revenir dans Paramètres (en haut de la page). | Le sommaire surligne la section réellement affichée. |
| EXP-1 | (**C139**) Bibliothèque : clic droit sur un son ▸ **Afficher dans l'explorateur** (« dans le Finder » sur Mac). | Le dossier s'ouvre avec le fichier sélectionné ; fichier absent : message clair. |
| CI-1 | (**B56**) GitHub Actions du build v1.4.0-rc.2. | Plus d'échec du test du ramasse-miettes ; build marqué vert si rien d'autre ne casse. |

## rc.3 — retours de tests de la rc.2
| # | Étapes | Attendu |
|---|---|---|
| EXP-2 | (**B68**) Bibliothèque : clic droit sur un son dont le chemin contient des espaces ▸ **Afficher dans l'explorateur**. | L'Explorateur s'ouvre dans le dossier du son, fichier sélectionné (plus Documents). |
| QLT-2 | (**B69**) Paramètres ▸ Téléchargement : faire défiler lentement autour du tableau « Quelle qualité j'obtiens vraiment ? ». | Tableau en cases tracées ; les lignes ne bougent plus. |
| ESP-5 | (**B71**) Paramètres : faire défiler de haut en bas plusieurs fois autour de la carte Espace occupé. | La carte ne se redessine pas et garde sa hauteur ; « Mesurer à nouveau » remesure. |
| NAV-1 | (**B70**) Paramètres ▸ Général ▸ Barre latérale : icônes seules. Cliquer sur chaque page. | Le fond du bouton actif est centré sous l'icône, aligné sur le logo. |
| NAV-2 | (**B73**) Barre latérale en icônes seules, pendant une analyse ou un téléchargement. | Bibliothèque active et Activité : une icône centrée dans un anneau de progression ; survol : texte complet (« Cet ordinateur · … libres »…) ; clic : ouvre la page. |
| QUA-3 | (**B67**) Ouvrir la Bibliothèque après la mise à jour (les mesures sont refaites), colonne Qualité réelle, sur un WAV tiré de YouTube (ex. « Désaccordé »). | Plus « Sans perte » : « ≈ 320 kbps · YouTube » en orange ; un vrai WAV / FLAC reste « Sans perte ». |
| SLK-5 | (**B72**) Améliorer ▸ Remplacer tout avec plusieurs sons trouvés chez le même utilisateur Soulseek. | Un seul téléchargement à la fois chez lui ; les autres partent chez d'autres pairs ou affichent « en attente : un autre téléchargement chez le même utilisateur » ; beaucoup moins d'échecs. |
| SLK-6 | (**B72**) Télécharger depuis un pair qui ne répond pas, puis depuis un pair qui a une file d'attente. | Pair muet : « connexion à l'autre utilisateur… » puis autre pair en ~20 s ; pair avec file : « en file chez l'autre utilisateur (place n) », attente sans coupure à 60 s. |
| SLK-7 | (**B72**) Retours ▸ Envoyer mes logs après une connexion à Soulseek. | Le journal contient « Soulseek listening on port … UPnP on, sharing on ». |

## rc.4 — retours de tests de la rc.3
| # | Étapes | Attendu |
|---|---|---|
| IMP-5 | (**B77**) Paramètres ▸ Dossier surveillé : choisir un dossier, Enregistrer. Copier un M4A puis un FLAC dedans ; attendre 15 s. | Les fichiers passent dans « DJSync imported » et dans la bibliothèque (playlist « Importés » si cochée) ; le journal dit « Watched folder: n file(s) seen, n taken ». |
| SRC-10 | (**B81**) Importer une adresse : « Step Harder – Yungeen Ace » (lien ffm.to) puis un son avec un vrai Free Download (Hypeddit, « FREE DL »). | Step Harder : plus de « free download » ; le vrai Free Download garde sa mention argentée. |
| SRC-11 | (**C151**) Importer une adresse : sélectionner un son avec Free Download. | Bouton « Free Download de l'artiste » en bas ; un clic ouvre la page de l'artiste ; sélection sans Free Download : pas de bouton. |
| IMP-6 | (**C148, B80**) Importer une playlist SoundCloud : cocher, décocher, Maj + clic, case de l'en-tête, Espace sur une sélection. | Vraies cases comme dans Uniformiser ; Maj + clic coche la plage ; l'en-tête montre tout / rien / mélangé ; « n / total cochés » à côté du bouton ; coin du tableau arrondi sans carré qui dépasse. |
| COL-3 | (**C150**) Importer une playlist SoundCloud de 200 sons, fenêtre en plein écran ; puis une recherche Haute qualité. | Source affichée en entier (« SoundCloud · protégé… ») ; le titre n'est pas plus large que le plus long titre ; colonne Bibliothèque vide réduite. |
| SET-1 | (**C152**) Paramètres ▸ Recherche ; survoler l'en-tête « Vues » des résultats. | « Charger le nombre de vues YouTube des titres… » ; bulle « Vues sur YouTube (lectures pour SoundCloud) ». |
| NAV-3 | (**C153**) Pendant un téléchargement ou une analyse : cliquer sur la carte Activité du volet (n'importe où), sur sa flèche, puis en volet replié sur l'anneau. | Toujours Téléchargements et analyse (plus la Bibliothèque). |
| NAV-4 | (**B76**) Replier le volet, fermer DJSync, le relancer ; lancer une analyse et des téléchargements en même temps. | Au lancement, icônes espacées comme après déplier / replier ; anneaux entiers (pas coupés) ; deux anneaux : analyse et téléchargements. |
| QUA-4 | (**B75**) Bibliothèque, colonne Qualité réelle : un son tiré de YouTube (ex. « Désaccordé ») et un vrai MP3 320. Paramètres ▸ Téléchargement : lire le tableau. | YouTube : « ≈ 192 kbps · YouTube » ; vrai MP3 320 : « ≈ 320 kbps » ; tableau à 4 colonnes (débit réel mesuré, équivalent MP3) et sa note sur les sources. |
| DEM-2 | (**C146**) Paramètres ▸ Général ▸ Revoir l'accueil (ou nouveau profil) : langue, présentation, Suivant. Puis Paramètres ▸ Téléchargement. | Étape « Qualité des téléchargements YouTube » : M4A coché (recommandé) ; choisir « Meilleur flux » affiche l'avertissement (≈ 2 fois plus lourd, ≈ 7 Mo pour 3 min 30) ; le choix est repris dans les Paramètres, où l'avertissement n'apparaît que coché. |
| DEM-3 | (**C155**) Premier lancement (profil neuf) avec une mise à jour disponible et un PC modeste. | L'accueil seul d'abord ; ensuite la proposition du mode léger ; la mise à jour arrive en bandeau en haut (« Mettre à jour · Plus tard »), jamais en fenêtre par-dessus. |
| HQ-1 | (**B78**) Rechercher ▸ Haute qualité : « Jul ». | Premiers résultats en ~1 s, Internet Archive en 2-3 s ; morceaux dans l'ordre d'archive.org puis des pistes de l'album ; beaucoup plus de titres de Jul qu'avant. |
| SRC-12 | (**B82**) SoundCloud ▸ Connecté avec Chrome (Windows) ; télécharger un fichier d'origine. Puis importer un lien de son privé sans son code « s-… ». | Libellé « peu fiable sous Windows » ; le flux est téléchargé à la place, avec la raison ; son privé : message clair (lien de partage privé), plus de « HTTP Error 404 » brut. |
| SLK-8 | (**B83**) Améliorer ▸ Remplacer tout avec des sons chez un pair qui met en file ou ne répond pas. | Colonne État : « Connexion au pair… », « En file chez le pair (place n) », « Pair suivant… », « Nouvelle recherche Soulseek… » (plus « Téléchargement 0 % ») ; si aucun pair n'envoie : message final clair. |
| SLK-9 | (**B83**) Se connecter à Soulseek sous VPN, puis sans VPN ; Retours ▸ Envoyer mes logs. | Sous VPN : avertissement « Aucun routeur UPnP trouvé… » dans le panneau Soulseek ; partage coupé : avertissement ; le journal garde les lignes de DJSync et de l'UPnP, sans les centaines de « ConnectToPeer ». |
