"""1.3.0-rc.6 (B27) : fichiers d'analyse des sons de DJSync rangés comme ceux de Rekordbox.

Jusqu'à la 1.3.0-rc.5, DJSync nommait les dossiers PIONEER/USBANLZ/Pxxx/xxxxxxxx avec son propre
hachage. Les platines suivent le chemin écrit dans la base (exportLibrary.db et export.pdb), donc ça
marchait ; mais Rekordbox calcule ce nom à partir du chemin du son, et rien ne garantit qu'aucun
lecteur ni logiciel ne le recalcule. Ici, à l'ouverture de la clé :

  1. les fichiers de chaque son AJOUTÉ PAR DJSYNC (masterDbId vide) dont l'analyse n'est pas au bon
     endroit sont COPIÉS vers le dossier de Rekordbox (ANLZ0001.* en cas de collision, comme lui) ;
  2. la base est mise à jour en une transaction (sauvegarde avant, comme toute écriture) ;
  3. la ligne export.pdb de ces sons est réécrite (même id, playlists intactes), une seule fois pour
     tous les sons de DJSync : elle prend aussi les champs corrigés (0x14, 0x18, chaînes…) ;
  4. les anciens fichiers ne sont effacés qu'une fois export.pdb à jour (sinon ils restent, et
     l'effacement est retenté à l'ouverture suivante).

Les sons de Rekordbox ne sont jamais touchés. Un fichier d'analyse dont la balise PPTH ne correspond
pas au son est laissé tel quel.
"""
from __future__ import annotations

import json
import os

from .common import *  # noqa: F401,F403 (imports et utilitaires partagés)
from ..pdb.sync import TRACK_REBUILT

MIGRATIONS_FILE = "djsync-migrations.json"
B27 = "b27-anlz-rekordbox"
ANLZ_EXTS = (".DAT", ".EXT", ".2EX")


class AnlzMigrateMixin:
    # -------------------------------------------------------------- état sur la clé
    def _migrations_path(self) -> Path:
        return self.backup_dir / MIGRATIONS_FILE

    def _migrations(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._migrations_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_migrations(self, data: Dict[str, Any]) -> None:
        path = self._migrations_path()
        try:
            path.parent.mkdir(exist_ok=True)       # jamais parents=True : clé retirée = pas de dossier recréé
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:            # une aide : ne bloque rien (refait à l'ouverture suivante)
            log.warning("Migration state not saved: %s", exc)

    def _retire_analysis(self, old: str, track_path: str) -> None:
        """Ancien emplacement à effacer quand export.pdb ne le cite plus (voir _cleanup_retired)."""
        data = self._migrations()
        todo = [x for x in data.get("retired", []) if isinstance(x, list) and len(x) == 2]
        if [old, track_path] not in todo:
            todo.append([old, track_path])
        data["retired"] = todo
        self._save_migrations(data)

    def _cleanup_retired(self) -> int:
        """Efface les anciens fichiers d'analyse, une fois export.pdb à jour (ou absent / non suivi)."""
        data = self._migrations()
        todo = [x for x in data.get("retired", []) if isinstance(x, list) and len(x) == 2]
        if not todo:
            return 0
        if self._pdb_enabled() and self.pdb_status().state != "ok":
            return 0                       # export.pdb cite peut-être encore l'ancien chemin
        current = {(r[0] or "").casefold() for r in self._read(
            "SELECT analysisDataFilePath FROM content WHERE analysisDataFilePath IS NOT NULL")}
        done = 0
        for old, track_path in todo:
            if old.casefold() not in current:          # jamais un fichier que la base cite encore
                self._delete_analysis(old, track_path)
                done += 1
        data["retired"] = []
        self._save_migrations(data)
        return done

    # ------------------------------------------------------------------- migration
    def migrate_analysis(self) -> int:
        """Range les analyses des sons de DJSync comme Rekordbox ; renvoie le nombre de sons déplacés.
        Ne lève que les erreurs d'écriture de la base (clé verrouillée…) : rien n'est alors changé."""
        from ...analysis.anlz import _write_atomic, choose_anlz_base, read_path

        if self.read_only:
            return 0
        state = self._migrations()
        rows = self._read("SELECT content_id, path, analysisDataFilePath FROM content "
                          "WHERE masterDbId IS NULL AND path IS NOT NULL AND path != ''")
        root = self.drive.root
        moves: List[Tuple[int, str, str, str]] = []       # (id, chemin du son, ancien, nouveau)
        written: List[Path] = []
        try:
            for cid, path, anlz in rows:
                if not anlz:
                    continue
                src = root / anlz.lstrip("/")
                if not src.is_file():
                    continue                               # analyse absente : rien à déplacer
                try:
                    if read_path(src.read_bytes()).casefold() != path.casefold():
                        continue                           # fichier d'un autre son : on ne touche pas
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                base = choose_anlz_base(root, path)
                if f"{base}.DAT".casefold() == anlz.casefold():
                    continue                               # déjà au bon endroit
                stem = root / base.lstrip("/")
                if not (root / "PIONEER" / "rekordbox").is_dir():
                    raise OSError("drive no longer present")   # jamais de dossiers recréés ailleurs
                for ext in ANLZ_EXTS:
                    old = src.with_suffix(ext)
                    if old.is_file():
                        target = stem.with_name(stem.name + ext)
                        _write_atomic(target, old.read_bytes())
                        written.append(target)
                moves.append((cid, path, anlz, f"{base}.DAT"))
        except OSError:
            self._discard(written)
            raise
        fix_rows = not state.get(B27) and bool(rows) and self._pdb_enabled()
        if not moves and not fix_rows:
            if not state.get(B27) and rows:          # clé sans son de DJSync : rien écrit sur la clé
                state[B27] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self._save_migrations(state)
            self._cleanup_retired()
            return 0
        try:
            with self._write() as conn:
                for cid, path, _old, new in moves:
                    conn.execute("UPDATE content SET analysisDataFilePath = ? WHERE content_id = ?", (new, cid))
                    self._pdb_mark(TRACK_REBUILT, path)
                if fix_rows:                               # une fois : champs des lignes au format Rekordbox
                    for _cid, path, _anlz in rows:
                        self._pdb_mark(TRACK_REBUILT, path)
        except BaseException:
            self._discard(written)
            raise
        for _cid, path, old, _new in moves:
            self._retire_analysis(old, path)
        state = self._migrations()
        state[B27] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._save_migrations(state)
        self._cleanup_retired()
        if moves:
            log.info("Analysis files moved to the Rekordbox folders: %d track(s)", len(moves))
        return len(moves)
