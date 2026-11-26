# Scénarios de test — DJSync 1.4.4

Numérotation : thème en 3 lettres + n° (voir `revues/numerotation-tests.md`) ; dans le suivi : « 144 · REC-1 ».
Règle : un test OK sous Windows est validé ; Mac et Linux seulement pour un point qui leur est propre.

## rc.1, lot 1

Fiches codées : C230, C216, C231, C232, C233, C234, C226, C227, C236, C220, C223, C235, C215, C222,
A09 (A : relevé ; B : processus d'analyse selon la mémoire libre), B128 (C : relevé de ce qui gonfle).
Tests automatiques : `tests/test_v144_rc1_ui.py`, `tests/test_v144_rc1_tools.py`.

### Recherche, accueil, apparence

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| REC-1 | Tous | Windows | (**C216**) Rechercher ▸ Lien ou playlist : taper « Daft Punk - One More Time », Entrée, puis « Rihanna - Umbrella ». Cliquer « Chercher 2 sons » (ou Ctrl+Entrée). | Entrée passe à la ligne, le champ grandit (8 lignes au plus, puis il défile) ; les 2 sons sont cherchés comme une playlist importée (cases, Correspondance, téléchargement). |
| REC-2 | Tous | Windows | (**C216**) Coller un lien Spotify ou YouTube seul, Entrée. Survoler le bouton à côté du champ. | Le lien est lu comme avant ; le bouton Coller n'a plus que son icône, « Coller » en bulle ; « Coller une liste… » a disparu. |
| ACC-1 | Tous | Windows | (**C227**) Paramètres ▸ DJSync ▸ revoir l'accueil (ou premier lancement). | Un seul écran : langue, thèmes (6 tuiles), zoom, qualité YouTube (2 choix, le reste replié), raccourci, visite guidée. « Passer » bordé, de la taille de « Commencer », en bas à gauche. |
| ACC-2 | Tous | Windows | (**C227**) Sur l'accueil : choisir le thème « Forêt », puis + au zoom, puis la qualité « Meilleure » ; « Commencer ». | Couleurs et zoom appliqués tout de suite, l'écran se redessine sans perdre la qualité choisie. |
| ACC-3 | Tous | Windows | (**C227**) Revoir l'accueil, « Passer ». | Fermé d'un coup, qualité de téléchargement inchangée, pas de visite guidée. |
| COU-1 | Tous | Windows | (**C226**) Paramètres ▸ Apparence : thèmes prêts (Club, Nuit, Forêt, Café, Prune, Néon, Plein jour, Contraste). | Un clic change le fond et la couleur ensemble ; la tuile du thème en cours est cochée. |
| COU-2 | Tous | Windows | (**C226**) Couleur : les 7 pastilles, puis la pastille de la couleur en cours (« Toutes… »). | 3 familles de 16 couleurs (vives, profondes, pastel), rangées par teinte, toutes lisibles ; fonds Bleu nuit, Brun, Vert sapin, Prune dans « Fond ». |

### Accueil et Paramètres

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| ACU-1 | Tous | Windows | (**C231**) Accueil, une clé ou la bibliothèque de l'ordinateur pas ouverte. | Sa carte n'a que « Connecter » (plus de Diagnostic). Une fois ouverte, Diagnostic revient. |
| ACU-2 | Tous | Windows | (**C232**) Accueil, clé ouverte avec export.pdb à jour, puis une clé dont export.pdb n'est pas à jour. | À jour : plus de pastille verte, « export.pdb est à jour » dans la bulle de « Connectée ». Pas à jour : la pastille orange et « Mettre à jour export.pdb » restent. |
| PAR-1 | Tous | Windows | (**C220**) Depuis l'Accueil, cliquer la pastille export.pdb (ou un lien vers les réglages) ; puis taper « export.pdb » dans la recherche des Paramètres. | Le titre de la section visée, puis les cartes trouvées, sont encadrés de la couleur d'accent un instant. |
| SAU-1 | Tous | Windows | (**C235**) Paramètres ▸ Sauvegardes : choisir « Légères », puis « Supprimer les anciennes ». | Message « Anciennes sauvegardes supprimées : x libérés » ; Espace : Sauvegardes plus petit ; point d'origine et au moins une copie de master.db toujours là. |
| SAU-2 | Tous | Windows | (**C235**) Un réglage « copies » de 5 (ou 20, 50) avant la mise à jour. | Repris en « Légères » (ou « Complètes »). |
| ESP-1 | Tous | Windows | (**C222**) Paramètres ▸ Espace, avec une 2e clé branchée (ou de la musique sur un autre disque). | Sous la barre de la bibliothèque ouverte, « Autres disques » : une barre par disque concerné et par clé branchée, avec libre / total et les mêmes alertes. |

### Grille et cues, lecteur, Doublons, Bibliothèque

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| GRI-1 | Tous | Windows | (**C233**) Grille et cues : glisser la petite barre sous la forme d'onde vers le haut ; fermer, rouvrir un son ; double-clic sur la barre. | Forme d'onde moins haute, hauteur gardée ; double-clic : hauteur automatique. |
| GRI-2 | Tous | Windows | (**C234**) Grille et cues : boutons 3 bandes / Bleu / RGB en haut à droite de la forme d'onde. | Le type change tout de suite, le lecteur et Paramètres ▸ Analyse suivent. |
| GRI-3 | Tous | Windows | (**C215**) Grille et cues d'un son avec pochette ; lecteur en bas. | Pochette en grand à côté du titre dans Grille et cues ; pochette du lecteur plus grande. |
| DOU-1 | Tous | Windows | (**C236**) Diagnostic ▸ Doublons pendant la vérification : « Pause », puis « Reprendre ». | Le groupe en cours finit, le suivant attend ; la tâche du volet suit (en pause / reprise). |
| DOU-2 | Tous | Windows | (**C236**) Décocher « Vérifier automatiquement », sélectionner 3 groupes (Ctrl+clic), « Vérifier les 3 groupes sélectionnés ». | Seuls ces 3 groupes sont vérifiés ; le choix « Vérifier automatiquement » est gardé au prochain lancement. |
| SUP-1 | Tous | Windows | (**C223**) Supprimer 2 sons (un téléchargé par DJSync, un autre), puis Bibliothèque ▸ ☰ ▸ Sons supprimés. | Les 2 sons listés (date, « lien d'origine » quand il existe) ; recherche ; « Retélécharger » ouvre le lien (un son) ou cherche « Artiste - Titre » ; « Retirer de la liste », « Vider la liste ». |

### Légèreté et mémoire (journal)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| MEM-1 | Tous | Windows | (**A09 A**, **B128 C**) Utiliser DJSync 30 min (téléchargements, analyse), puis « Envoyer mes logs ». | Lignes « Memory: RSS … MB (peak …), CPU … %, objects … » toutes les 5 min, avec les types d'objets les plus nombreux quand la mémoire grossit. |
| MEM-2 | Testeur au PC de 4 Go | Windows | (**A09 B**) Analyser 50 sons avec peu de mémoire libre. | Dans le journal : « Analysis processes limited by free memory: … » ; pas de mémoire épuisée. |

### Outils (pas de test à la main)

- **C230** : à la fin du build d'un tag, `metrics/<tag>.json` sur la branche `metrics` (durée, tailles exe / dmg / tar.gz). Vérifié au tag `v1.4.4-rc.1` : `git fetch origin metrics && git show origin/metrics:metrics/v1.4.4-rc.1.json`.

## rc.1, lot 2

Fiches codées : C225, C219, C221, C108, C138, A08 (option A), B125, A09 (B : A1-11).
Bloquées (non codées) : **C107** (clé passée sur platines), **B115**, **B118** (bibliothèque volumineuse d'un testeur), **C15** (essai sur la tour avec Rekordbox 7 ouvert).
Tests automatiques : `tests/test_v144_rc1_lot2_c225.py` (C225, C219), `…_b125.py`, `…_a09.py`, `…_c221.py`, `…_c108.py`, `…_c138.py`, `…_a08.py`.

### Paramètres et aide à l'écran

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| PAR-10 | Tous | Windows | (**C225**) Paramètres : cliquer chacune des 9 sections du volet, fenêtre à 1280×800 puis 860×560. | Une seule section affichée, cartes sur une colonne, contrôles alignés à droite, interrupteurs pour les oui / non, aucune barre de défilement horizontale. |
| PAR-11 | Tous | Windows | (**C225**) Page Général : chercher « soulseek » puis « ffmpeg », puis vider la recherche. | Les cartes trouvées dans les autres sections s'affichent et sont encadrées ; en vidant, retour à Général. |
| PAR-12 | Tous | Windows | (**C225**) Accueil ▸ Espace, pastille export.pdb, Diagnostic ▸ réglage. | Chaque lien ouvre la bonne page (Sauvegardes et espace, Bibliothèques et clés, Avancé) et met la carte en valeur. |
| AID-1 | Tous | Windows | (**C219**) Survoler puis cliquer un ⓘ ; cliquer à nouveau ; rouvrir et cliquer ailleurs. | Texte au survol ; la bulle reste au clic, se ferme au clic suivant ou ailleurs. |
| AID-2 | Tous | Windows, macOS | (**C219**) Accessibilité ▸ « Afficher les infobulles » à non ; survoler des boutons, puis un ⓘ ; relancer DJSync. | Plus aucune bulle ordinaire, les ⓘ marchent ; réglage gardé au redémarrage. |

### Grille et cues : tempo variable, 1er temps

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| TEM-1 | Tous | Windows | (**C221**) Son à 128 : curseur à 1:00, « Changement de tempo », BPM du passage = 140, Entrée ; enregistrer, réanalyser. | La bande montre 128 \| 140, la grille change au repère, BPM au curseur et sous la souris justes ; après réanalyse, même grille. |
| TEM-2 | Testeur platines | Windows | (**C221**) Dans un set, « Nouveau son » puis enregistrer ; ouvrir le son sur platine. | Mémoire « Nouveau son » sur platine ; la grille ne bouge pas. |
| TEM-3 | Tous | Windows | (**C221**) Glisser la poignée d'un repère ; Type ▸ Tempo stable ; Paramètres ▸ Analyse = Classique, puis analyser un beatswitch. | Le repère se cale sur un temps ; le son sort de « Tempo qui change » ; en Classique, grille fixe et rien de détecté. |
| PRT-1 | Auteur (tour) | Windows | (**B125**) Mesure sur les 294 sons Rekordbox du PC fixe : `python -m djsync.analysis --compare local --csv b125.csv`. | Ligne « Grid: same downbeat » ≥ 75 % ; grille à 20 ms inchangée (61,6 %). |
| PRT-2 | Tous | Windows | (**B125**) Bibliothèque, colonne Analyse : « 1er temps : à vérifier » ; ouvrir le son dans Grille et cues, ▶ sur chaque temps, choisir, Enregistrer. | Bandeau et 4 choix « Temps n » ; seuls les numéros de temps changent ; la colonne repasse à « Analysé ». |
| PRT-3 | Tous | Windows | (**B125**) Son à vérifier : choisir le temps proposé par l'analyse, ou « Grille juste ». | Rien à enregistrer, le marqueur disparaît. |

### Bibliothèque : volet Infos, énergie, bascule rapide

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| INF-1 | Tous | Windows | (**C138**) Bibliothèque, clic droit ▸ Infos, puis ↑ / ↓ ; touche I ; relancer DJSync. | Volet à droite qui suit la sélection, rempli (pochette, Analyse, Fichier, Origine, Rekordbox, playlists) ; I ferme / rouvre ; état et largeur gardés. |
| INF-2 | Tous | Windows | (**C138**) Cliquer l'album, le modifier, Annuler ; recommencer, Enregistrer ; modifier l'artiste puis cliquer un autre son. | Boutons seulement après modification ; Annuler rétablit ; Enregistrer met la table à jour ; changement de son : Enregistrer / Abandonner / Rester. |
| INF-3 | Tous | Windows | (**C138**) Fenêtre réduite à 860 px de large (ou zoom réduit), volet Infos ouvert sur un son. | Rien de coupé dans le volet (actions en icônes, libellé en bulle) ; la table garde au moins 300 px quand la place le permet. |
| NRG-1 | Tous | Windows | (**C108**) Analyser un son calme et un son de club ; afficher la colonne Énergie ; clic droit ▸ Énergie ▸ 9, puis Automatique. | Calme < club ; 9 aussi dans le lecteur ; Automatique rend la valeur de l'analyse. |
| NRG-2 | Testeur platines | Windows | (**C108**) Option « Énergie dans le commentaire », analyser un son SoundCloud, le chercher de nouveau. | Commentaire « E7 <lien> » sur platine ; source et doublon toujours reconnus. |
| BIB-1 | Tous | Windows | (**A08**) Ouvrir l'ordinateur, puis une clé, revenir à l'ordinateur, puis à la clé. | Retours presque instantanés ; journal « Open libraries: 2 (1 kept…) » avec la mémoire. |
| BIB-2 | Tous | Windows | (**A08**) Ordinateur gardé en arrière-plan : lancer Rekordbox ; puis clé gardée : la débrancher. | Ordinateur refermé en moins de 10 s (« Rekordbox open ») ; clé refermée (« drive removed ») ; aucune erreur. |
| BIB-3 | Tous | Windows | (**A08**) Clé gardée en arrière-plan (pas l'active) : l'éjecter depuis l'Explorateur. | À observer : refus probable « utilisé par DJSync » (risque connu). |

### Lecteur et mémoire

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| LEC-1 | Tous | Windows | (**A09 B**) Lire un son de 5 min, sauter, hot cue ; puis un mix de plus de 12 min : pause, saut, boucle, fin. | Tout marche ; mémoire +≈ 55 Mo pour 5 min (au lieu de ≈ 110) ; mix : « Playback streamed: … » au journal, mémoire stable. |
| MEM-3 | Auteur (tour) | Windows | (**A08**, **A09 A**) Vraie master.db + vraie clé : 1, 2, 3 bibliothèques ouvertes. | Mémoire notée au journal (« Open libraries… Memory: RSS … ») ; reportée dans le suivi. |

## rc.2

Fiches codées : C15 (mode live, voie XML), B131 + C237 (Grille et cues en onglets, passages éditables), B130, C238,
C239, B118, B132, B133, C240, B134.
Tests automatiques : `tests/test_v144_rc2.py`, `tests/test_v144_rc2_c15.py`.

### Mode live (C15)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| LIV-1 | Auteur (tour ou portable) | Windows | Accueil ▸ Mode live (ou Rechercher ▸ Live) la première fois. Suivre les 3 écrans, « Copier le chemin », régler Rekordbox comme indiqué, cocher « Ne plus afficher ». | Pas à pas en 3 écrans ; chemin de `djsync-live.xml` copié ; l'arbre « rekordbox xml » de Rekordbox montre la playlist « DJSync Live – date ». |
| LIV-2 | Auteur | Windows | Rekordbox ouvert : chercher un son, « Ajouter au live » ; à « Prêt », Actualiser dans Rekordbox, glisser le son sur un deck. Chronométrer. | Moins d'une minute de la demande au son jouable ; BPM, grille et cues identiques à DJSync ; master.db et clé non modifiées ; Rekordbox jamais fermé. |
| LIV-3 | Auteur | Windows | Live de 3 sons à la suite (dont un lien YouTube collé et un son déjà dans la bibliothèque), une analyse de la bibliothèque en cours. | Les 3 sons passent l'un après l'autre devant la file, chacun publié dès qu'il est prêt ; l'analyse de fond se met en pause puis reprend ; le son déjà là n'est pas retéléchargé. |
| LIV-4 | Auteur | Windows | Couper Internet, demander un son ; rétablir, « Réessayer ». | Erreur immédiate dans le panneau, le son n'entre pas dans le XML ; Réessayer le rend prêt. |
| LIV-5 | Auteur | Windows | « Terminer le live » Rekordbox ouvert, puis Rekordbox fermé. | Ouvert : message « Fermez Rekordbox », rien d'écrit. Fermé : playlist Live ▸ DJSync Live – date dans Rekordbox, aucun doublon (les sons glissés sur un deck gardent leur tonalité et leurs formes d'onde), XML vidé. |
| LIV-6 | Auteur | Windows | Fermer DJSync pendant un live, le relancer le lendemain. | Le live est retrouvé (même date de début) ; « Terminer le live » est proposé au lancement. |
| LIV-7 | Testeur Mac | macOS | Pas à pas, puis un son « Prêt » dans Rekordbox. | Chemin du XML juste, Location lue par Rekordbox (son jouable). |

### Grille et cues : onglets et passages (B131, C237)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| GRI-1 | Tous | Windows | (**C237**) Ouvrir Grille et cues sur un son au tempo fixe ; passer par Grille, Tempo, Cues ; fermer et rouvrir. | Un seul onglet visible ; Grille : 1er temps (kicks, début de mesure) puis Ajustement ; un seul Retour (en haut) ; le dernier onglet est rouvert ; pas de bande des passages. |
| GRI-2 | Tous | Windows | (**B131**) Son beatswitch : curseur dans le 2e passage, 1er kick / 2e kick ; puis BPM ÷ 2 ; puis « Tout le son » et décalage +10. | Seul le passage sous le curseur change (le beatswitch reste) ; avec « Tout le son », toute la grille bouge et les bornes suivent. |
| GRI-3 | Tous | Windows | (**B131**) Bande des passages (fine, sous la vue d'ensemble) : cliquer au milieu d'un passage, survoler. | Le curseur va à l'endroit cliqué ; la bulle donne le passage et son BPM. |
| GRI-4 | Tous | Windows | (**B131**) Son qui accélère : Tempo ▸ « Analyser ce passage », Appliquer ; puis Annuler les modifications. Type ▸ Accélération sur un autre son. | Rampe proposée (début → fin) ; appliquée en un clic, annulable ; le type change vraiment la grille. |
| GRI-5 | Tous | Windows | (**B131**) Passage de moins de 8 mesures, puis un passage lu au double du voisin : Analyser. | Message « trop court » (BPM du voisin proposé) ; ×2 refusé (« erreur probable ») ; saisie à la main acceptée. |
| TEM-4 | Testeur platines | Windows | (**B131**) Son avec une rampe enregistrée, sur clé, lu sur platine. | Grille qui suit la rampe ; BPM affiché = celui du passage le plus long. |

### Apparence, Bibliothèque, Espace, clé (C238, B130, C239, B118, B132, B133, C240, B134)

| # | Qui | Plateformes | Comment | Attendu |
|---|---|---|---|---|
| COU-3 | Tous | Windows | (**C238**) Paramètres ▸ Apparence : Fond (16 teintes) × Luminosité (Sombre, OLED, Clair) ; thèmes prêts (14). Parcourir toutes les vues en Clair. | Choix séparés ; aucun texte illisible ni couleur sombre oubliée en Clair (formes d'onde, pastilles, états). Ancien fond OLED ou Lumineux repris. |
| REC-3 | Tous | Windows | (**B130**) Rechercher ▸ Lien ou playlist à 100, 125, 150 et 200 %. | Champ de 2 lignes au départ, texte d'aide entier, pas de barre de défilement à vide ; ligne « Ou Coller une liste… » entière ; 6 lignes au plus puis défilement. |
| BIB-4 | Tous | Windows | (**C239**) Bibliothèque : bouton « Transférer / synchroniser » de la barre. | Ouvre l'outil de transfert ; replié dans ☰ si la place manque. |
| BIB-5 | Auteur (tour) | Windows | (**B118**) Bibliothèque, vue toutes colonnes : défilement vertical et en largeur, rc.1 puis rc.2 (même bibliothèque). | Défilement nettement plus fluide en rc.2 ; mesure avant / après notée dans le suivi. |
| PAR-2 | Tous | Windows | (**B132**) Paramètres : taper vite « export », effacer, retaper. | Les cartes sont filtrées, plus de surlignage pendant la recherche ; aucun cadre qui reste. |
| ESP-1 | Tous | Windows | (**B133**, **C240**) Paramètres ▸ Espace, clé ouverte, avec des sons de la collection sur un disque débranché. | « sauvegardes de l'ordinateur » dans la ligne DJSync, « Sauvegardes de la clé » dans la liste (bulle avec le dossier) ; mêmes tailles que la fenêtre Sauvegardes ; disque absent : ligne « G:\ absent : N sons (x Go) » qui ouvre les fichiers introuvables. |
| CLE-13 | Auteur (tour) | Windows | (**B134**) Rekordbox ouvert avec la clé D: affichée ; ouvrir la clé dans DJSync ; Continuer, ajouter un son ; fermer Rekordbox. | Question « Rekordbox a ouvert cette clé » ; exportLibrary.db écrite ; export.pdb réécrit tout seul dans les 30 s après la fermeture (journal « export.pdb caught up »). Annuler : clé en lecture seule. |
