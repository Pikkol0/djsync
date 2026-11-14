"""1.4.1 (B97) : pas de plantage au lancement quand un navigateur YouTube est réglé."""


# ------------------------------------------------------------------ B97 : navigateur YouTube réglé au démarrage
def test_b97_start_with_youtube_browser_set(tmp_path, monkeypatch):
    """Plantage au lancement (« 'AppController' object has no attribute 'jobs' ») quand un navigateur
    YouTube était choisi : la relance des refus « robot » (B66) partait avant la création de self.jobs."""
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    import djsync.ui.controller as controller

    from .demo_fixture import make_demo_usb
    from .qt_util import close_window, make_window
    from .test_ui_smoke import FakeService

    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(youtube_browser="firefox"), monkeypatch)
    try:
        c = window.ctrl
        assert c.jobs == []
        assert c.service._downloader.youtube_auth == {"cookiesfrombrowser": ("firefox",)}
        retried = []
        monkeypatch.setattr(c, "retry_bot_failures", lambda: retried.append(1))
        c._apply_output()                                    # enregistrement des Paramètres : relance gardée
        assert retried == [1]
        assert not window.errors
    finally:
        close_window(window)
