"""Optional full-motion evidence capture for visual creative classification.

Virlo normally supplies a post URL and a thumbnail, not a video file.  When
``yt-dlp`` and ``ffmpeg`` are available, this module resolves the public post
locally and extracts evenly distributed frames.  A thumbnail remains useful
evidence, but the caller can now distinguish it from a real video read.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from .media_evidence import MediaEvidenceError, plan_opening_frames, plan_video_frames


class VideoEvidenceError(RuntimeError):
    pass


def video_tools_available() -> bool:
    return bool(shutil.which("yt-dlp") and shutil.which("ffmpeg") and shutil.which("ffprobe"))


def capture_video_frames(
    source_url: str,
    run_dir: str,
    prefix: str,
    *,
    frame_count: int = 6,
    opening: bool = False,
    timeout_seconds: int = 20,
) -> list[str]:
    """Download one public creative and return local relative frame paths.

    This deliberately fails closed: callers receive an exception and must mark
    the record thumbnail-only rather than pretending the motion was observed.
    """
    source_url = str(source_url or "").strip()
    if not source_url:
        raise VideoEvidenceError("missing public video URL")
    if not video_tools_available():
        raise VideoEvidenceError("full-motion evidence needs yt-dlp, ffmpeg, and ffprobe on PATH")

    assets_dir = Path(run_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    base = f"{_slug(prefix)}-{hashlib.sha1(source_url.encode('utf-8')).hexdigest()[:12]}"
    existing = sorted(assets_dir.glob(f"{base}.mp4"))
    video_path = existing[0] if existing else _download_video(source_url, assets_dir, base, timeout_seconds)
    duration = _duration_seconds(video_path, timeout_seconds)
    plan = plan_opening_frames(duration, frame_count) if opening else plan_video_frames(duration, frame_count)
    frame_dir = assets_dir / f"{base}-opening-frames" if opening else assets_dir / f"{base}-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for item in plan:
        target = frame_dir / f"frame-{int(item['index']) + 1:02d}.jpg"
        if not target.is_file():
            _extract_frame(video_path, target, float(item["timestamp_seconds"]), timeout_seconds)
        if not target.is_file() or target.stat().st_size == 0:
            raise VideoEvidenceError(f"ffmpeg did not create frame {target.name}")
        paths.append(str(target.relative_to(run_dir)))
    return paths


def _download_video(source_url: str, assets_dir: Path, base: str, timeout_seconds: int) -> Path:
    template = str(assets_dir / f"{base}.%(ext)s")
    command = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--socket-timeout",
        "8",
        "--retries",
        "0",
        "--fragment-retries",
        "0",
        "--restrict-filenames",
        "--max-filesize",
        "40M",
        "--merge-output-format",
        "mp4",
        "-f",
        "bv*+ba/b",
        "-o",
        template,
        source_url,
    ]
    _run(command, timeout_seconds, "yt-dlp")
    matches = sorted(assets_dir.glob(f"{base}.*"))
    videos = [path for path in matches if path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not videos:
        raise VideoEvidenceError("yt-dlp completed without a usable video file")
    return videos[0]


def _duration_seconds(video_path: Path, timeout_seconds: int) -> float:
    completed = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        timeout_seconds,
        "ffprobe",
    )
    try:
        return float(completed.stdout.strip())
    except ValueError as error:
        raise VideoEvidenceError("ffprobe did not return a usable duration") from error


def _extract_frame(video_path: Path, target: Path, timestamp_seconds: float, timeout_seconds: int) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp_seconds),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(target),
        ],
        timeout_seconds,
        "ffmpeg",
    )


def _run(command: list[str], timeout_seconds: int, tool: str) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VideoEvidenceError(f"{tool} failed: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown failure").strip().replace("\n", " ")
        raise VideoEvidenceError(f"{tool} failed: {detail[-600:]}")
    return completed


def _slug(value: str) -> str:
    text = "".join(char.lower() if char.isalnum() else "-" for char in str(value or "video"))
    return "-".join(part for part in text.split("-") if part)[:48] or "video"
