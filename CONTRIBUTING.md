# Contributing to DJSync

Thanks for wanting to help! DJSync stays **100 % free, open source (GPL-3.0) and without any server**
— every contribution keeps it that way. *[Version française plus bas.](#en-français)*

## Report a bug

1. Check the [open issues](https://github.com/Pikkol0/djsync/issues) first.
2. Use the **[bug report](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)** form:
   DJSync version, system (Windows / macOS / Linux), steps to reproduce, what you expected.
3. Attach the **log file** (*Settings ▸ Open the log folder*) and a screenshot if useful.

## Test with real players

Testers with **CDJ / XDJ players** (not controllers) are the most useful help right now. Follow the
[tester guide](docs/TESTING.md) and send a
[deck test report](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml).

## Suggest an idea

Use the **[idea](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml)** form: describe the
situation (what you are trying to do in your DJ workflow), not only the solution. Every request is
reviewed before anything is developed.

## Never attach personal files

Do **not** attach your Rekordbox library (`master.db`), the content of your USB drive
(`exportLibrary.db`, `export.pdb`, `PIONEER` folder), music files or logs you have not read.
If a file is needed to reproduce a problem, say so in the issue and we will agree on what to share.

## Code

### Run from source and run the tests

See [Run from source](README.md#run-from-source) in the README, then:

```bash
pip install pytest
python -m pytest -q
```

Tests need no network and no real drive (generated Rekordbox database, synthetic tracks; the UI runs
in Qt's "offscreen" mode).

### Pull requests

- **One topic per pull request**, based on `main`; explain *what* and *why*, link the issue.
- **Open an issue first** for anything bigger than a small fix, so we agree on the approach.
- Add or update **tests** for what you change; the whole suite must pass.
- **User-visible text** goes through the translation files (`djsync/i18n/en.py` and `fr.py`), never
  hard-coded — a test checks it.
- Anything that writes to a USB drive or a Rekordbox database must stay compatible with Rekordbox and
  with the players: be careful with `export.pdb` and the analysis files (see `docs/export_pdb.md`).
- Do not add a dependency on a paid service, an account or a server.
- By contributing, you agree that your contribution is published under the
  [GPL-3.0 licence](LICENSE).

---

## En français

- **Bug** : formulaire [bug report](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)
  avec la version, le système, les étapes et le fichier journal (*Paramètres ▸ Ouvrir le dossier du
  journal*).
- **Test sur platines** : [guide du testeur](docs/TESTING.fr.md) puis
  [compte rendu](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml).
- **Idée** : formulaire [idea](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml) ;
  décrivez la situation de DJ, pas seulement la solution. Chaque demande est étudiée avant tout
  développement.
- **Ne joignez jamais** votre bibliothèque Rekordbox, le contenu de votre clé, des fichiers audio ou
  un journal que vous n'avez pas relu.
- **Code** : une pull request par sujet, avec des tests ; textes visibles dans les fichiers de
  traduction ; aucune dépendance à un service payant, un compte ou un serveur ; contributions sous
  licence GPL-3.0.
