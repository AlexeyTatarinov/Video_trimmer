# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: onedir, windowed, name VideoTrimmer.
# Build from the repository root:
#   pyinstaller packaging/VideoTrimmer.spec --noconfirm --clean
# ffmpeg.exe / ffprobe.exe are NOT bundled here; CI copies them into
# dist/VideoTrimmer/ffmpeg/ afterwards (next to the exe, see core._tool).
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (SPECPATH is injected)
SRC = ROOT / "src"
ASSETS = SRC / "video_trimmer" / "assets"
ICON = ASSETS / "icon.ico"

# Qt modules the app does not use. QtCore/Gui/Widgets/Multimedia/
# MultimediaWidgets (and QtNetwork, needed by Multimedia) stay.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtTextToSpeech",
    "PySide6.QtSpatialAudio", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport", "PySide6.QtConcurrent", "PySide6.QtDBus",
    "PySide6.QtStateMachine", "PySide6.QtHttpServer", "PySide6.QtNetworkAuth",
    "PySide6.QtUiTools", "PySide6.QtXml",
    "tkinter", "unittest", "pydoc", "test", "pytest",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(ASSETS), "video_trimmer/assets")],
    # The PyInstaller PySide6 hooks collect the Qt plugins used by the imported
    # modules (multimedia backends, platforms, imageformats, styles, ...). The
    # explicit imports make sure the multimedia modules are always picked up.
    hiddenimports=[
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetwork",
        "send2trash",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# Drop heavy files the app never needs (software OpenGL fallback, Qt translations).
_DROP = ("opengl32sw.dll", "d3dcompiler_47.dll")
a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in _DROP]
a.datas = [d for d in a.datas if not (d[0].replace("\\", "/").lower().find("/translations/") >= 0
                                      and d[0].lower().endswith(".qm"))]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoTrimmer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed
    icon=str(ICON),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VideoTrimmer",
)
