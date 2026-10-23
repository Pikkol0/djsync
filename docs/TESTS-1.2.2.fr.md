# Scénarios de test — DJSync 1.2.2

À faire avec ceux de la 1.2.1 (`docs/TESTS-1.2.1.fr.md`) et de la rc.4 (`docs/TESTS-1.2.0-rc.4.fr.md`) :
la 1.2.2 contient tout. Notez OK / KO ; un KO se signale directement depuis l'onglet **Retours**, avec une
capture.

**Avant de commencer** : faites une copie de la clé (ou au moins de `PIONEER/` et `Contents/`). Rien
n'est écrit sans validation, et DJSync sauvegarde la base avant chaque écriture, mais c'est une version de test.

**Ce que la 1.2.2 ne fait pas** (volontairement) : elle ne modifie ni ne renomme jamais les fichiers
audio (S05 reporté), et le genre n'est écrit que dans `exportLibrary.db` (et `master.db` pour le PC), pas
dans `export.pdb` : les anciennes platines ne voient pas le genre.

## D. Nouveautés de la 1.2.2

### D1. Modifier les infos d'un son (S04)
| # | Étapes | Attendu |
|---|---|---|
| D1.1 | Bibliothèque ▸ clic droit sur un son ▸ **Modifier les infos…** | Fenêtre : titre, artistes, album, année, genre, pochette actuelle. Même chose depuis le lecteur (clic droit sur le son en cours) et le menu *Outils* (un seul son sélectionné). |
| D1.2 | Artistes : `Booba, Damso` ; année ; genre (l'autocomplétion propose les genres déjà présents) ; *Enregistrer* | Message « Infos enregistrées. » ; le tableau montre les nouvelles valeurs. Rouvrir la fenêtre : tout est gardé. |
| D1.3 | *Chercher des pochettes* | Jusqu'à 6 pochettes Deezer ; un clic en choisit une (aperçu « Pochette trouvée en ligne »). |
| D1.4 | *Image de l'ordinateur…* (JPG / PNG) puis *Enregistrer* | La pochette s'affiche dans le lecteur et dans Rekordbox (clé rebranchée / base rechargée). |
| D1.5 | *Sans pochette* puis *Enregistrer* | Plus de pochette ; *Garder l'actuelle* avant d'enregistrer annule le choix. |
| D1.6 | Sur la clé, vérifier le fichier audio du son modifié | Même nom, même taille, même date : le fichier n'est pas touché. Hot cues et grille intacts sur platine. |
| D1.7 | Même chose sur la bibliothèque **de l'ordinateur** (Rekordbox fermé) | Titre, artistes, album, année, genre et pochette visibles dans Rekordbox. |

### D2. Uniformiser (C14, S01-S06)
| # | Étapes | Attendu |
|---|---|---|
| D2.1 | Bibliothèque ▸ *Outils* ▸ **Uniformiser « Tous les titres »…** (ou clic droit sur une playlist ▸ *Uniformiser…*) | Page « Uniformiser · … » : explication, filtre *Afficher*, tableau État / Titre / Artiste / Proposé / Source. La recherche avance (« recherche 12 / 80 »), la bibliothèque reste utilisable. |
| D2.2 | Un son « Artiste - Titre (Official Video) ft. Invité » téléchargé par DJSync | Proposé : titre `Titre`, artistes `Artiste, Invité`. Source « Deezer 9x % » (sûr) ou « Règles du titre ». Changements **cochés**. |
| D2.3 | Un son venu de Rekordbox (pas téléchargé par DJSync) | Propositions affichées mais **décochées** : rien ne change si on valide sans cocher (« Cochez au moins un changement »). |
| D2.4 | Correspondance « Douteux » (Deezer incertain) | Message « Vérifiez avant de valider », changements décochés. |
| D2.5 | Modifier un champ proposé dans sa case, puis **Valider** | État « Validé », passage au son suivant à revoir. **Rien n'est encore écrit** (vérifier dans la bibliothèque). |
| D2.6 | **Ignorer** un son ; **Modifier…** un autre (fenêtre D1, bouton « Utiliser ces valeurs ») | Ignoré : il ne revient plus dans « À revoir ». Modifié : il passe « Validé » avec vos valeurs. |
| D2.7 | Quitter la page (bouton retour) avec des sons validés | « Enregistrer avant de quitter ? ». Choisir de ne pas enregistrer, revenir dans Uniformiser : les validés et ignorés sont **retrouvés**. Relancer DJSync : pareil. |
| D2.8 | **Enregistrer les sons validés (n)** | Une seule sauvegarde, « n sons mis à jour », états « Enregistré ». Les nouveaux titres / artistes / pochettes sont dans la bibliothèque et dans Rekordbox / sur platine (titre, artiste). |
| D2.9 | Album, année, genre, pochette déjà remplis sur un son | Jamais remplacés par Uniformiser (seulement complétés s'ils sont vides ; l'album est remplacé seulement s'il ressemble au titre de la vidéo). |
| D2.10 | Sans internet | Propositions par « Règles du titre » seulement, pas d'erreur. |

### D3. Playlists par genre (C07, S07-S09)
| # | Étapes | Attendu |
|---|---|---|
| D3.1 | *Outils* ▸ **Playlists par genre…** | Désactivé par défaut. Une ligne par genre présent (au moins 3 sons), les autres regroupés dans « Autres », nombre de sons par ligne, genres « dans aucune playlist » listés. |
| D3.2 | Cocher « Créer des playlists par genre », renommer une ligne, regrouper deux genres dans une ligne (`Rap/Hip Hop, Rap français`), décocher une ligne, *Appliquer* | Dossier **DJSync ▸ Genres** avec une playlist par ligne cochée (pas de playlist vide), sons du plus ancien au plus récent. Message « x créées, y sons ajoutés ». |
| D3.3 | Télécharger un son dont le genre correspond (option « tenir à jour » cochée) | Il rejoint sa playlist par genre automatiquement. Pareil après *Modifier les infos* (changer le genre : il change de playlist). |
| D3.4 | Ajouter à la main un son d'un autre genre dans une playlist par genre | Il n'est jamais retiré par DJSync. |
| D3.5 | Déplacer une playlist par genre dans un autre dossier et la renommer (Rekordbox ou DJSync) | Elle reste tenue à jour. |
| D3.6 | Supprimer une playlist par genre | Pas recréée : sa ligne est décochée (message « plus tenues à jour »). |
| D3.7 | Décocher une ligne déjà créée, *Appliquer* | Confirmation « Supprimer ces playlists ? » ; seule celle-ci est supprimée, les sons restent dans la bibliothèque. |
| D3.8 | Décocher « Créer des playlists par genre », *Appliquer* | Confirmation ; toutes les playlists DJSync ▸ Genres supprimées, dossiers vides aussi ; vos autres playlists intactes. |
| D3.9 | Clé ET bibliothèque de l'ordinateur | Réglage séparé pour chaque bibliothèque. |

### D4. Non-régression
| # | Étapes | Attendu |
|---|---|---|
| D4.1 | Après D1-D3, brancher la clé sur une platine (et ouvrir dans Rekordbox) | Tous les sons lisibles, titres à jour, playlists DJSync ▸ Genres présentes, hot cues / grilles inchangés. |
| D4.2 | Recherche, téléchargement dans une playlist, analyse, éditeur de grille | Comme en 1.2.1. |
| D4.3 | Dossier `DJSync_Backups` sur la clé | Une sauvegarde par écriture (modifier, enregistrer les validés, appliquer les genres). |

## Outil vidéo (C17, développeur)
| # | Étapes | Attendu |
|---|---|---|
| V1 | `python tools/tour_video.py tour.mp4 --lang fr --dry` | Répétition sans erreur, interface en français. |
| V2 | `python tools/narrate.py tour.mp4 --script` | `tour.script.md` : chaque texte affiché et la phrase dite, à relire. |
| V3 | `pip install edge-tts` ; `narrate.py tour.mp4 --voice edge --measure` ; `tour_video.py tour.mp4 --lang fr --voice tour.durations.json` ; `narrate.py tour.mp4 --voice edge` | `tour.voice.mp4` avec voix calée sur les textes, `tour.srt`. Aucun avertissement « runs over ». Même chose en `--lang en`. |
