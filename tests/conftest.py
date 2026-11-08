"""Shared fixtures: sample media generated with ffmpeg (spec.md, section "Разделение работ")."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "ffprobe"
SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")


def _run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"{' '.join(cmd)}\n{res.stderr}"


_VIDEO_ARGS = [
    "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=25",
]
_AUDIO_ARGS = [
    "-f", "lavfi", "-i", "sine=frequency=440:duration=10:sample_rate=44100",
]
_VENC = [
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
    "-g", "25", "-keyint_min", "25", "-sc_threshold", "0",
]


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def sample_video(media_dir) -> Path:
    """10 s, 320x240, h264 + aac, keyframe every 1 s."""
    out = media_dir / "sample.mp4"
    _run([FFMPEG, "-y", "-v", "error", *_VIDEO_ARGS, *_AUDIO_ARGS, *_VENC,
          "-c:a", "aac", "-shortest", str(out)])
    return out


@pytest.fixture(scope="session")
def video_only(media_dir) -> Path:
    out = media_dir / "video_only.mp4"
    _run([FFMPEG, "-y", "-v", "error", *_VIDEO_ARGS, *_VENC, "-an", str(out)])
    return out


@pytest.fixture(scope="session")
def audio_only(media_dir) -> Path:
    out = media_dir / "audio_only.m4a"
    _run([FFMPEG, "-y", "-v", "error", *_AUDIO_ARGS, "-c:a", "aac", str(out)])
    return out


@pytest.fixture(scope="session")
def corrupt_file(media_dir) -> Path:
    out = media_dir / "corrupt.mp4"
    out.write_bytes(b"this is definitely not a media file\x00\x01\x02" * 50)
    return out


@pytest.fixture
def work_dir(tmp_path) -> Path:
    """Fresh per-test directory for outputs."""
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture(scope="session")
def ffprobe_json():
    """Callable: path -> dict with 'duration' (float), 'video' and 'audio' stream lists."""
    def _probe(path) -> dict:
        res = subprocess.run(
            [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        return {
            "duration": float(data["format"]["duration"]),
            "video": [s for s in streams if s.get("codec_type") == "video"],
            "audio": [s for s in streams if s.get("codec_type") == "audio"],
        }
    return _probe


@pytest.fixture(scope="session")
def src_path() -> str:
    return SRC_DIR


@pytest.fixture(autouse=True)
def _ensure_src_on_path(monkeypatch):
    import sys
    if SRC_DIR not in sys.path:
        monkeypatch.syspath_prepend(SRC_DIR)
