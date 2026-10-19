"""Popups modaux : choix de playlists (avec création), confirmation, saisie de texte, filtres."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import customtkinter as ctk

from ..models import SEARCH_MODE_LABELS, PlaylistInfo, SearchMode
from . import theme


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent: Any, title: str, width: int = 440, height: int = 300) -> None:
        super().__init__(parent, fg_color=theme.BG)
        self.title(title)
        self.withdraw()
        w, h = theme.px(width), theme.px(height)
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - w) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(w, min(h, theme.px(200)))
        self.transient(top)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.after(30, self._show)

    def _show(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.wait_visibility()
            self.grab_set()
            self.focus_set()
        except Exception:  # noqa: BLE001 - grab impossible (fenêtre fermée trop vite…)
            pass

    def close(self) -> None:
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    def footer(self, ok_text: str, on_ok: Callable[[], None], danger: bool = False,
               cancel_text: str = "Annuler") -> ctk.CTkButton:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=theme.px(18), pady=(0, theme.px(16)))
        ok = theme.button(bar, ok_text, on_ok, kind="danger" if danger else "primary", width=theme.px(130))
        ok.pack(side="right")
        theme.button(bar, cancel_text, self.close, kind="ghost", width=theme.px(90)).pack(side="right", padx=(0, 8))
        return ok


class ConfirmDialog(BaseDialog):
    def __init__(self, parent: Any, title: str, message: str, on_confirm: Callable[[], None],
                 confirm_text: str = "Confirmer", danger: bool = False, detail: str = "",
                 on_cancel: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent, title, 460, 230 if detail else 200)
        self._on_confirm, self._on_cancel = on_confirm, on_cancel
        self.footer(confirm_text, self._ok, danger=danger)
        theme.label(self, title, 15, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=theme.px(20), pady=(theme.px(18), 6))
        theme.label(self, message, 12, theme.TEXT, anchor="w", justify="left", wraplength=theme.px(410)).pack(
            fill="x", padx=theme.px(20))
        if detail:
            theme.label(self, detail, 11, theme.DIM, anchor="w", justify="left", wraplength=theme.px(410)).pack(
                fill="x", padx=theme.px(20), pady=(8, 0))
        self.bind("<Return>", lambda _e: self._ok())

    def _ok(self) -> None:
        self.close()
        self._on_confirm()

    def close(self) -> None:
        cancel, self._on_cancel = self._on_cancel, None
        super().close()
        if cancel:
            cancel()


class TextInputDialog(BaseDialog):
    def __init__(self, parent: Any, title: str, label: str, on_ok: Callable[[str], None], initial: str = "",
                 confirm_text: str = "Valider") -> None:
        super().__init__(parent, title, 420, 190)
        self._on_ok = on_ok
        self.footer(confirm_text, self._ok)
        theme.label(self, label, 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20), pady=(theme.px(20), 6))
        self._entry = theme.entry(self)
        self._entry.pack(fill="x", padx=theme.px(20))
        self._entry.insert(0, initial)
        self.after(120, lambda: (self._entry.focus_set(), self._entry.select_range(0, "end")))
        self.bind("<Return>", lambda _e: self._ok())

    def _ok(self) -> None:
        text = self._entry.get().strip()
        if text:
            self.close()
            self._on_ok(text)


class PlaylistPicker(BaseDialog):
    """Cocher une ou plusieurs playlists, ou en créer une. `on_ok(liste d'identifiants)`."""

    def __init__(self, parent: Any, controller: Any, title: str, confirm_text: str,
                 on_ok: Callable[[List[int]], None], multi: bool = True, preselect: Sequence[int] = (),
                 new_name: str = "", exclude: Sequence[int] = (), allow_empty: bool = False,
                 subtitle: str = "") -> None:
        super().__init__(parent, title, 460, 520)
        self.ctrl = controller
        self._on_ok, self._multi, self._allow_empty = on_ok, multi, allow_empty
        self._exclude = set(exclude)
        self._checked: set = set(preselect)
        self._vars: Dict[int, ctk.BooleanVar] = {}
        self._ok_btn = self.footer(confirm_text, self._confirm)

        theme.label(self, title, 15, theme.TEXT, "bold", anchor="w").pack(fill="x", padx=theme.px(20), pady=(theme.px(18), 2))
        if subtitle:
            theme.label(self, subtitle, 11, theme.DIM, anchor="w", wraplength=theme.px(400), justify="left").pack(
                fill="x", padx=theme.px(20))

        create = ctk.CTkFrame(self, fg_color="transparent")
        create.pack(side="bottom", fill="x", padx=theme.px(20), pady=(6, theme.px(12)))
        self._new = theme.entry(create, "Nom de la nouvelle playlist")
        self._new.pack(side="left", fill="x", expand=True)
        if new_name:
            self._new.insert(0, new_name)
        theme.button(create, "＋ Créer", self._create, kind="ghost", width=theme.px(90)).pack(side="left", padx=(8, 0))
        self._new.bind("<Return>", lambda _e: self._create())

        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=8)
        self._list.pack(fill="both", expand=True, padx=theme.px(20), pady=(10, 8))
        self._empty = theme.label(self._list, "", 12, theme.FAINT)
        self._reload()

    # -- liste
    def _paths(self, playlists: List[PlaylistInfo]) -> List[tuple]:
        by_id = {p.playlist_id: p for p in playlists}

        def path(p: PlaylistInfo) -> str:
            parts, cur, guard = [p.name], p, 0
            while cur.parent_id and cur.parent_id in by_id and guard < 10:
                cur = by_id[cur.parent_id]
                parts.append(cur.name)
                guard += 1
            return " / ".join(reversed(parts))

        rows = [(path(p), p) for p in playlists if not p.is_folder and p.playlist_id not in self._exclude and p.is_editable]
        return sorted(rows, key=lambda r: r[0].lower())

    def _reload(self, tick: Optional[int] = None) -> None:
        def show(playlists: List[PlaylistInfo]) -> None:
            if not self.winfo_exists():
                return
            for child in self._list.winfo_children():
                child.destroy()
            self._vars.clear()
            rows = self._paths(playlists)
            if tick is not None:
                self._checked = {tick} if not self._multi else self._checked | {tick}
            if not rows:
                theme.label(self._list, "Aucune playlist : créez-en une ci-dessous.", 12, theme.FAINT).pack(pady=24)
            for text, p in rows:
                var = ctk.BooleanVar(value=p.playlist_id in self._checked)
                self._vars[p.playlist_id] = var
                cb = theme.checkbox(self._list, f"{text}   ·   {p.track_count}", variable=var,
                                    command=lambda pid=p.playlist_id: self._toggled(pid))
                cb.pack(anchor="w", padx=8, pady=4)
            self._refresh_ok()

        self.ctrl.fetch_playlists(show)

    def _toggled(self, pid: int) -> None:
        if self._vars[pid].get():
            if not self._multi:
                for other, var in self._vars.items():
                    if other != pid:
                        var.set(False)
            self._checked = {pid} if not self._multi else self._checked | {pid}
        else:
            self._checked.discard(pid)
        self._refresh_ok()

    def _selected(self) -> List[int]:
        return [pid for pid, var in self._vars.items() if var.get()]

    def _refresh_ok(self) -> None:
        ok = self._allow_empty or bool(self._selected())
        self._ok_btn.configure(state="normal" if ok else "disabled")

    def _create(self) -> None:
        name = self._new.get().strip()
        if not name:
            return
        self._new.configure(state="disabled")

        def done(pid: Any) -> None:
            if self.winfo_exists():
                self._new.configure(state="normal")
                self._new.delete(0, "end")
                self._reload(tick=getattr(pid, "playlist_id", pid))

        def fail(exc: BaseException) -> None:
            if self.winfo_exists():
                self._new.configure(state="normal")
            self.ctrl._on_error(exc)

        self.ctrl.create_playlist(name, 0, ok=done, err=fail)

    def _confirm(self) -> None:
        ids = self._selected()
        if not ids and not self._allow_empty:
            return
        self.close()
        self._on_ok(ids)


class FiltersPopup(BaseDialog):
    """Options de recherche avancées : mots à exclure + type de résultat."""

    def __init__(self, parent: Any, exclude_words: str, mode: str,
                 on_apply: Callable[[str, str], None]) -> None:
        super().__init__(parent, "Filtres de recherche", 440, 290)
        self._on_apply = on_apply
        self.footer("Appliquer", self._apply)
        theme.label(self, "Filtres de recherche", 15, theme.TEXT, "bold", anchor="w").pack(
            fill="x", padx=theme.px(20), pady=(theme.px(18), 10))
        theme.label(self, "Mots à exclure", 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20))
        self._words = theme.entry(self, "remix, live, karaoké…")
        self._words.pack(fill="x", padx=theme.px(20), pady=(4, 2))
        self._words.insert(0, exclude_words)
        theme.label(self, "Séparés par des virgules. Un résultat contenant l'un de ces mots est masqué.",
                    11, theme.FAINT, anchor="w", wraplength=theme.px(390), justify="left").pack(fill="x", padx=theme.px(20))
        theme.label(self, "Type de résultat", 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20), pady=(14, 0))
        self._labels = {m.value: SEARCH_MODE_LABELS[m] for m in SearchMode}
        self._menu = theme.option_menu(self, list(self._labels.values()), width=theme.px(180))
        self._menu.set(self._labels.get(mode, SEARCH_MODE_LABELS[SearchMode.ALL]))
        self._menu.pack(anchor="w", padx=theme.px(20), pady=(4, 0))
        self.after(120, self._words.focus_set)
        self.bind("<Return>", lambda _e: self._apply())

    def _apply(self) -> None:
        label = self._menu.get()
        value = next((k for k, v in self._labels.items() if v == label), SearchMode.ALL.value)
        words = self._words.get().strip()
        self.close()
        self._on_apply(words, value)
