# Scénarios de test — DJSync 1.4.0-rc.5

Retours de tests de la rc.4 (**B80**, **B85**, **B86**, **B87**, **B88**, **B90**, **B91**, **B92**, **B93**, **C46**,
**C157**, **C160**, **C161**, **C162**, **C165**). Numérotation : thème en 3 lettres + n° (voir
`revues/numerotation-tests.md`) ; dans le suivi : « 140 · BIB-2 ». Les scénarios de la 1.4.0 restent dans
[TESTS-1.4.0.fr.md](TESTS-1.4.0.fr.md) ; IMP-8 et QUA-1 (KO en rc.4) sont à refaire avec cette version.

## Bibliothèque

| # | Étapes | Attendu |
|---|---|---|
| BIB-2 | (**B87**, régression) Ouvrir une playlist (clé, puis ordinateur), sans tri ni filtre. Glisser un son plus bas, puis plusieurs sons sélectionnés plus haut ; glisser jusqu'au bord bas d'une longue playlist. | Une ligne violette montre où les sons vont se poser ; l'ordre change au relâchement, « Enregistrer l'ordre • » apparaît ; la liste défile seule près des bords. Avec un filtre : bulle « Retirez le filtre pour réordonner la playlist ». |
| BIB-3 | (**B85**) Ouvrir une playlist, fenêtre en plein écran puis rétrécie (≈ 1000 px, puis ≈ 900 px), zoom 100 % puis 150 %. | Aucun texte ni icône coupé, aucun bouton qui en chevauche un autre : Importer, Harmonique, Suggestions et Colonnes passent en icônes (texte dans la bulle), puis dans le menu ☰ ; « Enregistrer l'ordre » n'apparaît qu'après un changement d'ordre. |
| BIB-4 | (**B86**) Bibliothèque de l'ordinateur : clic droit sur un son, survoler le bouton 🗑, puis le cliquer. Même chose sur la clé. | Ordinateur : « Retirer de la collection Rekordbox… », fenêtre « Retirer de la collection » qui explique que le fichier reste sur le disque (sauf s'il a été téléchargé par DJSync) ; clé : « Supprimer de la clé » comme avant. |

## Import d'une adresse et recherche

| # | Étapes | Attendu |
|---|---|---|
| IMP-9 | (**B80**) Importer une playlist SoundCloud, Windows à 100 %, 125 % et 150 % (Paramètres Windows ▸ Affichage ▸ Échelle). Regarder les cases et la case de l'en-tête. | Cases entières (aucun bord coupé) ; la case de l'en-tête a la même taille que celles des lignes et est centrée au-dessus d'elles ; coin du tableau arrondi. |
| SRC-13 | (**B93**) Importer une adresse SoundCloud ; sélectionner un son sans « Free Download » détecté. Clic droit sur le son. | Bouton « Page du morceau » en bas et « Ouvrir la page du morceau sur SoundCloud » dans le clic droit : la page s'ouvre dans le navigateur (lien gratuit à chercher dans la description). Un son YouTube : pas de bouton. |
| REC-3 | (**B90**) Paramètres ▸ Téléchargement ▸ Recherche : vues YouTube cochées. Taper vite « tif live » (lettre par lettre), si possible pendant des téléchargements. Puis Retours ▸ Envoyer mes logs. | La dernière recherche s'affiche sans attendre ; les vues se remplissent pour les lignes visibles, puis au défilement. Le journal contient « Search 'tif live' (all): n results in x s ». |
| HQ-2 | (**B92**) Rechercher ▸ Haute qualité (Soulseek activé) : « Jul ». | Colonne « Taille » (ex. « 12,3 Mo »), plus de colonne « Vues » ; recherche classique : « Vues » revient, pas de « Taille ». |

## Dossier surveillé

