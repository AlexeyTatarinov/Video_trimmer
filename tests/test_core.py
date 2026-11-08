"""Core API tests, written from spec.md only."""
from __future__ import annotations

import shutil

import pytest

from video_trimmer import core
from video_trimmer.core import TrimError


# ---------------------------------------------------------------- fixtures sanity
def test_fixtures_are_valid_media(sample_video, video_only, audio_only, ffprobe_json):
    s = ffprobe_json(sample_video)
    assert s["duration"] == pytest.approx(10.0, abs=0.3)
    assert s["video"] and s["audio"]
    assert (s["video"][0]["width"], s["video"][0]["height"]) == (320, 240)
    v = ffprobe_json(video_only)
    assert v["video"] and not v["audio"]
    a = ffprobe_json(audio_only)
    assert a["audio"] and not a["video"]


# ---------------------------------------------------------------- probe
def test_probe_full_video(sample_video):
    info = core.probe(sample_video)
    assert info.duration == pytest.approx(10.0, abs=0.3)
    assert (info.width, info.height) == (320, 240)
    assert info.has_audio is True
    assert info.has_video is True


def test_probe_accepts_str_path(sample_video):
    assert core.probe(str(sample_video)).has_video is True


def test_probe_video_only(video_only):
    info = core.probe(video_only)
    assert info.has_video is True
    assert info.has_audio is False
    assert info.duration == pytest.approx(10.0, abs=0.3)


def test_probe_audio_only(audio_only):
    info = core.probe(audio_only)
    assert info.has_audio is True
    assert info.has_video is False
    assert info.duration == pytest.approx(10.0, abs=0.3)


def test_probe_missing_file(tmp_path):
    with pytest.raises(TrimError):
        core.probe(tmp_path / "nope.mp4")


def test_probe_non_media_file(corrupt_file):
    with pytest.raises(TrimError):
        core.probe(corrupt_file)


# ---------------------------------------------------------------- keyframes
def test_keyframes_ascending_about_every_second(sample_video):
    kf = core.keyframes(sample_video)
    assert len(kf) >= 9
    assert all(isinstance(t, float) for t in kf)
    assert kf == sorted(kf)
    assert len(set(kf)) == len(kf)
    assert kf[0] == pytest.approx(0.0, abs=0.1)
    gaps = [b - a for a, b in zip(kf, kf[1:])]
    assert all(g == pytest.approx(1.0, abs=0.1) for g in gaps)


def test_keyframes_missing_file(tmp_path):
    with pytest.raises(TrimError):
        core.keyframes(tmp_path / "nope.mp4")


# ---------------------------------------------------------------- snap_to_keyframe
def test_snap_nearest_default(sample_video):
    assert core.snap_to_keyframe(sample_video, 3.2) == pytest.approx(3.0, abs=0.1)
    assert core.snap_to_keyframe(sample_video, 3.8) == pytest.approx(4.0, abs=0.1)
    assert core.snap_to_keyframe(sample_video, 3.2, "nearest") == pytest.approx(3.0, abs=0.1)


def test_snap_before(sample_video):
    assert core.snap_to_keyframe(sample_video, 3.8, "before") == pytest.approx(3.0, abs=0.1)
    assert core.snap_to_keyframe(sample_video, 3.2, direction="before") == pytest.approx(3.0, abs=0.1)


def test_snap_after(sample_video):
    assert core.snap_to_keyframe(sample_video, 3.2, "after") == pytest.approx(4.0, abs=0.1)
    assert core.snap_to_keyframe(sample_video, 3.8, direction="after") == pytest.approx(4.0, abs=0.1)


def test_snap_exactly_on_keyframe(sample_video):
    for d in ("nearest", "before", "after"):
        assert core.snap_to_keyframe(sample_video, 5.0, d) == pytest.approx(5.0, abs=0.1)


def test_snap_result_is_a_keyframe(sample_video):
    kf = core.keyframes(sample_video)
    r = core.snap_to_keyframe(sample_video, 6.4)
    assert any(abs(r - k) < 1e-6 for k in kf)


def test_snap_bad_direction(sample_video):
    with pytest.raises(TrimError):
        core.snap_to_keyframe(sample_video, 3.0, "sideways")


# ---------------------------------------------------------------- validate_ranges
def test_validate_valid_single():
    assert core.validate_ranges([(1.0, 2.0)], 10.0) == [(1.0, 2.0)]


def test_validate_sorts():
    out = core.validate_ranges([(5.0, 6.0), (1.0, 2.0), (3.0, 4.0)], 10.0)
    assert out == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


def test_validate_full_range_ok():
    assert core.validate_ranges([(0, 10.0)], 10.0) == [(0, 10.0)]


