# DJSync — guide d'installation rapide (Windows)

*English version: [INSTALL.md](INSTALL.md)*

Rien à installer sur l'ordinateur : DJSync tourne directement depuis la clé USB, avec tout ce dont il a
besoin (FFmpeg et le moteur JavaScript pour YouTube sont inclus).

## Ce qu'il faut
- **Windows 10 ou 11** (64 bits) et une connexion internet (recherche, téléchargements).
- **Une clé USB exportée par Rekordbox** : elle doit contenir `PIONEER\rekordbox\exportLibrary.db`.
  Si ce n'est pas le cas, exportez une playlist vers la clé depuis Rekordbox une première fois.
  *Ou* Rekordbox installé sur l'ordinateur, si vous voulez mettre à jour sa collection.
- Environ **250 Mo** libres sur la clé pour DJSync (plus la place de vos sons).

## Installer (2 minutes)
1. Téléchargez **`DJSync-<version>-windows.zip`** depuis la
   [dernière release](https://github.com/Pikkol0/djsync/releases/latest).
2. Clic droit sur le zip ▸ **Extraire tout…** ▸ choisissez **la racine de la clé** (par exemple `E:\`).
3. Ouvrez la clé et double-cliquez sur **`DJSync.exe`**.
   - Windows affiche « Windows a protégé votre ordinateur » ? Cliquez sur **Informations
     complémentaires** ▸ **Exécuter quand même** (application non signée, une seule fois par PC).
4. C'est prêt : DJSync reconnaît la clé sur laquelle il se trouve et l'ouvre tout seul.

> À côté de `DJSync.exe` se trouve un dossier `.djsync`, caché au premier lancement : il contient le
> programme et vos réglages. **Ne séparez pas `DJSync.exe` de ce dossier** (copiez toujours les deux).

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

## Mettre à jour DJSync
Téléchargez le nouveau zip et extrayez-le **au même endroit** en acceptant de remplacer les fichiers :
vos réglages sont conservés.

## En cas de souci
| Problème | Solution |
|---|---|
| Les téléchargements YouTube échouent | DJSync propose lui-même la mise à jour du moteur ; sinon *Paramètres* ▸ **Moteur de téléchargement** ▸ *Rechercher une mise à jour*. |
| « La base est verrouillée : fermez Rekordbox… » | Quittez Rekordbox (et vérifiez qu'il ne tourne plus dans la barre des tâches). |
| La clé n'est pas détectée | *Paramètres* ▸ *Clé USB Rekordbox* ▸ **Lettre de lecteur** (ex. `E`) ▸ *Enregistrer*. |
| Voir le dossier caché `.djsync` | Explorateur ▸ *Affichage* ▸ **Éléments masqués**. |
| L'antivirus bloque `DJSync.exe` | Autorisez-le : application non signée (la somme SHA-256 du zip est publiée avec la release). |
