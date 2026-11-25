"""The visible area of a segment (v0.4.0).

``Crop`` is the core's dataclass when the core provides it (core contract v0.4.0); until then a
stand-in with the same fields is used, so the UI works with either core.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    from video_trimmer.core import Crop  # noqa: F401  (re-exported)
except ImportError:  # pragma: no cover - depends on the core version
    @dataclass(frozen=True)
    class Crop:  # type: ignore[no-redef]
        """Area in source pixels: left, top, width, height."""
        x: int
        y: int
        w: int
        h: int

MIN_SIZE = 32  # source pixels


def even_floor(v: int) -> int:
    return int(v) - (int(v) % 2)


def min_size(width: int, height: int) -> int:
    """Minimum side of an area: 32 px, or the (even) picture side of a tiny video."""
    return max(2, min(MIN_SIZE, even_floor(width), even_floor(height)))


def is_full(x: int, y: int, w: int, h: int, width: int, height: int) -> bool:
    """True when the area covers the whole picture (an odd side may lose its last pixel)."""
    return w >= even_floor(width) and h >= even_floor(height) and x <= 1 and y <= 1


def normalize_crop(crop, width: int, height: int):
    """Clamp ``crop`` into a ``width`` x ``height`` picture; even sizes, at least 32x32.

    Returns None for no crop or a full-frame one (the UI mirror of ``core.validate_crop``).
    """
    if crop is None or width <= 0 or height <= 0:
        return None
    lo = min_size(width, height)
    w = min(max(even_floor(int(crop.w)), lo), even_floor(width))
    h = min(max(even_floor(int(crop.h)), lo), even_floor(height))
    x = min(max(int(crop.x), 0), width - w)
    y = min(max(int(crop.y), 0), height - h)
    if is_full(x, y, w, h, width, height):
        return None
    return Crop(x, y, w, h)


def describe(crop) -> str:
    """``"WxH"`` of an area (for the card mark)."""
    return f"{crop.w}x{crop.h}"
