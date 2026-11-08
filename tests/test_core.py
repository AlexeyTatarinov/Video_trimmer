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


# ================================================================ v0.2
def _names(d):
    return sorted(p.name for p in d.iterdir())


# ---------------------------------------------------------------- validate_segments
def test_segments_valid_single():
    assert core.validate_segments([(1.0, 3.0)], 10.0) == [(1.0, 3.0)]


def test_segments_overlaps_and_duplicates_allowed_order_preserved():
    ranges = [(5.0, 9.0), (1.0, 6.0), (5.0, 9.0), (0.0, 10.0)]
    assert core.validate_segments(ranges, 10.0) == ranges


def test_segments_touching_ok():
    assert core.validate_segments([(1.0, 2.0), (2.0, 3.0)], 10.0) == [(1.0, 2.0), (2.0, 3.0)]


@pytest.mark.parametrize("bad", [(3.0, 3.0), (4.0, 2.0)])
def test_segments_start_not_less_than_end(bad):
    with pytest.raises(TrimError):
        core.validate_segments([(0.0, 1.0), bad], 10.0)


def test_segments_negative_start():
    with pytest.raises(TrimError):
        core.validate_segments([(-0.5, 2.0)], 10.0)


def test_segments_beyond_duration():
    with pytest.raises(TrimError):
        core.validate_segments([(1.0, 10.01)], 10.0)


def test_segments_duration_tolerance():
    assert core.validate_segments([(1.0, 10.0009)], 10.0) == [(1.0, 10.0009)]


def test_segments_empty_list():
    with pytest.raises(TrimError):
        core.validate_segments([], 10.0)


# ---------------------------------------------------------------- segment_output_paths
def test_segment_paths_default_folder_is_source_folder(tmp_path):
    src = tmp_path / "movie.mp4"
    paths = core.segment_output_paths(src, 3)
    assert paths == [tmp_path / "movie_part1.mp4", tmp_path / "movie_part2.mp4",
                     tmp_path / "movie_part3.mp4"]
    assert all(isinstance(p, type(src)) for p in paths)


def test_segment_paths_out_dir_used_and_str_accepted(tmp_path):
    out = tmp_path / "o"
    paths = core.segment_output_paths(str(tmp_path / "a.mkv"), 2, str(out))
    assert paths == [out / "a_part1.mkv", out / "a_part2.mkv"]


def test_segment_paths_create_nothing(tmp_path):
    out = tmp_path / "new_folder"
    core.segment_output_paths(tmp_path / "a.mp4", 2, out)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_segment_paths_collision_suffixes_whole_set(tmp_path):
    (tmp_path / "a_part2.mp4").write_bytes(b"x")
    paths = core.segment_output_paths(tmp_path / "a.mp4", 3)
    assert paths == [tmp_path / f"a_2_part{i}.mp4" for i in (1, 2, 3)]
    assert (tmp_path / "a_part2.mp4").read_bytes() == b"x"


def test_segment_paths_second_collision_gives_3_no_mixing(tmp_path):
    (tmp_path / "a_part1.mp4").write_bytes(b"x")
    (tmp_path / "a_2_part3.mp4").write_bytes(b"y")
    paths = core.segment_output_paths(tmp_path / "a.mp4", 3)
    assert paths == [tmp_path / f"a_3_part{i}.mp4" for i in (1, 2, 3)]
    assert _names(tmp_path) == ["a_2_part3.mp4", "a_part1.mp4"]


