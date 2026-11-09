"""Decode-confirmed probe for supported local image receipts."""

from io import BytesIO
import os
import stat
import warnings

from PIL import Image, UnidentifiedImageError


MAX_MEDIA_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16384
MAX_IMAGE_PIXELS = 40_000_000

_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}


def probe_image_media(path):
    """Return ``(mime, bytes)`` only after Pillow fully decodes the image."""
    if not path:
        return None
    try:
        file_stat = os.stat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_size <= 0
        or file_stat.st_size > MAX_MEDIA_BYTES
    ):
        return None

    try:
        with open(path, "rb") as media:
            payload = media.read(MAX_MEDIA_BYTES + 1)
    except OSError:
        return None
    if len(payload) != file_stat.st_size or len(payload) > MAX_MEDIA_BYTES:
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(payload)) as image:
                image_format = image.format
                dimensions = image.size
                if image_format not in _MIME_BY_FORMAT or not _dimensions_allowed(dimensions):
                    return None
                image.verify()
            with Image.open(BytesIO(payload)) as decoded:
                if decoded.format != image_format or decoded.size != dimensions:
                    return None
                decoded.load()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
        ValueError,
        Warning,
    ):
        return None
    return _MIME_BY_FORMAT[image_format], payload


def _dimensions_allowed(dimensions):
    width, height = dimensions
    return bool(
        0 < width <= MAX_IMAGE_DIMENSION
        and 0 < height <= MAX_IMAGE_DIMENSION
        and width * height <= MAX_IMAGE_PIXELS
    )
