"""Pure helpers for transcript evidence."""

from __future__ import annotations

import re


_CUE_START = re.compile(r"^(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)\s+-->")


# Without cue timestamps we can't window by time, so cap the plain-text fallback to a
# sane opening-length proxy (roughly the first spoken sentence or two).
_PLAINTEXT_OPENING_WORDS = 40


def parse_vtt_opening(vtt_text: str, window_seconds: float = 3.0) -> str:
    """Return whitespace-collapsed WEBVTT cue text beginning within the opening window.

    Falls back to the leading words when the input carries no VTT cue headers (e.g.
    Instagram's transcript endpoint returns plain prose, not WEBVTT).
    """
    text = str(vtt_text or "")
    lines = text.splitlines()
    opening = []
    saw_cue = False
    index = 0
    while index < len(lines):
        match = _CUE_START.match(lines[index].strip())
        if not match:
            index += 1
            continue
        saw_cue = True
        hours, minutes, seconds = match.groups()
        starts_at = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        index += 1
        cue = []
        while index < len(lines) and lines[index].strip():
            cue.append(lines[index].strip())
            index += 1
        if starts_at < window_seconds:
            opening.extend(cue)
    if not saw_cue:
        words = text.replace("WEBVTT", "").split()
        return " ".join(words[:_PLAINTEXT_OPENING_WORDS])
    return " ".join(" ".join(opening).split())
