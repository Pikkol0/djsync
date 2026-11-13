"""1.4.1 (C143) : Paramètres ▸ Téléchargement, une seule liste de six choix ; « Même volume » retiré."""
from __future__ import annotations

import json
import wave

import pytest

from djsync.models import TrackResult


@pytest.mark.parametrize("fmt, best, normalize, expected", [
    ("m4a", False, False, "original"),
    ("m4a", True, True, "yt_best"),
    ("mp3", False, True, "mp3_320"),
    ("mp3", True, False, "mp3_320"),
])
def test_c143_old_settings_are_taken_over_without_question(tmp_path, monkeypatch, fmt, best, normalize, expected):
    from djsync.settings import Settings

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"audio_format": fmt, "youtube_best": best, "normalize_volume": normalize}))
    s = Settings.load(path)
    assert s.download_quality == expected and s.normalize_volume is False         # « Même volume » ignoré
    s.save(path)
    saved = json.loads(path.read_text())
    assert saved["download_quality"] == expected
    assert not {"audio_format", "youtube_best", "normalize_volume"} & set(saved)   # plus jamais écrits
    again = Settings.load(path)
    assert again.download_quality == expected


def _wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    return path


@pytest.mark.parametrize("quality, fmt_start, pp, mp3", [
    ("original", "bestaudio[ext=m4a]", None, None),
    ("yt_best", "141/", "256", None),
    ("mp3_320", "141/", None, "320k"),
    ("mp3_256", "141/", None, "256k"),
    ("mp3_192", "141/", None, "192k"),
    ("mp3_128", "141/", None, "128k"),
])
def test_c143_each_choice_gives_what_its_label_says(tmp_path, monkeypatch, quality, fmt_start, pp, mp3):
    from djsync.core import downloader as D

    seen, conv = [], []

    def fake_run(self, track, dest, base, extra, notify):
        seen.append(extra)
        return _wav(dest / f"{base}.webm"), "251"

    def fake_finalize(path, ffmpeg, audio_format="m4a", mp3_bitrate="320k"):
        conv.append((audio_format, mp3_bitrate))
        out = path.with_suffix(".mp3")
        path.rename(out)
        return out

    monkeypatch.setattr(D.Downloader, "_run", fake_run)
    monkeypatch.setattr(D, "finalize", fake_finalize)
    monkeypatch.setattr(D, "tag_audio", lambda *a, **k: None)
    d = D.Downloader(quality=quality)
    res = d.download(TrackResult(video_id="y" * 11, title="T", artist="A"), tmp_path)
    assert seen[-1]["format"].startswith(fmt_start)
    assert (seen[-1].get("postprocessors") or [{}])[0].get("preferredquality") == pp
    if mp3:
        assert conv == [("mp3", mp3)] and res.file_path.endswith(".mp3")      # MP3 depuis le meilleur flux
    else:
        assert conv == []                                                     # sans conversion de notre part


def test_c143_an_mp3_is_never_re_encoded_and_unreadable_streams_are_not_kept(tmp_path, monkeypatch):
    from djsync.core import downloader as D

    monkeypatch.setattr(D, "tag_audio", lambda *a, **k: None)
    monkeypatch.setattr(D.Downloader, "_run", lambda self, tr, dest, base, extra, n: (_wav(dest / f"{base}.mp3"), "0"))
    monkeypatch.setattr(D, "finalize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no re-encode")))
    sc = TrackResult(video_id="sc1", title="T", artist="A", source="soundcloud", source_url="https://soundcloud.com/a/t")
    res = D.Downloader(quality="mp3_192").download(sc, tmp_path / "a")            # déjà un MP3 : gardé
    assert res.file_path.endswith(".mp3")
    monkeypatch.setattr(D.Downloader, "_run", lambda self, tr, dest, base, extra, n: (_wav(dest / f"{base}.webm"), "251"))
    monkeypatch.setattr(D, "finalize", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no LAME")))
    with pytest.raises(RuntimeError):                                             # Opus illisible : pas gardé
        D.Downloader(quality="mp3_320").download(TrackResult(video_id="z" * 11, title="T", artist="A"), tmp_path / "b")


def test_c143_best_stream_named_on_one_line_only_in_both_languages():
    from djsync.i18n import en, fr
    from djsync.settings import DOWNLOAD_QUALITIES

    for strings, mark in ((en.STRINGS, "(best stream)"), (fr.STRINGS, "(meilleur flux)")):
        labels = [strings[f"settings.quality_{q}"] for q in DOWNLOAD_QUALITIES]
        assert sum(mark in x for x in labels) == 1
        assert all(("M4A" in x or "MP3" in x) and "kbps" in x for x in labels)    # vrai format sur chaque ligne
        assert "Original" not in " ".join(labels)
    assert "normalize" not in " ".join(en.STRINGS) or "settings.normalize" not in en.STRINGS


qt = pytest.importorskip("PySide6")

from .test_v122 import demo, usb  # noqa: E402,F401


def test_c143_settings_list_sizes_hints_and_no_same_volume(demo):  # noqa: F811
    from djsync.settings import DOWNLOAD_QUALITIES

    v = demo.views["settings"]
    m = v.format_menu
    assert [m.itemData(i) for i in range(m.count())] == list(DOWNLOAD_QUALITIES)
    assert m.itemText(0).startswith("M4A · AAC ≈ 128 kbps, no conversion") and "MB/min" in m.itemText(0)
    assert "To save space" in m.itemData(5, 0x0003)                              # Qt.ToolTipRole : MP3 128
    assert not hasattr(v, "normalize_var") and not hasattr(v, "yt_best_var")
    m.setCurrentIndex(m.findData("mp3_192"))
    assert not v.format_warn.isHidden() and v.yt_best_warn.isHidden()
    v._save()
    assert demo.ctrl.settings.download_quality == "mp3_192"
    assert demo.ctrl.service._downloader.quality == "mp3_192" if hasattr(demo.ctrl.service, "_downloader") else True
    m.setCurrentIndex(m.findData("original"))
    v._save()
    assert not demo.errors
