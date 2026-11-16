"""Menu d'un son, le même partout (1.4.2, C182, reste d'A06) : Bibliothèque (clic droit), lecteur (☰),
Téléchargements & analyse, pages du Diagnostic.

Chaque endroit garde ses entrées propres (Écouter, Ajouter à…, Retirer, Supprimer, Réessayer…) et ajoute ce bloc
commun, dans le même ordre : Diagnostic de ce son, Grille et cues, Modifier les infos ; Analyser (ou Analyser à
nouveau, Rétablir l'analyse de Rekordbox), Qualité, Compléter les infos ; Sons compatibles, Afficher dans la
bibliothèque, Afficher dans l'Explorateur / le Finder, Acheter.
"""
from __future__ import annotations

from typing import Any, List, Sequence

from ..i18n import t


def analyse_tracks(host: Any, ctrl: Any, tracks: Sequence[Any]) -> None:
    """Sons jamais analysés : analyse lancée ; sinon fenêtre de lancement (option « analyser à nouveau »)."""
    tracks = list(tracks)
    if not tracks or not ctrl.has_library:
        return
    if all(not x.is_analysed for x in tracks):
        ctrl.analyze([x.content_id for x in tracks])
        return
    if len(tracks) == 1:                          # 1.4.1 (C131) : choix demandé pour un son de Rekordbox
        from .reanalyse import analyse_again

        analyse_again(host, ctrl, [tracks[0].content_id])
        return
    from .analysis_dialog import AnalysisDialog

    AnalysisDialog(host, ctrl, tracks)


def open_grid(ctrl: Any, track: Any) -> None:
    if not track.is_analysed:
        ctrl.message("info", t("grid.not_analysed"))
        return
    ctrl._emit("open_grid", track)


def edit_metadata(host: Any, ctrl: Any, track: Any) -> None:
    from .track_info_dialog import TrackInfoDialog

    TrackInfoDialog(host, ctrl, track)


def open_track_diagnostic(host: Any, track: Any) -> None:
    """« Diagnostic de ce son » : onglet « Un son » du Diagnostic, ce son déjà choisi."""
    win = host.window()
    if hasattr(win, "open_track_diagnostic"):
        win.open_track_diagnostic(track.content_id)


def open_quality(host: Any, tracks: Sequence[Any]) -> None:
    win = host.window()
    if hasattr(win, "open_quality"):
        win.open_quality([x.content_id for x in tracks], focus=tracks[0].content_id if len(tracks) == 1 else None)


def complete_metadata(ctrl: Any, tracks: Sequence[Any]) -> None:
    if ctrl.tool_busy:
        ctrl.message("warn", t("tools.busy"))
        return
    ctrl.complete_metadata([x.content_id for x in tracks])


def _library_view(host: Any) -> Any:
    host_win = host.window()
    ctrl = getattr(host_win, "ctrl", None)
    if ctrl is not None:
        ctrl._emit("navigate", "library")
    return getattr(host_win, "views", {}).get("library")


def show_compatible(host: Any, track: Any) -> None:
    view = _library_view(host)
    if view is not None:
        view.set_harmonic(track)


def show_in_library(host: Any, track: Any) -> None:
    view = _library_view(host)
    if view is not None:
        view.reveal(track.content_id)


def restore_rekordbox(host: Any, ctrl: Any, track: Any) -> None:
    from .dialogs import ConfirmDialog

    ConfirmDialog(host, t("reanalyse.restore"), t("reanalyse.restore_confirm", title=track.title),
                  lambda: ctrl.restore_rekordbox_analysis(track.content_id), confirm_text=t("reanalyse.restore"))


def track_entries(host: Any, ctrl: Any, tracks: Sequence[Any], where: str = "",
                  harmonic: Any = None) -> List[Any]:
    """Bloc commun du menu d'un son (ou d'une sélection) de la bibliothèque. `where` : « library » (pas
    d'« Afficher dans la bibliothèque »), « player », « downloads », « diagnostic ». `harmonic` : action de la
    Bibliothèque pour « Sons compatibles » (filtre sur place) ; ailleurs, la Bibliothèque est ouverte."""
    tracks = [x for x in tracks if x is not None]
    if not tracks:
        return []
    one = tracks[0] if len(tracks) == 1 else None
    n = len(tracks)
    entries: List[Any] = []
    if one is not None:
        if where != "diagnostic_one":
            entries.append((t("menu.track_diagnostic"), lambda: open_track_diagnostic(host, one), "diagnostic"))
        if one.is_analysed:
            entries.append((t("lib.edit_grid"), lambda: open_grid(ctrl, one), "grid"))
        entries.append((t("action.edit_metadata"), lambda: edit_metadata(host, ctrl, one), "edit"))
        entries.append(None)
    if one is not None and one.is_analysed:
        entries.append((t("player.analyse_again"), lambda: analyse_tracks(host, ctrl, [one]), "wave"))
        try:
            originals = ctrl.rekordbox_originals
        except Exception:  # noqa: BLE001
            originals = set()
        if one.content_id in originals:
            entries.append((t("reanalyse.restore"), lambda: restore_rekordbox(host, ctrl, one), "back"))
    else:
        entries.append((t("lib.analyse_selection", n=n), lambda: analyse_tracks(host, ctrl, tracks), "wave"))
    if where != "quality":
        entries.append((t("quality.open_sel", n=n), lambda: open_quality(host, tracks), "wave"))
    entries.append((t("meta.complete_sel", n=n), lambda: complete_metadata(ctrl, tracks), "tag"))
    if one is not None:
        entries.append(None)
        if one.camelot:
            go = (lambda: harmonic(one)) if harmonic is not None else (lambda: show_compatible(host, one))
            entries.append((t("lib.show_compatible", code=one.camelot), go, "key"))
        if where != "library":
            entries.append((t("player.show_in_library"), lambda: show_in_library(host, one), "library"))
        from .reveal import reveal_entry
        from .views.common import buy_entry

        entries.append(reveal_entry(ctrl, one))
        entries.append(buy_entry(ctrl, one.artist or "", one.title))
    while entries and entries[-1] is None:
        entries.pop()
    return entries
