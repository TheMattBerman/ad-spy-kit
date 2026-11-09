"""Creative card frames: show each ad in its real shape, never cropped.

The board draws every creative inside a frame of one of a few standard ad ratios, picked
from the image's own pixels. With no readable image, video defaults to 9:16 (Reels/Stories)
and everything else to 4:5 (the feed static). The image sits in the frame with
object-fit: contain, so a slightly-off ratio letterboxes instead of losing the subject.
"""

from __future__ import annotations

import math
from pathlib import Path

# name -> (width, height); order is the tie-break.
FRAMES: dict[str, tuple[int, int]] = {
    "9:16": (9, 16),
    "4:5": (4, 5),
    "1:1": (1, 1),
    "16:9": (16, 9),
}
VIDEO_DEFAULT = "9:16"
STATIC_DEFAULT = "4:5"


def image_size(path: Path | None) -> tuple[int, int] | None:
    """(width, height) from the file header, or None when it can't be read."""
    if path is None:
        return None
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
    except (OSError, ValueError):
        return None
    return (w, h) if w > 0 and h > 0 else None


def nearest_frame(width: int, height: int) -> str:
    """The standard frame closest to width:height, compared on a log scale."""
    ratio = math.log(width / height)
    return min(FRAMES, key=lambda k: abs(ratio - math.log(FRAMES[k][0] / FRAMES[k][1])))


def is_video(fmt: str | None, media_kind: str | None = None) -> bool:
    return "video" in f"{fmt or ''} {media_kind or ''}".lower()


def card_frame(size: tuple[int, int] | None, *, video: bool) -> str:
    """Frame for a creative card: from the image when known, else the format default."""
    if size and size[0] > 0 and size[1] > 0:
        return nearest_frame(*size)
    return VIDEO_DEFAULT if video else STATIC_DEFAULT


def css_ratio(frame: str) -> str:
    """'9:16' -> '9 / 16' for the CSS aspect-ratio property."""
    w, h = FRAMES[frame]
    return f"{w} / {h}"
