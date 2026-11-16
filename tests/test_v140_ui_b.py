"""Suite de test_v140_ui.py (1.4.2, C183 : fichier découpé pour que la passe parallèle --dist loadfile
ne dépende plus d'un seul gros fichier ; mêmes tests, aucun retiré)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .test_v140_ui import (  # noqa: F401,E402 (fixtures et aides du premier fichier)
    FakeClient,
    SimpleNamespace,
    _flac,
    _res,
    demo,
    shutil,
    subprocess,
    usb,
)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_soulseek_search_download_and_fake_check(demo, tmp_path, monkeypatch):  # noqa: F811
    from .qt_util import pump

    ctrl = demo.ctrl
    src = tmp_path.parent / (tmp_path.name + "_peers")
    src.mkdir()
    real = _flac(src / "Bicep - Glue.flac")
    fake = _flac(src / "Bicep - Apricots.flac", cutoff=16000)
    files = [_res("good", "music\\Bicep - Glue.flac", "flac"), _res("liar", "music\\Bicep - Apricots.flac", "flac")]
    inbox = tmp_path.parent / (tmp_path.name + "_in")
    inbox.mkdir()
    client = FakeClient(inbox, files)
    client.made = {"music\\Bicep - Glue.flac": real, "music\\Bicep - Apricots.flac": fake}
    monkeypatch.setattr(ctrl, "slsk_client_factory", lambda: client)
    monkeypatch.setattr(ctrl.settings, "analyze_after_download_usb", False)
    s = ctrl.settings
    s.soulseek_enabled, s.soulseek_accepted, s.soulseek_user, s.soulseek_password = True, True, "dj", "pw"
    actions = []
    ctrl.on("message_action", lambda text, fn: actions.append((text, fn)))
    # recherche Haute qualité dans la vue Recherche
    ctrl._emit("settings_saved")
    view = demo.views["hq"]                         # 1.4.1 (C133) : page Haute qualité
    view.entry.setText("Bicep")
    view.run_search(force=True)
    assert pump(demo, 6, lambda: view.table.total == 2)
    row = view.table.row(next(iter(view._tracks)))
    assert row.values["source"] == "Soulseek" and row.values["quality"].startswith("FLAC")     # C175
    view.table.select([row.iid])
    view._refresh_buttons()
    assert not view.preview_btn.isEnabled() and view.equiv_btn.isVisibleTo(view)                 # C167
    # téléchargements : import sur la clé, vraie qualité vérifiée
    jobs = ctrl.slsk_enqueue(files, [])
    assert pump(demo, 25, lambda: all(j.is_finished for j in jobs)), [(j.status, j.message) for j in jobs]
    assert [j.status for j in jobs] == ["done", "done"]
    titles = {x.title for x in ctrl.library.list_tracks()}
    assert {"Glue", "Apricots"} <= titles
    assert pump(demo, 10, lambda: actions)
    pump(demo, 1.0)
    assert len(actions) == 1 and "Apricots" in actions[0][0]          # seul le faux FLAC est signalé
    assert not any(inbox.iterdir())                                     # copié sur la clé : plus rien en attente
    # compteurs P2P dans Téléchargements
    panel = demo.views["downloads"].p2p
    panel.refresh()
    assert panel.isVisibleTo(demo.views["downloads"]) and "↓" in panel.stats.text()
    panel.graph.grab()


def test_soulseek_needs_the_warning_accepted(demo):  # noqa: F811
    from djsync.ui.dialogs import ConfirmDialog

    from .qt_util import pump

    demo.show_view("settings")
    view = demo.views["settings"]
    assert not demo.ctrl.settings.soulseek_enabled and not view.slsk_var.isChecked()   # désactivé par défaut
    view.slsk_var.setChecked(True)
    pump(demo, 0.2)
    dlg = [w for w in demo.findChildren(ConfirmDialog) if w.isVisible()]
    assert dlg
    dlg[-1].close()                                                     # refusé : décoché
    pump(demo, 0.2)
    assert not view.slsk_var.isChecked() and not demo.ctrl.settings.soulseek_accepted
    view.slsk_var.setChecked(True)
    pump(demo, 0.2)
    dlg = [w for w in demo.findChildren(ConfirmDialog) if w.isVisible()]
    dlg[-1]._ok()                                                       # accepté
    assert demo.ctrl.settings.soulseek_accepted and view.slsk_var.isChecked()


# ------------------------------------------------------------------ C47 : améliorer ma bibliothèque
def test_improve_ranks_and_picks_better_versions():
    from djsync.core import improve as I
    from djsync.core.quality import AudioInfo
    from djsync.models import TrackResult

    lib_track = SimpleNamespace(content_id=1, title="Glue", artist="Bicep", duration_seconds=268)
    weak = I.Weak(lib_track, AudioInfo(codec="aac", bitrate=128, sample_rate=44100))
    finds = [TrackResult(video_id="a", title="Glue", artist="Bicep", duration_seconds=268, source="audius", quality="MP3 320"),
             TrackResult(video_id="b", title="Glue", artist="Bicep", duration_seconds=269, source="archive", quality="FLAC"),
             TrackResult(video_id="c", title="Glue (Live)", artist="Bicep", duration_seconds=400, source="archive", quality="FLAC"),
             TrackResult(video_id="d", title="Glue", artist="Bicep", duration_seconds=268, source="audius", quality="MP3 128")]
    weak.finds = I.better_finds(weak, finds)
    assert [f.video_id for f in weak.finds] == ["b", "a"]
    assert weak.gain == "AAC 128 → FLAC" and I.sure(weak)
    fake = AudioInfo(codec="flac", bitrate=900, sample_rate=44100, cutoff=16000)      # faux FLAC : faible
    good = AudioInfo(codec="flac", bitrate=900, sample_rate=44100, cutoff=21800)
    tracks = [SimpleNamespace(content_id=i) for i in (1, 2, 3)]
    out = I.weak_tracks(tracks, {1: AudioInfo(codec="mp3", bitrate=320), 2: fake, 3: good})
    assert [w.track.content_id for w in out] == [2]
    assert [w.track.content_id for w in I.weak_tracks(tracks, {1: AudioInfo(codec="mp3", bitrate=320), 2: fake, 3: good},
                                                       lossless_only=True)] == [2, 1]


def test_improve_page_search_and_confirmed_replace(demo, monkeypatch):  # noqa: F811
    """1.4.1 (C135) : l'ancien onglet « Améliorer » ouvre l'onglet Qualité ; « Tout chercher » puis
    « Remplacer tout ce qui est sûr » : une seule confirmation pour tout le lot."""
    from djsync.core import quality
    from djsync.models import TrackResult
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.quality_page import QualityPage

    from .qt_util import pump

    ctrl = demo.ctrl
    monkeypatch.setattr(quality, "probe", lambda path: quality.AudioInfo(codec="aac", bitrate=128, sample_rate=44100))
    lib_tracks = ctrl.library.list_tracks()

    from djsync.core.quality import search_terms

    def free_search(query, ok, partial=None):
        x = next(t for t in lib_tracks if " ".join(reversed(search_terms(t))).strip() == query)
        ok([TrackResult(video_id=f"archive:{x.content_id}", title=x.title, artist=x.artist or "",
                        duration_seconds=x.duration_seconds, source="archive", quality="FLAC")])

    monkeypatch.setattr(ctrl, "free_search", free_search)
    monkeypatch.setattr(ctrl, "find_alternatives", lambda track, ok: ok([]))
    replaced = []
    monkeypatch.setattr(ctrl, "replace_with_download", lambda tr, old: replaced.append((tr.video_id, old[0].content_id)) or 1)
    demo.open_diagnostic("improve")
    assert pump(demo, 6, lambda: isinstance(demo.stack.currentWidget(), QualityPage))
    page = demo.stack.currentWidget()
    assert pump(demo, 6, lambda: page.table.total == len(lib_tracks))
    assert ctrl.diag_counts.get("quality") == len(lib_tracks)
    page._search_all()
    ok_ = pump(demo, 6, lambda: all(w.searched for w in page.shown.values()))
    assert ok_, [(w.track.title, w.searched, page._queue, page._searching) for w in page.shown.values()]
    gains = [w.gain for w in page.shown.values()]
    assert gains.count("AAC 128 → FLAC") == len(gains) - 1 and gains.count("") == 1   # le clip : rien de mieux
    page._apply_sure()
    dlg = [w for w in demo.findChildren(ConfirmDialog) if w.isVisible()]
    assert len(dlg) == 1 and not replaced                           # rien sans confirmation, une seule fenêtre
    dlg[-1]._ok()
    assert len(replaced) == len(lib_tracks) - 1 and page.table.total == 1
