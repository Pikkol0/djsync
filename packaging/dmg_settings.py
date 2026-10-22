# dmgbuild settings: the macOS disk image (DJSync-macOS.dmg), the usual way to get an app on a Mac.
#   pip install dmgbuild
#   dmgbuild -s packaging/dmg_settings.py -D app=dist/DJSync.app -D background=packaging/dmg_background.png \
#            "DJSync" out/DJSync-macOS.dmg
# Opening the .dmg shows DJSync, the Finder sidebar (with the USB drive) and a background telling to
# drag DJSync onto the drive.
# No "Applications" shortcut on purpose: DJSync lives on the drive, next to the music.
import os.path

app = defines.get("app", "dist/DJSync.app")  # noqa: F821 (provided by dmgbuild)

format = "UDZO"
filesystem = "HFS+"
files = [app]
icon_locations = {os.path.basename(app): (360, 215)}
background = defines.get("background", "packaging/dmg_background.png")  # noqa: F821
sidebar_width = 180
window_rect = ((200, 120), (180 + 640, 420 + 22))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = True                      # the drive to drop DJSync onto
icon_size = 128
text_size = 14
