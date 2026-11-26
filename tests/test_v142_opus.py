"""1.4.2, lot Opus : B102 (dossier surveillé : quelle bibliothèque), B103 (Diagnostic sans calcul à l'ouverture),
C198 (Uniformiser : portée dans l'onglet) et fiches A2 de l'audit UX (textes, affichage, confirmations)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from djsync.i18n import t  # noqa: E402

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401
from .test_v140 import _wav  # noqa: E402


# ------------------------------------------------------------------ A2-1 : Paramètres dans la largeur de la page
@pytest.mark.parametrize("size", [(1280, 800), (860, 560)])
def test_a2_1_settings_fit_the_page(demo, size):  # noqa: F811
    from djsync.i18n import set_language

    for lang in ("en", "fr"):
        set_language(lang)
        demo.ctrl.settings.language = lang
        demo.rebuild_ui()
        demo.resize(*size)
        demo.show_view("settings")
        pump(demo, 0.5)
        view = demo.views["settings"]
        page = view.area.widget()
        room = view.area.viewport().width() + 1
        from PySide6.QtWidgets import QWidget

        wide = [(type(w).__name__, w.minimumSizeHint().width(), getattr(w, "text", lambda: "")()[:60])
                for w in page.findChildren(QWidget) if w.isVisibleTo(page) and not w.layout()
                and w.minimumSizeHint().width() > room]

        def rows(lay, out):                     # rangées trop larges, avec ce qu'elles contiennent
            for i in range(lay.count()):
                it = lay.itemAt(i)
                sub = it.layout() or (it.widget().layout() if it.widget() is not None else None)
                if sub is None:
                    continue
                if sub.minimumSize().width() > room - 40:
                    out.append((sub.minimumSize().width(), [
                        (type(sub.itemAt(k).widget()).__name__, sub.itemAt(k).widget().minimumSizeHint().width(),
                         getattr(sub.itemAt(k).widget(), "text", lambda: "")()[:30])
                        for k in range(sub.count()) if sub.itemAt(k).widget() is not None]))
                rows(sub, out)
            return out

        wide += rows(page.layout(), [])[-6:]
        assert page.minimumSizeHint().width() <= room, (lang, size, wide)
    set_language("en")
    demo.ctrl.settings.language = "en"


def test_a2_1_wrap_checkbox_keeps_qcheckbox_api(demo):  # noqa: F811
    from djsync.ui.widgets import WrapCheckBox

    box = WrapCheckBox("A very long text " * 10)
    box.setChecked(True)
    assert box.isChecked() and box.text().startswith("A very")
    assert box.minimumSizeHint().width() < box.sizeHint().width()
    assert box.heightForWidth(200) > box.heightForWidth(2000)


# ------------------------------------------------------------------ A2-3 : barre de la Bibliothèque recalculée
def test_a2_3_library_bar_refits_when_shown_after_resize(demo):  # noqa: F811
    demo.resize(1280, 800)
    demo.show_view("library")
    pump(demo, 0.5)
    demo.show_view("settings")
    pump(demo, 0.3)
    demo.resize(860, 560)
    pump(demo, 0.3)
    demo.show_view("library")
    bar = demo.views["library"].bar
    assert pump(demo, 2, lambda: bar._applied is not None and bar._need(bar._applied) <= bar.width())


# ------------------------------------------------------------------ A2-6 : formats à la française
def test_a2_6_numbers_dates_and_words():
    from djsync.i18n import date_text, num, set_language

    set_language("fr")
    try:
        assert num(44.1) == "44,1" and num(1.92, ".1f") == "1,9"
        assert date_text("2026-11-16 10:00:00") == "16/11/2026"
        assert t("machine.describe", cores=2, mem="8") == "2 cœurs, 8 Go"
        assert t("help.key_enter") == "Entrée" and t("unit.kbps", n=320) == "320 kbps"
    finally:
        set_language("en")
    assert num(44.1) == "44.1" and date_text("2026-11-16") == "2026-11-16"


# ------------------------------------------------------------------ A2-7, A2-8, A2-9 : textes
def test_a2_7_8_9_catalogue_wording():
    import re

    from djsync.i18n import en, fr

    fr_text = " ".join(fr.STRINGS.values())
    assert not re.search(r"\bmorceaux?\b", fr_text)                       # A2-8 : « son » partout
    assert not re.search(r"\b(tu|tes|ton|ta)\b|Rends-la|réessaie\b", fr_text)
    assert "kb/s" not in fr_text and "kbit/s" not in fr_text and "supposée" not in fr_text
    assert "même clé" not in fr_text and "Aucune cue" not in fr_text
    for cat in (en.STRINGS, fr.STRINGS):
        assert not any("Import URL" in v or "omnibar" in v for v in cat.values())      # A2-7, A2-9
        # 1.4.2-rc.2 (C208) : « export.pdb » revient dans les libellés, l'effet est dans la bulle
        assert all(cat[k].startswith("export.pdb") for k in ("home.pdb_short_no", "home.pdb_short_yes",
                                                              "home.pdb_stale", "set.row_pdb"))
        assert all("CDJ-2000NXS2" in cat[k] for k in ("home.pdb_yes", "home.pdb_no_tip", "home.pdb_stale_tip",
                                                      "pdb.older_tip"))
    from djsync.ui import help_dialog

    assert not hasattr(help_dialog, "TOPICS")                              # A2-7 : plus de « Guide rapide »


def test_a2_7_help_has_no_quick_guide(demo):  # noqa: F811
    from djsync.ui.help_dialog import HelpDialog

    h = HelpDialog(demo)
    assert h.tabs.count() == 2 and h.tabs.currentIndex() == 1               # Premiers pas, Raccourcis
    h.close()


# ------------------------------------------------------------------ A2-10 : Accueil sans bibliothèque
def test_a2_10_home_without_library_has_first_steps(demo, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QPushButton

    home = demo.views["home"]
    monkeypatch.setattr(demo.ctrl, "unprepared", [], raising=False)
    home._show([])
    texts = [b.text() for b in home.cards.findChildren(QPushButton)]
    assert t("start.tab") in texts


# ------------------------------------------------------------------ A2-11 : premier lancement
def test_a2_11_welcome_two_screens_and_tour_box(demo, monkeypatch):  # noqa: F811
    from djsync.ui import tour
    from djsync.ui.welcome import WelcomeDialog

    monkeypatch.setattr(tour, "OFFER_AT_START", True)
    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    started = []
    monkeypatch.setattr(tour, "start", lambda win: started.append(win))
    demo.ctrl.settings.tour_state = ""
    w = WelcomeDialog(demo, demo.ctrl)
    assert w._step == 1 and w.lang_buttons and w.star_btn.property("kind") == "flat"
    # 1.4.4 (C227) : un seul écran ; la case de la visite guidée est dessus, « Commencer » la lance
    assert w.tour_box is not None and w.tour_box.isChecked() and w.yt_buttons
    w.start_btn.click()
    assert demo.ctrl.settings.tour_state == "done" and demo._tour_asked
    assert pump(demo, 1, lambda: started == [demo])


# ------------------------------------------------------------------ A2-12 : « Prêt pour le set ? »
def test_a2_12_set_check_hints_and_real_buttons(demo):  # noqa: F811
    from djsync.core.set_check import Check
    from djsync.ui.set_check_dialog import open_set_check

    page = open_set_check(demo, demo.ctrl)
    assert pump(demo, 6, lambda: bool(page.checks))
    page._show([Check("fs", "error", "ext4"), Check("pdb", "warn", "x", state="absent"),
                Check("analysis", "warn", "y", action="analyse", ids=[1])])
    texts = " ".join(lbl.text() for lbl in page.box.findChildren(type(page.verdict)))
    assert t("set.fs_format_warn") in texts and t("set.pdb_absent_how") in texts
    assert page.rows["analysis"]["action"].property("kind") in (None, "", "secondary")
    assert not any(b.isChecked() for b in demo._nav.values())             # volet sans entrée cochée


# ------------------------------------------------------------------ A2-13 : confirmation des points supprimés
def test_a2_13_trim_asks_first(tmp_path):
    from djsync.core import space

    assert space.trim_preview(tmp_path, 5) == (0, 0)


# ------------------------------------------------------------------ A2-15 : compteur du volet
def test_a2_15_counter_ignores_uniformize(demo):  # noqa: F811
    demo.ctrl.diag_counts.update({"missing": 1, "dup": 2, "quality": None, "uniformize": 40})
    assert demo.diag_total() == 3


# ------------------------------------------------------------------ A2-16 : introuvables, état vide
def test_a2_16_missing_empty_hides_actions(demo):  # noqa: F811
    from djsync.ui.missing_dialog import MissingFilesDialog

    page = MissingFilesDialog(demo, demo.ctrl)
    assert pump(demo, 6, lambda: page.count.text() == t("missing.none_short"))
    assert page.remove_all_btn.isHidden() and page.left_box.isHidden()


# ------------------------------------------------------------------ A2-17 : Accueil
def test_a2_17_home_title_and_unknown_quality(demo):  # noqa: F811
    home = demo.views["home"]
    demo.ctrl.diag_counts.pop("quality", None)
    home._todo_refresh()
    assert t("home.todo_unknown") in home.todo["quality"].text()
    assert t("home.title") == "Home"


# ------------------------------------------------------------------ A2-18 : 1.4.3 (option A) dans test_v143_rc2.py


# ------------------------------------------------------------------ A2-22 : Retours
def test_a2_22_library_files_unchecked_by_default(demo):  # noqa: F811
    demo.show_view("feedback")
    assert not demo.views["feedback"].logs_files.isChecked()


# ------------------------------------------------------------------ B102 : dossier surveillé
def _tick(demo, ctrl):  # noqa: F811
    ctrl.watch_tick()
    assert pump(demo, 5, lambda: not getattr(ctrl, "_watch_busy", False) and not getattr(ctrl, "_watch_catching", False)
                and not getattr(ctrl, "_importing", False))


def test_b102_watched_folder_waits_for_the_chosen_library(demo, tmp_path):  # noqa: F811
    ctrl = demo.ctrl
    lib = ctrl.library
    folder = tmp_path.parent / (tmp_path.name + "_b102")
    folder.mkdir()
    ctrl.settings.watch_folder = str(folder)
    ctrl.settings.watch_playlist = False
    ctrl.settings.watch_scanned = ""
    assert ctrl.settings.watch_target == "local"                             # par défaut : l'ordinateur
    _wav(folder / "Artist - Waiting.wav")
    n = len(lib.list_tracks())
    msgs = []
    ctrl.on("message", lambda kind, text: msgs.append(text))
    _tick(demo, ctrl)
    pump(demo, 0.5)
    assert (folder / "Artist - Waiting.wav").exists() and len(lib.list_tracks()) == n       # rien de pris
    assert any(t("watch.target_local") in m for m in msgs)
    ctrl.settings.watch_target = "usb"                                        # la clé ouverte
    for _ in range(3):
        _tick(demo, ctrl)
        pump(demo, 0.8)
    assert pump(demo, 8, lambda: len(lib.list_tracks()) == n + 1)


def test_b102_setting_in_settings_page(demo):  # noqa: F811
    view = demo.views["settings"]
    view.watch_target.setCurrentIndex(view.watch_target.findData("usb"))
    view._save()
    assert demo.ctrl.settings.watch_target == "usb"


# ------------------------------------------------------------------ B103 : Diagnostic sans calcul à l'ouverture
def test_b103_diagnostic_idle_until_analyse_now(demo, monkeypatch):  # noqa: F811
    from djsync.ui.ctrl import diagnostic
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    monkeypatch.setattr(diagnostic, "ALWAYS_READY", False)
    ctrl = demo.ctrl
    calls = []
    real = ctrl.find_duplicates
    monkeypatch.setattr(ctrl, "find_duplicates", lambda *a, **k: (calls.append(1), real(*a, **k)))
    quick = []
    monkeypatch.setattr(ctrl, "diag_quick_counts", lambda: quick.append(1))
    demo.open_diagnostic("dup")
    page = demo.stack.currentWidget()
    assert isinstance(page, DuplicatesDialog)
    assert calls == [] and quick == [] and not page.analyse_now_btn.isHidden()
    page.analyse_now_btn.click()
    assert calls == [1]
    assert pump(demo, 8, lambda: ctrl.diag_last("dup") is not None)
    n, when = ctrl.diag_last("dup")
    assert n == ctrl.diag_counts["dup"] and len(when) == 10
    assert ctrl.diag_ready("dup")                                            # recalcule ensuite dans la session
    ctrl.settings.diag_auto = True
    assert ctrl.diag_auto()


def test_b103_last_counts_survive_a_new_session(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    ctrl._diag_remember({"missing": 4})
    ctrl._diag_counts.clear()
    ctrl._diag_counts_lib = None                                              # autre session / réouverture
    assert ctrl.diag_counts.get("missing") == 4


# ------------------------------------------------------------------ C198 : Uniformiser
def test_c198_uniformize_opens_without_scope_window(demo, monkeypatch):  # noqa: F811
    from djsync.ui.dialogs import BaseDialog

    scanned = []
    monkeypatch.setattr(demo.ctrl, "uniformize_scan", lambda tracks, *a, **k: scanned.append(len(tracks)))
    demo.ctrl.settings.uni_scope = "all"
    demo.open_diagnostic("uniformize")
    page = demo.uniformize_page
    assert page is not None and demo.stack.currentWidget() is page
    assert not [w for w in demo.findChildren(BaseDialog) if w.isVisible()]  # plus de fenêtre de portée
    assert page.scope_bar.kind == "all" and scanned == [] and not page.tracks
    page.scope_bar.choice.setCurrentIndex(0)
    page.scope_bar.start()
    assert pump(demo, 5, lambda: bool(scanned) or page.scope == t("uni.scope_problems"))
    assert demo.ctrl.settings.uni_scope == "problems"
