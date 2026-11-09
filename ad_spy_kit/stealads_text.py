"""Read a saved StealAds tool reply that came back as Markdown text instead of JSON.

Prod `search_ads` and `find_winning_ads` return a numbered text list (title, caption, run
line, label, hook, image URL, links), not the JSON rows dev returned. `get_ad` still returns
JSON. `load_saved` takes either and always gives back the row-list shape `ingest` reads:
`{"ads": [...], "next_cursor": ..., "has_more": ...}`.

Text rows carry less than JSON rows: no `variation_count`, `group_id`, `hook.spoken`,
`hook.on_screen` or `start_date`. The page id comes from the image URL
(`corpus:page:<id>`), the ad id from the last segment of the StealAds link.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROW_START = re.compile(r"^\s*(\d{1,3})\.\s+(.*\S)\s*$")
_RUN_LINE = re.compile(
    r"^\s*(\d+)\s+days?\s+running(?:\s*[·|\-]\s*(?P<state>.+?))?\s*$", re.IGNORECASE
)
_CURSOR = re.compile(r"Next page cursor[^:]*:\s*(\S+)", re.IGNORECASE)
_PAGE_IN_URL = re.compile(r"corpus:page:(\d+)")
_UUID_TAIL = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$")
_TRAILER = re.compile(r"^(more results may be available|next page cursor)", re.IGNORECASE)
_FIELD = re.compile(r"^(Label|Strength|Hook|Image|Preview|Ad|StealAds|Caution):\s*(.*)$")


def _row(block: list[str]) -> dict[str, Any] | None:
    title = _ROW_START.match(block[0])
    if not title:
        return None
    row: dict[str, Any] = {"page_name": title.group(2)}
    text: list[str] = []
    for line in block[1:]:
        run = _RUN_LINE.match(line)
        field = _FIELD.match(line.strip())
        if run:
            row["run_duration_days"] = int(run.group(1))
            state = (run.group("state") or "").strip().lower()
            if state.startswith("still"):
                row["still_running"] = True
            elif state:
                row["still_running"] = False
        elif field:
            key, value = field.group(1), field.group(2).strip()
            if key == "Label":
                row["strength_label"] = value.lower() or None
            elif key == "Strength":
                row["strength"] = value
            elif key == "Hook":
                row["hook_type"] = value
            elif key == "Image":
                row["image_url"] = value
            elif key == "Ad":
                row["ad_library_url"] = value
            elif key == "StealAds":
                tail = _UUID_TAIL.search(value)
                if tail:
                    row["id"] = tail.group(1)
            elif key == "Caution":
                row["steal_caution"] = value
        elif line.strip() and "Preview:" not in line and not _TRAILER.match(line.strip()):
            text.append(line.strip())
    if text:
        row["body_text"] = "\n".join(text)
    if not row.get("id"):
        return None
    page = _PAGE_IN_URL.search(str(row.get("image_url") or ""))
    if page:
        row["facebook_page_id"] = page.group(1)
    return row


def parse_stealads_text(text: str) -> dict[str, Any]:
    """Numbered Markdown reply → `{"ads": [...], "next_cursor": ..., "has_more": ...}`."""
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if _ROW_START.match(line) and not _FIELD.match(line.strip()):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    ads = [r for r in (_row(b) for b in blocks) if r]
    cursor = _CURSOR.search(text)
    return {
        "ads": ads,
        "next_cursor": cursor.group(1) if cursor else None,
        "has_more": bool(cursor) or "more results may be available" in text.lower(),
        "_from_text": True,
    }


def load_saved(path: Path) -> dict[str, Any]:
    """A saved tool reply as a dict: JSON when it is JSON, else parsed Markdown text."""
    raw = path.read_text()
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return parse_stealads_text(raw)
    return doc if isinstance(doc, dict) else {"ads": []}
