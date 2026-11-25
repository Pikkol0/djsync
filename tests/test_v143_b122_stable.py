"""1.4.3 (B122, FUS-3 KO en rc.4) : la ligne sélectionnée des Doublons ne tremble plus pendant la vérification
du son : les lignes sont mises à jour sur place au lieu d'une liste vidée puis refaite."""
from __future__ import annotations

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


def test_b122_selected_row_kept_in_place_while_groups_are_checked(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) >= 1)
    g = dup.groups[0]
    dup.groups = [g] * 30                                    # beaucoup de groupes, un choisi en bas
    dup.verified = [False] * 30
    dup.apart = [[] for _ in range(30)]
    dup._fill_list()
    dup.list.setCurrentRow(28)
    dup.list.scrollToBottom()
    top = dup.list.verticalScrollBar().value()
    item = dup.list.item(28)
    changes = []
    dup.list.currentRowChanged.connect(changes.append)
    for i in range(30):                                       # la vérification du son avance groupe par groupe
        dup.verified[i] = True
        dup._fill_list()
        assert dup.list.item(28) is item                      # même ligne : rien n'est recréé
        assert dup.list.currentRow() == 28
        assert dup.list.verticalScrollBar().value() == top
    assert changes == []
    assert dup.list.item(0).data(0x9) is None                 # plus grisée une fois vérifiée (ForegroundRole)
    dup.same_titles = [g]                                     # forme changée : reconstruite, sélection gardée
    dup._fill_list()
    assert dup.list.count() == 32 and dup.list.currentRow() == 28
    assert dup.list.verticalScrollBar().value() == top
    dup.close()