| # | Étapes | Attendu |
|---|---|---|
| IMP-10 | (**C160**) Paramètres ▸ Bibliothèques ▸ Dossier surveillé : lire la carte. Choisir un dossier, Enregistrer, y copier un son. | L'explication est écrite sous le titre (achats Bandcamp / Beatport…) ; au premier son : message « 1 son ajouté depuis le dossier surveillé » avec « Voir la playlist ». |
| IMP-11 | (**C160**) Bibliothèque après IMP-10 (et avec une ancienne playlist « Importés » si vous en avez une). | La playlist s'appelle « Dossier surveillé » (l'ancienne « Importés » est reprise et renommée), avec un œil dans l'arbre ; colonne Source du son : « Dossier surveillé » avec l'œil, bulle « Ajouté automatiquement depuis … le … ». Clic droit sur la playlist : « Ouvrir le dossier surveillé », « Réglages du dossier surveillé… ». Playlist vide : explication à la place du tableau. |

## Téléchargements, analyse, volet

| # | Étapes | Attendu |
|---|---|---|
| ANA-2 | (**C161**) Analyse après téléchargement cochée : télécharger 13 sons d'un coup (ou une playlist), avec des sons courts. | La carte Activité, l'anneau du volet replié et la page Téléchargements et analyse montrent l'analyse sur 13 dès le début (« 0 / 13 », « En attente des téléchargements… ») et ne reviennent jamais à zéro ; un téléchargement en échec fait passer à 12. Arrêter l'analyse : les téléchargements continuent sans la relancer. Case décochée : pas de barre d'analyse. |
| NAV-5 | (**C161**) Replier le volet pendant une analyse et des téléchargements, zoom 100 % puis 150 %. | Icônes et anneaux un peu plus gros qu'en rc.4, rien de coupé. |

## Paramètres

| # | Étapes | Attendu |
|---|---|---|
| PAR-13 | (**C165**) Parcourir toutes les sections des Paramètres, fenêtre large puis étroite. | Général : Apparence, Performance (mode léger). Bibliothèques : clé, ordinateur, Dossier surveillé, anciennes platines, sauvegardes, espace. Téléchargement : Recherche, Format et qualité (tableau « Quelle qualité vais-je obtenir ? » replié, s'ouvre au clic), YouTube, SoundCloud, Soulseek. Analyse et lecture : Analyse, Lecture (retard audio + Tester). DJSync : Mises à jour, À propos, Cette installation. Libellés alignés, champs de même largeur, aucune carte portant le même titre que sa section. |
| ENG-1 | (**B88**) Paramètres ▸ Avancé ▸ Moteur de téléchargement : cliquer « Rechercher une mise à jour ». | La page ne saute plus ; le bouton affiche « Recherche… » puis « Vous avez la dernière version (vérifié à 14 h 05) ». Version intégrée : pas de bouton « Version précédente » ; après une mise à jour : « Revenir à la version intégrée (…) ». |
| QUA-5 | (**C162**, **C46**) Bibliothèque ▸ Colonnes ▸ Qualité supposée ; survoler l'en-tête. Paramètres ▸ Téléchargement ▸ Format et qualité. Puis refaire QUA-1. | « Qualité supposée » partout (anglais : « Estimated quality ») ; bulle « Estimée d'après le spectre… : une indication, pas une mesure certaine » ; « Quelle qualité vais-je obtenir ? ». QUA-1 : préciser dans la note ce qui ne va pas s'il reste KO. |
| LOG-1 | (**B91**) Bibliothèque de l'ordinateur : télécharger 3 sons, puis Retours ▸ Envoyer mes logs. | Plus de dizaines de lignes « Playlist … not found in masterPlaylists6.xml » ; une seule ligne « n playlist(s) missing from masterPlaylists6.xml (harmless…) ». |

## Dépôt et site (C157, à faire par l'auteur)

| # | Étapes | Attendu |
|---|---|---|
| DEP-1 | Sur GitHub : description, site et sujets du dépôt posés à la main (valeurs dans la PR) ; Settings ▸ Pages ▸ Source : GitHub Actions ; après la fusion, Actions ▸ Pages. | https://pikkol0.github.io/djsync/ s'ouvre (titre, bouton de téléchargement, image de partage) ; le README commence par « DJSync — free Rekordbox USB export… » et renvoie au README français. |
