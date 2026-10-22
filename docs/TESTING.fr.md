# Tester DJSync — guide du testeur

*English version: [TESTING.md](TESTING.md)*

Merci de tester ! Le but de cette bêta : vérifier que DJSync **n'abîme jamais une clé**, et que ce
qu'il écrit est correct **dans Rekordbox et sur de vraies platines**. 30 à 60 minutes suffisent.

## Avant de commencer
1. **Copiez toute votre clé USB** sur l'ordinateur (ou utilisez une clé de test). DJSync sauvegarde
   sa base avant chaque modification, mais une copie complète reste le vrai filet de sécurité.
2. Téléchargez DJSync pour votre ordinateur depuis la
   [dernière pré-version](https://github.com/Pikkol0/djsync/releases) et suivez le
   [guide d'installation](INSTALL.fr.md).
3. **Fermez Rekordbox** pendant que DJSync modifie une clé ou la bibliothèque de l'ordinateur.

## 1. Sur l'ordinateur (tout le monde)
Cochez ce qui marche, notez ce qui ne marche pas :

- [ ] DJSync démarre depuis la clé et l'ouvre tout seul
- [ ] **Chercher** un son, le **télécharger** dans une **nouvelle playlist** et dans une existante
- [ ] **Importer** le lien d'une playlist Spotify : les bons sons sont-ils trouvés ?
- [ ] **Bibliothèque ▸ Non analysés ▸ Tout analyser** : BPM et tonalité semblent justes ?
- [ ] **Écouter** un son : la forme d'onde défile dans la barre du lecteur
- [ ] **Corriger la grille** d'un son (clic droit ▸ Modifier la grille de temps) : décaler, *Début de mesure ici*, Enregistrer
- [ ] Réordonner une playlist, renommer un son, ajouter un son à une autre playlist
- [ ] **Accueil ▸ Diagnostic** : doublons / mauvaise qualité / clips trouvés ? Essayez *Télécharger et remplacer*
- [ ] **Éjecter** (en bas de la barre latérale), débrancher, rebrancher : tout est toujours là
- [ ] Facultatif : ouvrir la clé dans **Rekordbox** (Périphériques) : playlists, BPM, tonalités, formes d'onde

## 2. Dans Rekordbox — contrôle des modifications

Le but : vérifier que **tout ce que DJSync modifie** se retrouve à l'identique dans Rekordbox, dans
**les deux bibliothèques de la clé** (celle des platines récentes et l'ancienne « Device Library »).

### 2a. Préparer la clé dans DJSync (notez chaque valeur dans le tableau du rapport)
Créez une playlist **« Test DJSync »** et faites ces modifications, chacune sur un son différent :

| ID | Action dans DJSync | À noter |
|---|---|---|
| P1 | Télécharger 3 sons dans « Test DJSync », puis *Tout analyser* | BPM et tonalité affichés |
| P2 | Son A : grille ▸ **Décaler** de +10 ms cinq fois (+50 ms), Enregistrer | position du 1er temps avant / après |
| P3 | Son B : grille ▸ placer le curseur sur un autre kick ▸ **Début de mesure ici**, Enregistrer | nouveau 1er temps de mesure |
| P4 | Son C : grille ▸ **BPM × 2** (ou **Imposer le BPM** avec une valeur précise), Enregistrer | nouveau BPM |
| P5 | Son D : **Modifier titre / artiste** | nouveau titre |
| P6 | Réordonner « Test DJSync », ajouter un son à une 2e playlist, en retirer un autre | ordre final |
| P7 | **Diagnostic** : remplacer un doublon par une version propre | playlist et position du son remplacé |
| P8 | **Supprimer de la clé** un son de test | son supprimé |
| P9 | Corriger la grille d'un son **analysé par Rekordbox** (s'il y en a) | BPM / 1er temps |

Puis **Éjecter**, débrancher.

### 2b. Vérifier dans Rekordbox
Branchez la clé sur un ordinateur avec Rekordbox, ouvrez-la (*Périphériques*), et vérifiez **dans les
deux bibliothèques de la clé** :

| ID | Vérification | Attendu |
|---|---|---|
| R1 | Sons et playlists | Les mêmes sons et playlists dans les **deux** bibliothèques ; « Test DJSync » est là |
| R2 | BPM | Chaque son a le BPM noté dans DJSync (P1, P4) |
| R3 | Grille / 1er temps | Les repères tombent sur les kicks ; le « 1 » de la mesure est au même endroit que dans DJSync (P2, P3) — zoomez sur le début |
| R4 | Forme d'onde détaillée | Présente, en couleur, alignée avec la grille |
| R5 | Forme d'onde miniature | La vue d'ensemble (en haut / dans la liste) est présente **et à jour** après une correction de grille |
| R6 | Tonalité | Même tonalité que dans DJSync |
| R7 | Titre, artiste, pochette | Le titre modifié (P5) est à jour ; pochettes présentes |
| R8 | Playlists | Ordre (P6), son ajouté / retiré, son remplacé à la même place (P7), son supprimé absent (P8) |
| R9 | Mémoire cue | Sur le premier temps fort (si activé dans les Réglages) |
| R10 | Sons d'origine | Les sons exportés par Rekordbox (grilles, cues, hot cues) sont **inchangés**, sauf P9 |
| R11 | Aller-retour | Exportez un nouveau son depuis Rekordbox vers la clé, puis rouvrez la clé dans DJSync : tout est encore là, des deux côtés |
| R12 | Bibliothèque du PC (facultatif) | Si vous testez la collection de l'ordinateur : mêmes vérifications R2–R8 dans la Collection de Rekordbox (Rekordbox fermé pendant que DJSync écrit) |

Puis, si vous avez des platines : refaites R1–R9 sur les platines (partie 3).

## 3. Sur les platines (CDJ / XDJ) — le test le plus précieux
Pas un contrôleur : de vraies platines qui lisent la clé. Préparez la clé avec DJSync (partie 2a),
branchez-la sur la platine, et comparez **les sons ajoutés ou modifiés par DJSync** aux sons exportés
par Rekordbox :

| À vérifier | Ce qui est attendu |
|---|---|
| Bibliothèque | La clé est reconnue ; playlists et dossiers présents, dans le bon ordre |
| Infos du son | Titre, artiste, pochette, BPM, tonalité |
| Formes d'onde | Vue d'ensemble et forme d'onde défilante, en couleur sur les platines récentes |
| Grille | Les repères tombent sur les kicks ; **Sync** et **Quantize** se comportent comme avec Rekordbox |
| Mémoire cue | Un repère sur le premier temps fort (si activé dans les Réglages) |
| Grille corrigée | Une grille corrigée dans DJSync est juste sur la platine |
| Sons Rekordbox | Les sons exportés par Rekordbox marchent exactement comme avant |

Les platines récentes (CDJ-3000, XDJ-AZ, OPUS-QUAD…) lisent le nouveau format (`exportLibrary.db`) ;
les plus anciennes (CDJ-2000NXS2, XDJ-1000MK2, XDJ-RX2…) lisent `export.pdb`. DJSync écrit les deux :
**précisez le modèle utilisé**. Les photos de l'écran de la platine sont très utiles.

## 4. Envoyer vos retours
- **[Rapport « Test dans Rekordbox »](https://github.com/Pikkol0/djsync/issues/new?template=rekordbox_test.yml)**
  pour la partie 2 (tableau des résultats déjà rempli avec les numéros de test),
  **[rapport « Test sur platines »](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml)**,
  **[bug](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)** pour le reste, ou
  **[idée](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml)** (formulaires en anglais,
  répondez en français sans problème).
- **Joignez le journal** : `djsync.log` dans le dossier caché `.djsync/data` à côté de DJSync
  (Windows : tapez `E:\.djsync\data` dans la barre d'adresse de l'Explorateur, avec la lettre de votre
  clé ; macOS : Cmd+Maj+. affiche les fichiers cachés ; Linux : Ctrl+H).
- Pas de compte GitHub ? Envoyez les mêmes infos et le journal à la personne qui vous a invité.
