"""1.3.0-rc.2 : export.pdb réconcilié avec exportLibrary.db (P02) et clé vide préparée par Rekordbox (B13)."""
import json
import struct
import re
from datetime import datetime, timezone

from sqlcipher3 import dbapi2 as sqlcipher

from djsync.db._key import get_default_key
from djsync.db.library.common import format_date_like
from djsync.db.pdb import PdbDatabase, rows
from djsync.db.pdb import sync as pdb_sync
from djsync.db.pdb.format import PAGE_SIZE, T

from .pdb_fixture import build_pdb, sample_track
from .test_pdb_sync import make_usb, open_lib, pdb_of
from .test_usb_library import make_wav


def _order(pdb: PdbDatabase, name: str):
    return [p.rsplit("/", 1)[-1] for p in pdb.playlist_tracks((name,))]


def _break_pdb(usb, monkeypatch):
    """Les écritures d'export.pdb échouent (fichier verrouillé par Rekordbox, clé en lecture seule…)."""
    from djsync.db.pdb import store

    def boom(self, data):
        raise store.PdbError("cannot write export.pdb (file used by another program?)")
    monkeypatch.setattr(store.PdbStore, "_write_atomic", boom)


def test_failed_writes_are_caught_up_including_removals_and_renames(tmp_path, monkeypatch):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        c = lib.add_track(make_wav(lib, "C", "c"), "c", "C", None, None, [1, 2])
        assert lib.pdb_state == "ok"
        with monkeypatch.context() as m:
            _break_pdb(usb, m)
            lib.reorder_track(1, c.content_id, 1)              # ordre
            lib.remove_from_playlist(1, [b.content_id])          # retrait
            lib.rename_playlist(2, "Deep House")                 # renommage
            lib.delete_track(a.content_id)                       # suppression d'un son
            lib.update_track_metadata(c.content_id, title="c (edit)", artist="C")
            assert lib.pdb_state == "stale" and "cannot write" in lib.pdb_problem
            journal = json.loads((usb / "DJSync_Backups" / "pdb-journal.json").read_text("utf-8"))
            kinds = sorted(m["kind"] for m in journal["marks"])
            assert kinds == ["playlist_deleted", "track_deleted", "track_fields"]
            st = lib.pdb_status()
            assert st.state == "stale" and st.different_playlists == 1 and st.pending_removals == 2
        # rien n'est perdu : l'écriture suivante (ou « Synchroniser maintenant ») rattrape TOUT
        lib.pdb_catch_up()
        assert lib.pdb_status().state == "ok" and lib.pdb_state == "ok"
    pdb = pdb_of(usb)
    assert _order(pdb, "Rap") == ["c.wav"]
    assert pdb.find_playlist(("House",)) is None and _order(pdb, "Deep House") == ["c.wav"]
    assert not pdb.has_track(a.path) and pdb.track_info(c.path)["title"] == "c (edit)"
    assert not (usb / "DJSync_Backups" / "pdb-journal.json").exists()


def test_next_write_catches_up_after_a_failure(tmp_path, monkeypatch):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        with monkeypatch.context() as m:
            _break_pdb(usb, m)
            a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
            assert lib.pdb_state == "stale"
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])   # écriture suivante, qui passe
        assert lib.pdb_state == "ok"
    pdb = pdb_of(usb)
    assert pdb.has_track(a.path) and pdb.has_track(b.path) and _order(pdb, "Rap") == ["a.wav", "b.wav"]


def test_status_sees_entries_missing_from_an_existing_playlist(tmp_path):
    """Faille 3 : un son déjà présent ajouté à une AUTRE playlist pendant un échec n'était pas vu."""
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        conn = lib._db()
        conn.execute("INSERT INTO playlist_content (playlist_id, content_id, sequenceNo) VALUES (2, ?, 1)",
                     (a.content_id,))
        st = lib.pdb_status()
        assert st.state == "stale" and st.missing_tracks == 0 and st.different_playlists == 1
        lib.pdb_catch_up()
    assert _order(pdb_of(usb), "House") == ["a.wav"]


def test_unknown_tracks_and_playlists_are_never_removed(tmp_path):
    """Un son ou une playlist présents dans export.pdb mais inconnus de exportLibrary.db (ancien export,
    autre logiciel) sont conservés : seul ce que DJSync a lui-même supprimé est retiré."""
    other = sample_track(2)
    pdb_bytes = build_pdb([sample_track(1), other], {("Rap",): [other.path], ("Old",): [other.path],
                                                     ("House",): [], ("Dossier",): []})
    usb = make_usb(tmp_path, pdb_bytes=pdb_bytes)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert lib.pdb_status().state == "ok"
    pdb = pdb_of(usb)
    assert pdb.has_track(other.path) and pdb.find_playlist(("Old",)) is not None
    assert _order(pdb, "Rap")[0] == "a.wav" and len(_order(pdb, "Rap")) == 2      # l'inconnu reste, à la fin


