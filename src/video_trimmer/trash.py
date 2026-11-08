"""Recycle Bin access. ``move_to_trash`` is the ONE place that touches the real trash;
tests replace ``video_trimmer.trash.move_to_trash``."""
from __future__ import annotations


def move_to_trash(path: str) -> None:
    """Move a file to the Recycle Bin (never deletes it permanently). Raises on failure."""
    from send2trash import send2trash
    send2trash(str(path))
