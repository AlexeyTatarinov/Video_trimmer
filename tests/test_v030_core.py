"""v0.3.0 (APP): version, ffmpeg lookup order (`core._tool`), --selftest, command-line start."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import video_trimmer
from video_trimmer import core

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""


# ---------------------------------------------------------------- version (single source)
def test_version_is_0_3_0():
    assert video_trimmer.__version__ == "0.3.0"


def test_pyproject_version_is_in_sync():
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version\s*=\s*"0\.3\.0"\s*$', text, re.M)


def test_send2trash_is_a_declared_dependency():
    root = Path(__file__).resolve().parent.parent
    assert "send2trash" in (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "send2trash" in (root / "pyproject.toml").read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------- _tool lookup order
def _fake_tool(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / (name + EXE)
    p.write_text("#!/bin/sh\necho fake\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


@pytest.fixture
def layout(tmp_path, monkeypatch):
    """A fake install: exe folder, project tools folder and a PATH folder, all empty."""
    exe_dir = tmp_path / "app"
    proj = tmp_path / "proj"
    path_dir = tmp_path / "pathdir"
    for d in (exe_dir, proj, path_dir):
        d.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / ("VideoTrimmer" + EXE)))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(core, "_PROJECT_ROOT", proj)
    monkeypatch.setenv("PATH", str(path_dir))
    return exe_dir, proj, path_dir


def test_tool_prefers_ffmpeg_folder_next_to_executable(layout):
    exe_dir, proj, path_dir = layout
    _fake_tool(path_dir, "ffmpeg")
    _fake_tool(proj / "tools" / "ffmpeg" / "bin", "ffmpeg")
    want = _fake_tool(exe_dir / "ffmpeg", "ffmpeg")
    assert Path(core._tool("ffmpeg")) == want


def test_tool_accepts_bin_subfolder_of_exe_ffmpeg_folder(layout):
    exe_dir, proj, path_dir = layout
    want = _fake_tool(exe_dir / "ffmpeg" / "bin", "ffprobe")
    assert Path(core._tool("ffprobe")) == want


def test_tool_uses_meipass_folder_when_present(layout, monkeypatch, tmp_path):
    exe_dir, proj, path_dir = layout
    meipass = tmp_path / "meipass"
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    _fake_tool(path_dir, "ffmpeg")
    want = _fake_tool(meipass / "ffmpeg", "ffmpeg")
    assert Path(core._tool("ffmpeg")) == want


def test_tool_then_project_tools_folder(layout):
    exe_dir, proj, path_dir = layout
    _fake_tool(path_dir, "ffmpeg")
    want = _fake_tool(proj / "tools" / "ffmpeg-8.0-essentials" / "bin", "ffmpeg")
    assert Path(core._tool("ffmpeg")) == want


def test_tool_then_path(layout):
    exe_dir, proj, path_dir = layout
    want = _fake_tool(path_dir, "ffmpeg")
    assert Path(core._tool("ffmpeg")) == want


def test_tool_not_frozen_ignores_executable_folder(layout, monkeypatch):
    exe_dir, proj, path_dir = layout
    monkeypatch.delattr(sys, "frozen", raising=False)
    _fake_tool(exe_dir / "ffmpeg", "ffmpeg")      # python's own folder must not be searched
    with pytest.raises(core.TrimError):
        core._tool("ffmpeg")


def test_tool_error_message_unchanged(layout):
    with pytest.raises(core.TrimError) as ei:
        core._tool("ffmpeg")
    assert str(ei.value) == "ffmpeg was not found. Please install ffmpeg and make sure it is in PATH."


# ---------------------------------------------------------------- --selftest
def _run_module(src_path, *args, timeout=120):
    env = dict(os.environ)
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["VIDEO_TRIMMER_NO_AUDIO"] = "1"
    return subprocess.run([sys.executable, "-m", "video_trimmer", *args],
                          capture_output=True, text=True, env=env, timeout=timeout)


def test_selftest_ok(src_path):
    r = _run_module(src_path, "--selftest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELFTEST OK" in r.stdout


def test_selftest_writes_result_file_for_windowed_exe(src_path, tmp_path):
    out = tmp_path / "result.txt"
    r = _run_module(src_path, "--selftest", "--selftest-out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_text(encoding="utf-8").strip() == "SELFTEST OK"


def test_selftest_fails_without_ffmpeg(src_path, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = dict(os.environ)
    env.update(PYTHONPATH=src_path, QT_QPA_PLATFORM="offscreen", VIDEO_TRIMMER_NO_AUDIO="1",
               PATH=str(empty))
    if (Path(src_path).parent / "tools").exists():
        pytest.skip("project tools/ffmpeg folder present")
    r = subprocess.run([sys.executable, "-m", "video_trimmer", "--selftest"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 1
    assert "SELFTEST OK" not in r.stdout
    assert "ffmpeg" in (r.stdout + r.stderr)


def test_selftest_function_reports_icon_problem(monkeypatch):
    from video_trimmer import selftest
    from PySide6.QtGui import QIcon
    monkeypatch.setattr("video_trimmer.icon.load_icon", lambda: QIcon())
    ok, message = selftest.run()
    assert not ok and "icon" in message.lower()


# ---------------------------------------------------------------- command line
def test_parse_args_variants():
    from video_trimmer.__main__ import parse_args
    a = parse_args([])
    assert a.path is None and a.selftest is False
    a = parse_args([r"C:\x y\clip.mp4"])
    assert a.path == r"C:\x y\clip.mp4"
    assert parse_args(["--selftest"]).selftest is True


def test_main_opens_path_after_show(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from video_trimmer import __main__ as entry
    from video_trimmer.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    seen = []
    monkeypatch.setattr(MainWindow, "open_startup_path", lambda self, p: seen.append(p))
    monkeypatch.setattr(QTimer, "singleShot", staticmethod(lambda ms, fn: fn()))
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(MainWindow, "show", lambda self: None)
    assert entry.main([str(tmp_path / "clip.mp4")]) == 0
    assert seen == [str(tmp_path / "clip.mp4")]
    seen.clear()
    assert entry.main([]) == 0
    assert seen == []
