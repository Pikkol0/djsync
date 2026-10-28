"""1.3.2 : accueil (C54), hors playlist (C56), réglages par défaut (C57), boutons de ligne (C58),
premiers pas (C68), raccourci système (C70), version sur l'Accueil (C73), écoute depuis la recherche (C74),
page Analyser (C76)."""
import json
import sys
from pathlib import Path

import pytest

from .test_v122 import demo, usb  # noqa: F401
from .qt_util import find, pump


# ------------------------------------------------------------------ C57
def test_reset_to_defaults_keeps_state_and_optionally_choices(tmp_path):
    from djsync.settings import Settings

    s = Settings()
    s.language, s.contents_dir, s.geometry = "fr", "Musique", "10,10,800,600"
    s.welcome_done = True
    default = Settings()
    changed = [f for f in ("theme", "accent", "volume") if hasattr(s, f)]
    for f in changed:
        v = getattr(s, f)
        setattr(s, f, (v + 1) if isinstance(v, int) and not isinstance(v, bool) else ("lime" if isinstance(v, str) else v))
    old = s.reset_to_defaults(keep_choices=True)
    assert s.language == "fr" and s.contents_dir == "Musique"         # choix gardés
    assert s.geometry == "10,10,800,600" and s.welcome_done is True   # état jamais touché
    for f in changed:
        assert getattr(s, f) == getattr(default, f)
    s.restore(old)                                                    # Annuler
    assert s.language == "fr" and s.geometry == "10,10,800,600"
    s.reset_to_defaults(keep_choices=False)
    assert s.language == default.language and s.contents_dir == default.contents_dir
    assert s.geometry == "10,10,800,600"


# ------------------------------------------------------------------ C54
def test_first_run_only_without_a_settings_file(tmp_path):
    from djsync.settings import Settings

    fresh = Settings.load(tmp_path / "none.json")
    assert fresh.first_run is True and fresh.welcome_done is False
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"language": "fr"}), encoding="utf-8")   # mise à jour d'une version d'avant
    upd = Settings.load(old)
    assert upd.first_run is False and upd.welcome_done is True


def test_welcome_two_steps_and_done(demo, monkeypatch):  # noqa: F811
    from djsync.ui.welcome import WelcomeDialog

    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    w = WelcomeDialog(demo, demo.ctrl)
    assert w._step == 1
    w._choose(demo.ctrl.settings.language)                      # même langue : étape 2
    assert w._step == 2 and hasattr(w, "shortcut")
    w._finish()
    assert demo.ctrl.settings.welcome_done is True
    assert not demo.errors


# ------------------------------------------------------------------ C68
def test_help_opens_on_first_steps(demo):  # noqa: F811
    from djsync.ui.help_dialog import HelpDialog

    h = HelpDialog(demo, start=True)
    assert h.tabs.currentIndex() == 0 and h.tabs.count() >= 2
    h.close()


# ------------------------------------------------------------------ C70
@pytest.mark.skipif(sys.platform == "win32", reason="raccourci .desktop (Linux)")
def test_linux_shortcut_created_and_removed(tmp_path):
    from djsync.core import shortcut

    exe = tmp_path / "DJSync"
    exe.write_text("#!/bin/sh\n")
    dest = shortcut.location("linux", home=tmp_path)
    assert dest.name == "djsync.desktop"
    shortcut.create(dest=dest, exe=exe, platform="linux")
    text = dest.read_text(encoding="utf-8")
    assert f'Exec="{exe}"' in text and "Name=DJSync" in text
    assert shortcut.remove(dest, "linux") is True and not dest.exists()


def test_shortcut_needs_the_downloaded_program(monkeypatch):
    from djsync.core import shortcut

    monkeypatch.delenv("DJSYNC_LAUNCHER", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert shortcut.target() is None                            # depuis les sources : rien à pointer
    with pytest.raises(OSError):
        shortcut.create(dest=Path("/nonexistent/x.desktop"), platform="linux")
    assert shortcut.location("win32").name == "DJSync.lnk"
    assert shortcut.location("darwin", home=Path("/h")) == Path("/h/Applications/DJSync.app")


# ------------------------------------------------------------------ C73
def test_version_on_home_opens_about(demo):  # noqa: F811
    from djsync import full_version

    home = demo.views["home"]
    assert full_version() in home.version_btn.text()
    home._open_about()
    assert pump(demo, 2, lambda: demo.stack.currentWidget() is demo.views["settings"])
    assert not demo.errors


# ------------------------------------------------------------------ C74
def test_announce_shows_the_track_while_it_loads():
    from djsync.audio.player import LOADING, AudioPlayer, NowPlaying

    states = []
    p = AudioPlayer(lambda fn: fn(), lambda kind, payload: states.append((kind, payload)) if kind == "state" else None)
    p.announce(NowPlaying("Titre", "Artiste", ""))
    assert p.state == LOADING and p.meta.title == "Titre"
    p.stop()


# ------------------------------------------------------------------ C58
def test_action_columns_are_buttons(demo):  # noqa: F811
    from djsync.ui.table import ICON_COLUMNS, _ButtonDelegate

    assert {"dl", "grid", "an"} <= set(ICON_COLUMNS)
    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 0)
    keys = [c.key for c in lib.table.columns]
    assert "grid" in keys or "an" in keys
    assert any(isinstance(lib.table.itemDelegateForColumn(i), _ButtonDelegate) for i in range(len(keys)))
    assert not demo.errors