def test_segment_paths_collision_only_in_out_dir(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (tmp_path / "a_part1.mp4").write_bytes(b"x")  # in source folder: irrelevant
    assert core.segment_output_paths(tmp_path / "a.mp4", 1, out) == [out / "a_part1.mp4"]


def test_segment_paths_invalid_count(tmp_path):
    with pytest.raises(TrimError):
        core.segment_output_paths(tmp_path / "a.mp4", 0)


# ---------------------------------------------------------------- trim_each
_OVERLAP = [(2.0, 6.0), (4.0, 9.0), (4.0, 9.0)]


def test_trim_each_precise_overlapping_and_duplicate(sample_video, work_dir, ffprobe_json):
    out = work_dir / "res"
    paths = core.trim_each(sample_video, _OVERLAP, out, mode="precise")
    assert [p.name for p in paths] == ["sample_part1.mp4", "sample_part2.mp4", "sample_part3.mp4"]
    assert _names(out) == [p.name for p in paths]
    for p, (s, e) in zip(paths, _OVERLAP):
        info = ffprobe_json(p)
        assert info["duration"] == pytest.approx(e - s, abs=0.1)
        assert info["video"] and info["audio"]


def test_trim_each_fast_overlapping_and_duplicate(sample_video, work_dir, ffprobe_json):
    paths = core.trim_each(sample_video, _OVERLAP, work_dir / "res")  # default fast
    assert len(paths) == 3
    for p, (s, e) in zip(paths, _OVERLAP):
        info = ffprobe_json(p)
        assert info["duration"] == pytest.approx(e - s, abs=1.0)
        assert info["video"] and info["audio"]
        assert info["video"][0]["codec_name"] == "h264"
        assert info["audio"][0]["codec_name"] == "aac"


def test_trim_each_order_matches_ranges(sample_video, work_dir, ffprobe_json):
    ranges = [(6.0, 9.0), (1.0, 2.0), (3.0, 5.0)]
    paths = core.trim_each(sample_video, ranges, work_dir / "r", mode="precise")
    durs = [ffprobe_json(p)["duration"] for p in paths]
    for d, (s, e) in zip(durs, ranges):
        assert d == pytest.approx(e - s, abs=0.1)


def test_trim_each_files_independent(sample_video, work_dir, ffprobe_json):
    paths = core.trim_each(sample_video, _OVERLAP, work_dir / "r", mode="precise")
    paths[0].unlink()
    assert ffprobe_json(paths[1])["duration"] == pytest.approx(5.0, abs=0.1)
    assert ffprobe_json(paths[2])["duration"] == pytest.approx(5.0, abs=0.1)


def test_trim_each_creates_nested_out_dir(sample_video, work_dir):
    out = work_dir / "a" / "b"
    paths = core.trim_each(sample_video, [(1.0, 3.0)], out)
    assert out.is_dir() and paths[0].parent == out


def test_trim_each_accepts_str_paths(sample_video, work_dir):
    paths = core.trim_each(str(sample_video), [(1.0, 3.0)], str(work_dir / "s"))
    assert paths[0].is_file()


def test_trim_each_existing_set_gets_suffix_and_stays_intact(sample_video, work_dir):
    out = work_dir / "r"
    out.mkdir()
    (out / "sample_part1.mp4").write_bytes(b"precious")
    paths = core.trim_each(sample_video, [(1.0, 3.0), (4.0, 6.0)], out)
    assert [p.name for p in paths] == ["sample_2_part1.mp4", "sample_2_part2.mp4"]
    assert (out / "sample_part1.mp4").read_bytes() == b"precious"
    assert len(_names(out)) == 3


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_each_progress(sample_video, work_dir, mode):
    calls: list[float] = []
    core.trim_each(sample_video, [(1.0, 3.0), (2.0, 5.0)], work_dir / "r", mode=mode,
                   progress=calls.append)
    assert calls
    assert all(0.0 <= v <= 1.0 for v in calls)
    assert calls[-1] == 1.0


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_each_video_only(video_only, work_dir, ffprobe_json, mode):
    paths = core.trim_each(video_only, [(2.0, 5.0), (3.0, 6.0)], work_dir / "r", mode=mode)
    for p in paths:
        info = ffprobe_json(p)
        assert info["video"] and not info["audio"]
        assert info["duration"] == pytest.approx(3.0, abs=1.0 if mode == "fast" else 0.1)


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_each_audio_only(audio_only, work_dir, ffprobe_json, mode):
    paths = core.trim_each(audio_only, [(2.0, 5.0), (3.0, 6.0)], work_dir / "r", mode=mode)
    assert [p.suffix for p in paths] == [".m4a", ".m4a"]
    for p in paths:
        info = ffprobe_json(p)
        assert info["audio"] and not info["video"]
        assert info["duration"] == pytest.approx(3.0, abs=1.0 if mode == "fast" else 0.2)


def _preexisting(work_dir):
    out = work_dir / "r"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"precious")
    (out / "sample_part1.mp4").write_bytes(b"precious2")
    return out


@pytest.mark.parametrize("ranges", [
    [], [(3.0, 3.0)], [(1.0, 2.0), (4.0, 2.0)], [(-1.0, 2.0)], [(1.0, 2.0), (1.0, 50.0)],
])
def test_trim_each_invalid_ranges_leave_nothing(sample_video, work_dir, ranges):
    out = _preexisting(work_dir)
    with pytest.raises(TrimError):
        core.trim_each(sample_video, ranges, out)
    assert _names(out) == ["keep.txt", "sample_part1.mp4"]
    assert (out / "keep.txt").read_bytes() == b"precious"
    assert (out / "sample_part1.mp4").read_bytes() == b"precious2"


def test_trim_each_invalid_ranges_do_not_create_out_dir(sample_video, work_dir):
    out = work_dir / "newdir"
    with pytest.raises(TrimError):
        core.trim_each(sample_video, [(1.0, 99.0)], out)
    assert not out.exists()


def test_trim_each_invalid_mode(sample_video, work_dir):
    out = _preexisting(work_dir)
    with pytest.raises(TrimError):
        core.trim_each(sample_video, [(1.0, 3.0)], out, mode="turbo")
    assert _names(out) == ["keep.txt", "sample_part1.mp4"]


def test_trim_each_missing_src(tmp_path):
    out = tmp_path / "r"
    with pytest.raises(TrimError):
        core.trim_each(tmp_path / "nope.mp4", [(0.0, 1.0)], out)
    assert not out.exists()


@pytest.mark.parametrize("mode", ["fast", "precise"])
def test_trim_each_corrupt_source(corrupt_file, work_dir, mode):
    src = work_dir / "bad.mp4"
    shutil.copy(corrupt_file, src)
    out = work_dir / "r"
    with pytest.raises(TrimError):
        core.trim_each(src, [(0.0, 1.0)], out, mode=mode)
    assert _names(work_dir) == ["bad.mp4"]


def test_trim_each_failure_midway_removes_everything(sample_video, work_dir, monkeypatch):
    """If a later fragment fails, no file from this call remains; old files stay."""
    out = _preexisting(work_dir)
    real = core._run_ffmpeg
    calls = {"n": 0}

    def flaky(args, total, on_fraction):
        calls["n"] += 1
        if calls["n"] == 2:
            raise TrimError("ffmpeg failed: simulated")
        return real(args, total, on_fraction)

    monkeypatch.setattr(core, "_run_ffmpeg", flaky)
    with pytest.raises(TrimError):
        core.trim_each(sample_video, [(1.0, 3.0), (4.0, 6.0), (5.0, 7.0)], out)
    assert calls["n"] == 2
    assert _names(out) == ["keep.txt", "sample_part1.mp4"]
    assert (out / "sample_part1.mp4").read_bytes() == b"precious2"