def test_validate_touching_ranges_ok():
    # end == next start is not an overlap
    assert core.validate_ranges([(1.0, 2.0), (2.0, 3.0)], 10.0) == [(1.0, 2.0), (2.0, 3.0)]


@pytest.mark.parametrize("bad", [(3.0, 3.0), (4.0, 3.0)])
def test_validate_start_not_less_than_end(bad):
    with pytest.raises(TrimError):
        core.validate_ranges([bad], 10.0)


def test_validate_negative_start():
    with pytest.raises(TrimError):
        core.validate_ranges([(-0.5, 2.0)], 10.0)


def test_validate_beyond_duration():
    with pytest.raises(TrimError):
        core.validate_ranges([(1.0, 10.5)], 10.0)


def test_validate_duration_tolerance():
    assert core.validate_ranges([(1.0, 10.0005)], 10.0) == [(1.0, 10.0005)]
    with pytest.raises(TrimError):
        core.validate_ranges([(1.0, 10.01)], 10.0)


def test_validate_overlap():
    with pytest.raises(TrimError):
        core.validate_ranges([(1.0, 4.0), (3.0, 5.0)], 10.0)


def test_validate_overlap_unsorted_input():
    with pytest.raises(TrimError):
        core.validate_ranges([(3.0, 5.0), (1.0, 4.0)], 10.0)


def test_validate_empty_list():
    with pytest.raises(TrimError):
        core.validate_ranges([], 10.0)


# ---------------------------------------------------------------- default_output_path
def test_default_output_path_basic(tmp_path):
    src = tmp_path / "movie.mp4"
    src.write_bytes(b"x")
    assert core.default_output_path(src) == tmp_path / "movie_trimmed.mp4"


def test_default_output_path_accepts_str_and_keeps_extension(tmp_path):
    src = tmp_path / "clip.MOV"
    src.write_bytes(b"x")
    out = core.default_output_path(str(src))
    assert out.parent == tmp_path
    assert out.name == "clip_trimmed.MOV"


def test_default_output_path_no_overwrite(tmp_path):
    src = tmp_path / "movie.mp4"
    src.write_bytes(b"x")
    (tmp_path / "movie_trimmed.mp4").write_bytes(b"x")
    assert core.default_output_path(src) == tmp_path / "movie_trimmed_2.mp4"
    (tmp_path / "movie_trimmed_2.mp4").write_bytes(b"x")
    assert core.default_output_path(src) == tmp_path / "movie_trimmed_3.mp4"


def test_default_output_path_does_not_create_file(tmp_path):
    src = tmp_path / "movie.mp4"
    src.write_bytes(b"x")
    out = core.default_output_path(src)
    assert not out.exists()


