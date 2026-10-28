"""Vue « Retours » (1.2.1, C18) : signaler un bug, proposer une idée, laisser un commentaire.

Un envoi = plusieurs remarques, chacune avec son type, son titre, sa description et jusqu'à 3
captures (capture de la fenêtre DJSync, image choisie ou glissée). Les infos techniques (version,
système, fin du journal sans chemins personnels) sont jointes si la case reste cochée.
Envoi : core/feedback.py (e-mail via le script de l'auteur ; sinon formulaire GitHub prérempli).
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLineEdit, QPlainTextEdit, QScrollArea, QWidget

from ...core import feedback as fb
from ...i18n import plural, t
from .. import theme
from ..widgets import button, hbox, icon_button, label, panel, vbox
from .common import View, alive

THUMB = 72


def _png_bytes(pix: QPixmap) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, "PNG")
    buf.close()
    return bytes(data)


class RemarkCard(QWidget):
    """Une remarque : type, titre, description, captures."""

    def __init__(self, view: "FeedbackView", number: int) -> None:
        super().__init__()
        self.view = view
        self.images: List[fb.Attachment] = []
        self.setAcceptDrops(True)
        outer = vbox(self)
        box = panel()
        outer.addWidget(box)
        lay = vbox(box, margins=theme.px(12), spacing=theme.px(8))
        head = hbox(spacing=theme.px(8))
        self.number = label("", "h2")
        head.addWidget(self.number)
        self._kinds = {"bug": t("fb.kind_bug"), "idea": t("fb.kind_idea"), "comment": t("fb.kind_comment")}
        self.kind = QComboBox()
        self.kind.addItems(list(self._kinds.values()))
        head.addWidget(self.kind)
        self.title = QLineEdit()
        self.title.setPlaceholderText(t("fb.title_placeholder"))
        head.addWidget(self.title, 1)
        self.remove_btn = icon_button("trash", lambda: view.remove_card(self), t("fb.remove"))
        head.addWidget(self.remove_btn)
        lay.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(t("fb.text_placeholder"))
        self.text.setMinimumHeight(theme.px(110))
        lay.addWidget(self.text)
        row = hbox(spacing=theme.px(8))
        self.thumbs = hbox(spacing=theme.px(6))
        row.addLayout(self.thumbs)
        row.addStretch(1)
        self.capture_btn = button(t("fb.capture"), lambda: view.capture_into(self), icon="computer",
                                  tooltip=t("fb.capture_tip"))
        row.addWidget(self.capture_btn)
        self.add_btn = button(t("fb.add_image"), self._choose, kind="flat", icon="plus")
        row.addWidget(self.add_btn)
        lay.addLayout(row)
        self.set_number(number)

    def set_number(self, n: int) -> None:
        self.number.setText(f"{n}.")

    @property
    def kind_key(self) -> str:
        return next((k for k, v in self._kinds.items() if v == self.kind.currentText()), "comment")

    def remark(self) -> fb.Remark:
        return fb.Remark(self.kind_key, self.title.text(), self.text.toPlainText(), list(self.images))

    # ----------------------------------------------------------------- captures
    def add_image(self, data: bytes, name: str) -> None:
        if len(self.images) >= fb.MAX_IMAGES:
            self.view.ctrl.message("warn", t("fb.max_images", n=fb.MAX_IMAGES))
            return
        try:
            att = fb.shrink_image(data, name)
        except fb.FeedbackError:
            self.view.ctrl.message("error", t("fb.bad_image"))
            return
        self.images.append(att)
        self._show_thumbs()

    def _show_thumbs(self) -> None:
        while self.thumbs.count():
            item = self.thumbs.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for k, att in enumerate(self.images):
            cell = QWidget()
            cl = vbox(cell, spacing=0)
            pix = QPixmap()
            pix.loadFromData(att.data)
            img = label()
            img.setPixmap(pix.scaled(theme.px(THUMB), theme.px(THUMB), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img.setToolTip(f"{att.name} · {len(att.data) // 1024} Ko")
            cl.addWidget(img)
            cl.addWidget(button(t("fb.remove_image"), lambda i=k: self._remove(i), kind="flat"))
            self.thumbs.addWidget(cell)
        full = len(self.images) >= fb.MAX_IMAGES
        self.capture_btn.setEnabled(not full)
        self.add_btn.setEnabled(not full)

    def _remove(self, i: int) -> None:
        if 0 <= i < len(self.images):
            self.images.pop(i)
            self._show_thumbs()

    def _choose(self) -> None:
        paths, _f = QFileDialog.getOpenFileNames(self, t("fb.add_image"), "", t("fb.image_filter"))
        for p in paths[: fb.MAX_IMAGES - len(self.images)]:
            try:
                with open(p, "rb") as fh:
                    self.add_image(fh.read(), p)
            except OSError:
                self.view.ctrl.message("error", t("fb.bad_image"))

    def dragEnterEvent(self, e: Any) -> None:       # noqa: N802
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e: Any) -> None:            # noqa: N802
        md = e.mimeData()
        if md.hasImage():
            self.add_image(_png_bytes(QPixmap.fromImage(md.imageData())), "image.png")
        for url in md.urls():
            if url.isLocalFile():
                try:
                    with open(url.toLocalFile(), "rb") as fh:
                        self.add_image(fh.read(), url.toLocalFile())
                except OSError:
                    pass
        e.acceptProposedAction()


class FeedbackView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.cards: List[RemarkCard] = []
        self._sending = False
        self.root.addLayout(self.header(t("tab.feedback")))
        self.root.addWidget(label(t("fb.intro"), "dim", wrap=True))
        from ...credits import thanks_text            # 1.3.1 (C55)
        from ...i18n import get_language

        self.root.addWidget(label("🙏 " + thanks_text(get_language()), "faint", wrap=True))

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        self.list = vbox(inner, spacing=theme.px(10))
        area.setWidget(inner)
        self.root.addWidget(area, 1)
        self.list_end = hbox()
        self.add_btn = button(t("fb.add_remark"), self.add_card, icon="plus")
        self.list_end.addWidget(self.add_btn)
        self.list_end.addStretch(1)
        self.list.addLayout(self.list_end)
        self.list.addStretch(1)

        bottom = panel()
        bl = vbox(bottom, margins=theme.px(12), spacing=theme.px(6))
        row = hbox(spacing=theme.px(8))
        row.addWidget(label(t("fb.email"), "dim"))
        self.email = QLineEdit()
        self.email.setPlaceholderText(t("fb.email_placeholder"))
        row.addWidget(self.email, 1)
        bl.addLayout(row)
        self.with_info = QCheckBox(t("fb.with_info"))
        self.with_info.setChecked(True)
        self.with_info.setToolTip(t("fb.with_info_tip"))
        bl.addWidget(self.with_info)
        row = hbox(spacing=theme.px(8))
        self.status = label("", "dim", wrap=True)
        row.addWidget(self.status, 1)
        self.send_btn = button(t("fb.send"), self.send, kind="primary", icon="go")
        row.addWidget(self.send_btn)
        bl.addLayout(row)
        self.root.addWidget(bottom)

        logs = panel()                                 # 1.2.3 : « Envoyer les logs »
        ll = vbox(logs, margins=theme.px(12), spacing=theme.px(6))
        ll.addWidget(label(t("fb.logs_title"), "h2"))
        ll.addWidget(label(t("fb.logs_hint"), "dim", wrap=True))
        self.logs_note = QLineEdit()
        self.logs_note.setPlaceholderText(t("fb.logs_note"))
        ll.addWidget(self.logs_note)
        self.logs_files = QCheckBox(t("fb.logs_files"))
        self.logs_files.setToolTip(t("fb.logs_files_tip"))
        self.logs_files.setChecked(True)
        ll.addWidget(self.logs_files)
        row = hbox(spacing=theme.px(8))
        self.logs_status = label("", "dim", wrap=True)
        row.addWidget(self.logs_status, 1)
        self.logs_btn = button(t("fb.logs_send"), self.send_logs, icon="go")
        row.addWidget(self.logs_btn)
        ll.addLayout(row)
        self.root.addWidget(logs)
        self.add_card()

    # ------------------------------------------------------------------- remarques
    def add_card(self) -> Optional[RemarkCard]:
        if len(self.cards) >= fb.MAX_ITEMS:
            self.ctrl.message("warn", t("fb.max_items", n=fb.MAX_ITEMS))
            return None
        card = RemarkCard(self, len(self.cards) + 1)
        self.cards.append(card)
        self.list.insertWidget(self.list.count() - 2, card)
        self._renumber()
        card.title.setFocus()
        return card

    def remove_card(self, card: RemarkCard) -> None:
        if card in self.cards and len(self.cards) > 1:
            self.cards.remove(card)
            card.deleteLater()
            self._renumber()

    def _renumber(self) -> None:
        for n, c in enumerate(self.cards, start=1):
            c.set_number(n)
            c.remove_btn.setVisible(len(self.cards) > 1)
        self.add_btn.setEnabled(len(self.cards) < fb.MAX_ITEMS)

    def capture_into(self, card: RemarkCard) -> None:
        """Capture de la fenêtre DJSync telle qu'elle était sur l'onglet précédent."""
        app = self.window()
        previous = getattr(app, "_previous", None) or "home"
        show = getattr(app, "show_view", None)
        if show is not None and previous != "feedback":
            show(previous)

        def grab() -> None:
            if not alive(card):
                return
            data = _png_bytes(app.grab())
            if show is not None:
                show("feedback")
            card.add_image(data, f"djsync-{previous}.png")

        QTimer.singleShot(350, grab)

    # ----------------------------------------------------------------------- envoi
    def remarks(self) -> List[fb.Remark]:
        return [c.remark() for c in self.cards]

    def send(self) -> None:
        if self._sending:
            return
        remarks = [r for r in self.remarks() if not r.empty]
        if not remarks:
            self.status.setText(t("fb.empty"))
            return
        from ... import full_version
        from ...settings import settings_dir

        ctrl = self.ctrl
        lib = t("local.name") if ctrl.is_local else ("USB" if ctrl.has_library else "")
        info = fb.system_info(full_version(), lib) if self.with_info.isChecked() else {"version": full_version()}
        with_log = self.with_info.isChecked()
        email = self.email.text().strip()
        client = ctrl.feedback_client_id()
        from ...i18n import get_language

        language = get_language()
        self._sending = True
        self.send_btn.setEnabled(False)
        self.status.setText(t("fb.sending"))

        def work() -> None:
            log_text = fb.log_tail(settings_dir()) if with_log else ""
            payload = fb.build_payload(remarks, email, info, log_text, client, language)
            fb.send(payload)

        def ok(_r: Any) -> None:
            self._sending = False
            if not self.winfo_exists():
                return
            self.send_btn.setEnabled(True)
            self.status.setText(plural("fb.sent_one", "fb.sent_many", len(remarks)))
            ctrl.message("ok", t("fb.thanks"))
            for c in list(self.cards):
                c.deleteLater()
            self.cards = []
            self.add_card()

        def failed(exc: BaseException) -> None:
            self._sending = False
            if not self.winfo_exists():
                return
            self.send_btn.setEnabled(True)
            reason = str(exc) if isinstance(exc, fb.FeedbackError) else "network"
            if reason in ("empty", "too_big", "limit"):
                self.status.setText(t(f"fb.err_{reason}"))
                return
            # pas de script configuré, réseau, refus : formulaire GitHub prérempli
            self.status.setText(t("fb.fallback"))
            ctrl._emit("open_url", fb.issue_url(remarks, info))

        ctrl.dispatcher.submit(work, ok, failed, pool="net")

    # ------------------------------------------------------------- 1.2.3 : logs de test
    def send_logs(self) -> None:
        """Journal complet (chemins masqués), rapport de la clé (format, fichiers, contrôle d'export.pdb)
        et, si coché, les fichiers de la bibliothèque de la clé zippés."""
        if self._sending:
            return
        from ... import full_version
        from ...i18n import get_language
        from ...settings import settings_dir

        ctrl = self.ctrl
        lib = t("local.name") if ctrl.is_local else ("USB" if ctrl.has_library else "")
        info = fb.system_info(full_version(), lib)
        root = None if (ctrl.drive is None or ctrl.is_local) else getattr(ctrl.drive, "root", None)
        with_files = self.logs_files.isChecked() and root is not None
        note, email, client, language = self.logs_note.text(), self.email.text().strip(), ctrl.feedback_client_id(), get_language()
        self._sending = True
        self.logs_btn.setEnabled(False)
        self.logs_status.setText(t("fb.sending"))

        def work() -> bool:
            report = fb.drive_report(root)
            if ctrl.is_local and ctrl.library is not None:
                report.append(f"Computer library: {fb.anonymise(str(getattr(ctrl.library, 'db_path', '')))}")
            zipped = fb.library_zip(root) if with_files else None
            log_text = fb.log_tail(settings_dir(), fb.LOGS_TAIL_LINES)
            fb.send(fb.build_logs_payload(note, email, info, log_text, report, client, zipped, language))
            return zipped is not None or not with_files

        def ok(files_ok: bool) -> None:
            self._sending = False
            if not self.winfo_exists():
                return
            self.logs_btn.setEnabled(True)
            self.logs_note.clear()
            self.logs_status.setText(t("fb.logs_sent") if files_ok else t("fb.logs_sent_no_files"))
            ctrl.message("ok", t("fb.thanks"))

        def failed(exc: BaseException) -> None:
            self._sending = False
            if not self.winfo_exists():
                return
            self.logs_btn.setEnabled(True)
            reason = str(exc) if isinstance(exc, fb.FeedbackError) else "network"
            self.logs_status.setText(t(f"fb.err_{reason}") if reason in ("too_big", "limit") else t("fb.logs_failed"))

        ctrl.dispatcher.submit(work, ok, failed, pool="net")

