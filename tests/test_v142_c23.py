"""1.4.2 (C23) : transfert et synchronisation de playlists en lot, avec l'arborescence, dans les 4 sens.
Les clés sont de vraies clés vides (gabarit de C24) : export.pdb est vérifié après chaque lot."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from djsync.analysis.cues import Cue
from djsync.db import LibraryError, RekordboxUsbLibrary, blank_key
from djsync.db import transfer as T
from djsync.db.pdb import PdbDatabase

from .test_local_library import make_wav
from .test_v050 import local  # noqa: F401 (fixture : bibliothèque de l'ordinateur)


@pytest.fixture(autouse=True)
def not_system_disk(monkeypatch):
    monkeypatch.setattr(blank_key, "_is_system_disk", lambda root: False)


def _open_key(root: Path) -> RekordboxUsbLibrary:
    root.mkdir()
    return RekordboxUsbLibrary(blank_key.prepare_drive(root, "FAT32"), analyze=True).connect()


@pytest.fixture
def key(tmp_path):
    lib = _open_key(tmp_path / "keyA")
    yield lib
    lib.close()


@pytest.fixture
def key2(tmp_path):
    lib = _open_key(tmp_path / "keyB")
    yield lib
    lib.close()


def _add(lib, title: str, artist: str = "DJ", bpm: float = 124.0, seconds: float = 8.0, url: str = None):
    album = "" if T._is_local(lib) else None
    path = make_wav(Path(lib.default_download_dir(artist, album)), title, seconds, bpm=bpm)
    return lib.add_track(path, title, artist, None, url)


def _playlist(lib, name: str, tracks, parent: int = 0):
    pl = lib.create_playlist(name, parent)
    if tracks:
        lib.add_to_playlist(pl.playlist_id, [t.content_id for t in tracks])
    return pl


TRIAL = "Trial playlist"       # la base d'essai de l'ordinateur a déjà deux playlists de ce nom (une intelligente)


def _all(lib) -> list:
    return [p.playlist_id for p in lib.list_playlists() if not p.name.startswith(TRIAL)]


def _paths(lib) -> dict:
    """{chemin « Dossier / Playlist »: [titres dans l'ordre]} ; un dossier vaut None."""
    by_id, _kids = T._tree(lib)
    out = {}
    for p in by_id.values():
        if p.name.startswith(TRIAL):
            continue
        path = " / ".join(T.playlist_path(by_id, p))
        out[path] = None if p.is_folder else [t.title for t in lib.get_playlist_tracks(p.playlist_id)]
    return out


def _pdb_matches(lib) -> None:
    """export.pdb dit la même chose qu'exportLibrary.db (sons, playlists, contenu et ordre)."""
    status = lib.pdb_status()
    assert status.state == "ok", status
    pdb = PdbDatabase((lib.db_path.parent / "export.pdb").read_bytes())
    assert pdb.track_count == lib.track_count()
    assert pdb.playlist_count() == len(lib.list_playlists())


def _digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(("-wal", "-shm"))}


def _state(lib) -> tuple:
    return (_paths(lib), sorted((t.title, t.artist, t.path) for t in lib.list_tracks()))


def _send(src, dst, ids=None, action: str = "", origin: str = "départ", **kw):
    comp = T.compare(src, dst, ids if ids is not None else _all(src), origin)
    if action:
        comp.set_action(action)
    return comp, T.apply(src, dst, comp, **kw)


# ------------------------------------------------------------------ Comparer ne fait que lire
def test_compare_writes_nothing_on_either_side(key, local):  # noqa: F811
    a, b = _add(local, "One"), _add(local, "Two", bpm=128)
    folder = local.create_folder("Soirée")
    _playlist(local, "Été", [a, b], folder.playlist_id)
    _playlist(key, "Déjà là", [_add(key, "Three")])
    before = (_digest(key.drive.root), _state(local), _state(key))
    backups = sorted(p.name for p in local.backup_dir.glob("master-*"))
    comp = T.compare(local, key, [folder.playlist_id], "ordinateur")
    assert (_digest(key.drive.root), _state(local), _state(key)) == before
    assert sorted(p.name for p in local.backup_dir.glob("master-*")) == backups
    (line,) = comp.lines
    assert line.path == ("Soirée", "Été") and line.status == T.NEW and line.add == 2 and len(line.copy_ids) == 2
    assert comp.new_folders == [("Soirée",)] and comp.tracks_to_copy() == 2 and comp.needed() > 0
    assert comp.ready


# ------------------------------------------------------------------ Ordinateur → clé (142-TRA-1)
def test_computer_to_key_keeps_folders_analysis_and_cues(key, local):  # noqa: F811
    tracks = [_add(local, f"Son {i}", bpm=120 + i) for i in range(4)]
    local.save_track_cues(tracks[0].content_id, [Cue(1, 1000), Cue(2, 2000, name="Drop"), Cue(0, 500)])
    house = local.create_folder("House é")
    deep = local.create_folder("Deep", house.playlist_id)
    for i in range(10):
        _playlist(local, f"Set {i}", tracks[i % 4:] + tracks[:i % 4], deep.playlist_id)
    for i in range(9):
        _playlist(local, f"Warm-up {i}", tracks[:2], house.playlist_id)
    _playlist(local, "Racine", tracks)
    src_before = _state(local)
    calls = []
    real = key._pdb_reconcile
    key._pdb_reconcile = lambda journal: (calls.append(1), real(journal))[1]

    comp = T.compare(local, key, [house.playlist_id] + [p.playlist_id for p in local.list_playlists()
                                                        if p.name == "Racine"], "ordinateur")
    assert len(comp.lines) == 20 and all(line.status == T.NEW for line in comp.lines)
    assert comp.tracks_to_copy() == 4 and comp.new_folders == [("House é",), ("House é", "Deep")]
    res = T.apply(local, key, comp, backup_label="Avant transfert")

    assert (res.created, res.merged, res.folders, res.copied, res.failed) == (20, 0, 2, 4, 0), res.problems
    assert len(calls) == 1                                    # UNE seule réconciliation d'export.pdb pour le lot
    wanted = {k: v for k, v in _paths(local).items() if k.startswith(("House é", "Racine"))}
    assert _paths(key) == wanted                              # mêmes dossiers, mêmes playlists, même ordre
    assert all(t.is_analysed for t in key.list_tracks())
    by_title = {t.title: t for t in key.list_tracks()}
    for t in tracks:                                          # analyse reprise, pas recalculée
        assert by_title[t.title].bpm == pytest.approx(local.get_track(t.content_id).bpm, abs=0.01)
        assert key.absolute_path(by_title[t.title]).is_file()
        assert "/Contents/" in by_title[t.title].path
    cues = sorted((c.slot, c.ms, c.name) for c in key.track_cues(by_title["Son 0"].content_id))
    assert (1, 1000, "") in cues and (2, 2000, "Drop") in cues and any(c[0] == 0 and c[1] == 500 for c in cues)
    _pdb_matches(key)
    from djsync.db import backups

    points = backups.list_points(key.backup_dir)
    assert any(p.kind == "manual" and p.label == "Avant transfert" and p.tracks == 0 for p in points)
    assert res.restore_point
    assert _state(local) == src_before                        # le départ n'est jamais écrit

    # même lot une seconde fois : tout est « identique », rien n'est écrit
    again = T.compare(local, key, [house.playlist_id], "ordinateur")
    assert all(line.status == T.SAME and not line.selectable for line in again.lines) and not again.ready
    digest = _digest(key.drive.root)
    assert T.apply(local, key, again).done == 0 and _digest(key.drive.root) == digest


# ------------------------------------------------------------------ Clé → ordinateur (142-TRA-2)
def test_key_to_computer_writes_master_db_with_backup_and_cues(key, local):  # noqa: F811
    a, b = _add(key, "Alpha", url="https://music.youtube.com/watch?v=AAAAAAAAAAA"), _add(key, "Beta", bpm=128)
    key.save_track_cues(a.content_id, [Cue(1, 1500), Cue(4, 3000)])
    folder = key.create_folder("Clé")
    _playlist(key, "Peak", [b, a], folder.playlist_id)
    _playlist(key, "Vide", [], folder.playlist_id)
    key_before = (_state(key), _digest(key.drive.root))
    n_backups = len(list(local.backup_dir.glob("master-*")))

    comp, res = _send(key, local, [folder.playlist_id], origin="clé")
    assert (res.created, res.folders, res.copied, res.failed) == (2, 1, 2, 0), res.problems
    assert _paths(local)["Clé / Peak"] == ["Beta", "Alpha"] and _paths(local)["Clé / Vide"] == []
    assert len(list(local.backup_dir.glob("master-*"))) == n_backups + 1      # master.db sauvegardé avant, une fois
    alpha = next(t for t in local.list_tracks() if t.title == "Alpha")
    assert alpha.is_analysed and alpha.source_url and Path(alpha.path).is_file()
    assert local.drive.music_dir.resolve().as_posix() in Path(alpha.path).resolve().as_posix()
    rows = local._read("SELECT Kind, InMsec FROM djmdCue WHERE ContentID = :i ORDER BY Kind", {"i": str(alpha.content_id)})
    assert (1, 1500) in [tuple(r) for r in rows] and any(r[1] == 3000 for r in rows)     # cues dans master.db
    assert (_state(key), _digest(key.drive.root)) == key_before               # la clé de départ : pas un octet


# ------------------------------------------------------------------ Synchroniser les deux (142-TRA-3, TRA-4)
def test_sync_both_ways_gives_the_union_without_duplicating(key, local):  # noqa: F811
    k = {n: _add(key, n) for n in ("4", "5", "6", "7", "a")}
    c = {n: _add(local, n) for n in ("1", "2", "3", "4", "c", "d")}
    _playlist(key, "A", [k["a"]])
    _playlist(key, "B", [k["4"], k["5"], k["6"], k["7"]])
    _playlist(local, "B", [c["1"], c["2"], c["3"], c["4"]])
    _playlist(local, "C", [c["c"]])
    _playlist(local, "D", [c["d"]])
    # deux comparaisons calculées AVANT toute écriture, puis deux transferts à sens unique
    to_key = T.compare(local, key, _all(local), "ordinateur")
    to_pc = T.compare(key, local, _all(key), "clé")
    assert {line.name: line.status for line in to_key.lines} == {"B": T.CONFLICT, "C": T.NEW, "D": T.NEW}
    assert {line.name: line.status for line in to_pc.lines} == {"A": T.NEW, "B": T.CONFLICT}
    b = next(line for line in to_key.lines if line.name == "B")
    assert (b.add, b.common, b.dst_only, len(b.copy_ids)) == (3, 1, 3, 3)
    assert not to_key.ready and to_key.missing_choices == 1                  # choix obligatoire, rien par défaut
    with pytest.raises(LibraryError):
        T.apply(local, key, to_key)
    assert _paths(key) == {"A": ["a"], "B": ["4", "5", "6", "7"]}            # rien n'a été écrit
    to_key.set_action(T.MERGE)
    to_pc.set_action(T.MERGE)
    r1, r2 = T.apply(local, key, to_key), T.apply(key, local, to_pc)
    assert (r1.created, r1.merged, r1.copied, r1.reused) == (2, 1, 5, 1)
    assert (r2.created, r2.merged, r2.copied, r2.reused) == (1, 1, 4, 1)
    # l'arrivée garde son ordre et reçoit à la fin ce qui lui manque : l'ordre de B diffère donc d'un côté à l'autre
    assert _paths(key) == {"A": ["a"], "B": ["4", "5", "6", "7", "1", "2", "3"], "C": ["c"], "D": ["d"]}
    assert _paths(local) == {"A": ["a"], "B": ["1", "2", "3", "4", "5", "6", "7"], "C": ["c"], "D": ["d"]}
    assert sorted(t.title for t in key.list_tracks()) == sorted(
        t.title for t in local.list_tracks() if not t.title.startswith("Demo Track"))
    assert len([t for t in key.list_tracks() if t.title == "4"]) == 1        # « 4 » en un seul exemplaire
    _pdb_matches(key)
    # une seconde synchronisation n'a plus rien à faire
    assert all(line.status == T.SAME for d in (T.compare(local, key, _all(local)),
                                               T.compare(key, local, _all(key)))
               for line in d.lines)


# ------------------------------------------------------------------ Garder les deux / Garder l'arrivée (142-TRA-5)
def test_keep_both_renames_only_the_arriving_copy_and_keep_destination_changes_nothing(key, local):  # noqa: F811
    _playlist(key, "B", [_add(key, "k1")])
    _playlist(key, "Other", [_add(key, "k2")])
    _playlist(local, "B", [_add(local, "c1"), _add(local, "c2")])
    _playlist(local, "Other", [_add(local, "c3")])
    comp = T.compare(local, key, _all(local), "ordinateur")
    comp.set_action(T.KEEP_BOTH)                                             # choix global…
    next(line for line in comp.lines if line.name == "Other").action = T.KEEP_DEST      # …modifié sur une ligne
    assert comp.ready and comp.tracks_to_copy() == 2
    res = T.apply(local, key, comp)
    assert (res.created, res.merged, res.copied) == (1, 0, 2)
    assert _paths(key) == {"B": ["k1"], "B (ordinateur)": ["c1", "c2"], "Other": ["k2"]}
    assert [(r.outcome, r.name) for r in res.lines] == [("both", "B (ordinateur)")]
    assert "c3" not in [t.title for t in key.list_tracks()]                  # Garder l'arrivée : rien copié
    _pdb_matches(key)
    # une 2e fois : la copie précédente n'est pas écrasée
    comp = T.compare(local, key, [p.playlist_id for p in local.list_playlists() if p.name == "B"], "ordinateur")
    comp.set_action(T.KEEP_BOTH)
    T.apply(local, key, comp)
    assert "B (ordinateur) 2" in _paths(key) and _paths(key)["B (ordinateur)"] == ["c1", "c2"]


# ------------------------------------------------------------------ rien n'est retiré ; sons présents non touchés
def test_nothing_is_removed_and_existing_tracks_are_left_alone(key, local):  # noqa: F811
    url = "https://music.youtube.com/watch?v=BBBBBBBBBBB"
    mine = _add(key, "Titre corrigé sur la clé", url=url)
    extra = _add(key, "Seulement sur la clé")
    key.save_track_cues(mine.content_id, [Cue(1, 700)])
    _playlist(key, "Set", [extra, mine])
    theirs = _add(local, "Titre d'origine", url=url)
    other = _add(local, "Nouveau")
    _playlist(local, "Set", [theirs, other])
    file_before = hashlib.sha256(key.absolute_path(mine).read_bytes()).hexdigest()
    dat = key.absolute_path(key.get_track(mine.content_id).analysis_path)
    dat_before = hashlib.sha256(dat.read_bytes()).hexdigest()

    comp, res = _send(local, key, action=T.MERGE, origin="ordinateur")
    assert (res.merged, res.copied, res.reused, res.different) == (1, 1, 1, 1)
    assert res.different_detail.get("info") == 1 and res.different_detail.get("cues") == 1
    assert _paths(key) == {"Set": ["Seulement sur la clé", "Titre corrigé sur la clé", "Nouveau"]}
    assert key.get_track(mine.content_id).title == "Titre corrigé sur la clé"            # infos inchangées
    assert hashlib.sha256(key.absolute_path(mine).read_bytes()).hexdigest() == file_before
    assert hashlib.sha256(dat.read_bytes()).hexdigest() == dat_before                    # cues et grille inchangés
    assert [(c.slot, c.ms) for c in key.track_cues(mine.content_id) if c.slot] == [(1, 700)]
    _pdb_matches(key)


def test_a_different_file_with_the_same_name_is_never_overwritten(key, local):  # noqa: F811
    t = _add(local, "Same name", artist="Art", seconds=2.0)
    _playlist(local, "P", [t])
    folder = Path(key.default_download_dir("Art", None))
    folder.mkdir(parents=True)
    (folder / "Same name.wav").write_bytes(b"something else, kept as it is")
    _comp, res = _send(local, key)
    assert res.copied == 1 and (folder / "Same name.wav").read_bytes() == b"something else, kept as it is"
    assert key.absolute_path(key.list_tracks()[0]).name == "Same name (2).wav"


# ------------------------------------------------------------------ casse, dossiers fusionnés, intelligentes
def test_case_only_difference_is_flagged_and_arrives_as_a_second_playlist(key, local):  # noqa: F811
    folder = key.create_folder("house")
    _playlist(key, "peak time", [_add(key, "k")], folder.playlist_id)
    src_folder = local.create_folder("House")
    _playlist(local, "Peak Time", [_add(local, "c")], src_folder.playlist_id)
    comp = T.compare(local, key, [src_folder.playlist_id], "ordinateur")
    (line,) = comp.lines
    assert line.status == T.NEW and line.case_clash == "peak time" and comp.new_folders == []
    res = T.apply(local, key, comp)
    assert res.folders == 0                                                  # dossiers du même nom : fusionnés
    assert _paths(key) == {"house": None, "house / peak time": ["k"], "house / Peak Time (ordinateur)": ["c"]}
    _pdb_matches(key)


def test_folders_with_the_same_name_are_merged(key, local):  # noqa: F811
    for lib, name in ((key, "K"), (local, "C")):
        folder = lib.create_folder("Genres")
        sub = lib.create_folder("Techno", folder.playlist_id)
        _playlist(lib, name, [_add(lib, name.lower())], sub.playlist_id)
    _send(local, key, origin="ordinateur")
    assert _paths(key) == {"Genres": None, "Genres / Techno": None, "Genres / Techno / K": ["k"],
                           "Genres / Techno / C": ["c"]}


def test_smart_playlists_are_listed_but_never_copied(key, key2):
    t = _add(key, "x")
    _playlist(key, "Normale", [t])
    with key._write() as conn:
        conn.execute("INSERT INTO playlist (sequenceNo, name, image_id, attribute, playlist_id_parent) "
                     "VALUES (9, 'Intelligente', NULL, 4, 0)")
    comp = T.compare(key, key2, _all(key), "clé A")
    smart = next(line for line in comp.lines if line.name == "Intelligente")
    assert smart.status == T.SMART and not smart.selectable and not smart.will_write
    smart.selected = True                                                    # même forcée, elle n'est pas copiée
    T.apply(key, key2, comp)
    assert _paths(key2) == {"Normale": ["x"]}


# ------------------------------------------------------------------ Clé → autre clé, arrêt, espace (142-TRA-7)
def test_key_to_key_with_stop_between_playlists(key, key2):
    tracks = [_add(key, f"T{i}", bpm=122 + i) for i in range(3)]
    key.save_track_cues(tracks[0].content_id, [Cue(3, 1234)])
    for i in range(3):
        _playlist(key, f"P{i}", [tracks[i]])
    comp = T.compare(key, key2, _all(key), "clé A")
    seen = []

    def stop() -> bool:
        seen.append(1)
        return len(seen) > 2                                                 # arrêt demandé après 2 playlists

    res = T.apply(key, key2, comp, should_stop=stop)
    assert res.stopped and res.created == 2
    assert _paths(key2) == {"P0": ["T0"], "P1": ["T1"]}                      # ce qui est fait est complet
    _pdb_matches(key2)
    first = next(t for t in key2.list_tracks() if t.title == "T0")
    assert first.is_analysed and [(c.slot, c.ms) for c in key2.track_cues(first.content_id) if c.slot] == [(3, 1234)]
    # reprise : le reste arrive, sans doublon
    _send(key, key2, origin="clé A")
    assert _paths(key2) == {"P0": ["T0"], "P1": ["T1"], "P2": ["T2"]} and key2.track_count() == 3
    _pdb_matches(key2)


def test_not_enough_space_is_known_before_and_nothing_is_written(key, key2, monkeypatch):
    _playlist(key, "P", [_add(key, "big")])
    monkeypatch.setattr(T, "_free_space", lambda path: T.SPACE_MARGIN + 10)
    comp = T.compare(key, key2, _all(key))
    assert comp.needed() > 10 and not comp.enough_space and not comp.ready
    digest = _digest(key2.drive.root)
    with pytest.raises(LibraryError, match="free space"):
        T.apply(key, key2, comp)
    assert _digest(key2.drive.root) == digest


def test_unchecked_lines_are_not_transferred(key, key2):
    _playlist(key, "Oui", [_add(key, "o")])
    _playlist(key, "Non", [_add(key, "n")])
    comp = T.compare(key, key2, _all(key))
    next(line for line in comp.lines if line.name == "Non").selected = False
    assert comp.tracks_to_copy() == 1
    T.apply(key, key2, comp)
    assert _paths(key2) == {"Oui": ["o"]} and key2.track_count() == 1


def test_one_failing_track_does_not_stop_the_batch(key, key2):
    ok, gone = _add(key, "ok"), _add(key, "gone")
    _playlist(key, "P", [gone, ok])
    comp = T.compare(key, key2, _all(key))
    key.absolute_path(gone).unlink()
    res = T.apply(key, key2, comp)
    assert (res.copied, res.failed) == (1, 1) and "gone" in res.problems[0]
    assert _paths(key2) == {"P": ["ok"]}
    _pdb_matches(key2)


def test_rekordbox_open_blocks_the_transfer_to_the_computer_before_any_write(key, local, monkeypatch):  # noqa: F811
    from djsync.db import local_library as L

    _playlist(key, "P", [_add(key, "x")])
    comp = T.compare(key, local, _all(key))
    monkeypatch.setattr(L, "rekordbox_running", lambda: True)
    with pytest.raises(LibraryError):
        T.apply(key, local, comp)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    assert "P" not in _paths(local) and "x" not in [t.title for t in local.list_tracks()]


@pytest.mark.slow
def test_large_batch_is_one_reconciliation_and_export_pdb_matches(key, key2):
    """Volume (risque 4 de la spec) : 150 sons, 40 playlists, dossiers sur 2 niveaux, noms longs et accentués."""
    key.analyze = False
    tracks = [_add(key, f"Morceau numéro {i:03d} — édition spéciale", artist=f"Artiste {i % 12}", seconds=0.2, bpm=0)
              for i in range(150)]
    with key.batch():
        for g in range(4):
            genre = key.create_folder(f"Genre très long nom accentué éàü {g}")
            for s in range(2):
                sub = key.create_folder(f"Sous-dossier {s}", genre.playlist_id)
                for n in range(5):
                    start = (g * 37 + s * 11 + n * 5) % 150
                    _playlist(key, f"Playlist {g}.{s}.{n}", (tracks + tracks)[start:start + 30], sub.playlist_id)
    calls = []
    real = key2._pdb_reconcile
    key2._pdb_reconcile = lambda journal: (calls.append(1), real(journal))[1]
    comp = T.compare(key, key2, _all(key), "clé A")
    assert len(comp.lines) == 40
    res = T.apply(key, key2, comp)
    assert (res.created, res.folders, res.failed) == (40, 12, 0) and len(calls) == 1
    assert _paths(key2) == _paths(key)
    _pdb_matches(key2)