# ------------------------------------------------------------------ C56
def test_tracks_outside_any_playlist(demo):  # noqa: F811
    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 0)
    ids = [r.data.content_id for r in lib.table.all_rows() if r.data is not None]
    got = []
    demo.ctrl.orphan_ids(ids, got.append)
    assert pump(demo, 4, lambda: bool(got))
    orphans = got[0]
    assert orphans <= set(ids)
    in_lists = demo.ctrl.library.playlists_of(ids)
    assert orphans == {cid for cid in ids if not in_lists.get(cid)}
    from djsync.ui.views.library_view import ORPH

    assert ORPH in lib._items
    assert not demo.errors


# ------------------------------------------------------------------ C76
def test_analysis_page_lists_tracks_and_starts(demo, monkeypatch):  # noqa: F811
    from djsync.ui.analysis_dialog import AnalysisDialog

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 1)
    tracks = [r.data for r in lib.table.all_rows() if r.data is not None][:3]
    started = []
    monkeypatch.setattr(demo.ctrl, "analyze", lambda ids, force=False: started.append((list(ids), force)))
    d = AnalysisDialog(demo, demo.ctrl, tracks)
    assert d.list.count() == len(tracks)
    d.force.setChecked(True)                                    # analyser à nouveau : tous concernés
    first = d.list.item(0)
    from PySide6.QtCore import Qt

    first.setCheckState(Qt.Unchecked)                           # retirer un son de la liste
    assert len(d._todo()) == len(tracks) - 1
    d._start()
    assert started and len(started[0][0]) == len(tracks) - 1 and started[0][1] is True
    assert not d.start_btn.isVisible() or d.start_btn.isHidden()
    d.close()
    assert not demo.errors


# ------------------------------------------------------------------ C80
def _dup_page(demo, monkeypatch, refine):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    monkeypatch.setattr(demo.ctrl, "refine_duplicate_group", lambda g, ok: None)    # vérification à la main
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    return dup


def test_same_title_different_audio_stays_greyed_and_never_deleted(demo, monkeypatch):  # noqa: F811
    dup = _dup_page(demo, monkeypatch, None)
    group = list(dup.groups[0])
    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 2)
    stranger = next(r.data for r in lib.table.all_rows()
                    if r.data is not None and r.data.content_id not in {x.content_id for x in group})
    dup.groups[0] = group + [stranger]                       # 3 sons au même titre, dont un son différent
    dup._refined(dup.groups[0], [group])
    assert [x.content_id for x in dup.groups[0]] == [x.content_id for x in group]
    assert dup.apart[0] == [stranger]                        # gardé, grisé
    dup._select(0)
    deleted = []
    monkeypatch.setattr(demo.ctrl, "resolve_duplicates", lambda keep, others, *a, **k: deleted.append(others))
    from djsync.ui import duplicates_dialog as D

    monkeypatch.setattr(D, "ConfirmDialog", lambda *a, **k: a[3]())
    dup._apply()
    assert deleted and stranger.content_id not in deleted[0]  # jamais supprimé par la fusion
    assert demo.ctrl.diag_counts.get("dup") == 1
    dup.close()
    assert not demo.errors


def test_group_without_real_duplicate_goes_to_the_same_titles_section(demo, monkeypatch):  # noqa: F811
    dup = _dup_page(demo, monkeypatch, None)
    group = dup.groups[0]
    dup._refined(group, [])                                  # aucun son identique
    assert dup.groups == [] and dup.same_titles == [group]
    assert dup.list.count() == 2                             # titre de section + le groupe
    assert not (dup.list.item(0).flags() & __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ItemIsSelectable)
    dup._select(1)
    assert dup._same_index == 0 and not dup.apply_btn.isEnabled()
    dup._set_apart(group[0], group[1:])                      # « pas un doublon » : la section se vide
    assert dup.same_titles == [] and len(demo.ctrl.duplicate_ignores.entries) == 1
    assert demo.ctrl.diag_counts.get("dup") == 0
    dup.close()
    assert not demo.errors
