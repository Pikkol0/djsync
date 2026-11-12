# Scénarios de test — DJSync 1.4.1

Lot « analyse, Grille et cues » (spec : `claude/spec-1.4.1.md` dans le projet). Numérotation : thème en 3 lettres + n°
(voir `revues/numerotation-tests.md`) ; dans le suivi : « 141 · IMP-13 ». Rangés par bloc, pour pouvoir tester en
plusieurs fois. Les fiches encore en cours (A05, C46, B11, B12, A02 détection, C71, C131, C59, C77) auront leurs
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
| TAC-5 | Tous | Windows, macOS, Linux | (**C145**) Quatre tâches en même temps (TAC-1 + TAC-4), volet déplié puis replié ; zoom 200 % ; écran de 768 px de haut. | Au plus 3 cartes visibles, les autres en défilant ; rien de coupé ; replié, un anneau par tâche. |

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
