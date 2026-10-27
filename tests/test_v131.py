"""1.3.1 : confort (C29 couleurs, C34 lecteur centré, C33 filtres, C37 colonnes, C28 réglages, C27 espace,
C30 suggestions, C38 genre dans export.pdb, C41/C43 Diagnostic, C42 qualité des doublons)."""
import pytest

pytest.importorskip("PySide6")

from .test_v130rc3 import _demo_app  # noqa: E402


# ------------------------------------------------------------------ C29 / C42 : échelle de qualité
def test_quality_scale_thresholds():
    from djsync.ui import levels as L

    assert [L.similarity(p) for p in (95, 80, 60, 30)] == ["good", "fair", "warn", "bad"]
    assert [L.audio_quality(k) for k in (320, 256, 160, 96)] == ["good", "fair", "warn", "bad"]
    assert L.audio_quality(0, lossless=True) == "good" and L.audio_quality(0) == "neutral"
    assert [L.bpm_gap(p) for p in (1, -3, 5, 9)] == ["good", "fair", "warn", "bad"]
    assert L.quality_rank(0, True) > L.quality_rank(320) > L.quality_rank(128)


def test_audio_text_always_says_format_bitrate_and_rate():
    from djsync.core.quality import AudioInfo
    from djsync.ui import levels as L

    assert L.audio_text(AudioInfo("aac", 256, 44100), 4) == ("AAC · 256 kbps · 44.1 kHz", "fair")
    assert L.audio_text(AudioInfo("flac", 900, 48000), 5)[0] == "FLAC · lossless · 48 kHz"
    assert L.audio_text(None, 1) == ("MP3", "neutral")
    assert L.audio_text(AudioInfo("aac", 128, 44100), 4, missing=True) == ("?", "neutral")
    assert "320" in L.expected_download("ytmusic", "mp3")[0]


# ------------------------------------------------------------------ C34 : lecteur centré
@pytest.mark.parametrize("width", [1100, 1600, 2200])
def test_player_controls_are_centred_in_the_window(tmp_path, monkeypatch, width):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.resize(width, 800)
        pump(app, 0.3)
        bar = app.player_bar
        btn = bar.play_btn
        centre = btn.mapTo(bar, btn.rect().center()).x()
        assert abs(centre - bar.width() / 2) <= max(6, bar.width() * 0.01)
    finally:
        close_window(app)


# ------------------------------------------------------------------ C33 : un seul bouton de filtres
def test_search_has_one_filters_button_showing_active_filters(tmp_path, monkeypatch):
    from djsync.i18n import t
    from djsync.ui.dialogs import FiltersPopup

    from .qt_util import close_window

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        view = app.views["search"]
        assert not hasattr(view, "field_menu")
        assert view.filter_btn.text() == t("search.filters_short")
        got = {}
        monkeypatch.setattr(FiltersPopup, "show_dialog", lambda self: got.setdefault("dlg", self))
        view._open_filters()
        dlg = got["dlg"]
        dlg._field.setCurrentText(view._field_labels["artist"])
        dlg._minutes.setCurrentIndex(3)                      # ≤ 10 min
        dlg._apply()
        s = app.ctrl.settings
        assert s.search_field == "artist" and s.search_max_minutes == 10
        assert view.filter_btn.text() == f"{view._field_labels['artist']} · ≤ 10 min"
    finally:
        close_window(app)
