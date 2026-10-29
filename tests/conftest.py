"""Tests d'interface Qt sans écran : plateforme « offscreen » (aucun Xvfb nécessaire)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")       # sortie audio « null » (miniaudio)
os.environ.setdefault("DJSYNC_ERROR_REPORTS", "off")  # 1.2.3 : jamais de rapport d'erreur envoyé par les tests

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _quality_register(tmp_path_factory):
    """1.4.0 (C46) : registre des vraies qualités dans un dossier de test, jamais celui de l'utilisateur."""
    from djsync.analysis import spectrum

    spectrum.use_store(tmp_path_factory.mktemp("quality") / "quality.json")
    yield
    spectrum.use_store(None)


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """Jamais de vraie requête « nouvelle version de DJSync ? » pendant les tests."""
    import djsync.core.updates as updates

    def offline(url):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(updates, "_http_get", offline)


# ---------------------------------------------------------------- CI : tests en parallèle (1.3.0-rc.8)
# DJSYNC_SHARD / DJSYNC_SHARDS : la CI répartit les fichiers de test sur plusieurs machines (un fichier
# reste entier sur une machine). DJSYNC_FAST_EXIT : à la fin, sortie immédiate avec le bon code, sans
# laisser Qt et les fils audio se détruire (plantage aléatoire à la fermeture alors que tout est passé).
def pytest_configure(config):
    # C91 (1.3.1) : « slow » = gros tests d'interface, lancés quand une PR est prête et à la release,
    # pas pendant le développement (workflow « Tests », -m "not slow").
    config.addinivalue_line("markers", "slow: long UI test, skipped by the quick test run")


# C91 (1.3.1) : les 30 tests les plus lents mesurés en CI (Linux, 28/10 : 7 à 17 s chacun, ~300 s sur 544 au
# total) : sautés par la passe rapide de développement (-m "not slow"), gardés par la passe complète (PR
# prête, release). Liste à revoir à partir des durées publiées par le workflow « Tests ».
SLOW_TESTS = {
    "test_ui_v020.py::test_zoom_is_live_and_window_size_does_not_change_it",
    "test_ui_v020.py::test_language_rebuild",
    "test_ui_v020.py::test_dialogs_open",
    "test_ui_v020.py::test_queue_next_previous",
    "test_v130rc4.py::test_new_accent_recolors_home_tools_without_restart",
    "test_v130rc4.py::test_uniformize_blocks_are_never_squeezed",
    "test_v130rc4.py::test_removed_drive_one_clear_message_then_reopens",
    "test_v130rc4.py::test_latency_test_dialog_sets_the_offset_live",
    "test_v130rc7.py::test_disk_io_error_on_a_replugged_drive_reopens_it_quietly",
    "test_v130rc7.py::test_watch_notices_a_dead_connection_although_the_drive_is_back",
    "test_v130rc7.py::test_alive_never_blocks_a_busy_library",
    "test_v130rc7.py::test_other_errors_are_still_shown",
    "test_v130rc8.py::test_opening_a_page_logs_any_other_visible_window",
    "test_v130rc8.py::test_reanalysis_started_elsewhere_shows_in_the_analysis_list",
    "test_v130rc8.py::test_play_pause_follows_the_current_track_when_grid_page_is_hidden",
    "test_v130rc8.py::test_back_when_the_origin_page_was_closed_meanwhile",
    "test_v130rc8.py::test_back_from_grid_editor_still_returns_to_a_tab",
    "test_v130rc8.py::test_back_from_grid_editor_returns_to_the_duplicates_page",
    "test_ui_smoke.py::test_search_download_reorder_and_backup",
    "test_ui_local.py::test_computer_library_opens_and_works",
    "test_backups.py::test_retention_keeps_origin_year_month_week_and_five_recent",
    "test_ui_v024.py::test_unanalysed_section_and_background_analysis",
    "test_ui_v024.py::test_stop_analysis_empties_the_queue",
    "test_ui_v050.py::test_usb_export_pdb_repaired_on_open_and_rekordbox_warning",
    "test_ui_v050.py::test_settings_engine_offer_and_copy_menu",
    "test_v131_c88_c89.py::test_check_list_closes_and_folds_away_when_all_is_well",
    "test_v131_c88_c89.py::test_check_everything",
    "test_v131_c88_c89.py::test_advanced_section_and_folded_cards",
    "test_v131_c88_c89.py::test_uninstall_button_always_in_djsync_section",
    "test_v123.py::test_duplicates_and_diagnostic_open_as_pages",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("/")[-1] in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)
    shards = int(os.environ.get("DJSYNC_SHARDS", "1") or 1)
    if shards <= 1:
        return
    import zlib

    shard = int(os.environ.get("DJSYNC_SHARD", "1")) - 1
    keep, drop = [], []
    for item in items:
        name = item.nodeid.split("::", 1)[0]
        (keep if zlib.crc32(name.encode()) % shards == shard else drop).append(item)
    items[:] = keep
    config.hook.pytest_deselected(items=drop)


_exit_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _exit_status["code"] = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if os.environ.get("DJSYNC_FAST_EXIT") and not hasattr(config, "workerinput"):
        import sys

        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_exit_status["code"])
