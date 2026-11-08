"""Core trimming API. See spec.md for the contract."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_TOLERANCE = 0.001
_EPS = 1e-6
_MODES = ("fast", "precise")
_DIRECTIONS = ("nearest", "before", "after")


class TrimError(Exception):
    """User-facing error with a clear message."""


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    has_audio: bool
    has_video: bool


# ---------------------------------------------------------------- helpers
def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise TrimError(f"{name} was not found. Please install ffmpeg and make sure it is in PATH.")
    return found


def _check_file(path: "str | Path") -> Path:
    p = Path(path)
    if not p.is_file():
        raise TrimError(f"File not found: {p}")
    return p


def _tail(text: str, lines: int = 3) -> str:
    parts = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    return " | ".join(parts[-lines:]) if parts else "unknown error"


def _ffprobe_json(path: Path, args: "list[str]") -> dict:
    cmd = [_tool("ffprobe"), "-v", "error", *args, "-of", "json", str(path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    except OSError as exc:
        raise TrimError(f"Could not run ffprobe: {exc}") from exc
    if res.returncode != 0:
        raise TrimError(f"Cannot read media file {path.name}: {_tail(res.stderr)}")
    try:
        return json.loads(res.stdout or "{}")
    except ValueError as exc:
        raise TrimError(f"Cannot read media file {path.name}: unexpected ffprobe output") from exc


def _to_float(value) -> "float | None":
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


# ---------------------------------------------------------------- public API
def probe(path: "str | Path") -> VideoInfo:
    p = _check_file(path)
    data = _ffprobe_json(p, ["-show_format", "-show_streams"])
    streams = data.get("streams") or []
    video = [
        s for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not video and not audio:
        raise TrimError(f"No audio or video streams found in {p.name}")
    duration = _to_float((data.get("format") or {}).get("duration"))
    if duration is None:
        candidates = [_to_float(s.get("duration")) for s in video + audio]
        candidates = [c for c in candidates if c is not None]
        duration = max(candidates) if candidates else None
    if duration is None or duration <= 0:
        raise TrimError(f"Cannot determine the duration of {p.name}")
    width = int(video[0].get("width") or 0) if video else 0
    height = int(video[0].get("height") or 0) if video else 0
    return VideoInfo(duration=duration, width=width, height=height,
                     has_audio=bool(audio), has_video=bool(video))


def keyframes(path: "str | Path") -> "list[float]":
    p = _check_file(path)
    data = _ffprobe_json(
        p, ["-select_streams", "v:0", "-show_entries", "packet=pts_time,flags"]
    )
    times: set[float] = set()
    for pkt in data.get("packets") or []:
        if "K" not in (pkt.get("flags") or ""):
            continue
        t = _to_float(pkt.get("pts_time"))
        if t is not None:
            times.add(float(t))
    return sorted(times)


def snap_to_keyframe(path: "str | Path", t: float, direction: str = "nearest") -> float:
    if direction not in _DIRECTIONS:
        raise TrimError(f"Invalid direction '{direction}'. Use one of: {', '.join(_DIRECTIONS)}.")
    kf = keyframes(path)
    if not kf:  # audio-only or no keyframe info: nothing to snap to
        return float(t)
    if direction == "before":
        cand = [k for k in kf if k <= t + _EPS]
        return cand[-1] if cand else kf[0]
    if direction == "after":
        cand = [k for k in kf if k >= t - _EPS]
        return cand[0] if cand else kf[-1]
    return min(kf, key=lambda k: (abs(k - t), k))


def validate_ranges(ranges: "list[tuple[float, float]]", duration: float) -> "list[tuple[float, float]]":
    if not ranges:
        raise TrimError("No ranges given: choose at least one fragment to keep.")
    clean: list[tuple[float, float]] = []
    for r in ranges:
        try:
            start, end = r
            start, end = start + 0, end + 0  # type check
        except (TypeError, ValueError) as exc:
            raise TrimError(f"Invalid range: {r!r}") from exc
        if start < 0:
            raise TrimError(f"Range start {start} is before the beginning of the video.")
        if start >= end:
            raise TrimError(f"Range start ({start}) must be less than its end ({end}).")
        if end > duration + _TOLERANCE:
            raise TrimError(f"Range end {end} is beyond the video duration ({duration:.3f} s).")
        clean.append((start, end))
    clean.sort()
    for (s1, e1), (s2, e2) in zip(clean, clean[1:]):
        if s2 < e1:
            raise TrimError(f"Ranges overlap: ({s1}, {e1}) and ({s2}, {e2}).")
    return clean


def default_output_path(src: "str | Path") -> Path:
    p = Path(src)
    candidate = p.with_name(f"{p.stem}_trimmed{p.suffix}")
    n = 2
    while candidate.exists():
        candidate = p.with_name(f"{p.stem}_trimmed_{n}{p.suffix}")
        n += 1
    return candidate


# ---------------------------------------------------------------- ffmpeg runner
def _run_ffmpeg(args: "list[str]", total: float, on_fraction: "Callable[[float], None] | None") -> None:
    """Run ffmpeg; report fraction (0..1) of `total` output seconds from -progress."""
    cmd = [_tool("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-nostats",
           "-progress", "pipe:1", *args]
    with tempfile.TemporaryFile() as errf:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                    stdin=subprocess.DEVNULL, text=True, errors="replace")
        except OSError as exc:
            raise TrimError(f"Could not run ffmpeg: {exc}") from exc
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                key, _, val = line.strip().partition("=")
                if key in ("out_time_us", "out_time_ms") and on_fraction and total > 0:
                    us = _to_float(val)
                    if us is not None and us >= 0:
                        on_fraction(min(us / 1e6 / total, 1.0))
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if code != 0:
            errf.seek(0)
            msg = _tail(errf.read().decode("utf-8", "replace"))
            raise TrimError(f"ffmpeg failed: {msg}")


def _concat(parts: "list[Path]", out: Path, tmp: Path) -> None:
    listing = tmp / "concat.txt"
    lines = []
    for part in parts:
        escaped = str(part.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'\n")
    listing.write_text("".join(lines), encoding="utf-8")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                 "-map", "0:v?", "-map", "0:a?", "-c", "copy", "-y", str(out)], 0, None)


def trim(
    src: "str | Path",
    ranges: "list[tuple[float, float]]",
    dst: "str | Path",
    mode: str = "fast",
    progress: "Callable[[float], None] | None" = None,
) -> Path:
    src_p = _check_file(src)
    dst_p = Path(dst)
    if mode not in _MODES:
        raise TrimError(f"Invalid mode '{mode}'. Use 'fast' or 'precise'.")
    try:
        same = src_p.resolve() == dst_p.resolve()
    except OSError:
        same = False
    if same:
        raise TrimError("The output file must differ from the source file.")
    if dst_p.exists() or dst_p.is_symlink():
        raise TrimError(f"Output file already exists: {dst_p}")
    if not dst_p.parent.is_dir():
        raise TrimError(f"Output folder does not exist: {dst_p.parent}")

    info = probe(src_p)
    valid = validate_ranges(ranges, info.duration)

    def report(v: float) -> None:
        if progress:
            progress(max(0.0, min(1.0, v)))

    try:
        tmp = Path(tempfile.mkdtemp(prefix=".vt_tmp_", dir=dst_p.parent))
    except OSError as exc:
        raise TrimError(f"Cannot write to {dst_p.parent}: {exc}") from exc
    try:
        suffix = dst_p.suffix or ".mp4"
        total = sum(e - s for s, e in valid)
        seg_share = 1.0 if len(valid) == 1 else 0.95
        report(0.0)
        parts: list[Path] = []
        done = 0.0
        last = [0.0]
        for i, (start, end) in enumerate(valid):
            length = end - start
            out = tmp / f"seg{i}{suffix}"
            args = ["-ss", f"{start:.6f}", "-i", str(src_p), "-t", f"{length:.6f}",
                    "-map", "0:v:0?", "-map", "0:a:0?"]
            if mode == "fast":
                args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
            else:
                args += ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                         "-pix_fmt", "yuv420p", "-c:a", "aac"]
            args += ["-y", str(out)]

            def on_frac(f: float, done=done, length=length) -> None:
                v = (done + f * length) / total * seg_share
                if v > last[0]:
                    last[0] = v
                    report(v)

            _run_ffmpeg(args, length, on_frac)
            if not out.is_file() or out.stat().st_size == 0:
                raise TrimError("ffmpeg produced no output for a fragment.")
            parts.append(out)
            done += length
            last[0] = max(last[0], done / total * seg_share)
            report(last[0])

        if len(parts) == 1:
            result = parts[0]
        else:
            result = tmp / f"joined{suffix}"
            _concat(parts, result, tmp)
            if not result.is_file() or result.stat().st_size == 0:
                raise TrimError("ffmpeg produced no output when joining fragments.")
        if dst_p.exists():
            raise TrimError(f"Output file already exists: {dst_p}")
        try:
            os.replace(result, dst_p)
        except OSError as exc:
            raise TrimError(f"Cannot save the result to {dst_p}: {exc}") from exc
        report(1.0)
        return dst_p
    except TrimError:
        raise
    except OSError as exc:
        raise TrimError(f"File error during trimming: {exc}") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def validate_segments(ranges: "list[tuple[float, float]]", duration: float) -> "list[tuple[float, float]]":
    """v0.2 contract stub: overlaps allowed, order preserved. See spec.md."""
    raise NotImplementedError


def segment_output_paths(src: "str | Path", count: int, out_dir: "str | Path | None" = None) -> "list[Path]":
    """v0.2 contract stub: <stem>_part1<ext>... without overwriting. See spec.md."""
    raise NotImplementedError


def trim_each(
    src: "str | Path",
    ranges: "list[tuple[float, float]]",
    out_dir: "str | Path",
    mode: str = "fast",
    progress: "Callable[[float], None] | None" = None,
) -> "list[Path]":
    """v0.2 contract stub: one output file per range. See spec.md."""
    raise NotImplementedError
