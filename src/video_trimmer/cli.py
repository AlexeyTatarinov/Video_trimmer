"""Console interface: python -m video_trimmer.cli INPUT OUTPUT --range START-END [...]."""
from __future__ import annotations

import argparse
import re
import sys

from .core import Crop, TrimError, trim, trim_each


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


def parse_crop(text: str) -> "Crop | None":
    """X:Y:W:H in source pixels (integers), or 'full' for no crop."""
    t = text.strip()
    if t.lower() == "full":
        return None
    pieces = t.split(":")
    if len(pieces) != 4 or not all(re.fullmatch(r"\s*[0-9]+\s*", p) for p in pieces):
        raise argparse.ArgumentTypeError(
            f"invalid crop '{text}': expected X:Y:W:H in pixels (e.g. 0:0:640:360) or 'full'")
    x, y, w, h = (int(p) for p in pieces)
    return Crop(x, y, w, h)


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
    ap.add_argument("--crop", dest="crops", action="append", type=parse_crop, metavar="X:Y:W:H",
                    help="with --separate: visible area for the Nth --range (Nth --crop), in "
                         "source pixels, or 'full'; ranges without a --crop are not cropped. "
                         "The area is fitted into the original size with black bars and the "
                         "fragment is re-encoded")
    return ap


def main(argv: "list[str] | None" = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    crops = None
    if args.crops is not None:
        if not args.separate:
            ap.error("--crop can only be used together with --separate")
        if len(args.crops) > len(args.ranges):
            ap.error(f"too many --crop values: {len(args.crops)} for {len(args.ranges)} --range")
        crops = args.crops + [None] * (len(args.ranges) - len(args.crops))
    try:
        if args.separate:
            outs = trim_each(args.input, args.ranges, args.output, mode=args.mode, crops=crops)
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
