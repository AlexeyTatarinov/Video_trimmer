"""v0.4.0 (CORE): visible area per segment -- Crop, validate_crop, trim_each(crops=...),
rotation-aware VideoInfo.width/height and CLI --crop. Real ffmpeg on generated videos."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from video_trimmer import core
from video_trimmer.core import Crop, TrimError, validate_crop

FFMPEG = "/usr/local/bin/ffmpeg"
W, H = 320, 240

# 8-bit RGB reference colours of the quadrants (top-left, top-right, bottom-left, bottom-right)
RED, GREEN, BLUE, WHITE, BLACK = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0)


def _run(cmd):
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"{' '.join(map(str, cmd))}\n{res.stderr.decode(errors='replace')}"
    return res.stdout


def _quadrants(out: Path, extra_in=(), duration=3) -> Path:
    q = f"s={W // 2}x{H // 2}:d={duration}:r=25"
    graph = (f"color=c=red:{q}[a];color=c=lime:{q}[b];color=c=blue:{q}[c];color=c=white:{q}[d];"
             "[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack,format=yuv420p[v]")
    _run([FFMPEG, "-y", "-v", "error", "-filter_complex", graph,
          "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}:sample_rate=44100",
          "-map", "[v]", "-map", "0:a",
          "-c:v", "libx264", "-preset", "ultrafast", "-g", "25", "-keyint_min", "25",
          "-sc_threshold", "0", "-c:a", "aac", "-shortest", str(out)])
    return out


@pytest.fixture(scope="session")
def quad(media_dir) -> Path:
    """3 s, 320x240, h264 + aac, keyframe every 1 s; red|green over blue|white."""
    return _quadrants(media_dir / "quad.mp4")


@pytest.fixture(scope="session")
def quad_rot90(media_dir, quad) -> Path:
    """Same picture stored 320x240 with a 90 degree display rotation (shown 240x320)."""
    out = media_dir / "quad_rot90.mp4"
    _run([FFMPEG, "-y", "-v", "error", "-display_rotation", "90", "-i", str(quad),
          "-c", "copy", str(out)])
    return out


def _size(ffprobe_json, path):
    v = ffprobe_json(path)["video"][0]
    return int(v["width"]), int(v["height"])


def _frame(path: Path, t: float = 0.5):
    """(width, height, rgb bytes) of the displayed frame at time t."""
    probe = core.probe(path)
    raw = _run([FFMPEG, "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    assert len(raw) == probe.width * probe.height * 3
    return probe.width, probe.height, raw


def _px(frame, x, y):
    w, _h, raw = frame
    i = (y * w + x) * 3
    return tuple(raw[i:i + 3])


def _close(c1, c2, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def _assert_colour(frame, x, y, want):
    got = _px(frame, x, y)
    assert _close(got, want), f"pixel ({x},{y}) = {got}, expected about {want}"


def _files(d: Path):
    return sorted(p.name for p in d.iterdir())


# ---------------------------------------------------------------- the test picture itself
def test_quad_fixture_has_known_pattern(quad):
    f = _frame(quad)
    assert f[:2] == (W, H)
    _assert_colour(f, 80, 60, RED)
    _assert_colour(f, 240, 60, GREEN)
    _assert_colour(f, 80, 180, BLUE)
    _assert_colour(f, 240, 180, WHITE)


# ---------------------------------------------------------------- Crop / validate_crop
def test_crop_is_a_frozen_dataclass_with_int_fields():
    c = Crop(1, 2, 30, 40)
    assert (c.x, c.y, c.w, c.h) == (1, 2, 30, 40)
    assert c == Crop(x=1, y=2, w=30, h=40)
    with pytest.raises(Exception):
        c.x = 5  # type: ignore[misc]


def test_validate_none_is_none():
    assert validate_crop(None, W, H) is None


def test_validate_full_frame_is_none():
    assert validate_crop(Crop(0, 0, W, H), W, H) is None


def test_validate_bigger_than_picture_is_none():
    assert validate_crop(Crop(-10, -10, W + 50, H + 50), W, H) is None


def test_validate_keeps_valid_crop():
    assert validate_crop(Crop(10, 20, 100, 80), W, H) == Crop(10, 20, 100, 80)


def test_validate_evens_odd_sizes():
    assert validate_crop(Crop(1, 1, 101, 77), W, H) == Crop(1, 1, 100, 76)


def test_validate_clamps_to_picture():
    # 20 px left inside the picture -> grown to the 32 px minimum, moved back inside
    assert validate_crop(Crop(300, 200, 100, 100), W, H) == Crop(288, 200, 32, 40)
    assert validate_crop(Crop(100, 50, 400, 100), W, H) == Crop(100, 50, 220, 100)
    assert validate_crop(Crop(-20, -30, 100, 100), W, H) == Crop(0, 0, 80, 70)


def test_validate_minimum_32_stays_inside():
    assert validate_crop(Crop(10, 10, 4, 6), W, H) == Crop(10, 10, 32, 32)
    c = validate_crop(Crop(310, 235, 4, 4), W, H)
    assert (c.w, c.h) == (32, 32)
    assert c.x + c.w <= W and c.y + c.h <= H


@pytest.mark.parametrize("bad", [Crop(0, 0, 0, 10), Crop(0, 0, 10, 0), Crop(0, 0, -5, 10),
                                 Crop(5, 5, 10, -1)])
def test_validate_rejects_non_positive_size(bad):
    with pytest.raises(TrimError):
        validate_crop(bad, W, H)


@pytest.mark.parametrize("bad", [Crop(W, 0, 50, 50), Crop(0, H + 5, 50, 50), Crop(-100, 0, 50, 50)])
def test_validate_rejects_crop_outside_picture(bad):
    with pytest.raises(TrimError):
        validate_crop(bad, W, H)


def test_validate_rejects_wrong_types():
    with pytest.raises(TrimError):
        validate_crop((0, 0, 10, 10), W, H)  # type: ignore[arg-type]
    with pytest.raises(TrimError):
        validate_crop(Crop(0, 0, 10.5, 10), W, H)  # type: ignore[arg-type]


def test_validate_needs_a_picture():
    with pytest.raises(TrimError):
        validate_crop(Crop(0, 0, 40, 40), 0, 0)


# ---------------------------------------------------------------- VideoInfo width/height
def test_probe_reports_plain_size(quad):
    info = core.probe(quad)
    assert (info.width, info.height) == (W, H)


def test_probe_reports_displayed_size_for_rotated_video(quad_rot90, ffprobe_json):
    assert _size(ffprobe_json, quad_rot90) == (W, H)  # stored size
    info = core.probe(quad_rot90)
    assert (info.width, info.height) == (H, W)
    assert info.has_video and info.has_audio and info.duration == pytest.approx(3.0, abs=0.2)


def test_probe_audio_only_has_zero_size(audio_only):
    info = core.probe(audio_only)
    assert (info.width, info.height) == (0, 0)


# ---------------------------------------------------------------- trim_each with crops (real ffmpeg)
def test_quadrant_crop_fills_source_size(quad, work_dir, ffprobe_json):
    outs = core.trim_each(quad, [(0.0, 2.0)], work_dir, mode="precise",
                          crops=[Crop(0, 0, 160, 120)])
    assert len(outs) == 1
    assert _size(ffprobe_json, outs[0]) == (W, H)
    f = _frame(outs[0])
    for x, y in [(8, 8), (160, 120), (311, 8), (8, 231), (311, 231)]:
        _assert_colour(f, x, y, RED)


def test_other_quadrant_crop(quad, work_dir):
    outs = core.trim_each(quad, [(0.0, 1.0)], work_dir, crops=[Crop(160, 120, 160, 120)])
    f = _frame(outs[0])
    for x, y in [(8, 8), (160, 120), (311, 231)]:
        _assert_colour(f, x, y, WHITE)


def test_tall_crop_gives_pillarbox(quad, work_dir, ffprobe_json):
    # left half 160x240 (2:3) -> scaled to 160x240, black bars 80 px left and right
    outs = core.trim_each(quad, [(0.0, 1.0)], work_dir, mode="precise",
                          crops=[Crop(0, 0, 160, 240)])
    assert _size(ffprobe_json, outs[0]) == (W, H)
    f = _frame(outs[0])
    for x, y in [(4, 120), (70, 10), (70, 230), (250, 120), (315, 10), (315, 230)]:
        _assert_colour(f, x, y, BLACK)
    _assert_colour(f, 160, 60, RED)
    _assert_colour(f, 160, 180, BLUE)
    _assert_colour(f, 90, 60, RED)
    _assert_colour(f, 230, 180, BLUE)


def test_wide_crop_gives_letterbox(quad, work_dir, ffprobe_json):
    # top strip 320x60 (16:3) -> scaled to 320x60, black bars 90 px top and bottom
    outs = core.trim_each(quad, [(0.0, 1.0)], work_dir, crops=[Crop(0, 0, 320, 60)])
    assert _size(ffprobe_json, outs[0]) == (W, H)
    f = _frame(outs[0])
    for x, y in [(160, 4), (10, 80), (310, 80), (160, 236), (10, 160), (310, 160)]:
        _assert_colour(f, x, y, BLACK)
    _assert_colour(f, 80, 120, RED)
    _assert_colour(f, 240, 120, GREEN)


def test_odd_crop_is_evened_and_encodes(quad, work_dir, ffprobe_json):
    outs = core.trim_each(quad, [(0.0, 1.0)], work_dir, crops=[Crop(1, 1, 101, 77)])
    assert _size(ffprobe_json, outs[0]) == (W, H)
    f = _frame(outs[0])
    _assert_colour(f, 160, 120, RED)


def test_mixed_crops_in_fast_mode(quad, work_dir, ffprobe_json):
    ranges = [(0.5, 1.5), (0.5, 1.5)]
    outs = core.trim_each(quad, ranges, work_dir, mode="fast",
                          crops=[None, Crop(160, 120, 160, 120)])
    assert [p.name for p in outs] == ["quad_part1.mp4", "quad_part2.mp4"]
    plain, cropped = ffprobe_json(outs[0]), ffprobe_json(outs[1])
    # crop segment: re-encoded, frame-accurate
    assert cropped["duration"] == pytest.approx(1.0, abs=0.08)
    assert cropped["video"][0]["codec_name"] == "h264"
    assert cropped["audio"], "audio is kept in a cropped segment"
    # no-crop segment: stream copy, snapped to the keyframe before 0.5 s
    assert abs(plain["duration"] - 1.0) > 0.2
    assert _size(ffprobe_json, outs[0]) == (W, H)
    _assert_colour(_frame(outs[1]), 40, 40, WHITE)
    fp = _frame(outs[0])
    _assert_colour(fp, 80, 60, RED)
    _assert_colour(fp, 240, 180, WHITE)


def test_no_crop_segment_matches_call_without_crops(quad, tmp_path, ffprobe_json):
    a, b = tmp_path / "a", tmp_path / "b"
    pa = core.trim_each(quad, [(0.5, 1.5)], a, mode="fast")
    pb = core.trim_each(quad, [(0.5, 1.5)], b, mode="fast", crops=[None])
    assert ffprobe_json(pa[0])["duration"] == pytest.approx(ffprobe_json(pb[0])["duration"], abs=1e-6)
    assert pa[0].read_bytes() == pb[0].read_bytes()


def test_full_frame_crop_means_no_crop(quad, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    pa = core.trim_each(quad, [(0.5, 1.5)], a, mode="fast")
    pb = core.trim_each(quad, [(0.5, 1.5)], b, mode="fast", crops=[Crop(0, 0, W, H)])
    assert pa[0].read_bytes() == pb[0].read_bytes()


def test_rotated_video_crop_uses_displayed_picture(quad_rot90, work_dir, ffprobe_json):
    src = _frame(quad_rot90)
    assert src[:2] == (H, W)
    top_left = _px(src, 60, 80)          # colour of the displayed top-left quadrant
    outs = core.trim_each(quad_rot90, [(0.0, 1.0)], work_dir, crops=[Crop(0, 0, 120, 160)])
    info = core.probe(outs[0])
    assert (info.width, info.height) == (H, W)
    f = _frame(outs[0])
    for x, y in [(8, 8), (120, 160), (231, 311)]:
        _assert_colour(f, x, y, top_left)


def test_crop_progress_reaches_one(quad, work_dir):
    seen = []
    core.trim_each(quad, [(0.0, 1.0), (1.0, 2.0)], work_dir, crops=[Crop(0, 0, 64, 64), None],
                   progress=seen.append)
    assert seen[0] == 0.0 and seen[-1] == 1.0
    assert seen == sorted(seen)


# ---------------------------------------------------------------- invalid crops in trim_each
@pytest.mark.parametrize("crops", [[], [None], [None, None, None]])
def test_crops_length_mismatch_rejected(quad, work_dir, crops):
    with pytest.raises(TrimError):
        core.trim_each(quad, [(0.0, 1.0), (1.0, 2.0)], work_dir, crops=crops)
    assert _files(work_dir) == []


@pytest.mark.parametrize("bad", [Crop(0, 0, 0, 10), Crop(W + 10, 0, 40, 40), (0, 0, 40, 40), "full"])
def test_invalid_crop_rejected_nothing_written(quad, work_dir, bad):
    with pytest.raises(TrimError):
        core.trim_each(quad, [(0.0, 1.0), (1.0, 2.0)], work_dir, crops=[None, bad])
    assert _files(work_dir) == []


def test_invalid_crop_rejected_before_ffmpeg_runs(quad, work_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(core, "_run_ffmpeg", lambda *a, **k: calls.append(a))
    with pytest.raises(TrimError):
        core.trim_each(quad, [(0.0, 1.0), (1.0, 2.0)], work_dir, crops=[None, Crop(0, 0, -2, 4)])
    assert calls == []


def test_crop_on_audio_only_rejected(audio_only, work_dir):
    with pytest.raises(TrimError):
        core.trim_each(audio_only, [(0.0, 1.0)], work_dir, crops=[Crop(0, 0, 40, 40)])


def test_crops_none_items_on_audio_only_ok(audio_only, work_dir):
    outs = core.trim_each(audio_only, [(0.0, 1.0)], work_dir, crops=[None])
    assert len(outs) == 1 and outs[0].stat().st_size > 0


# ---------------------------------------------------------------- unchanged command path without crops
def _record(monkeypatch):
    calls = []

    def fake(args, total, on_fraction):
        calls.append(list(args))
        Path(args[-1]).write_bytes(b"x")
    monkeypatch.setattr(core, "_run_ffmpeg", fake)
    return calls


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_commands_without_crops_are_unchanged(quad, tmp_path, monkeypatch, mode):
    calls = _record(monkeypatch)
    ranges = [(0.0, 1.0), (0.5, 2.5)]
    variants = [{}, {"crops": None}, {"crops": [None, None]},
                {"crops": [Crop(0, 0, W, H), None]}]
    runs = []
    for i, kw in enumerate(variants):
        calls.clear()
        core.trim_each(quad, ranges, tmp_path / f"o{i}", mode=mode, **kw)
        runs.append([[a for a in c if not a.startswith(str(tmp_path))] for c in calls])
    assert all(r == runs[0] for r in runs)
    # and they are exactly the pre-0.4 arguments
    expect = [core._cut_args(Path(quad), s, e - s, mode, Path("X"))[:-1] for s, e in ranges]
    assert runs[0] == expect


def test_crop_command_uses_contract_filter(quad, tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    core.trim_each(quad, [(0.25, 1.75)], tmp_path / "o", mode="fast", crops=[Crop(10, 20, 100, 80)])
    (args,) = calls
    vf = args[args.index("-vf") + 1]
    assert vf == ("crop=100:80:10:20,scale=320:240:force_original_aspect_ratio=decrease,"
                  "pad=320:240:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-crf") + 1] == "18"
    assert args[args.index("-c:a") + 1] == "aac"
    assert "copy" not in args
    assert args[args.index("-ss") + 1] == "0.250000"
    assert args[args.index("-t") + 1] == "1.500000"


def test_crop_filter_uses_displayed_size_of_rotated_video(quad_rot90, tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    core.trim_each(quad_rot90, [(0.0, 1.0)], tmp_path / "o", crops=[Crop(0, 0, 120, 160)])
    vf = calls[0][calls[0].index("-vf") + 1]
    assert "scale=240:320:" in vf and "pad=240:320:" in vf


# ---------------------------------------------------------------- CLI --crop
@pytest.fixture
def run_cli(src_path):
    def _run(*args):
        env = dict(os.environ)
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        res = subprocess.run([sys.executable, "-m", "video_trimmer.cli", *map(str, args)],
                             capture_output=True, text=True, env=env, timeout=120)
        assert "Traceback" not in res.stderr, res.stderr
        return res
    return _run


def test_cli_parse_crop():
    from video_trimmer.cli import parse_crop
    assert parse_crop("10:20:100:80") == Crop(10, 20, 100, 80)
    assert parse_crop("full") is None
    assert parse_crop(" FULL ") is None


@pytest.mark.parametrize("bad", ["", "1:2:3", "a:b:c:d", "1:2:3:4:5", "1.5:2:3:4", "-1:0:40:40"])
def test_cli_parse_crop_rejects(bad):
    import argparse
    from video_trimmer.cli import parse_crop
    with pytest.raises(argparse.ArgumentTypeError):
        parse_crop(bad)


def test_cli_crop_per_range(run_cli, quad, work_dir, ffprobe_json):
    r = run_cli(quad, work_dir, "--separate", "--range", "0.5-1.5", "--range", "0-1",
                "--crop", "full", "--crop", "0:0:160:120")
    assert r.returncode == 0, r.stderr
    p1, p2 = work_dir / "quad_part1.mp4", work_dir / "quad_part2.mp4"
    assert r.stdout.count("Saved:") == 2
    assert abs(ffprobe_json(p1)["duration"] - 1.0) > 0.2          # fast, keyframe-snapped
    assert ffprobe_json(p2)["duration"] == pytest.approx(1.0, abs=0.08)
    assert _size(ffprobe_json, p2) == (W, H)
    _assert_colour(_frame(p2), 300, 220, RED)
    _assert_colour(_frame(p1), 300, 220, WHITE)


def test_cli_fewer_crops_than_ranges_rest_full(run_cli, quad, work_dir):
    r = run_cli(quad, work_dir, "--separate", "--range", "0-1", "--range", "1-2",
                "--crop", "160:120:160:120")
    assert r.returncode == 0, r.stderr
    _assert_colour(_frame(work_dir / "quad_part1.mp4"), 10, 10, WHITE)
    _assert_colour(_frame(work_dir / "quad_part2.mp4"), 10, 10, RED)


def test_cli_more_crops_than_ranges_is_error(run_cli, quad, work_dir):
    r = run_cli(quad, work_dir, "--separate", "--range", "0-1",
                "--crop", "full", "--crop", "0:0:40:40")
    assert r.returncode != 0
    assert "crop" in r.stderr.lower()
    assert _files(work_dir) == []


def test_cli_crop_without_separate_is_error(run_cli, quad, work_dir):
    dst = work_dir / "o.mp4"
    r = run_cli(quad, dst, "--range", "0-1", "--crop", "0:0:40:40")
    assert r.returncode != 0
    assert "--separate" in r.stderr
    assert not dst.exists()


def test_cli_bad_crop_syntax_is_error(run_cli, quad, work_dir):
    r = run_cli(quad, work_dir, "--separate", "--range", "0-1", "--crop", "abc")
    assert r.returncode != 0
    assert "crop" in r.stderr.lower()


def test_cli_invalid_crop_value_exit_1(run_cli, quad, work_dir):
    r = run_cli(quad, work_dir, "--separate", "--range", "0-1", "--crop", "400:0:40:40")
    assert r.returncode == 1
    assert r.stderr.startswith("Error:")
    assert _files(work_dir) == []


def test_cli_help_mentions_crop(run_cli):
    r = run_cli("--help")
    assert r.returncode == 0 and "--crop" in r.stdout and "X:Y:W:H" in r.stdout
