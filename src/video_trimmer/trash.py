"""Recycle Bin access. ``move_to_trash`` is the ONE place that touches the real trash;
tests replace ``video_trimmer.trash.move_to_trash``."""
from __future__ import annotations

import os
import sys


def _win_recycle(path: str) -> None:
    """Move one file to the Windows Recycle Bin with the shell (SHFileOperationW, FOF_ALLOWUNDO).
    No third-party modules: nothing for the packaged app to miss."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = path + "\0"                  # double-NUL terminated list
    op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0 or op.fAnyOperationsAborted:
        raise OSError(f"Windows could not move the file to the Recycle Bin (code {rc:#x}); "
                      "it may still be open in another program")
    if os.path.exists(path):
        raise OSError("The file is still there after moving it to the Recycle Bin")


def _move(path: str) -> None:
    """Move a file to the Recycle Bin (never deletes it permanently). Raises OSError on failure
    (FileNotFoundError when the file is gone)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    if sys.platform == "win32":
        _win_recycle(os.path.abspath(os.path.realpath(path)))
        return
    from send2trash import send2trash
    send2trash(str(path))


def move_to_trash(path: str) -> None:
    """Public entry point (tests replace this one; ``_move`` is the real work)."""
    _move(path)
