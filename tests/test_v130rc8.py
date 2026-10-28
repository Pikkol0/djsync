"""1.3.0-rc.8 : B29 (Retour vers la page d'origine), B30 (liste Analyse), B31 (Lecture après Grille et cues)."""
from .test_v122 import demo, usb  # noqa: F401
from .qt_util import pump


def _library_track(app):
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total > 0)
    return next(r.data for r in lib.table.all_rows() if r.data is not None)


# ------------------------------------------------------------------ B29
def test_back_from_grid_editor_returns_to_the_duplicates_page(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    track = _library_track(demo)
    demo.show_view("home")
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert demo.stack.currentWidget() is dup
    demo.open_grid_editor(track)
    assert demo.stack.currentWidget() is demo.grid_editor
    demo.grid_editor.close()                                   # Retour (rien à enregistrer)
    assert pump(demo, 2, lambda: demo.stack.currentWidget() is dup)
    assert len(dup.groups) == 1                                # même état
    dup.close()                                                # puis Retour des Doublons : l'Accueil
    assert pump(demo, 2, lambda: demo.stack.currentWidget() is demo.views["home"])
    assert not demo.errors


def test_back_from_grid_editor_still_returns_to_a_tab(demo):  # noqa: F811
    track = _library_track(demo)
    demo.open_grid_editor(track)
    demo.grid_editor.close()
    assert pump(demo, 2, lambda: demo.stack.currentWidget() is demo.views["library"])


def test_back_when_the_origin_page_was_closed_meanwhile(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    track = _library_track(demo)
    dup = DuplicatesDialog(demo.views["library"], demo.ctrl)
    demo.open_grid_editor(track)
    demo.close_dialog_page(dup)                                # fermée entre-temps
    dup.deleteLater()
    pump(demo, 0.3)
    demo.open_grid_editor(track)
    demo.grid_editor.close()
    assert pump(demo, 2, lambda: demo.stack.currentWidget() in demo.views.values())
    assert not demo.errors


# ------------------------------------------------------------------ B30
def test_reanalysis_started_elsewhere_shows_in_the_analysis_list(demo, monkeypatch):  # noqa: F811
    track = _library_track(demo)
    view = demo.views["downloads"]
    cid = track.content_id
    if not track.is_analysed:                                  # d'abord un son déjà analysé
        demo.ctrl.analyze([cid])
        assert pump(demo, 30, lambda: not demo.ctrl.analysis.running)
    demo.ctrl.analysis_results.clear()                         # nouvelle session : la liste ne le montre plus
    view._fill()
    assert pump(demo, 4, lambda: view.an_table.row(str(cid)) is None)
    demo.show_view("downloads")
    import threading
    lib, gate = demo.ctrl.library, threading.Event()
    real = lib.analyze_tracks
    monkeypatch.setattr(lib, "analyze_tracks", lambda *a, **k: (gate.wait(10), real(*a, **k))[1])
    demo.ctrl.analyze([cid], force=True)                       # réanalyse lancée depuis la Bibliothèque
    assert pump(demo, 4, lambda: view.an_table.row(str(cid)) is not None)   # visible PENDANT l'analyse
    gate.set()
    assert pump(demo, 30, lambda: not demo.ctrl.analysis.running)
    assert not demo.errors


# ------------------------------------------------------------------ B31
def test_play_pause_follows_the_current_track_when_grid_page_is_hidden(demo, monkeypatch):  # noqa: F811
    """Testeur Mac : son A, Grille et cues, on change d'onglet, son B, Pause puis Lecture -> c'était A."""
    track = _library_track(demo)
    demo.open_grid_editor(track)
    ed = demo.grid_editor
    called = []
    monkeypatch.setattr(ed, "_play", lambda *a, **k: called.append(1))
    demo.ctrl.toggle_play()                                     # page affichée : Lecture = son de la page
    assert called == [1]
    demo.show_view("library")                                   # la page reste ouverte, cachée
    assert pump(demo, 1, lambda: not ed.isVisible())
    assert demo.player_bar._grid_editor is None                 # le lecteur du bas ne la suit plus
    toggled = []
    monkeypatch.setattr(demo.ctrl.player, "toggle_pause", lambda: toggled.append(1))
    monkeypatch.setattr(type(demo.ctrl.player), "state", property(lambda self: "playing"), raising=False)
    demo.ctrl.toggle_play()                                     # Pause / Lecture du son en cours
    assert called == [1] and toggled == [1]
    demo.open_grid_editor(track)                                # on revient sur la page : elle reprend la main
    assert pump(demo, 1, lambda: ed.isVisible()) and demo.player_bar._grid_editor is ed
    assert not demo.errors


# ------------------------------------------------------------------ B33
def test_audio_callback_late_is_logged(monkeypatch, caplog):
    """Mac : petit saut entendu quand l'interface travaille. Le retard du thread audio est journalisé
    (une fois toutes les 2 s) pour le diagnostic du testeur."""
    import logging

    from djsync.audio import player as P

    class _S:
        done = False

        def read(self, n):
            return b"\0" * n

    clock = [100.0]
    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    pl = P.AudioPlayer.__new__(P.AudioPlayer)
    import threading
    pl._lock, pl._stream, pl._paused, pl._frames, pl._volume = threading.Lock(), _S(), False, 0, 1.0
    pl._dev_t0, pl._dev_frames, pl._dev_lead = None, 0, 0.0
    caplog.set_level(logging.INFO, logger=P.__name__)
    n = P.RATE // 10                                           # paquets de 100 ms
    for _ in range(5):                                         # à l'heure : rien
        pl._fill(n)
        clock[0] += 0.1
    assert "Audio late" not in caplog.text
    clock[0] += 0.5                                            # le thread audio attend 500 ms de trop
    pl._fill(n)
    assert "Audio late" not in caplog.text                     # rien n'est écrit depuis le thread audio
    pl.state = P.STOPPED
    pl.position()                                              # l'interface le note
    assert "Audio late by" in caplog.text


# ------------------------------------------------------------------ B32
def test_opening_a_page_logs_any_other_visible_window(demo, caplog):  # noqa: F811
    """Mac plein écran : ouvrir Doublons renvoyait au bureau. Diagnostic : à l'ouverture d'une page,
    toute autre fenêtre visible est notée dans le journal (aucune attendue)."""
    import logging

    from PySide6.QtWidgets import QWidget

    from djsync.ui.duplicates_dialog import DuplicatesDialog

    caplog.set_level(logging.INFO, logger="djsync.ui.app")
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    pump(demo, 0.6)
    assert not dup.isWindow()
    assert "window shown" not in caplog.text
    demo.watch_windows("Test", seconds=1.0)                     # 1.3.0-rc.9 : surveillance continue
    extra = QWidget()                                           # une fenêtre en trop : notée
    extra.show()
    assert pump(demo, 1, lambda: "window shown after" in caplog.text)
    extra.close()
    extra.deleteLater()
    pump(demo, 0.2)
    dup.close()
    assert not demo.errors