def test_plan_is_empty_when_identical_and_journal_survives_reload(tmp_path):
    j = pdb_sync.Journal(tmp_path)
    j.add([pdb_sync.Mark(pdb_sync.PLAYLIST_DELETED, ("Rap", "2026"))])
    assert pdb_sync.Journal(tmp_path).marks == [pdb_sync.Mark("playlist_deleted", ("Rap", "2026"))]
    db = PdbDatabase(build_pdb([sample_track(1)], {("Rap",): [sample_track(1).path]}))
    target = pdb_sync.Target([sample_track(1)], [(("Rap",), False, [sample_track(1).path])])
    p = pdb_sync.plan(db, target, [])
    assert p.empty and p.describe() == "up to date"


# ------------------------------------------------------------------ B13 : clé vide préparée par Rekordbox
def test_dates_on_an_empty_key_use_rekordbox_form():
    now = datetime(2026, 10, 26, 19, 53, 55, tzinfo=timezone.utc)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", format_date_like(None, now))
    assert format_date_like("2024-10-18", now) == now.astimezone().strftime("%Y-%m-%d")


def test_track_built_without_template_has_rekordbox_strings():
    meta = sample_track(7)
    data = rows.build_track(meta, 7, 1, 0, 0, None)
    r = rows.read_track(data, 0)
    s = r["strings"]
    assert s["kuvo_public"] == "ON" and s["autoload_hot_cues"] == "ON" and s["unk3"] == "1"


def test_empty_key_gets_musical_key_names_and_plain_dates(tmp_path):
    usb = make_usb(tmp_path, pdb_bytes=build_pdb([], {("Rap",): [], ("House",): [], ("Dossier",): []}))
    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        conn = lib._db()
        added = conn.execute("SELECT dateAdded, dateCreated FROM content WHERE content_id = ?", (t.content_id,)).fetchone()
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in added)
        kid = lib._key_id_for(conn, "Am")
        assert conn.execute("SELECT name FROM key WHERE key_id = ?", (kid,)).fetchone()[0] == "Am"
    pdb = pdb_of(usb)
    row = pdb.track_row(t.path)
    assert row["strings"]["autoload_hot_cues"] == "ON"


# ------------------------------------------------------------------ B13 : lien de la page d'index
def _break_links(data: bytes) -> bytes:
    """Remet le défaut écrit par la 1.3.0-rc.1 : index -> « aucune page » alors que la table en a."""
    from djsync.db.pdb.file import INDEX_FIRST_DATA, INDEX_NO_PAGE, PdbFile
    f = PdbFile(data)
    out = bytearray(data)
    for ttype in f.tables:
        chain = f.chain(ttype)
        if f.page(chain[0]).is_index and len(chain) > 1:
            struct.pack_into("<I", out, chain[0] * PAGE_SIZE + INDEX_FIRST_DATA, INDEX_NO_PAGE)
    return bytes(out)


def test_first_data_page_is_linked_from_the_index(tmp_path):
    """Clé vide préparée par Rekordbox : les tables n'ont qu'une page d'index. Quand DJSync crée la
    première page de données, l'index doit la désigner (sinon Rekordbox : « bibliothèque corrompue »)."""
    from djsync.db.pdb.file import PdbFile
    empty = build_pdb([], {})
    f = PdbFile(empty)
    assert any(len(f.chain(t)) == 1 for t in f.tables)               # tables sans page de données
    usb = make_usb(tmp_path, pdb_bytes=empty)
    with open_lib(usb) as lib:
        pl = lib.create_playlist("test")
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [pl.playlist_id])
        assert lib.pdb_state == "ok", lib.pdb_problem
    data = (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes()
    assert PdbFile(data).index_link_problems() == []
    assert _order(pdb_of(usb), "test") == ["a.wav"]


def test_broken_index_links_are_repaired_and_reported(tmp_path):
    """Clé écrite par la 1.3.0-rc.1 (test K2) : l'état n'est pas « à jour » tant que l'index est faux,
    et la réconciliation le répare sans rien changer d'autre."""
    from djsync.db.pdb.check import report
    from djsync.db.pdb.file import PdbFile
    t = sample_track(1)
    broken = _break_links(build_pdb([t], {("Rap",): [t.path], ("House",): [], ("Dossier",): []}))
    assert PdbFile(broken).repairable_index_links()
    usb = make_usb(tmp_path, pdb_bytes=broken)
    path = usb / "PIONEER" / "rekordbox" / "export.pdb"
    assert any("INDEX:" in line for line in report(path))
    with open_lib(usb) as lib:
        st = lib.pdb_status()
        assert st.state == "stale" and "index page" in st.detail
        lib.pdb_catch_up()
        assert lib.pdb_status().state == "ok"
    assert PdbFile(path.read_bytes()).index_link_problems() == []
    assert not any("INDEX:" in line for line in report(path))
