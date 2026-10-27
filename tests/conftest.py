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
