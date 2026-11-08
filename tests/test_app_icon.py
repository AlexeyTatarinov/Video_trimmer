"""App icon: files exist, are valid multi-size images, and every window shows the icon."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication

from video_trimmer import icon as icon_mod

from test_ui import app, fake, isolated_settings  # noqa: F401

ASSETS = Path(icon_mod.__file__).parent / "assets"


def test_png_and_ico_exist_and_valid():
    png = QImage(str(ASSETS / "icon.png"))
    assert not png.isNull() and png.width() == png.height() >= 256
    assert (ASSETS / "icon.ico").stat().st_size > 1000


def test_icon_not_empty_and_has_alpha_corners():
    img = QImage(str(ASSETS / "icon.png")).convertToFormat(QImage.Format_ARGB32)
    assert img.pixelColor(0, 0).alpha() == 0          # transparent outside the tile
    assert img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255


def test_load_icon_has_standard_sizes(app):
    ic = icon_mod.load_icon()
    assert not ic.isNull()
    sizes = {s.width() for s in ic.availableSizes()}
    assert {16, 32, 48, 256} <= sizes


def test_install_sets_application_icon(app):
    icon_mod.install(app)
    assert not app.windowIcon().isNull()


def test_main_and_fullscreen_windows_have_icon(app):
    from video_trimmer.ui.main_window import MainWindow
    icon_mod.install(app)
    w = MainWindow()
    assert not w.windowIcon().isNull()
    ctrl = w._fullscreen
    if ctrl is not None:
        assert not ctrl.ensure_window().windowIcon().isNull()
    w.close()


def test_icon_cache_is_the_same_for_all(app):
    assert icon_mod.load_icon().cacheKey() == icon_mod.load_icon().cacheKey()
