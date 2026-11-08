"""Console interface: python -m video_trimmer.cli INPUT OUTPUT --range START-END [...]."""
from __future__ import annotations

import argparse
import sys

from .core import TrimError, trim, trim_each


def parse_time(text: str) -> float:
    """Parse seconds (12.5), mm:ss or hh:mm:ss into seconds."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(parts):
        raise ValueError(f"invalid time '{text}'")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"invalid time '{text}'") from None
    if any(n < 0 or n != n or n == float("inf") for n in nums):
        raise ValueError(f"invalid time '{text}'")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def parse_range(text: str) -> "tuple[float, float]":
    pieces = text.split("-")
    if len(pieces) != 2:
        raise argparse.ArgumentTypeError(
            f"invalid range '{text}': expected START-END, e.g. 10-25.5 or 0:10-0:25")
    try:
        return parse_time(pieces[0]), parse_time(pieces[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid range '{text}': {exc}") from None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m video_trimmer.cli",
        description="Keep selected fragments of a video and save them as one file.")
    ap.add_argument("input", help="source video file")
    ap.add_argument("output", help="output file (must not exist); with --separate: output folder")
    ap.add_argument("--range", dest="ranges", action="append", required=True,
                    type=parse_range, metavar="START-END",
                    help="fragment to keep; seconds, mm:ss or hh:mm:ss; repeatable")
    ap.add_argument("--separate", action="store_true",
                    help="save every --range as its own file; OUTPUT is then a folder "
                         "(ranges may overlap)")
    ap.add_argument("--mode", choices=("fast", "precise"), default="fast",
                    help="fast: no re-encoding, keyframe-snapped (default); "
                         "precise: re-encode, frame-accurate")
    return ap


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.separate:
            outs = trim_each(args.input, args.ranges, args.output, mode=args.mode)
            for path in outs:
                print(f"Saved: {path}")
            return 0
        out = trim(args.input, args.ranges, args.output, mode=args.mode)
    except TrimError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
