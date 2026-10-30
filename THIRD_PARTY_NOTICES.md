# Third-party software

DJSync is free software under the **GNU General Public License v3.0** (see [LICENSE](LICENSE)).
The downloadable builds also contain the following components, each under its own license.
Their source code is available at the addresses below.

| Component | Used for | License |
|---|---|---|
| [Qt](https://www.qt.io/) / [PySide6](https://pypi.org/project/PySide6-Essentials/) | interface | LGPL-3.0 |
| [FFmpeg](https://ffmpeg.org/) (audio-only build, `packaging/build_ffmpeg.sh`) | decoding, conversion, analysis | LGPL-2.1-or-later |
| [LAME](https://lame.sourceforge.io/) (inside FFmpeg) | MP3 encoding | LGPL-2.0-or-later |
| [QuickJS-NG](https://github.com/quickjs-ng/quickjs) | JavaScript runtime for yt-dlp | MIT |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp), yt-dlp-ejs | downloads | Unlicense |
| [ytmusicapi](https://github.com/sigma67/ytmusicapi) | YouTube Music search | MIT |
| [pyrekordbox](https://github.com/dylanljones/pyrekordbox) | Rekordbox `master.db` | MIT |
| [sqlcipher3-wheels](https://github.com/laggykiller/sqlcipher3) / [SQLCipher](https://www.zetetic.net/sqlcipher/) | encrypted `exportLibrary.db` | zlib / BSD-3-Clause |
| [mutagen](https://github.com/quodlibet/mutagen) | audio tags | GPL-2.0-or-later |
| [NumPy](https://numpy.org/) | audio analysis | BSD-3-Clause |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | duplicates, matching | MIT |
| [Pillow](https://python-pillow.org/) | artwork, icons | MIT-CMU (HPND) |
| [miniaudio](https://github.com/irmen/pyminiaudio) | audio player | MIT |
| [requests](https://requests.readthedocs.io/) | artwork, Spotify pages | Apache-2.0 |
| [aioslsk](https://github.com/JurgenR/aioslsk) | Soulseek protocol (off by default) | GPL-3.0-or-later |
| [pydantic](https://github.com/pydantic/pydantic), [async-upnp-client](https://github.com/StevenLooman/async_upnp_client), [aiohttp](https://github.com/aio-libs/aiohttp), aiofiles, multidict | used by aioslsk | MIT / Apache-2.0 |
| [psutil](https://github.com/giampaolo/psutil) | "is Rekordbox open?" | BSD-3-Clause |
| [rkbdb2xml](https://github.com/kuwa72/rkbdb2xml) (algorithm, re-implemented in `djsync/analysis/anlz.py`) | analysis folder names computed like Rekordbox | MIT |
| [miniz](https://github.com/richgel999/miniz) (`packaging/launcher`) | single-file Windows launcher | MIT |
| [Python](https://www.python.org/) (via PyInstaller) | runtime | PSF License |

The Rekordbox file formats were documented by [Deep Symmetry / crate-digger](https://djl-analysis.deepsymmetry.org/)
and the pyrekordbox project. DJSync is not affiliated with Pioneer DJ or AlphaTheta; "Rekordbox",
"CDJ" and "XDJ" are trademarks of their owners.
