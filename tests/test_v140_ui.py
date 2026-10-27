"""1.4.0 : tests d'interface sur la clé de démonstration (fixtures de test_v122)."""
from .test_v122 import demo, usb  # noqa: F401


# ------------------------------------------------------------------ C50 : choix de couleur discret
def test_color_choice_is_one_button_with_a_menu(demo):  # noqa: F811
    from PySide6.QtWidgets import QToolButton

    from djsync.ui import theme
    from djsync.ui.palettes import PALETTES, RETIRED

    from .qt_util import pump

    assert all(v in PALETTES for v in RETIRED.values())
    demo.show_view("settings")
    view = demo.views["settings"]
    btn = view.theme_btn
    assert isinstance(btn, QToolButton) and len(btn.menu().actions()) == 12
    assert btn.height() <= theme.px(48)                       # une ligne, plus une grille de 2 × 10
    next(a for a in btn.menu().actions() if a.text() == view._swatches["red"].text()).trigger()
    pump(demo, 0.3)
    assert demo.ctrl.settings.theme == "red" and theme.ACCENT.upper() == PALETTES["red"].upper()
    assert demo.views["settings"].theme_btn.text() == view._swatches["red"].text()   # vue reconstruite (B23)


# ------------------------------------------------------------------ C10.2 : Soulseek (client simulé)
import shutil  # noqa: E402
import subprocess  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402


def _res(user, path, ext, bitrate=0, duration=269, free=True, queue=0, speed=1_000_000, size=30_000_000):
    from djsync.core.soulseek import SlskResult

    return SlskResult(user, path, size, ext, bitrate=bitrate, duration=duration, free_slot=free, queue=queue,
                      speed=speed, sample_rate=44100 if ext in ("flac", "wav") else 0,
                      bit_depth=16 if ext in ("flac", "wav") else 0)


def test_soulseek_results_are_parsed_and_ranked():
    from djsync.core.soulseek import from_aioslsk, rank

    item = SimpleNamespace(filename="@@music\\Bicep\\Isles\\03 - Bicep - Glue.flac", filesize=31_000_000,
                           extension="flac", attributes=[SimpleNamespace(key=1, value=269),
                                                         SimpleNamespace(key=4, value=44100),
                                                         SimpleNamespace(key=5, value=24)])
    peer = SimpleNamespace(username="a", has_free_slots=True, avg_speed=900_000, queue_size=0, shared_items=[item])
    [r] = from_aioslsk(peer)
    assert (r.ext, r.duration, r.bit_depth, r.lossless, r.name) == ("flac", 269, 24, True, "03 - Bicep - Glue.flac")
    assert r.quality_label() == "FLAC · 24 bit · 44.1 kHz" and r.folder == "Isles"
    pool = [
        _res("b", "x\\Bicep - Glue.mp3", "mp3", bitrate=128),
        _res("c", "x\\Bicep - Glue.mp3", "mp3", bitrate=320),
        _res("d", "x\\Bicep - Glue (Live).wav", "wav", duration=420),     # durée très différente : recule
        _res("e", "x\\Other - Song.flac", "flac"),                       # pas pertinent : retiré
        _res("f", "x\\Bicep - Glue.jpg", "jpg"),                         # pas de l'audio : retiré
        r,
    ]
    ranked = rank(pool, "Bicep Glue", duration=269)
    assert [x.username for x in ranked] == ["a", "c", "b", "d"]


def test_soulseek_track_name_from_the_file():
    from djsync.ui.ctrl.soulseek import track_of

    tr = track_of(_res("u", "@@a\\Isles\\03 - Bicep - Glue.flac", "flac"))
    assert (tr.artist, tr.title, tr.album, tr.source, tr.source_label) == ("Bicep", "Glue", "Isles", "soulseek", "Soulseek")
    assert tr.video_id.startswith("slsk:") and tr.slsk is not None


class FakeClient:
    def __init__(self, folder, files):
        from djsync.core.soulseek import Metrics

        self.folder, self.files, self.metrics = folder, files, Metrics()
        self.started = False

    @property
    def connected(self):
        return self.started

    def start(self):
        self.started = self.metrics.connected = True
        self.metrics.down.extend([0, 200_000, 800_000])
        self.metrics.up.extend([0, 0, 10_000])

    def stop(self):
        self.started = False

    def search(self, query, duration=0, on_partial=None):
        if on_partial:
            on_partial(self.files[:1])
        return list(self.files)

    def download(self, result, progress=None, should_stop=None):
        if progress:
            progress(50.0, "downloading")
        src = self.made[result.path]
        out = self.folder / src.name
        shutil.copyfile(src, out)
        return out


def _flac(path, cutoff=0):
    tmp = path.with_suffix(".src.flac")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=25:c=pink:a=0.3",
                    "-ar", "44100", str(tmp)], check=True)
    if cutoff:
        mp3 = path.with_suffix(".lossy.mp3")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp), "-b:a", "128k", "-cutoff", str(cutoff),
                        str(mp3)], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), str(path)], check=True)
        mp3.unlink()
        tmp.unlink()
    else:
        tmp.replace(path)
    return path


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
    view = demo.views["search"]
    view.mode.setCurrentIndex(1)
    assert view.hq
    view.entry.setText("Bicep")
    view.run_search(force=True)
    assert pump(demo, 6, lambda: view.table.total == 2)
    row = view.table.row(next(iter(view._tracks)))
    assert row.values["source"].startswith("Soulseek · FLAC") and not view.preview_btn.isEnabled()
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
