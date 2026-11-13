# Scénarios de test — DJSync 1.4.1

Lot « analyse, Grille et cues » (spec : `claude/spec-1.4.1.md` dans le projet). Numérotation : thème en 3 lettres + n°
(voir `revues/numerotation-tests.md`) ; dans le suivi : « 141 · IMP-13 ». Rangés par bloc, pour pouvoir tester en
plusieurs fois. Les fiches encore en cours (A05, C46, B11, B12, A02 détection, C71, C131, C77…) auront leurs
scénarios quand elles seront codées.

## Dossier surveillé (B95)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| IMP-13 | Tous | Windows, macOS, Linux | (**B95**) Dossier surveillé déjà utilisé (des sons rangés dans « DJSync imported », dont un dans un sous-dossier). Paramètres ▸ Bibliothèques : « Désactiver », enregistrer ; supprimer la playlist « Dossier surveillé » ; puis rechoisir le même dossier et enregistrer. | En quelques secondes, la playlist « Dossier surveillé » revient avec tous les sons déjà importés (sous-dossiers compris), sans doublon, et un message « n sons remis dans la playlist ». Aucun fichier du dossier n'a bougé. Les sons rangés mais absents de la bibliothèque sont importés. |
| IMP-14 | Tous | Windows, macOS, Linux | (**B95**) Avec une ancienne playlist « Importés » / « Imported » créée par une version d'avant la 1.4.0 : activer le dossier surveillé. | L'ancienne playlist est renommée « Dossier surveillé » et complétée ; pas de deuxième playlist. |
| IMP-15 | Tous | Windows, macOS, Linux | (**B95**) Dossier surveillé actif : redémarrer DJSync deux fois. | Rien ne se passe au redémarrage (le rattrapage n'est fait qu'à l'activation) ; les nouveaux fichiers posés dans le dossier sont toujours importés comme avant. |

## Grille et cues (C177, C92, A02)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| GRI-1 | Tous | Windows, macOS, Linux | (**C177**) Ouvrir Grille et cues sur un son analysé. | Les numéros de mesure en haut de la forme d'onde commencent à 0 : 0, 1, 2… ; la 9e mesure porte le 8. Sur la platine et dans Rekordbox, rien ne change (grille et cues identiques). |
| GRI-2 | Tous | Windows, macOS, Linux | (**C92**) Grille et cues : cocher « Aimant », choisir « 1 temps », cliquer un peu à côté d'un temps ; puis « 1/4 de temps » et poser un hot cue entre deux temps ; puis maintenir Alt et poser un autre hot cue. | Avec l'aimant, le curseur saute sur le temps le plus proche ; au quart, le cue se pose sur le quart de temps le plus proche ; avec Alt, exactement où est le curseur. Aimant décoché : le curseur suit la souris, les cues se calent au temps comme avant. Le choix est gardé après fermeture de la page. |
| GRI-3 | Tous | Windows, macOS, Linux | (**A02**, boutons) Son lu à 90 BPM au lieu de 135 (ou l'inverse) : sélectionner un temps sur un kick, « BPM × 3/2 » (ou « × 2/3 »), écouter, enregistrer. | Le BPM passe à 135 (ou 90), le temps sélectionné ne bouge pas, la grille tombe sur les kicks. Les boutons ont une bulle qui explique le cas. |

## Cues placés (C60)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| CUE-1 | Tous | Windows, macOS, Linux | (**C60**) Bibliothèque (clé, puis bibliothèque de l'ordinateur) : regarder la colonne « Cues » ; passer la souris sur une cellule ; trier par cette colonne. | Une pastille par hot cue posé, à sa couleur ; « — » si aucun ; « · » si seulement des mémoires. Bulle « 3 hot cues, 1 boucle, 2 mémoires ». Tri par nombre de hot cues. Colonne masquable par le bouton Colonnes. |
| CUE-2 | Tous | Windows, macOS, Linux | (**C60**) Arbre de la Bibliothèque ▸ « Sans hot cue ». Poser un hot cue sur un des sons (Grille et cues ▸ Enregistrer), revenir. | La liste montre les sons sans hot cue, avec leur nombre dans l'arbre. Après l'enregistrement, le son sort de la liste et sa pastille apparaît dans la colonne. |
| CUE-3 | Tous | Windows, macOS, Linux | (**C60**) Téléchargements et analyse ▸ liste du bas ; Diagnostic ▸ Améliorer. | Même colonne « Cues » dans ces deux listes. |
| CUE-4 | Testeur Windows | Windows | (**C60**) Clé avec plus de 1 000 sons : ouvrir la Bibliothèque. | L'interface reste fluide ; la colonne se remplit en quelques secondes la première fois, tout de suite ensuite. |

## Installation et CI (B84, C181)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| INS-1 | Testeur Windows | Windows | (**B84**) Build empaqueté : copier DJSync.exe dans `C:\Program Files\djsync` (en administrateur), puis le lancer en utilisateur normal (double-clic). | DJSync s'ouvre (première fois : fenêtre d'installation) ; ses fichiers vont dans `%LOCALAPPDATA%\DJSync` (dossiers `app` et `data`), rien n'est écrit dans Program Files. Les réglages sont gardés d'un lancement à l'autre. Paramètres ▸ DJSync ▸ mise à jour : la page de la release s'ouvre au lieu du remplacement automatique. |
| INS-2 | Tous | Windows | (**B84**, non-régression) DJSync.exe à la racine d'une clé, puis dans Documents. | Comme avant : dossier caché `.djsync` à côté de l'exe, réglages gardés, mise à jour depuis l'application. |
| CI-2 | Claude | Windows, Linux | (**C181**) Passe complète `ci/full` sur la branche de la rc. | Windows en 3 lots et Linux en 2, chacun sous 45 min ; les tests de zoom et de langue tournent en parallèle des autres. |

## Site (C179)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| SIT-1 | Auteur | Navigateur | (**C179**) Après la fusion sur main : ouvrir https://pikkol0.github.io/djsync/ , puis `#fr`, puis le bouton de langue ; sur ordinateur et sur téléphone. | Page détaillée : fonctions, captures, installation par système, questions, limites. Navigateur en français : la page s'ouvre en français. Rien de coupé sur téléphone, liens de téléchargement justes. |

## Tâches longues dans le volet (C145)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| TAC-1 | Tous | Windows, macOS, Linux | (**C145**) Lancer une analyse, puis des téléchargements pendant qu'elle tourne ; replier le volet, le redéplier. | Une carte par tâche : « ANALYSE » (« 3 / 10 · son », → ⏸ ■) et « TÉLÉCHARGEMENTS » (« 1 / 2 », → ⏸ ⏹). Volet replié : une petite carte par tâche, avec son anneau et sa bulle. Chaque carte disparaît dès que sa tâche est finie. |
| TAC-2 | Tous | Windows, macOS, Linux | (**C145**) Analyse en cours : ⏸, attendre 30 s, ⏸ (reprendre) ; puis ■. | Pause : le son en cours finit, aucun autre ne commence (« En pause ») ; reprise : la suite continue, aucun son sauté ni analysé deux fois (compteur juste à la fin). ■ : « ARRÊT… » puis la carte disparaît. |
| TAC-3 | Tous | Windows, macOS, Linux | (**C145**) Plusieurs téléchargements en file : ⏸ sur la carte « TÉLÉCHARGEMENTS », attendre, puis reprendre ; fermer DJSync pendant une pause. | Pause : les fichiers en cours finissent et sont ajoutés, les suivants restent « en attente » ; reprise : ils partent. DJSync se ferme normalement pendant une pause. |
| TAC-6 | Tous | Windows, macOS, Linux | (**C145**) Lancer par erreur un très long son (mix de plusieurs heures) suivi de 3 autres ; pendant son téléchargement, ⏹ sur la carte « TÉLÉCHARGEMENTS ». Recommencer avec un son Soulseek. Puis Téléchargements ▸ sélectionner un son arrêté ▸ Réessayer. | En quelques secondes le téléchargement en cours s'arrête, sans attendre la fin du fichier ; les 3 autres ne partent pas. Tous restent dans la liste, « ■ Arrêté » ; aucun fichier partiel dans le dossier de la clé, rien d'ajouté à la bibliothèque. Un son déjà en « Ajout à la clé… » finit normalement. La carte disparaît. Réessayer relance le son choisi. |
| TAC-4 | Tous | Windows, macOS, Linux | (**C145**) Diagnostic ▸ Doublons (plusieurs groupes) puis Uniformiser : revenir à l'Accueil ; sur chaque carte ⏸, ⏸, ⏹ ; puis → . | Une carte « DOUBLONS » et une « UNIFORMISER ». Pause et arrêt : l'élément en cours finit toujours ; après ⏹, les groupes non vérifiés restent dans la liste (« Vérifier maintenant » marche). → rouvre la page telle quelle. Fermer la page fait disparaître sa carte. |
| TAC-5 | Tous | Windows, macOS, Linux | (**C145**, socle de **C140**) Quatre tâches en même temps (TAC-1 + TAC-4), volet déplié puis replié ; zoom 200 % ; écran de 768 px de haut. | Au plus 3 cartes visibles, les autres en défilant ; rien de coupé ; replié, un anneau par tâche. Quand la hauteur manque : cartes en une ligne (« 12 / 40  ANALYSE », → ⏸ ⏹ gardés, détail dans la bulle) et entrées du volet qui défilent (voir DIA-5). |

## Page Haute qualité (C133, C134, C170, C175, C171, C167, C147)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| HQ-1 | Tous | Windows, macOS, Linux | (**C133**) Volet ▸ « Haute qualité » ; puis Rechercher : taper « bicep glue », choisir le mode « Haute qualité ». | La page s'ouvre (entrée entre Rechercher et Bibliothèque, Ctrl+3). Depuis Rechercher, elle s'ouvre avec le texte tapé et lance la recherche ; le menu de Rechercher revient sur « Classique ». Bandeau Soulseek (coupé / prêt / connecté, port, partage) et « Réglages Soulseek » qui ouvre Paramètres ▸ Téléchargement ; compteurs P2P si Soulseek est activé. Rien n'a disparu de Téléchargements ni de Paramètres. |
| HQ-2 | Tous | Windows, macOS, Linux | (**C171**) Lancer une recherche avec Soulseek activé. | Barre animée et « 1 / 3 sources terminées · 12 résultats · 4 s » qui avance ; deuxième barre « Soulseek : écoute des réponses, encore 5 s » (un temps, pas un pourcentage) ; le bandeau disparaît quand tout a répondu. Une source en panne : « sans réponse : Audius ». |
| HQ-3 | Tous | Windows, macOS, Linux | (**C134**) Filtres : Sans perte seulement, puis durée « 4:28 » ± 5 s, puis place libre (Soulseek) ; trier par kbps, Durée, Taille, Année. | Le bouton devient « Filtres actifs » ; les lignes qui ne conviennent pas disparaissent, y compris celles qui arrivent après coup ; « n masqués par les filtres ». Tri numérique (96 < 128 < 320, 59 s < 1:15 < 10:00). Filtres gardés au redémarrage, sans toucher à ceux de Rechercher. |
| HQ-4 | Tous | Windows, macOS, Linux | (**C170**, **C175**) Regarder les colonnes Qualité, Année, Licence, Pair ; survoler. | « FLAC 16/44 », « MP3 VBR ≈ 245 », « MP3 320 » en texte doré (sans perte) ou argenté (≥ 300), jamais en pastille ; bulle « Qualité annoncée, vérifiée après le téléchargement ». Pochette et année pour Internet Archive ; dossier du pair dans la bulle du titre. Case vide quand la source ne donne rien. |
| HQ-5 | Tous | Windows, macOS, Linux | (**C167**) Sélectionner une ligne Soulseek ▸ « Écouter un équivalent (YouTube Music) » (ou double-clic). | La version officielle de YouTube Music se lance dans le lecteur ; « Version approchante en écoute : Bicep - Glue ». Aucun résultat : message, rien n'est joué. Le téléchargement n'est pas touché. |
| HQ-6 | Tous | Windows, macOS, Linux | (**C147**) Chercher un artiste de netlabel (Internet Archive) ; cliquer ▸ sur une ligne d'album ; trier par Durée ; filtrer « Titres seulement » puis « AAC » ; « Télécharger l'album ». | Un album se voit d'un coup d'œil : icône de disque, « Album · 12 titres », fond différent ; ses titres s'insèrent dessous, en retrait, numérotés, dans l'ordre de l'album, et y restent au tri. Un filtre qui exclut tous ses titres masque l'album. Télécharger l'album propose une playlist au nom de l'album (jamais créée d'office). Mention « fichiers déposés par des utilisateurs d'archive.org ». Les albums de Rechercher ont la même icône et l'étiquette « Album ». |

## Paramètres ▸ Téléchargement (C143)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| PAR-1 | Tous | Windows, macOS, Linux | (**C143**) Ouvrir Paramètres ▸ Téléchargement ▸ Qualité ; survoler chaque ligne. | Six lignes : « M4A · AAC ≈ 128 kbps, sans conversion », « M4A · AAC 256 kbps (meilleur flux) », « MP3 · 320 / 256 / 192 / 128 kbps », chacune avec « ≈ x Mo/min » ; « (meilleur flux) » sur une seule ligne ; bulles : conversion de l'Opus pour le meilleur flux, « pour gagner de la place » pour 192 et 128. Plus de case « Même volume », plus de case « meilleur flux » dans YouTube. |
| PAR-2 | Tous | Windows, macOS, Linux | (**C143**) Installation 1.4.0 avec MP3 choisi (puis une autre avec meilleur flux) : passer en 1.4.1. | Sans question : MP3 → « MP3 · 320 kbps » ; meilleur flux → « M4A · AAC 256 kbps (meilleur flux) » ; sinon la première ligne. Les sons déjà téléchargés ne sont pas touchés. |
| PAR-3 | Tous | Windows, macOS, Linux | (**C143**) Choisir « MP3 · 192 kbps », télécharger un son YouTube, puis un son SoundCloud déjà en MP3. | Le premier est un MP3 à 192 kbps (fait depuis le meilleur flux) ; le second reste tel quel (jamais de MP3 → MP3). |

## Fichiers introuvables (C173)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| INT-1 | Tous | Windows, macOS, Linux | (**C173**) Renommer le fichier d'un son qui a un double présent (même titre, même artiste, durée à 3 s près) ; Diagnostic ▸ Fichiers introuvables. | La ligne porte « 1 version existante » ; le détail montre la version (titre, artiste, format, durée, playlists). Un son de durée très différente n'est pas rapproché. |
| INT-2 | Tous | Windows, macOS, Linux | (**C173**) « Fusionner avec celle-ci » : refuser, puis recommencer et confirmer. | La confirmation nomme les deux entrées ; refus : rien ne change. Accepté : une seule entrée reste, avec les playlists de l'entrée introuvable (et ses hot cues si la version n'en avait pas). Jamais en lot. |
| INT-3 | Tous | Windows, macOS, Linux | (**C173**) « Tout retirer » avec une ligne qui a une version existante. | La confirmation signale « n d'entre eux ont une version existante » et les nomme. |

## Diagnostic dans le volet (C140, D19)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| DIA-1 | Tous | Windows, macOS, Linux | (**C140**) Volet ▸ « Diagnostic » (entre Téléchargements et Importer) ; passer d'un onglet à l'autre ; revenir à la Bibliothèque. | Une seule entrée, sans sous-entrées. Premier ouvert : onglet « Un son », puis le dernier onglet utilisé. L'entrée reste cochée sur tous les onglets (Uniformiser compris) et se décoche ailleurs. « Diagnostic (n) » : somme des compteurs déjà connus, rien avant le premier comptage. Ctrl+1 à 8 inchangés (Ctrl+4 : Bibliothèque). |
| DIA-2 | Tous | Windows, macOS, Linux | (**C140**) Onglet « Un son » : taper deux mots (titre et artiste, ou album) ; Entrée ; choisir un son. | La liste se filtre en tapant (tous les mots, sans tenir compte des majuscules ni des accents saisis tels quels) ; Entrée prend le premier. Fiche : titre, artiste, album, durée, BPM, tonalité (pastille Camelot), format, qualité supposée, genre, année, playlists, fichier (introuvable signalé). Quatre actions **sous** les infos ; pas de cartes d'outils. |
| DIA-3 | Tous | Windows, macOS, Linux | (**C140**) Sur la fiche : « Modifier les infos… » (enregistrer un nouveau titre), « Ses doublons » (un son sans doublon, puis un avec), « Mesurer la qualité », « Afficher dans l'explorateur / le Finder ». | La fiche suit la modification. Sans doublon : « Aucun doublon trouvé pour ce son. » ; avec : l'onglet Doublons s'ouvre sur son groupe. Qualité : « Mesure de la qualité… » puis la ligne « Qualité supposée » remplie. Le dossier s'ouvre avec le fichier sélectionné. |
| DIA-4 | Tous | Windows, macOS, Linux | (**C140**) Choisir un son, aller sur « Doublons » puis revenir sur « Un son ». Volet replié : cliquer l'icône Diagnostic. | Le même son est de nouveau affiché. Replié : une icône (bulle « Diagnostic (n) »), aucun menu ; la page s'ouvre. |
| DIA-5 | Tous | Windows, macOS, Linux | (**C140**, socle) Écran de 768 px (ou fenêtre de 700 px de haut) avec 2 tâches ; puis Windows à 125 % ; puis 1080p à 200 %, déplié et replié ; puis 1280 × 800 à 100 %. | Rien d'écrasé ni de coupé : cartes des tâches et de la bibliothèque en une ligne quand la hauteur manque (« DEMO · 29,5 Go libres », détail dans la bulle) ; les entrées défilent (barre visible dépliée, molette repliée) ; l'entrée cochée reste visible. Aide et Réduire sur une ligne (l'une sous l'autre en volet replié). À 1280 × 800 : cartes entières. Onglets du Diagnostic trop larges : les plus longs ne gardent que l'icône et le compteur (nom dans la bulle), jamais de texte coupé ; les 4 actions passent sur 2 lignes. |

## Analyser à nouveau un son analysé par Rekordbox (C131, D20, B96)

Avant ces tests : garder une copie de la clé (ou de la bibliothèque) d'essai. Sons « de Rekordbox » = exportés depuis Rekordbox, avec hot cues, mémoires et au moins une boucle.

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| REA-1 | Tous | Windows, macOS, Linux | (**C131**) Bibliothèque : sélectionner 3 sons de Rekordbox et 2 sons de DJSync déjà analysés ▸ Analyser la sélection. Lancer sans cocher la case ; puis cocher « Analyser à nouveau les titres déjà analysés » et lancer. | Une seule case, pour tous les sons (plus de mention « jamais touchés »). Sans la case : rien n'est refait. Avec : la fenêtre « Que réanalyser sur les titres analysés par Rekordbox ? » s'ouvre (« 3 titres… »), trois cases, « Grille et BPM » seule cochée ; elle dit que les cues ne sont jamais touchés, que l'analyse de Rekordbox est gardée et que la grille de DJSync peut être moins juste. Annuler : rien n'est lancé. |
| REA-2 | Tous | Windows, macOS, Linux | (**C131**) Valider la fenêtre avec « Grille et BPM » seule. Ensuite : Grille et cues sur un des sons de Rekordbox ; comparer avec la copie de la clé. | Les 5 sons sont analysés. Sons de Rekordbox : grille et BPM de DJSync ; tonalité et formes d'onde inchangées ; hot cues, mémoires, boucles, noms et couleurs à l'identique. Le dossier DJSync_Backups/anlz-rekordbox contient un dossier par son de Rekordbox réanalysé. |
| REA-3 | Tous | Windows, macOS, Linux | (**C131**) Relancer REA-1 sur les mêmes sons ; puis clic droit sur un seul son de Rekordbox ▸ « Analyser à nouveau » ; puis Paramètres ▸ Analyse : cocher « Tonalité » et « Formes d'onde », enregistrer, réanalyser un son de Rekordbox. | La fenêtre à trois cases ne revient pas : pour un lot, confirmation courte (« 3 titres analysés par Rekordbox seront modifiés : Grille et BPM ») ; pour un seul son, analyse directe. Paramètres ▸ Analyse montre les trois cases avec le choix fait ; après changement, tonalité et formes d'onde du son sont celles de DJSync, cues toujours identiques. Tout décoché : ces sons sont laissés tels quels (« ignorés »). |
| REA-4 | Tous | Windows, macOS, Linux | (**C131**) Clic droit sur un son de Rekordbox réanalysé ▸ « Rétablir l'analyse de Rekordbox » ; avant cela, lui ajouter un hot cue dans Grille et cues. Clic droit sur un son jamais réanalysé. | Confirmation, puis grille, BPM, tonalité et formes d'onde de Rekordbox revenus ; le hot cue ajouté est toujours là. L'entrée reste disponible ensuite (la copie d'origine n'est jamais retirée, même après 30 corrections de grille). Son jamais réanalysé : pas d'entrée « Rétablir ». |
| REA-5 | Auteur | Windows | (**C131**) Ordinateur, Rekordbox ouvert : « Analyser à nouveau » sur un son de Rekordbox. Fermer Rekordbox, recommencer, rouvrir Rekordbox. | Rekordbox ouvert : son en échec avec le message habituel (fermer Rekordbox), rien d'écrit. Fermé : grille de DJSync dans Rekordbox, cues identiques (liste des cues de Rekordbox inchangée) ; le son n'est pas devenu un son « de DJSync » (Grille et cues le dit toujours « analysé par Rekordbox »). |
| REA-6 | Testeur platines | Platines | (**C131**, grille réécrite) Clé avec 3 sons de Rekordbox réanalysés (grille et BPM), dont un MP3, et 1 son rétabli (REA-4). Charger chaque son, lancer depuis un hot cue, activer la quantification, avancer dans le morceau à la molette (MP3). | Sons chargés sans erreur ; BPM et grille de DJSync affichés ; hot cues, mémoires et boucles à leur place ; recherche dans le MP3 normale ; pas de phrases affichées (retirées avec la grille). Le son rétabli se comporte comme avant. |
| REA-7 | Auteur | Windows, macOS, Linux | (**B96**) Son de DJSync avec des cues : abîmer la liste des cues de son fichier ANLZ0000.DAT (éditeur hexadécimal, dans une balise PCOB), puis « Analyser à nouveau ». Même essai avec le .EXT tronqué d'un son de Rekordbox. | Le son est compté en échec avec la raison (« cues … could not be read » ou « Unreadable analysis file ») ; ses fichiers d'analyse et sa ligne dans la bibliothèque ne changent pas (avant : cues perdus sans message). |

## Qualité supposée (C46, banc A05)

Mesures du banc (81 pistes de CD, 2 025 copies) et règles : `djsync/analysis/spectrum.py` ; `python tools/quality_calibrate.py bench_out/features.jsonl` les rejoue. Les mesures de la 1.4.0 ne sont pas reprises : les sons sont mesurés de nouveau à la demande (onglet Qualité, « Recalculer la qualité supposée ») ou à la prochaine analyse.

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| QUA-1 | Auteur | Windows | (**C46**, remplace 140-QUA-8) Le fichier « YouTube → MP3 320 → WAV » de 140-QUA-8 : clic droit ▸ Recalculer la qualité supposée. | Plus jamais « Sans perte » ni doré : « ≈ 320 » (ou moins), signalé faux sans perte. |
| QUA-2 | Auteur | Windows | (**C46**) Un vrai FLAC de CD, un MP3 320 acheté, un MP3 128, un « FLAC » fait depuis un MP3 128 : Recalculer la qualité supposée. | FLAC : Sans perte (doré). MP3 320 : ≈ 320. MP3 128 et faux FLAC : ≈ 128, le faux FLAC signalé. |
| QUA-3 | Tous | Windows, macOS, Linux | (**C46**) Un son téléchargé de YouTube (M4A ou Opus), et le même converti en WAV. | ≈ 192 au plus, jamais Sans perte. |
| QUA-4 | Tous | Windows, macOS, Linux | (**C46**) Après la mise à jour, ouvrir la Bibliothèque avec la colonne Qualité supposée. | Les anciennes mesures ne s'affichent plus (case vide) jusqu'à un nouveau calcul ; rien n'est recalculé seul au lancement. Le calcul d'un son prend environ 1 s. |

Limites connues (banc) : un AAC 256 ou un MP3 V0 remis en WAV peuvent passer pour du sans perte (AAC 256 : 94 %, MP3 V0 : 27 %) ; un Opus 128 et un Opus 160 ne se distinguent pas.

## Grille : contretemps et premier temps (B11, B12, A02)

Mesure sur la tour (192 sons, 13/11) après la 1re passe : contretemps 34 → 24, même premier temps 81 → 97 (72 % des grilles justes). 2e passe de B11 (deux indices de plus) : sur 100 sons, contretemps 12 → 9, aucune grille juste qui bascule. A02 : un seul son sur 100 en rapport 3:2 (et un en 4:3) : pas de détection automatique, seulement les boutons × 3/2 et × 2/3 (déjà faits). Mesure complète à refaire sur la tour : `python -m djsync.analysis --compare local --playlist "Échantillon DJSync" --csv bench_out\mesure-b12.csv`.

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| GRI-1 | Auteur | Windows | (**B11**, **B12**) Relancer la commande ci-dessus et comparer au résumé de la mesure de départ (12/11 : BPM 160 / 192, contretemps 34 / 160, premier temps 81 / 160). | Contretemps en baisse nette, premier temps en hausse, BPM identiques au moins aussi nombreux ; aucune famille (house, hardstyle, rap, pop) qui recule. |
| GRI-2 | Testeur platines | Platines | (**B11**, **B12**) Analyser 3 sons hardstyle ou hypertechno et 3 sons pop sur une clé ; les charger sur platine. | Grille sur les kicks (pas entre deux kicks) ; le « 1 » de la platine tombe sur le début des mesures (entrée de la basse, du refrain). |

## Or et argent (C141, D14)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| OR-1 | Tous | Windows, macOS, Linux | (**C141**) Bibliothèque avec un FLAC et un MP3 320 (colonnes Format, Débit) ; recherche Haute qualité (colonne Qualité) ; Recherche (colonne Source « original » / « free download »). | Textes or et argent en dégradé métallique (plus clairs au milieu), en gras ; un reflet les traverse environ toutes les 5 s, décalé d'une ligne à l'autre. Le jaune « ≈ 192 » et le gris restent unis : jamais confondus avec l'or ou l'argent. |
| OR-2 | Tous | Windows, macOS, Linux | (**C141**) Mode léger activé ; puis fenêtre réduite ou autre application au premier plan. | Mode léger : dégradé fixe, plus de reflet. Fenêtre réduite ou inactive : plus aucun redessin (processeur au repos). |

## Onglet Qualité unique (C135)

Remplace les onglets « Mauvaise qualité » et « Améliorer » du Diagnostic (reprend 140-DIA-1, 140-DIA-5, 140-QUA-2, 140-QUA-7 et 131-DIA-10).

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| QLT-1 | Tous | Windows, macOS, Linux | (**C135**) Diagnostic dans le volet : regarder les onglets ; ouvrir **Qualité**. Changer la portée : Toute la bibliothèque, une playlist. | Un seul onglet « Qualité » (plus « Mauvaise qualité » ni « Améliorer »). Liste : titre, artiste, qualité annoncée, qualité mesurée (« non mesurée » en gris tant que rien n'est mesuré), signalé (vidéo, faux, sous le seuil), meilleure version, gain, cues. La portée change la liste. |
| QLT-2 | Tous | Windows, macOS, Linux | (**C135**) Filtres : décocher les trois ; puis cocher seulement « Sous [256 kbps] » et changer la valeur ; puis seulement « Vient d'une vidéo » ; puis seulement « Faux sans perte ». | Rien de coché : tous les sons de la portée. Chaque filtre seul : seulement les sons concernés (un clip, un son tiré de YouTube ; un faux FLAC). Le seuil choisi est retenu à la réouverture. |
| QLT-3 | Tous | Windows, macOS, Linux | (**C135**, C145) « Mesurer la qualité (n) » ; dans le volet des tâches : Pause, Reprendre, puis Arrêter ; relancer. Pendant la mesure, aller dans la Bibliothèque et revenir. | Mesure en arrière-plan, carte « Qualité » dans le volet avec progression, pause, reprise et arrêt. Relancée, elle ne refait que les sons restants (n diminue). La page revient telle quelle. |
| QLT-4 | Tous | Windows, macOS, Linux | (**C135**) Double-clic sur un son (ou « Chercher une meilleure version ») ; modifier l'artiste ou le titre, Chercher ; Écouter un résultat gratuit puis un résultat Soulseek ; Acheter. | Fenêtre « Chercher une meilleure version » : mêmes colonnes et pastilles que la page Haute qualité, plus « Écart de durée » et « Gain ». Versions gratuites suffisantes (≥ 256, même durée) en tête, puis Soulseek, puis le reste. Écouter : le résultat (Soulseek : l'équivalent YouTube Music). Acheter : menu des magasins. |
| QLT-5 | Tous | Windows, macOS, Linux | (**C135**) Un son tiré d'un clip (« Clip officiel ») : détail. Un son MP3 128 qui n'est pas une vidéo : détail. | Clip : YouTube Music et SoundCloud proposent la version audio propre (jamais un autre clip). MP3 128 : pas de YouTube ; YouTube n'est jamais compté « sûr ». |
| QLT-6 | Tous | Windows, macOS, Linux | (**C135**) « Tout chercher », puis « Remplacer tous les sûrs (n) » avec au moins 3 sons ; confirmer. Vérifier playlists et hot cues d'un son remplacé. | **Une seule** confirmation, avec le nombre de sons et les sources ; jamais une fenêtre par son. Remplacement habituel : playlists à la même place, hot cues recalés. |
| QLT-7 | Tous | Windows, macOS, Linux | (**C135**, C140) Bibliothèque : clic droit sur un son ▸ « Qualité et meilleure version (1) » ; puis sur 5 sons. Diagnostic ▸ Un son : choisir un son ▸ Mesurer la qualité. | Un son : onglet Qualité, portée « Sélection (1) », détail ouvert sur ce son. 5 sons : portée « Sélection (5) ». Un son (Diagnostic) : après la mesure, même détail ouvert sur ce son. |
| QLT-8 | Tous | Windows, macOS, Linux | (**C135**) Ignorer un son ; fermer et rouvrir l'onglet. | Le son ne revient pas (même mémoire que l'ancien « Ignorer »). |

## Proposer des cues sur les vraies parties (C71)

Mesure du 13/11 sur 16 sons de la clé de l'auteur (89 hot cues posés à la main), à une mesure près : ancien pas de 32 mesures : 36 % des cues proposés tombent sur un cue de l'auteur, 24 % de ses cues retrouvés ; nouvelle méthode : 56 % et 72 % (54 % et 67 % en laissant chaque son de côté pour le réglage).

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| PCU-1 | Tous | Windows, macOS, Linux | (**C71**) Grille et cues sur un son sans cue (rap, house) ▸ Proposer des cues. | Le bouton dit « Écoute du son… » une à trois secondes, puis la fenêtre « Cues proposés » : une ligne par cue (pad, mesure comptée depuis 0, temps), cochée, avec Écouter. A sur le premier temps de la grille, les autres sur des changements de partie (couplet, refrain, drop, break, outro), au début d'une mesure, au moins 4 mesures d'écart. |
| PCU-2 | Tous | Windows, macOS, Linux | (**C71**) Dans la fenêtre : Écouter deux lignes ; décocher un cue ; Ajouter. Puis Enregistrer. | La lecture part du cue choisi, la fenêtre reste ouverte. Seuls les cues cochés sont posés ; rien n'est écrit avant Enregistrer. |
| PCU-3 | Tous | Windows, macOS, Linux | (**C71**) Son avec A et C déjà posés et une mémoire : Proposer des cues. Son avec les 8 pads pris. Son très plat (une boucle). | A et C ne bougent pas ; aucun cue proposé à moins d'un demi-temps de A ou de C ; une mémoire n'empêche pas un hot cue au même endroit. 8 pads pris : « Aucun pad libre à remplir ». Son plat : seulement A, avec le message « Aucun changement de partie net ». |
| PCU-4 | Auteur | Windows | (**C71**) Les 16 sons de l'échantillon cues : copier la clé, effacer les hot cues de 4 sons, Proposer des cues. | Les cues proposés retombent en grande partie sur tes anciens cues (à une mesure près) ; dire ceux qui manquent ou qui sont en trop. |
