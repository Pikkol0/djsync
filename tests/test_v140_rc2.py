"""1.4.0-rc.2 : retours de tests de la rc.1."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B58 : onglet Améliorer
def test_b58_every_diagnostic_tab_opens_its_own_page(demo, monkeypatch):  # noqa: F811
    from djsync.ui import diag_tabs
    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.improve_dialog import ImproveDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    kinds = {"missing": MissingFilesDialog, "dup": DuplicatesDialog, "quality": DiagnosticDialog,
             "improve": ImproveDialog}
    for tab in diag_tabs.TABS:
        if tab == "uniformize":
            continue
        demo.open_diagnostic(tab)
        assert pump(demo, 2, lambda t=tab: isinstance(demo.stack.currentWidget(), kinds[t])), tab
        assert demo.ctrl.settings.diag_tab == tab
        demo.stack.currentWidget().close()
        pump(demo, 0.3)
    demo.ctrl.settings.diag_tab = "improve"                 # dernier onglet mémorisé : Améliorer
    demo.open_diagnostic()
    assert pump(demo, 2, lambda: isinstance(demo.stack.currentWidget(), ImproveDialog))
    assert demo.stack.currentWidget() in demo._diag_pages()
    demo.stack.currentWidget().close()
    assert not demo.errors


# ------------------------------------------------------------------ B63 : tâche reprise au retour
def test_b63_quality_page_comes_back_with_its_task(demo):  # noqa: F811
    from djsync.ui.diagnostic_dialog import DiagnosticDialog

    demo.open_diagnostic("quality")
    page = demo.stack.currentWidget()
    assert isinstance(page, DiagnosticDialog)
    demo.show_view("library")                                  # ailleurs pendant la tâche
    assert demo.stack.currentWidget() is not page
    demo.open_diagnostic()                                     # bouton Diagnostic : même page
    assert demo.stack.currentWidget() is page
    demo.open_diagnostic("quality")
    assert demo.stack.currentWidget() is page
    pages = [demo.stack.widget(i) for i in range(demo.stack.count())]
    assert sum(isinstance(p, DiagnosticDialog) for p in pages) == 1
    page.close()
    assert not demo.errors


# ------------------------------------------------------------------ B61 / B65 : colonnes
def test_b65_every_track_table_remembers_its_columns(demo):  # noqa: F811
    from djsync.ui.improve_dialog import ImproveDialog
    from djsync.ui.widgets import TrackTable

    for view in demo.views.values():
        for table in view.findChildren(TrackTable):
            assert table._layout_key, type(view).__name__
    page = ImproveDialog(demo.views["home"], demo.ctrl)
    assert page.table._layout_key == "improve"
    page.close()


def test_b61_narrow_last_column_does_not_eat_the_title(demo):  # noqa: F811
    v = demo.views["downloads"]
    table = v.table
    table._user_widths["title"] = 30                       # largeur trop petite retenue d'avant
    demo.show_view("downloads")
    demo.resize(1400, 800)
    pump(demo, 0.5)
    table._fit_columns()
    head = table.horizontalHeader()
    idx = {c.key: i for i, c in enumerate(table.columns)}
    from djsync.ui import theme

    assert head.sectionSize(idx["title"]) >= theme.px(160)
    assert head.sectionSize(idx["time"]) < theme.px(160)   # l'Heure garde sa taille
