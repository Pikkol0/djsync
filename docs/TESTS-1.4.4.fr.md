# Scénarios de test — DJSync 1.4.4

Numérotation : thème en 3 lettres + n° (voir `revues/numerotation-tests.md`) ; dans le suivi : « 144 · REC-1 ».
Règle : un test OK sous Windows est validé ; Mac et Linux seulement pour un point qui leur est propre.

## rc.1

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

## Non codées dans la rc.1

- Bloquées : **C107** (clé passée sur platines), **B115**, **B118** (bibliothèque volumineuse d'un testeur), **C15** (essai sur la tour avec Rekordbox 7 ouvert).
- À coder dans une rc suivante : **C219**, **C225**, **C138**, **A08**, **C221**, **B125**, **C108**, **A09** (reste de B : lecture au fil de l'eau A1-11).
