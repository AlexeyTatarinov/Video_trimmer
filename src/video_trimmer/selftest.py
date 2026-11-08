"""``python -m video_trimmer --selftest``: checks that the program can work on this machine.

Builds the main window without showing it, runs ``ffmpeg -version`` and ``ffprobe -version``
and loads the icon. Used by CI on the frozen executable."""
from __future__ import annotations

import subprocess
import sys


def _check_tool(name: str) -> "str | None":
    from video_trimmer import core
    try:
        exe = core._tool(name)
    except core.TrimError as exc:
        return str(exc)
    try:
        res = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{name} found at {exe} but does not run: {exc}"
    if res.returncode != 0:
        return f"{name} found at {exe} but '-version' failed (exit code {res.returncode})"
    return None


def run() -> "tuple[bool, str]":
    """Return (ok, message). Needs a QApplication (offscreen is fine)."""
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from video_trimmer import icon

    problems: list[str] = []
    for name in ("ffmpeg", "ffprobe"):
        problem = _check_tool(name)
        if problem:
            problems.append(problem)
    try:
        if icon.load_icon().isNull():
            problems.append("icon could not be loaded")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"icon could not be loaded: {exc}")
    try:
        from video_trimmer.ui.main_window import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:        # never touch the user's real settings
            settings = QSettings(str(Path(tmp) / "selftest.ini"), QSettings.IniFormat)
            window = MainWindow(settings=settings)
            window.close()
            window.deleteLater()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"main window could not be created: {exc}")
    if problems:
        return False, "SELFTEST FAILED: " + "; ".join(problems)
    return True, "SELFTEST OK"


def report(ok: bool, message: str, out_file: "str | None" = None) -> int:
    """Print the result (a windowed exe has no stdout, so it can also go to a file)."""
    if sys.stdout is not None:
        print(message)
    if out_file:
        try:
            with open(out_file, "w", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except OSError:
            pass
    return 0 if ok else 1
