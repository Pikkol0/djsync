# DJSync — guide d'installation rapide (Windows, macOS, Linux)

*English version: [INSTALL.md](INSTALL.md)*

Rien à installer sur l'ordinateur : DJSync tourne directement depuis la clé USB, avec tout ce dont il a
besoin (FFmpeg et le moteur JavaScript pour YouTube sont inclus).

## Ce qu'il faut
- Un ordinateur : **Windows 10 ou 11** (64 bits), **macOS 11 ou plus récent** sur puce Apple (M1, M2,
  M3…) ou **Linux** (x86-64) — macOS et Linux sont en *bêta* — et une connexion internet (recherche,
  téléchargements).
- **Une clé USB exportée par Rekordbox** : elle doit contenir `PIONEER\rekordbox\exportLibrary.db`.
  Si ce n'est pas le cas, exportez une playlist vers la clé depuis Rekordbox une première fois.
  *Ou* Rekordbox installé sur l'ordinateur, si vous voulez mettre à jour sa collection.
- Environ **300 Mo** libres sur la clé pour DJSync et ses sauvegardes (plus la place de vos sons).

## Installer (1 minute)
Choisissez le fichier de votre ordinateur sur la **[page de téléchargement](https://github.com/Pikkol0/djsync/releases/latest)**.

### Windows
1. **[Téléchargez DJSync.exe](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync.exe)** :
   un seul fichier, rien à décompresser.
2. Copiez-le **à la racine de votre clé** (par exemple `E:\`).
3. **Double-cliquez dessus.**
   - Windows affiche « Windows a protégé votre ordinateur » ? Cliquez sur **Informations
     complémentaires** ▸ **Exécuter quand même** (application non signée, une seule fois par PC).
   - Le premier lancement prend un moment : DJSync prépare ses fichiers sur la clé (une seule fois).

### macOS (bêta)
1. **[Téléchargez DJSync-macOS.dmg](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync-macOS.dmg)**
   et ouvrez-le.
2. **Glissez DJSync sur votre clé USB** (dans la barre latérale du Finder, sous *Emplacements*).
3. Ouvrez la clé et **double-cliquez sur DJSync**.
   - **La première fois seulement**, macOS dit qu'il ne peut pas vérifier l'app (elle n'est pas signée par
     Apple) : ouvrez *Réglages Système* ▸ *Confidentialité et sécurité*, descendez, cliquez sur
     **Ouvrir quand même**, confirmez.
   - DJSync s'installe alors sur la clé et redémarre une fois tout seul. Les fois suivantes : un simple
     double-clic.

### Linux (bêta)
1. **[Téléchargez DJSync-Linux-x86_64.tar.gz](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync-Linux-x86_64.tar.gz)**
   et extrayez le dossier **DJSync** **sur votre clé**.
2. Lancez `DJSync/DJSync` (double-clic dans la plupart des gestionnaires de fichiers, ou depuis un
   terminal). Si Qt se plaint de `xcb`, installez `libxcb-cursor0` (Debian/Ubuntu) ou `xcb-util-cursor`
   (Fedora, Arch).

Ensuite : DJSync reconnaît la clé sur laquelle il se trouve et l'ouvre tout seul.

> DJSync range ses fichiers et vos réglages dans un dossier caché à côté de lui. Si vous le copiez
> ailleurs ou supprimez ce dossier, il le recrée tout seul au lancement suivant (les réglages repartent
> alors de zéro).

## Premiers pas
- **Français** : *Settings* ▸ *Appearance* ▸ *Language* ▸ **Français**.
- **Chercher un son** : `Ctrl+K` (ou collez un lien Spotify / YouTube / SoundCloud), puis
  **Télécharger** et choisissez la playlist.
- **Analyser** (BPM, tonalité, grille, formes d'onde) : *Bibliothèque* ▸ **Non analysés** ▸ *Tout analyser*.
- **Avant de débrancher la clé** : bouton **Éjecter** (barre latérale, en bas) — la bibliothèque est
  fermée proprement.
- **Raccourcis et aide** : bouton en bas de la barre latérale, ou `F1`.

## Bon à savoir
- **Fermez Rekordbox** pendant que DJSync modifie une bibliothèque (clé ou ordinateur).
- DJSync **sauvegarde la base avant chaque modification** (dossier `DJSync_Backups` sur la clé). Gardez
  quand même une copie de votre clé.
- Lancé depuis une clé, DJSync **demande avant** d'ouvrir la bibliothèque Rekordbox d'un ordinateur.
- **Sans Internet**, DJSync fonctionne quand même : playlists, lecture, analyse, grille, doublons, copie
  entre bibliothèques. Seuls la recherche, les téléchargements et les pochettes en ligne en ont besoin.

## Mettre à jour DJSync
DJSync vous prévient quand une nouvelle version sort (désactivable dans *Paramètres* ▸ *Moteur de
téléchargement*). Remplacez DJSync (`DJSync.exe`, DJSync sur Mac ou le dossier `DJSync`) par le nouveau :
vos réglages sont conservés.

## En cas de souci
| Problème | Solution |
|---|---|
| Les téléchargements YouTube échouent | DJSync propose lui-même la mise à jour du moteur ; sinon *Paramètres* ▸ **Moteur de téléchargement** ▸ *Rechercher une mise à jour*. |
| « La base est verrouillée : fermez Rekordbox… » | Quittez Rekordbox (et vérifiez qu'il ne tourne plus dans la barre des tâches). |
| La clé n'est pas détectée | *Paramètres* ▸ *Clé USB Rekordbox* ▸ **Lettre de lecteur** (ex. `E` ; sur macOS/Linux le dossier de la clé, ex. `/Volumes/DJ KEY`) ▸ *Enregistrer*. |
| macOS : « ne peut pas être ouvert » à chaque fois, ou un message de copie temporaire | *Réglages Système* ▸ *Confidentialité et sécurité* ▸ **Ouvrir quand même**. Si ça persiste : dans le Terminal, `xattr -dr com.apple.quarantine ` puis glissez DJSync depuis la clé dans la fenêtre, Entrée. |
| Voir le dossier caché `.djsync` | Tapez `E:\.djsync` dans la barre d'adresse de l'Explorateur (le dossier est protégé comme un fichier système). |
| L'antivirus bloque `DJSync.exe` | Autorisez-le : application non signée (son empreinte SHA-256 est publiée avec la release). |
| Autre problème | Joignez le journal `.djsync/data/djsync.log` à votre message (Windows : tapez `E:\.djsync\data` dans la barre d'adresse de l'Explorateur, avec la lettre de votre clé ; macOS : Cmd+Maj+. affiche les fichiers cachés ; Linux : Ctrl+H). |
