"""1.3.2 : Doublons qui défile (B34), Doublons repris là où il en était (C95), choix de la version à
installer (C96)."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B34
def test_duplicates_detail_scrolls_instead_of_squeezing(demo):  # noqa: F811
    from PySide6.QtWidgets import QScrollArea

    from djsync.ui.duplicates_dialog import DuplicatesDialog

    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert isinstance(dup.detail_scroll, QScrollArea) and dup.detail_scroll.widget() is dup.detail
    assert dup.detail_scroll.widgetResizable()
    demo.resize(900, 420)                                      # petite fenêtre : ça défile, rien n'est tassé
    # sous charge (CI Windows), la mise en page arrive après quelques tours de boucle : on l'attend
    assert pump(demo, 4, lambda: dup.detail.height() >= dup.detail.minimumSizeHint().height())
    assert dup.apply_btn.isVisibleTo(dup)                      # actions hors de la zone qui défile
    dup.detail_scroll.verticalScrollBar().setValue(dup.detail_scroll.verticalScrollBar().maximum())
    dup._select(0)                                             # nouveau groupe : en haut
    assert dup.detail_scroll.verticalScrollBar().value() == 0
    dup.close()


# ------------------------------------------------------------------ C95
def test_reopening_duplicates_brings_back_the_same_page(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    demo.open_diagnostic("dup")
    dup = demo.stack.currentWidget()
    assert isinstance(dup, DuplicatesDialog)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    dup.index = 0
    demo.show_view("library")                                  # ailleurs (Accueil, Bibliothèque, Grille…)
    assert demo.stack.currentWidget() is not dup
    demo.open_diagnostic("dup")                                # Accueil ▸ Trouver les doublons
    assert demo.stack.currentWidget() is dup                   # la même page, pas une nouvelle
    assert len(dup.groups) == 1 and dup.index == 0
    pages = [demo.stack.widget(i) for i in range(demo.stack.count())]
    assert sum(isinstance(p, DuplicatesDialog) for p in pages) == 1
    dup.close()                                                # Fermer : la prochaine fois, une nouvelle
    assert pump(demo, 2, lambda: demo.stack.currentWidget() is not dup)
    demo.open_diagnostic("dup")
    assert isinstance(demo.stack.currentWidget(), DuplicatesDialog) and demo.stack.currentWidget() is not dup
    demo.stack.currentWidget().close()
    assert not demo.errors


# ------------------------------------------------------------------ C96
def _release(tag, pre=False, date="2026-10-01", sha=True, asset=True):
    from djsync.core.updates import asset_name

    name = asset_name()
    assets = ([{"name": name, "browser_download_url": f"https://dl/{tag}/{name}"}] if asset else []) \
        + ([{"name": name + ".sha256", "browser_download_url": f"https://dl/{tag}/{name}.sha256"}] if sha else [])
    return {"tag_name": tag, "prerelease": pre, "draft": False, "html_url": f"https://rel/{tag}",
            "published_at": date + "T10:00:00Z", "assets": assets}


RELEASES = [_release("v1.3.1-rc.1", True, "2026-10-29"), _release("v1.3.0", False, "2026-10-28"),
            _release("v1.3.0-rc.9", True, "2026-10-28"), _release("v1.2.4", False, "2026-10-23"),
            _release("v1.2.0-rc.3", True, sha=False), {**_release("v9.9.9"), "draft": True}]


def _fetch(_url):
    return json.dumps(RELEASES).encode()


def test_list_versions_newest_first_with_or_without_test_versions():
    from djsync.core import updates

    stable = [u.version for u in updates.list_versions(_fetch, include_prerelease=False)]
    assert stable == ["1.3.0", "1.2.4"]
    every = updates.list_versions(_fetch, include_prerelease=True)
    assert [u.version for u in every] == ["1.3.1-rc.1", "1.3.0", "1.3.0-rc.9", "1.2.4"]   # sans empreinte : non
    assert every[1].date == "2026-10-28" and every[0].prerelease and every[1].checksum.endswith(".sha256")
    assert updates.is_older("1.2.4", "1.3.0-rc.9") and not updates.is_older("1.3.0", "1.3.0-rc.9")


def test_show_test_versions_box():
    from djsync.ui.version_dialog import show_test_versions

    assert show_test_versions("test", "1.3.0") and not show_test_versions("stable", "1.3.0-rc.9")
    assert show_test_versions("auto", "1.3.0-rc.9") and not show_test_versions("auto", "1.3.0")


def test_version_dialog_installs_an_older_version_after_a_warning(demo, monkeypatch):  # noqa: F811
    from djsync.core import updates
    from djsync.ui import version_dialog
    from djsync.ui.dialogs import ConfirmDialog

    ctrl = demo.ctrl
    monkeypatch.setattr(version_dialog, "full_version", lambda: "1.3.0-rc.9")
    asked = []
    monkeypatch.setattr(ctrl, "app_versions", lambda pre, ok, failed=None: (asked.append(pre),
                        ok(updates.list_versions(_fetch, include_prerelease=pre))))
    monkeypatch.setattr(ctrl, "can_self_update", lambda: True)
    installed = []
    monkeypatch.setattr(ctrl, "app_update_install", installed.append)
    confirms = []
    real_confirm = version_dialog.ConfirmDialog

    def spy_confirm(*a, **k):
        confirms.append(real_confirm(*a, **k))
        return confirms[-1]

    monkeypatch.setattr(version_dialog, "ConfirmDialog", spy_confirm)
    ctrl.settings.update_channel = "auto"
    box = version_dialog.VersionDialog(demo, ctrl)
    assert box.show_rc.isChecked() and asked == [True]         # version de test : rc affichées
    rows = [box.list.item(i).data(0x0100) for i in range(box.list.count())]
    assert rows == ["1.3.1-rc.1", "1.3.0", "1.3.0-rc.9", "1.2.4"]
    from djsync.i18n import t

    assert t("update.pick_installed") in box.list.item(2).text()
    box.list.setCurrentRow(rows.index("1.3.0-rc.9"))           # la version installée : pas d'installation
    assert not box.install_btn.isEnabled()
    box.list.setCurrentRow(rows.index("1.3.0"))                 # plus récente : directe
    box._install()
    assert [u.version for u in installed] == ["1.3.0"] and not confirms
    box = version_dialog.VersionDialog(demo, ctrl)
    rows = [box.list.item(i).data(0x0100) for i in range(box.list.count())]
    box.list.setCurrentRow(rows.index("1.2.4"))                 # plus ancienne : avertissement d'abord
    box._install()
    assert len(installed) == 1 and len(confirms) == 1 and isinstance(confirms[0], ConfirmDialog)
    confirms[0]._ok()
    assert [u.version for u in installed] == ["1.3.0", "1.2.4"]
    box = version_dialog.VersionDialog(demo, ctrl)
    box.show_rc.setChecked(False)                               # sans les rc : enregistré, liste relue
    assert ctrl.settings.update_channel == "stable" and asked[-1] is False and box.list.count() == 2
    box.close()


def test_settings_box_and_button(demo):  # noqa: F811
    demo.show_view("settings")
    view = demo.views["settings"]
    assert hasattr(view, "show_rc_var") and not hasattr(view, "channel_menu")
    view.show_rc_var.setChecked(True)
    view._save()
    assert demo.ctrl.settings.update_channel == "test"