# ---------------------------------------------------------------- trim: fast
def test_trim_fast_single_range(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "out.mp4"
    res = core.trim(sample_video, [(2.0, 5.0)], dst)  # default mode is fast
    assert res == dst
    assert dst.exists()
    p = ffprobe_json(dst)
    assert p["duration"] == pytest.approx(3.0, abs=1.0)
    assert p["video"] and p["audio"]


def test_trim_fast_unaligned_range(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "out.mp4"
    core.trim(sample_video, [(2.5, 5.5)], dst, mode="fast")
    p = ffprobe_json(dst)
    # boundaries snap to keyframes: error bounded by the 1 s keyframe spacing per edge
    assert p["duration"] == pytest.approx(3.0, abs=2.0)
    assert p["video"] and p["audio"]


def test_trim_fast_multiple_ranges(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "out.mp4"
    core.trim(sample_video, [(1.0, 3.0), (6.0, 9.0)], dst, mode="fast")
    p = ffprobe_json(dst)
    assert p["duration"] == pytest.approx(5.0, abs=1.5)
    assert p["video"] and p["audio"]


def test_trim_fast_accepts_str_paths(sample_video, work_dir):
    dst = work_dir / "s.mp4"
    res = core.trim(str(sample_video), [(1.0, 4.0)], str(dst))
    assert dst.exists()
    assert str(res) == str(dst)


def test_trim_fast_does_not_reencode(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "out.mp4"
    core.trim(sample_video, [(2.0, 5.0)], dst, mode="fast")
    p = ffprobe_json(dst)
    assert p["video"][0]["codec_name"] == "h264"
    assert p["audio"][0]["codec_name"] == "aac"


# ---------------------------------------------------------------- trim: precise
def test_trim_precise_single_range(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "p.mp4"
    core.trim(sample_video, [(2.5, 5.5)], dst, mode="precise")
    p = ffprobe_json(dst)
    assert p["duration"] == pytest.approx(3.0, abs=0.1)
    assert p["video"] and p["audio"]
    assert p["video"][0]["codec_name"] == "h264"
    assert p["audio"][0]["codec_name"] == "aac"


def test_trim_precise_multiple_ranges(sample_video, work_dir, ffprobe_json):
    dst = work_dir / "p.mp4"
    core.trim(sample_video, [(0.5, 2.0), (4.25, 6.0), (8.0, 9.5)], dst, mode="precise")
    p = ffprobe_json(dst)
    expected = 1.5 + 1.75 + 1.5
    assert p["duration"] == pytest.approx(expected, abs=0.1 * 3)
    assert p["video"] and p["audio"]


def test_trim_precise_sorts_unordered_ranges_duration(sample_video, work_dir, ffprobe_json):
    # validate_ranges sorts; trim output total length must still equal the sum.
    dst = work_dir / "p.mp4"
    core.trim(sample_video, [(6.0, 7.0), (1.0, 2.0)], dst, mode="precise")
    assert ffprobe_json(dst)["duration"] == pytest.approx(2.0, abs=0.2)


# ---------------------------------------------------------------- trim: stream layouts
@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_video_only(video_only, work_dir, ffprobe_json, mode):
    dst = work_dir / "v.mp4"
    core.trim(video_only, [(2.0, 5.0)], dst, mode=mode)
    p = ffprobe_json(dst)
    assert p["video"] and not p["audio"]
    assert p["duration"] == pytest.approx(3.0, abs=1.0 if mode == "fast" else 0.1)


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_audio_only(audio_only, work_dir, ffprobe_json, mode):
    dst = work_dir / "a.m4a"
    core.trim(audio_only, [(2.0, 5.0)], dst, mode=mode)
    p = ffprobe_json(dst)
    assert p["audio"] and not p["video"]
    assert p["duration"] == pytest.approx(3.0, abs=1.0 if mode == "fast" else 0.2)


# ---------------------------------------------------------------- trim: progress
@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_progress_values(sample_video, work_dir, mode):
    calls: list[float] = []
    core.trim(sample_video, [(1.0, 3.0), (5.0, 7.0)], work_dir / "o.mp4", mode=mode,
              progress=calls.append)
    assert calls, "progress must be called at least once"
    assert all(0.0 <= v <= 1.0 for v in calls)
    assert calls[-1] == 1.0


# ---------------------------------------------------------------- trim: errors
def test_trim_missing_src(tmp_path):
    dst = tmp_path / "o.mp4"
    with pytest.raises(TrimError):
        core.trim(tmp_path / "nope.mp4", [(0.0, 1.0)], dst)
    assert not dst.exists()


def test_trim_dst_exists(sample_video, work_dir):
    dst = work_dir / "exists.mp4"
    dst.write_bytes(b"precious")
    with pytest.raises(TrimError):
        core.trim(sample_video, [(1.0, 3.0)], dst)
    assert dst.read_bytes() == b"precious"
    assert [p.name for p in work_dir.iterdir()] == ["exists.mp4"]


def test_trim_dst_equals_src(work_dir, sample_video):
    src = work_dir / "copy.mp4"
    shutil.copy(sample_video, src)
    before = src.read_bytes()
    with pytest.raises(TrimError):
        core.trim(src, [(1.0, 3.0)], src)
    assert src.read_bytes() == before
    assert [p.name for p in work_dir.iterdir()] == ["copy.mp4"]


def test_trim_invalid_mode(sample_video, work_dir):
    dst = work_dir / "o.mp4"
    with pytest.raises(TrimError):
        core.trim(sample_video, [(1.0, 3.0)], dst, mode="turbo")
    assert [p.name for p in work_dir.iterdir()] == []


@pytest.mark.parametrize("ranges", [
    [], [(3.0, 3.0)], [(4.0, 2.0)], [(-1.0, 2.0)], [(1.0, 50.0)], [(1.0, 4.0), (3.0, 5.0)],
])
def test_trim_invalid_ranges(sample_video, work_dir, ranges):
    dst = work_dir / "o.mp4"
    with pytest.raises(TrimError):
        core.trim(sample_video, ranges, dst)
    assert [p.name for p in work_dir.iterdir()] == []


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_corrupt_source_leaves_nothing(corrupt_file, work_dir, mode):
    src = work_dir / "bad.mp4"
    shutil.copy(corrupt_file, src)
    dst = work_dir / "o.mp4"
    with pytest.raises(TrimError):
        core.trim(src, [(0.0, 1.0)], dst, mode=mode)
    assert not dst.exists()
    assert [p.name for p in work_dir.iterdir()] == ["bad.mp4"]
