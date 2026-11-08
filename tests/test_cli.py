"""Console interface tests: python -m video_trimmer.cli (spec.md)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture
def run_cli(src_path):
    def _run(*args):
        env = dict(os.environ)
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        res = subprocess.run(
            [sys.executable, "-m", "video_trimmer.cli", *map(str, args)],
            capture_output=True, text=True, env=env, timeout=120,
        )
        # the module itself must exist and import cleanly (no vacuous passes)
        assert "No module named" not in res.stderr, res.stderr
        assert "Traceback" not in res.stderr, res.stderr
        return res
    return _run


def test_range_seconds(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "2-5")
    assert r.returncode == 0, r.stderr
    assert dst.exists()
    assert ffprobe_json(dst)["duration"] == pytest.approx(3.0, abs=1.0)


def test_range_fractional_seconds(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "1.5-4.5", "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert ffprobe_json(dst)["duration"] == pytest.approx(3.0, abs=0.1)


def test_range_mmss(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "0:02-0:05", "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert ffprobe_json(dst)["duration"] == pytest.approx(3.0, abs=0.1)


def test_range_hhmmss(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "00:00:02-00:00:05", "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert ffprobe_json(dst)["duration"] == pytest.approx(3.0, abs=0.1)


def test_multiple_ranges(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "1-3", "--range", "0:06-0:09", "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert ffprobe_json(dst)["duration"] == pytest.approx(5.0, abs=0.2)


def test_mode_fast_explicit(run_cli, sample_video, work_dir, ffprobe_json):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "2-5", "--mode", "fast")
    assert r.returncode == 0, r.stderr
    assert ffprobe_json(dst)["duration"] == pytest.approx(3.0, abs=1.0)


def test_range_beyond_duration_exit_1(run_cli, sample_video, work_dir):
    dst = work_dir / "o.mp4"
    r = run_cli(sample_video, dst, "--range", "5-50")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert not dst.exists()


def test_missing_input_exit_1(run_cli, work_dir):
    r = run_cli(work_dir / "nope.mp4", work_dir / "o.mp4", "--range", "0-1")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert not (work_dir / "o.mp4").exists()


def test_existing_output_exit_1(run_cli, sample_video, work_dir):
    dst = work_dir / "o.mp4"
    dst.write_bytes(b"keep")
    r = run_cli(sample_video, dst, "--range", "1-3")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert dst.read_bytes() == b"keep"


def test_corrupt_input_exit_1(run_cli, corrupt_file, work_dir):
    dst = work_dir / "o.mp4"
    r = run_cli(corrupt_file, dst, "--range", "0-1")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert not dst.exists()


def test_overlapping_ranges_exit_1(run_cli, sample_video, work_dir):
    r = run_cli(sample_video, work_dir / "o.mp4", "--range", "1-4", "--range", "3-6")
    assert r.returncode == 1
    assert r.stderr.strip()


def test_missing_arguments_nonzero(run_cli):
    r = run_cli()
    assert r.returncode != 0
    assert r.stderr.strip()


def test_missing_range_nonzero(run_cli, sample_video, work_dir):
    r = run_cli(sample_video, work_dir / "o.mp4")
    assert r.returncode != 0
    assert r.stderr.strip()
    assert not (work_dir / "o.mp4").exists()


# ---------------------------------------------------------------- --separate (v0.2)
def test_separate_overlapping_ranges(run_cli, sample_video, work_dir, ffprobe_json):
    out = work_dir / "res"
    r = run_cli(sample_video, out, "--separate", "--range", "2-6", "--range", "4-9",
                "--range", "4-9", "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert out.is_dir()
    files = sorted(out.iterdir())
    assert [f.name for f in files] == ["sample_part1.mp4", "sample_part2.mp4", "sample_part3.mp4"]
    for f, want in zip(files, (4.0, 5.0, 5.0)):
        assert ffprobe_json(f)["duration"] == pytest.approx(want, abs=0.1)
    for f in files:
        assert str(f) in r.stdout


def test_separate_fast_default_mode(run_cli, sample_video, work_dir, ffprobe_json):
    out = work_dir / "res"
    r = run_cli(sample_video, out, "--separate", "--range", "1-4", "--range", "2-5")
    assert r.returncode == 0, r.stderr
    assert len(list(out.iterdir())) == 2
    for f in out.iterdir():
        assert ffprobe_json(f)["duration"] == pytest.approx(3.0, abs=1.0)


def test_separate_existing_folder_with_files_not_overwritten(run_cli, sample_video, work_dir):
    out = work_dir / "res"
    out.mkdir()
    (out / "sample_part1.mp4").write_bytes(b"keep")
    r = run_cli(sample_video, out, "--separate", "--range", "1-3")
    assert r.returncode == 0, r.stderr
    assert (out / "sample_part1.mp4").read_bytes() == b"keep"
    assert (out / "sample_2_part1.mp4").is_file()
    assert str(out / "sample_2_part1.mp4") in r.stdout


def test_separate_error_exit_1(run_cli, sample_video, work_dir):
    out = work_dir / "res"
    r = run_cli(sample_video, out, "--separate", "--range", "1-3", "--range", "5-50")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert not out.exists()


def test_separate_missing_input_exit_1(run_cli, work_dir):
    r = run_cli(work_dir / "nope.mp4", work_dir / "res", "--separate", "--range", "0-1")
    assert r.returncode == 1
    assert r.stderr.strip()
    assert not (work_dir / "res").exists()


def test_without_flag_overlap_still_error_and_single_file(run_cli, sample_video, work_dir):
    r = run_cli(sample_video, work_dir / "o.mp4", "--range", "1-4", "--range", "3-6")
    assert r.returncode == 1
    r = run_cli(sample_video, work_dir / "o.mp4", "--range", "1-3", "--range", "5-7",
                "--mode", "precise")
    assert r.returncode == 0, r.stderr
    assert (work_dir / "o.mp4").is_file()
