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

## 2. Sur les platines (CDJ / XDJ) — le test le plus précieux
Pas un contrôleur : de vraies platines qui lisent la clé. Préparez la clé avec DJSync (étape 1),
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

## 3. Envoyer vos retours
- **[Rapport « Test sur platines »](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml)**,
  **[bug](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)** pour le reste, ou
  **[idée](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml)** (formulaires en anglais,
  répondez en français sans problème).
- **Joignez le journal** : `djsync.log` dans le dossier caché `.djsync/data` à côté de DJSync
  (Windows : tapez `E:\.djsync\data` dans la barre d'adresse de l'Explorateur, avec la lettre de votre
  clé ; macOS : Cmd+Maj+. affiche les fichiers cachés ; Linux : Ctrl+H).
- Pas de compte GitHub ? Envoyez les mêmes infos et le journal à la personne qui vous a invité.
