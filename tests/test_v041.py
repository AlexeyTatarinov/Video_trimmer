"""v0.4.1: no console windows for ffmpeg/ffprobe on Windows; robust deletion of the source
(the preview player is destroyed so Windows lets go of the file, retries while it is still locked,
own Recycle Bin call on Windows)."""
from __future__ import annotations

import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VIDEO_TRIMMER_NO_AUDIO", "1")

import pytest
from PySide6.QtWidgets import QApplication

from video_trimmer import core, selftest, trash
from video_trimmer.ui import preview
from video_trimmer.ui.main_window import MainWindow

from test_ui import app, fake, win as _win, wait_for  # noqa: F401
from test_v030_delete import isolated_settings, _add_card, _save_and_wait  # noqa: F401

needs_mm = pytest.mark.skipif(not preview.MULTIMEDIA_AVAILABLE, reason="QtMultimedia not installed")


# ---------------------------------------------------------------- no console windows
def test_no_window_kwargs_on_windows(monkeypatch):
    monkeypatch.setattr(core.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    class SI:
        dwFlags = 0
        wShowWindow = 1
    monkeypatch.setattr(subprocess, "STARTUPINFO", SI, raising=False)
    kw = core.no_window_kwargs()
    assert kw["creationflags"] & 0x08000000
    assert kw["startupinfo"].wShowWindow == 0


def test_no_window_kwargs_elsewhere_empty(monkeypatch):
    monkeypatch.setattr(core.sys, "platform", "linux")
    assert core.no_window_kwargs() == {}


def test_every_ffmpeg_call_hides_the_console(monkeypatch, tmp_path):
    """ffprobe and ffmpeg calls of core all ask for the no-window flags."""
    src = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:d=2",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    seen = []
    for name in ("run", "Popen"):
        real = getattr(subprocess, name)

        def spy(*a, _real=real, **kw):
            seen.append(kw.get("creationflags", "MISSING"))
            return _real(*a, **kw)
        monkeypatch.setattr(core.subprocess, name, spy)
    monkeypatch.setattr(core, "no_window_kwargs", lambda: {"creationflags": 0})
    core.trim_each(src, [(0.0, 1.0)], tmp_path / "out", "precise")
    assert len(seen) >= 2 and "MISSING" not in seen


def test_selftest_hides_the_console():
    assert "no_window_kwargs" in open(selftest.__file__, encoding="utf-8").read()


# ---------------------------------------------------------------- Recycle Bin
def test_trash_uses_windows_shell_on_windows(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(trash.sys, "platform", "win32")
    monkeypatch.setattr(trash, "_win_recycle", lambda p: called.append(p))
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    trash._move(str(f))
    assert called == [str(f.resolve())]


def test_trash_uses_send2trash_elsewhere(monkeypatch, tmp_path):
    import send2trash
    called = []
    monkeypatch.setattr(trash.sys, "platform", "linux")
    monkeypatch.setattr(send2trash, "send2trash", lambda p: called.append(p))
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    trash._move(str(f))
    assert called == [str(f)]


def test_trash_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        trash._move(str(tmp_path / "nope.mp4"))


# ---------------------------------------------------------------- player really lets go
@needs_mm
def test_release_destroys_the_player_and_a_new_one_works(_win):
    old = _win.player._player
    _win.player.release()
    QApplication.processEvents()
    assert _win.player._player is not old
    assert _win.player._player is not None
    assert _win.player._player.source().isEmpty()
    # the new player still feeds the preview widget
    assert _win.player._player.videoSink() is _win.video_widget.videoSink()


@pytest.fixture
def win(_win, monkeypatch):
    monkeypatch.setattr(MainWindow, "TRASH_RETRY_MS", 10)
    _win.show()
    QApplication.processEvents()
    return _win


def test_retries_while_the_file_is_locked(win, fake, monkeypatch):
    attempts = []

    def flaky(path):
        attempts.append(path)
        if len(attempts) < 3:
            raise OSError("file in use")
    monkeypatch.setattr(trash, "move_to_trash", flaky)
    _add_card(win)
    _save_and_wait(win, fake)
    assert len(attempts) == 3
    assert not win.has_video()                  # moved: back to the no-video state
    assert "warning" not in [k for k, _ in win.notes]


def test_gives_up_after_the_retries(win, fake, monkeypatch):
    attempts = []

    def locked(path):
        attempts.append(path)
        raise OSError("file in use")
    monkeypatch.setattr(trash, "move_to_trash", locked)
    monkeypatch.setattr(win.player, "set_source", lambda p: None)
    _add_card(win)
    _save_and_wait(win, fake)
    assert len(attempts) == MainWindow.TRASH_RETRIES
    assert win.has_video()
    assert "warning" in [k for k, _ in win.notes]


def test_missing_source_is_not_retried(win, fake, monkeypatch):
    attempts = []

    def gone(path):
        attempts.append(path)
        raise FileNotFoundError("gone")
    monkeypatch.setattr(trash, "move_to_trash", gone)
    monkeypatch.setattr(win.player, "set_source", lambda p: None)
    _add_card(win)
    _save_and_wait(win, fake)
    assert len(attempts) == 1


def test_version_0_4_1():
    import video_trimmer
    assert video_trimmer.__version__ == "0.4.1"
