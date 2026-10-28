"""Tests d'interface Qt sans écran : plateforme « offscreen » (aucun Xvfb nécessaire)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")       # sortie audio « null » (miniaudio)
os.environ.setdefault("DJSYNC_ERROR_REPORTS", "off")  # 1.2.3 : jamais de rapport d'erreur envoyé par les tests

import pytest  # noqa: E402


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


def pytest_collection_modifyitems(config, items):
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
