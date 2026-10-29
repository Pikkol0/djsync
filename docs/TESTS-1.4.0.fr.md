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
