"""Pure helpers: seconds <-> [h:]mm:ss.mmm text."""
from __future__ import annotations


def format_time(seconds: float) -> str:
    """Format seconds as ``mm:ss.mmm`` (``h:mm:ss.mmm`` from one hour up)."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{ms:03d}"
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


def parse_time(text: str) -> float:
    """Parse ``12.5``, ``mm:ss[.ms]`` or ``hh:mm:ss[.ms]``; raise ValueError if invalid."""
    parts = text.strip().replace(",", ".").split(":")
    if not 1 <= len(parts) <= 3 or any(p.strip() == "" for p in parts):
        raise ValueError(f"invalid time: {text!r}")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"invalid time: {text!r}") from None
    if any(v < 0 or v != v or v == float("inf") for v in values):
        raise ValueError(f"invalid time: {text!r}")
    if len(values) > 1 and values[-1] >= 60:
        raise ValueError(f"invalid time: {text!r}")
    if len(values) == 3 and values[1] >= 60:
        raise ValueError(f"invalid time: {text!r}")
    total = 0.0
    for v in values:
        total = total * 60 + v
    return total
