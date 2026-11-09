"""Deterministic local-media receipts for future visual classification flows.

This module deliberately does not download media or extract video frames.  Callers
provide local paths, while video extraction is injected through a small callable
boundary so the classification layer can choose its runtime dependency.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class MediaEvidenceError(ValueError):
    """Raised when local media cannot be safely used as visual evidence."""


_IMAGE_SIGNATURES = (
    ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", lambda data: data.startswith(b"\xff\xd8")),
    ("image/gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    ("image/webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
)


def sha256_file(local_path: str | os.PathLike[str]) -> str:
    """Return the SHA-256 digest of a local file without loading it all at once."""
    path = Path(local_path)
    if not path.is_file():
        raise MediaEvidenceError(f"media file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_image_media(local_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Validate a supported local raster image and return its stable metadata."""
    path = Path(local_path)
    if not path.is_file():
        raise MediaEvidenceError(f"image file does not exist: {path}")
    with path.open("rb") as handle:
        header = handle.read(32)
    media_type = next((mime for mime, matches in _IMAGE_SIGNATURES if matches(header)), None)
    if media_type is None:
        raise MediaEvidenceError(f"unsupported or invalid image media: {path}")
    return {
        "local_path": os.path.normpath(str(path)),
        "media_type": media_type,
        "byte_size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_evidence_manifest(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a canonical visual-evidence manifest from local image records.

    Every item needs ``role``, ``source_record_id``, and ``local_path``.  The
    resulting hash covers only canonical, JSON-serializable receipt fields.
    """
    entries = []
    for item in items:
        role = _required_text(item, "role")
        source_record_id = _required_text(item, "source_record_id")
        local_path = _required_text(item, "local_path")
        entry = validate_image_media(local_path)
        entry.update({"role": role, "source_record_id": source_record_id})
        entries.append(entry)
    entries.sort(key=lambda entry: (entry["role"], entry["source_record_id"], entry["local_path"]))
    manifest = {"version": 1, "evidence": entries}
    manifest["sha256"] = _sha256_json(manifest)
    return manifest


def plan_video_frames(duration_seconds: float, frame_count: int = 4) -> list[dict[str, float | int]]:
    """Return evenly distributed, JSON-ready timestamps including first and last frame."""
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise MediaEvidenceError("frame_count must be a positive integer")
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError) as error:
        raise MediaEvidenceError("duration_seconds must be a finite non-negative number") from error
    if not math.isfinite(duration) or duration < 0:
        raise MediaEvidenceError("duration_seconds must be a finite non-negative number")
    if frame_count == 1 or duration == 0:
        return [{"index": 0, "timestamp_seconds": 0.0}]
    # Seeking to exactly `duration` makes ffmpeg return no packets (error -22) and fails the
    # whole extraction, so keep the last sample just short of the end.
    last = max(0.0, duration - min(0.2, duration * 0.05))
    return [
        {"index": index, "timestamp_seconds": round(min(duration * index / (frame_count - 1), last), 6)}
        for index in range(frame_count)
    ]


def plan_opening_frames(
    duration_seconds: float, frame_count: int = 5, window_seconds: float = 3.0
) -> list[dict[str, float | int]]:
    """Return dense, JSON-ready samples from the opening window of a video."""
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise MediaEvidenceError("frame_count must be a positive integer")
    try:
        duration = float(duration_seconds)
        window = float(window_seconds)
    except (TypeError, ValueError) as error:
        raise MediaEvidenceError("duration_seconds and window_seconds must be finite non-negative numbers") from error
    if not math.isfinite(duration) or duration < 0 or not math.isfinite(window) or window < 0:
        raise MediaEvidenceError("duration_seconds and window_seconds must be finite non-negative numbers")
    if frame_count == 1 or duration == 0 or window == 0:
        return [{"index": 0, "timestamp_seconds": 0.0}]
    opening_duration = min(window, duration)
    last = max(0.0, duration - min(0.2, duration * 0.05))
    return [
        {"index": index, "timestamp_seconds": round(min(opening_duration * index / frame_count, last), 6)}
        for index in range(frame_count)
    ]


def extract_video_frames(
    video_path: str | os.PathLike[str],
    frame_plan: Sequence[Mapping[str, Any]],
    extractor: Callable[[Path, Sequence[Mapping[str, Any]]], Any],
) -> Any:
    """Invoke an injected extractor; this module intentionally has no ffmpeg dependency."""
    if not callable(extractor):
        raise MediaEvidenceError("extractor must be callable")
    path = Path(video_path)
    if not path.is_file():
        raise MediaEvidenceError(f"video file does not exist: {path}")
    return extractor(path, tuple(frame_plan))


def build_image_data_uri(local_path: str | os.PathLike[str]) -> str:
    """Encode validated local visual evidence as a base64 data URI."""
    metadata = validate_image_media(local_path)
    with Path(local_path).open("rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{metadata['media_type']};base64,{encoded}"


def _required_text(item: Mapping[str, Any], key: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise MediaEvidenceError(f"evidence item requires {key}")
    return value


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
