"""Popups modaux : choix de playlists (avec création), confirmation, saisie de texte, filtres, métadonnées."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import customtkinter as ctk

from ..i18n import t
from ..models import SEARCH_MODE_LABELS, PlaylistInfo, SearchMode
from . import theme


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent: Any, title: str, width: int = 440, height: int = 300) -> None:
        super().__init__(parent, fg_color=theme.BG)
        self.title(title)
        self.withdraw()
        self._base_size = (width, height)
        top = parent.winfo_toplevel()
        self._place(top, width, height)
        self.transient(top)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.after(30, self._show)

    def _scaling(self) -> float:
        try:
            return max(0.5, float(self._get_window_scaling()))
        except Exception:  # noqa: BLE001 - autre version de customtkinter
            return 1.0

    def _place(self, top: Any, width: float, height: float) -> None:
        """Taille et position, TOUJOURS entièrement dans l'écran (V0.2.3).

        customtkinter met le CONTENU à l'échelle DPI × zoom (`ui_factor`) mais la TAILLE de la fenêtre
        seulement au DPI, et ne convertit pas la position (pixels réels). Avant, une fenêtre de 940 × 560
        gardait cette taille alors que son contenu grandissait (×1,45 avec une grande fenêtre) : boutons du
        bas coupés, texte tronqué, voire fenêtre en partie hors de l'écran ; comme elle est modale, l'appli
        semblait bloquée (éditeur de grille)."""
        k = self._scaling()
        f = theme.ui_factor()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()        # pixels réels
        w = min(width * f, sw / k * 0.96)
        h = min(height * f, sh / k * 0.88)
        wp, hp = w * k, h * k
        x = top.winfo_rootx() + (top.winfo_width() - wp) / 2
        y = top.winfo_rooty() + (top.winfo_height() - hp) / 3
        x = int(min(max(0, x), max(0, sw - wp)))
        y = int(min(max(0, y), max(0, sh - hp - 48 * k)))       # 48 : barre des tâches / titre
        self.geometry(f"{int(w)}x{int(h)}+{x}+{y}")
        self.minsize(int(min(w, 320 * f)), int(min(h, 200 * f)))

    def fit_content(self) -> None:
        """Agrandit la fenêtre (sans sortir de l'écran) si son contenu ne tient pas en hauteur."""
        try:
            self.update_idletasks()
            k = self._scaling()
            need = self.winfo_reqheight() / k
            cur = self.winfo_height() / k
            if need > cur + 2:
                limit = self.winfo_screenheight() / k * 0.88
                self.geometry(f"{int(self.winfo_width() / k)}x{int(min(need + 8, limit))}")
        except Exception:  # noqa: BLE001 - fenêtre fermée entre-temps
            pass

    modal = True            # False : la fenêtre ne bloque pas le reste de l'appli

    def _show(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_set()
        except Exception:  # noqa: BLE001 - fenêtre fermée trop vite
            return
        self.fit_content()
        if self.modal:
            self._grab()

    def _grab(self, tries: int = 0) -> None:
        """Modale seulement une fois VISIBLE (sans `wait_visibility`, qui peut attendre indéfiniment
        sous Windows) : une fenêtre modale invisible bloquerait toute l'appli."""
        try:
            if not self.winfo_exists():
                return
            if self.winfo_viewable():
                self.grab_set()
                self.focus_set()
            elif tries < 40:
                self.after(50, lambda: self._grab(tries + 1))
        except Exception:  # noqa: BLE001 - grab impossible (autre fenêtre modale…) : reste non modale
            pass

    def close(self) -> None:
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    def footer(self, ok_text: str, on_ok: Callable[[], None], danger: bool = False,
               cancel_text: str = "", show_cancel: bool = True) -> ctk.CTkButton:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=theme.px(18), pady=(0, theme.px(16)))
        ok = theme.button(bar, ok_text, on_ok, kind="danger" if danger else "primary", width=theme.px(130))
        ok.pack(side="right")
        if show_cancel:
            theme.button(bar, cancel_text or t("action.cancel"), self.close, kind="ghost", width=90).pack(
                side="right", padx=(0, 8))
        return ok


class ConfirmDialog(BaseDialog):
    def __init__(self, parent: Any, title: str, message: str, on_confirm: Callable[[], None],
                 confirm_text: str = "", danger: bool = False, detail: str = "",
                 on_cancel: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent, title, 460, 230 if detail else 200)
        self._on_confirm, self._on_cancel = on_confirm, on_cancel
        self.footer(confirm_text or t("action.confirm"), self._ok, danger=danger)
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
                 confirm_text: str = "") -> None:
        super().__init__(parent, title, 420, 190)
        self._on_ok = on_ok
        self.footer(confirm_text or t("action.ok"), self._ok)
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
        self._new = theme.entry(create, t("picker.new_name"))
        self._new.pack(side="left", fill="x", expand=True)
        if new_name:
            self._new.insert(0, new_name)
        theme.button(create, "＋ " + t("action.create"), self._create, kind="ghost", width=theme.px(90)).pack(side="left", padx=(8, 0))
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
                theme.label(self._list, t("picker.none"), 12, theme.FAINT).pack(pady=24)
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
        super().__init__(parent, t("filters.title"), 440, 290)
        self._on_apply = on_apply
        self.footer(t("action.apply"), self._apply)
        theme.label(self, t("filters.title"), 15, theme.TEXT, "bold", anchor="w").pack(
            fill="x", padx=theme.px(20), pady=(theme.px(18), 10))
        theme.label(self, t("filters.exclude"), 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20))
        self._words = theme.entry(self, t("filters.exclude_placeholder"))
        self._words.pack(fill="x", padx=theme.px(20), pady=(4, 2))
        self._words.insert(0, exclude_words)
        theme.label(self, t("filters.exclude_hint"),
                    11, theme.FAINT, anchor="w", wraplength=theme.px(390), justify="left").pack(fill="x", padx=theme.px(20))
        theme.label(self, t("filters.type"), 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20), pady=(14, 0))
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


class MetadataDialog(BaseDialog):
    """Modifier le titre et l'artiste d'un son (base + export.pdb ; le fichier n'est pas renommé)."""

    def __init__(self, parent: Any, title: str, artist: str, on_ok: Callable[[str, str], None]) -> None:
        super().__init__(parent, t("meta.title"), 460, 270)
        self._on_ok = on_ok
        self.footer(t("action.save"), self._ok)
        theme.label(self, t("meta.title"), 15, theme.TEXT, "bold", anchor="w").pack(
            fill="x", padx=theme.px(20), pady=(theme.px(18), 8))
        theme.label(self, t("track.title"), 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20))
        self._title = theme.entry(self)
        self._title.pack(fill="x", padx=theme.px(20), pady=(2, 8))
        self._title.insert(0, title)
        theme.label(self, t("track.artist"), 12, theme.DIM, anchor="w").pack(fill="x", padx=theme.px(20))
        self._artist = theme.entry(self)
        self._artist.pack(fill="x", padx=theme.px(20), pady=(2, 4))
        self._artist.insert(0, artist)
        theme.label(self, t("meta.hint"), 10, theme.FAINT, anchor="w", wraplength=theme.px(410), justify="left").pack(
            fill="x", padx=theme.px(20))
        self.after(120, lambda: (self._title.focus_set(), self._title.select_range(0, "end")))
        self.bind("<Return>", lambda _e: self._ok())

    def _ok(self) -> None:
        title, artist = self._title.get().strip(), self._artist.get().strip()
        if title:
            self.close()
            self._on_ok(title, artist)
