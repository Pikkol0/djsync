"""English catalogue (reference language: every key must exist here)."""

STRINGS = {
    # ---- navigation
    "tab.home": "Home",
    "tab.search": "Search",
    "tab.library": "Library",
    "tab.downloads": "Downloads",
    "tab.import": "Import",
    "tab.settings": "Settings",
    "nav.active_drive": "ACTIVE DRIVE",
    "nav.no_drive": "No drive detected",
    "nav.drive_not_connected": "Drive detected, not connected",

    # ---- generic actions
    "action.download": "Download",
    "action.play": "Play",
    "action.pause": "Pause",
    "action.next": "Next",
    "action.previous": "Previous",
    "action.search": "Search",
    "action.cancel": "Cancel",
    "action.ok": "OK",
    "action.close": "Close",
    "action.save": "Save",
    "action.delete": "Delete",
    "action.rename": "Rename",
    "action.paste": "Paste",
    "action.analyse": "Analyse",
    "action.apply": "Apply",
    "action.retry": "Retry",
    "action.skip": "Skip",
    "action.keep_both": "Keep both",
    "action.replace": "Replace",
    "action.edit_metadata": "Edit metadata",

    # ---- track / playlist vocabulary
    "track.song": "Song",
    "track.video": "Video",
    "track.title": "Title",
    "track.artist": "Artist",
    "track.album": "Album",
    "track.duration": "Duration",
    "track.key": "Key",
    "track.bpm": "BPM",
    "track.views": "Views",
    "lib.all_tracks": "All tracks",
    "lib.tracks_one": "{n} track",
    "lib.tracks_many": "{n} tracks",

    # ---- search modes (menu "Type")
    "mode.all": "All",
    "mode.songs": "Songs",
    "mode.videos": "Videos",
    "mode.artists": "Artists",

    # ---- Spotify -> YouTube Music matching
    "match.auto": "Automatic",
    "match.song": "Prefer songs",
    "match.video": "Prefer videos",

    # ---- download queue status
    "job.queued": "Queued",
    "job.downloading": "Downloading",
    "job.converting": "Converting…",
    "job.tagging": "Tagging…",
    "job.adding": "Adding to drive…",
    "job.done": "✓ Done",
    "job.error": "✗ Error",

    # ---- settings
    "settings.title": "Settings",
    "settings.language": "Language",
    "settings.theme": "Theme colour",
    "settings.zoom": "Interface zoom",
    "settings.zoom_hint": "100 % to 200 %. Applied immediately.",
    "settings.restart_hint": "Some changes are fully applied after restarting DJSync.",

    # ---- themes (palette names)
    "theme.violet_light": "Light violet",
    "theme.lavender": "Lavender",
    "theme.neon_violet": "Neon violet",
    "theme.electric_blue": "Electric blue",
    "theme.sky": "Sky blue",
    "theme.cyan": "Neon cyan",
    "theme.turquoise": "Turquoise",
    "theme.mint": "Mint",
    "theme.neon_green": "Neon green",
    "theme.lime": "Acid lime",
    "theme.yellow": "Neon yellow",
    "theme.amber": "Amber",
    "theme.orange": "Neon orange",
    "theme.coral": "Coral",
    "theme.red": "Laser red",
    "theme.hot_pink": "Hot pink",
    "theme.magenta": "Magenta",
    "theme.pastel_pink": "Pastel pink",
    "theme.pastel_peach": "Pastel peach",
    "theme.pastel_blue": "Pastel blue",

    # ---- drive / Rekordbox database diagnostics
    "db.legacy_format": (
        'This drive also contains the older Rekordbox format (export.pdb). DJSync updates it together with the OneLibrary database (exportLibrary.db) when it recognises it; otherwise it leaves it untouched and players reading it will not see new tracks.'
    ),
    "db.no_legacy_format": "OneLibrary database only: tracks added by DJSync are visible to compatible players.",
    "db.diagnose_title": "Drive diagnostics",
}
