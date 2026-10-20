"""Gestion de PIONEER/rekordbox/exportLibrary.db (OneLibrary / Device Library Plus).

Points clés, vérifiés sur une vraie base de clé USB :
  * la base est chiffrée en SQLCipher 4 (le module `sqlite3` standard ne peut PAS l'ouvrir) ;
  * elle est en mode WAL ; le -wal est chiffré lui aussi ;
  * les chemins sont stockés relatifs à la racine de la clé, en "/", ex. "/Contents/Artiste/Album/x.mp3" ;
  * playlist.attribute : 0 = playlist, 1 = dossier, 4 = playlist intelligente ;
  * un son ajouté sans analyse laisse NULL : analysisDataFilePath, analysedBits, masterDbId,
    masterContentId, contentLink (même choix que pyrekordbox) ;
  * color_id et artist_id_lyricist valent 0 (et non NULL) pour un son sans valeur : c'est la
    convention des sons créés par Rekordbox lui-même (constaté sur une vraie clé : 213 sons natifs
    sur 213 ont 0). La V1.1-A les mettait à NULL par erreur ; rétabli ;
  * V1.1-A4 : chaque son ajouté est ANALYSÉ localement (djsync/analysis : BPM + grille, tonalité,
    formes d'onde ANLZ écrites dans PIONEER/USBANLZ) et reçoit sa POCHETTE (PIONEER/Artwork) ; la
    date d'ajout suit le format des sons natifs de la clé. analysisDataFilePath, bpmx100, key_id et
    image_id sont donc renseignés ; en cas d'échec de l'analyse, le son est ajouté comme avant ;
  * V1.1-A3 : si la clé contient aussi l'ancien format (PIONEER/rekordbox/export.pdb, lu par les
    platines CDJ/XDJ « historiques »), chaque écriture est répercutée dans ce fichier APRÈS le commit de
    exportLibrary.db (voir djsync/db/pdb/). export.pdb n'est jamais créé, seulement mis à jour s'il est
    reconnu ; en cas d'échec, l'écriture OneLibrary reste valide et `pdb_state` passe à « stale ».

Sécurité des données :
  * sauvegarde chiffrée de la base avant la première écriture de chaque session ;
  * chaque modification = une transaction (BEGIN IMMEDIATE ... COMMIT), annulée si erreur ;
  * après chaque commit, `wal_checkpoint(TRUNCATE)` : le fichier principal contient tout et le
    -wal est vidé, car un lecteur/une platine qui ignore le WAL ne verrait sinon rien de neuf.
"""
from __future__ import annotations

# V0.2.0 : l'implémentation est découpée par sujet dans djsync/db/library/ (le fichier unique dépassait
# 1 300 lignes). Ce module garde le nom public et ré-exporte les utilitaires historiques.
from .base import LibraryBackend
from .library.base import LibraryBase
from .library.common import *  # noqa: F401,F403 (FILE_TYPES, format_date_like, extract_video_id…)
from .library.common import _Extras, _meta_select, _safe_name, _track_select  # noqa: F401
from .library.ingest import IngestMixin
from .library.metadata import BeatGrid, MetadataMixin, PlaylistStats  # noqa: F401
from .library.pdb_mirror import PdbMirrorMixin
from .library.playlists import PlaylistsMixin
from .library.tracks import TracksMixin


class RekordboxUsbLibrary(IngestMixin, MetadataMixin, TracksMixin, PlaylistsMixin, PdbMirrorMixin, LibraryBase,
                          LibraryBackend):
    """Bibliothèque d'une clé USB Rekordbox. Thread-safe (un verrou protège la connexion)."""
