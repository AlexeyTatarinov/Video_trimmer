"""Application icon: loaded once, installed on the QApplication so every window uses it."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtCore import Qt

ASSETS = Path(__file__).parent / "assets"
APP_ID = "AlexeyTatarinov.VideoTrimmer"
SIZES = (16, 24, 32, 48, 64, 128, 256)

_cache: "QIcon | None" = None


def load_icon() -> QIcon:
    """Return the app icon with several sizes (scaled smoothly from the 512 px master)."""
    global _cache
    if _cache is None:
        icon = QIcon()
        master = QImage(str(ASSETS / "icon.png"))
        if not master.isNull():
            for s in SIZES:
                icon.addPixmap(QPixmap.fromImage(
                    master.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        _cache = icon
    return _cache


def install(app) -> QIcon:
    """Set the icon for the whole application (all top-level windows, dialogs, taskbar)."""
    if sys.platform == "win32":
        try:    # own taskbar group + icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    app.setApplicationName("Video Trimmer")
    icon = load_icon()
    app.setWindowIcon(icon)
    return icon
