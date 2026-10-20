"""Settings, i18n, thème : infrastructure de la V1.1 (aucun écran requis)."""
import json

import pytest

from djsync import i18n
from djsync.models import JOB_STATUS_LABELS, PREFERENCE_LABELS, SEARCH_MODE_LABELS, DownloadJob, SearchMode, TrackResult, format_views
from djsync.settings import Settings, clamp_zoom


@pytest.fixture(autouse=True)
def _english():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


# ------------------------------------------------------------------ i18n
def test_english_is_default_and_french_optional():
    assert i18n.get_language() == "en"
    assert i18n.t("tab.home") == "Home"
    i18n.set_language("fr")
    assert i18n.t("tab.home") == "Accueil"


def test_language_normalisation_and_fallbacks():
    assert i18n.set_language("FR_fr") == "fr"
    assert i18n.set_language("de") == "en"        # inconnue -> anglais
    assert i18n.t("no.such.key") == "no.such.key"  # jamais d'exception
    assert i18n.t("lib.tracks_many", n=5) == "5 tracks"
    assert i18n.t("lib.tracks_many") == "{n} tracks"   # paramètre manquant : texte brut, pas de crash


def test_catalogues_have_identical_keys_and_placeholders():
    import re
    en, fr = i18n.en.STRINGS, i18n.fr.STRINGS
    assert set(en) == set(fr), set(en) ^ set(fr)
    for key in en:
        assert sorted(re.findall(r"{(\w+)}", en[key])) == sorted(re.findall(r"{(\w+)}", fr[key])), key


def test_plural_rules():
    assert i18n.plural("lib.tracks_one", "lib.tracks_many", 1) == "1 track"
    assert i18n.plural("lib.tracks_one", "lib.tracks_many", 0) == "0 tracks"
    i18n.set_language("fr")
    assert i18n.plural("lib.tracks_one", "lib.tracks_many", 0) == "0 titre"
    assert i18n.plural("lib.tracks_one", "lib.tracks_many", 2) == "2 titres"


def test_model_labels_follow_the_language():
    assert SEARCH_MODE_LABELS[SearchMode.ALL] == "All"
    assert list(PREFERENCE_LABELS.values())[0] == "Automatic"
    job = DownloadJob(1, TrackResult("id", "t", "a"), status="downloading", percent=42)
    assert job.status_label == "Downloading 42 %"
    i18n.set_language("fr")
    assert SEARCH_MODE_LABELS[SearchMode.ALL] == "Tout"
    assert job.status_label == "Téléchargement 42 %"
    assert TrackResult("id", "t", "a", result_type="video").kind_label == "Vidéo"
    assert format_views(1250) == "1,2 k"
    i18n.set_language("en")
    assert format_views(1250) == "1.2 k" and format_views(None) == "—"


# --------------------------------------------------------------- settings
def test_settings_defaults_are_v11():
    s = Settings()
    assert (s.language, s.theme, s.zoom) == ("en", "violet_light", 100)


def test_settings_load_validates_and_roundtrips(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"zoom": 350, "language": "de", "volume": 9.0, "theme": "cyan", "geometry": "1x1"}))
    s = Settings.load(f)
    assert (s.zoom, s.language, s.volume, s.theme) == (200, "en", 1.0, "cyan")
    s.zoom, s.language = 130, "fr"
    s.save(f)
    again = Settings.load(f)
    assert (again.zoom, again.language) == (130, "fr")


def test_old_v010_settings_file_still_loads(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"forced_drive": "E", "exclude_words": "live", "geometry": "1200x700"}))
    s = Settings.load(f)
    assert s.forced_drive == "E" and s.language == "en" and s.zoom == 100


@pytest.mark.parametrize("raw, expected", [(50, 80), (85, 85), (100, 100), (149.6, 150), (999, 200), ("120", 120), (None, 100), ("x", 100)])
def test_clamp_zoom(raw, expected):
    assert clamp_zoom(raw) == expected


# ------------------------------------------------------------------ thème
def test_palettes():
    pytest.importorskip("PySide6")
    from djsync.ui import theme

    assert len(theme.PALETTES) == 20 and theme.DEFAULT_THEME == "violet_light"
    for name, accent in theme.PALETTES.items():
        assert i18n.en.STRINGS[f"theme.{name}"] and i18n.fr.STRINGS[f"theme.{name}"]   # nom traduit
        colors = theme.palette_colors(accent)
        # texte posé sur l'accent lisible (le meilleur de noir/blanc donne toujours >= 4.4 : WCAG « grand texte » = 3)
        assert theme.contrast(colors["ACCENT"], colors["ON_ACCENT"]) >= 4.4, name
    assert theme.apply_palette("cyan") == "cyan" and theme.ACCENT == "#36E2FF"
    assert theme.apply_palette("inconnu") == "violet_light" and theme.ACCENT == "#B79CFF"
    assert theme.ACCENT in theme.stylesheet()


def test_zoom_is_fixed_by_the_setting_only():
    """V0.3.0 : plus de zoom automatique selon la taille de la fenêtre ; Qt gère le DPI."""
    pytest.importorskip("PySide6")
    from djsync.ui import theme

    try:
        assert theme.set_zoom(100) == 1.0 and theme.px(32) == 32
        theme.set_zoom(150)
        assert theme.px(32) == 48 and theme.font_pt() == theme.BASE_PT * 1.5
        assert theme.set_zoom(999) == 2.0 and theme.set_zoom(10) == 0.8   # bornes 80-200 %
        assert not hasattr(theme, "update_auto")
    finally:
        theme.set_zoom(100)
