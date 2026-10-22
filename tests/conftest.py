"""Tests d'interface Qt sans écran : plateforme « offscreen » (aucun Xvfb nécessaire)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")       # sortie audio « null » (miniaudio)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """Jamais de vraie requête « nouvelle version de DJSync ? » pendant les tests."""
    import djsync.core.updates as updates

    def offline(url):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(updates, "_http_get", offline)
