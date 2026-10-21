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

## Installer (1 minute)
1. **[Téléchargez DJSync.exe](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync.exe)** :
   un seul fichier, rien à décompresser.
2. Copiez-le **à la racine de votre clé** (par exemple `E:\`).
3. **Double-cliquez dessus.**
   - Windows affiche « Windows a protégé votre ordinateur » ? Cliquez sur **Informations
     complémentaires** ▸ **Exécuter quand même** (application non signée, une seule fois par PC).
   - Le premier lancement prend un moment : DJSync prépare ses fichiers sur la clé (une seule fois).
4. C'est prêt : DJSync reconnaît la clé sur laquelle il se trouve et l'ouvre tout seul.

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

## Mettre à jour DJSync
Remplacez `DJSync.exe` par le nouveau : au lancement suivant, il se met à jour tout seul et garde vos
réglages.

## En cas de souci
| Problème | Solution |
|---|---|
| Les téléchargements YouTube échouent | DJSync propose lui-même la mise à jour du moteur ; sinon *Paramètres* ▸ **Moteur de téléchargement** ▸ *Rechercher une mise à jour*. |
| « La base est verrouillée : fermez Rekordbox… » | Quittez Rekordbox (et vérifiez qu'il ne tourne plus dans la barre des tâches). |
| La clé n'est pas détectée | *Paramètres* ▸ *Clé USB Rekordbox* ▸ **Lettre de lecteur** (ex. `E`) ▸ *Enregistrer*. |
| Voir le dossier caché `.djsync` | Tapez `E:\.djsync` dans la barre d'adresse de l'Explorateur (le dossier est protégé comme un fichier système). |
| L'antivirus bloque `DJSync.exe` | Autorisez-le : application non signée (la somme SHA-256 du zip est publiée avec la release). |
| Autre problème | Joignez le journal `.djsync\data\djsync.log` à votre message (tapez `E:\.djsync\data` dans la barre d'adresse de l'Explorateur, avec la lettre de votre clé). |
