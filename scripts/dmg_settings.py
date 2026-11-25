"""dmgbuild settings for PDF 얼개 (PDF Eolgae) macOS DMG."""

import os
import unicodedata

app_path = defines["app"]
app_name = defines.get("app_name", os.path.basename(app_path))
background_path = defines["background"]
icon_path = defines["icon"]

format = "UDZO"

files = [app_path]
symlinks = {"Applications": "/Applications"}

badge_icon = icon_path
background = background_path

window_rect = ((200, 120), (660, 400))
default_view = "icon-view"

show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180

icon_size = 112
text_size = 13

icon_locations = {
    unicodedata.normalize("NFC", app_name): (180, 185),
    unicodedata.normalize("NFD", app_name): (180, 185),
    "Applications": (480, 185),
}
