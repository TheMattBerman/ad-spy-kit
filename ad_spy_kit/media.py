"""Saved ad images, kept a sane size.

Meta serves some creatives at 6000+ px. Embedded as is, a six-ad board came to 26 MB of HTML
and 80 MB of media. Every image is saved and embedded at most MAX_EDGE px on its long edge,
as JPEG (quality JPEG_QUALITY). The full-size original is only kept on request
(`--keep-originals`, saved under media/originals/).
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

MAX_EDGE = 1200
JPEG_QUALITY = 85
ORIGINALS_DIR = "originals"
_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def shrink_bytes(data: bytes, max_edge: int = MAX_EDGE) -> bytes | None:
    """JPEG bytes of the image at most max_edge on its long edge, or None when unreadable."""
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if max(im.size) > max_edge:
                scale = max_edge / max(im.size)
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, (255, 255, 255))
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            else:
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except (OSError, ValueError):
        return None


def shrink_image(path: Path, *, keep_originals: bool = False, max_edge: int = MAX_EDGE) -> Path:
    """Replace `path` with a downscaled JPEG (same stem). Returns the new path.

    An image already within max_edge is left alone, whatever its format."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            size = im.size
    except (OSError, ValueError):
        return path
    if max(size) <= max_edge:
        return path
    small = shrink_bytes(path.read_bytes(), max_edge)
    if small is None:
        return path
    if keep_originals:
        keep = path.parent / ORIGINALS_DIR
        keep.mkdir(exist_ok=True)
        shutil.copy2(path, keep / path.name)
    out = path.with_suffix(".jpg")
    out.write_bytes(small)
    if out != path:
        path.unlink(missing_ok=True)
    return out


def shrink_media_dir(media_dir: Path, ads_raw: dict[str, Any] | None = None) -> int:
    """Shrink every saved image in a run's media/ folder (idempotent). Returns how many files
    changed. When `ads_raw` is given, each ad's `media[].path` is pointed at the new file."""
    if not media_dir.is_dir():
        return 0
    changed = 0
    for path in sorted(media_dir.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in _EXTS:
            continue
        before = path.stat().st_size
        new = shrink_image(path)
        if new != path or new.stat().st_size != before:
            changed += 1
        if new != path and ads_raw is not None:
            for ad in ads_raw.get("ads", []):
                for m in ad.get("media") or []:
                    if m.get("path") == f"media/{path.name}":
                        m["path"] = f"media/{new.name}"
    return changed


def normalize_run(run_dir: Path) -> dict[str, int]:
    """Make a saved run safe to draw: empty placeholder text, shrink big images. Idempotent.

    Returns {"templates": ads fixed, "images": files shrunk}. ads.raw.json is rewritten only
    when something changed."""
    from ad_spy_kit.template_text import scrub_ads_raw

    path = run_dir / "ads.raw.json"
    ads_raw = json.loads(path.read_text())
    templates = scrub_ads_raw(ads_raw)
    images = shrink_media_dir(run_dir / "media", ads_raw)
    if templates or images:
        path.write_text(json.dumps(ads_raw, indent=2, ensure_ascii=False) + "\n")
    return {"templates": templates, "images": images}
