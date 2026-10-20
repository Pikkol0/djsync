<p align="center">
  <img src="docs/logos/djsync-violet_light.png" width="96" alt="Logo DJSync">
</p>

<h1 align="center">DJSync</h1>

<p align="center">
  Trouver de la musique, la mettre sur sa clé USB Rekordbox, prête pour les platines Pioneer — sans passer par Rekordbox.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.2.0-B79CFF">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB">
  <img alt="Plateforme" src="https://img.shields.io/badge/plateforme-Windows%20%7C%20Linux-555">
</p>

---

## Ce que fait DJSync

DJSync est une application de bureau **portable** (elle peut tourner directement depuis la clé USB) qui
travaille sur une clé exportée par Rekordbox :

- **Rechercher et télécharger** sur YouTube Music (résultats pendant la frappe, préécoute avant
  téléchargement), ou **importer un lien** Spotify, YouTube ou SoundCloud (titre ou playlist).
- **Écrire directement dans la bibliothèque de la clé** : `exportLibrary.db` (OneLibrary, platines récentes)
  **et** `export.pdb` (anciennes platines), avec date d'ajout et pochette.
- **Analyser les titres** sans Rekordbox : BPM, grille de temps, tonalité (affichée en Camelot), formes
  d'onde Pioneer (fichiers ANLZ). Les titres déjà analysés par Rekordbox ne sont jamais modifiés.
- **Gérer la bibliothèque** comme un mini-Rekordbox : playlists et dossiers, glisser-déposer, ordre des
  titres, filtre harmonique, lecteur intégré avec forme d'onde.
- **Corriger** une grille de temps décalée, **trouver et fusionner les doublons**, modifier titre / artiste.
- **Sauvegarder avant chaque modification** : copie de la base dans `DJSync_Backups/` sur la clé.

Interface en **anglais** par défaut, **français** disponible ; 20 couleurs de thème ; zoom de 80 à 200 %.

> ⚠️ Projet personnel, non affilié à Pioneer DJ / AlphaTheta. Les formats de la clé sont rétro-conçus :
> **gardez une copie de votre clé** et fermez Rekordbox pendant que DJSync écrit dessus.

## Captures

| Bibliothèque | Éditeur de grille |
|---|---|
| ![Bibliothèque](docs/captures/library.png) | ![Grille](docs/captures/grid.png) |

## Installation

### Prérequis
- **Python 3.10+** (développé et testé en 3.12)
- **FFmpeg** (`ffmpeg` + `ffprobe`) : téléchargement, lecture des m4a, analyse. Dans le `PATH`, ou dossier
  indiqué dans *Settings ▸ FFmpeg*.
- **Deno** (ou Node) : nécessaire à yt-dlp pour certains téléchargements YouTube — <https://deno.com>

### Lancer depuis les sources
```bash
git clone https://github.com/Pikkol0/djsync.git
cd djsync
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Sous Linux, Tkinter vient du système (`sudo apt install python3-tk`).

### Exécutable Windows portable
```bash
pip install pyinstaller
pyinstaller packaging/DJSync.spec
```
Produit `dist/DJSync.exe`. Copiez-le sur la clé avec `ffmpeg.exe`, `ffprobe.exe` et `deno.exe` à côté :
DJSync reconnaît alors la clé sur laquelle il tourne et la connecte d'office.
*(Build non encore validé sur une machine Windows.)*

## Utilisation rapide

| Raccourci | Action |
|---|---|
| `Ctrl+K` | Chercher un titre ou coller un lien, depuis n'importe où |
| `Ctrl+1` … `Ctrl+6` | Accueil, Recherche, Bibliothèque, Téléchargements, Import URL, Paramètres |
| `Ctrl+F` | Champ de recherche / filtre de la page |
| `Espace` | Lecture / pause |
| `Ctrl+→` / `Ctrl+←` | Titre suivant / précédent |
| `F1` | Aide |

Guide détaillé : bouton **Raccourcis et aide** dans l'application, et [docs/interface_v020.md](docs/interface_v020.md).

## Organisation du code

```
app.py                  point d'entrée (python app.py)
djsync/
  core/                 recherche YouTube Music, téléchargement (yt-dlp), import Spotify, doublons, Camelot
  db/                   clé USB : exportLibrary.db (SQLCipher) — library/ ; export.pdb — pdb/ ; pochettes
  analysis/             BPM, grille, tonalité, formes d'onde, fichiers ANLZ (numpy + FFmpeg uniquement)
  audio/                lecteur intégré, pochettes
  ui/                   interface customtkinter : app, contrôleur (ctrl/), vues (views/), dialogues
  i18n/                 textes anglais (en.py) et français (fr.py)
tests/                  tests pytest (fausse clé, morceaux synthétiques)
tools/                  outils de développement : captures d'écran, export du logo
packaging/              spécification PyInstaller + icône
docs/                   documentation technique (analyse audio, export.pdb, interface)
```

## Tests

```bash
pip install pytest
python -m pytest -q                 # Windows : tout, y compris l'interface
xvfb-run -a python -m pytest -q     # Linux sans écran
```
Les tests n'utilisent ni le réseau ni une vraie clé : base Rekordbox fabriquée, morceaux synthétiques.
Outil de captures : `python tools/ui_screenshots.py captures --sizes 860x560,1280x800 --lang fr`.

## Documentation technique
- [Analyse audio, pochettes, date d'ajout](docs/analyse_audio.md) — calibrage sur une vraie clé
- [export.pdb (anciennes platines)](docs/export_pdb.md)
- [Interface V0.2.0, grille, doublons](docs/interface_v020.md)

## Historique des versions

| Version | Contenu |
|---|---|
| **0.2.0** | Nouvelle interface : Accueil + omnibar, recherche dynamique, « Tous les titres », pastilles Camelot, glisser-déposer vers les playlists, filtre harmonique, lecteur précédent/suivant + forme d'onde, zoom et petite fenêtre, anglais par défaut, logo par couleur. Analyse à la demande, éditeur de grille, outil doublons, aide et raccourcis. Code découpé (bibliothèque, contrôleur). |
| 0.1.6 | Analyse locale BPM / tonalité / formes d'onde ANLZ, date d'ajout et pochettes dans les deux bases, calibrage sur une vraie clé (MP3 : silence d'amorçage). |
| 0.1.x | Recherche et téléchargement YouTube Music, import Spotify/YouTube/SoundCloud, écriture dans exportLibrary.db puis export.pdb, bibliothèque et playlists, lecteur, mode portable. |

## Feuille de route
- [ ] Mesurer et corriger le décalage de grille des m4a (AAC)
- [ ] Valider l'exécutable et l'affichage sous Windows (DPI 125–150 %)
- [ ] Test sur platine (CDJ récent et ancien modèle lisant export.pdb)

## Crédits
- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) et la documentation communautaire
  [Deep Symmetry / crate-digger](https://djl-analysis.deepsymmetry.org/) pour les formats Rekordbox.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp), [ytmusicapi](https://github.com/sigma67/ytmusicapi),
  [customtkinter](https://github.com/TomSchimansky/CustomTkinter), [SQLCipher](https://www.zetetic.net/sqlcipher/).

Téléchargez uniquement des contenus que vous avez le droit d'utiliser.
