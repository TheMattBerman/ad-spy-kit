"""On-screen hooks for the free route: the user's own agent reads each winner's image.

No OCR service. `ad-spy-kit onscreen <run_dir>` lists what to read: every winner image
(the creative) and every winner video with no spoken hook (its thumbnail, as poster-frame
text). The agent looks at each file and records, verbatim:

- `onscreen_text`: every line of text in the image, top to bottom, one per line.
- `onscreen_hook`: the headline, or the biggest text when there is no headline.

into `<run_dir>/onscreen.json`; `--apply` writes it into ads.raw.json, where hooks.py makes
it the hook (`hook_source: onscreen`, tag "on screen") unless the ad has a spoken one.

An image with no words on it (a product shot, a catalog photo) is recorded as
`{"ad_id": "...", "onscreen_hook": null, "no_text": true}`. That counts as read: the ad
keeps its caption hook and `ad-spy-kit onscreen` stops listing it.
Gate A3 then checks the analysis hook against the stored `onscreen_hook`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ad_spy_kit.hooks import resolve_hooks

_MEDIA_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _norm(text: Any) -> str:
    return " ".join(str(text or "").replace("\u2019", "'").split()).lower()


def onscreen_targets(
    ads_raw: dict[str, Any], winners: dict[str, Any], media_dir: Path
) -> list[dict[str, Any]]:
    """Winner images, plus winner videos with no spoken hook, that have a cached file."""
    ads = {a["ad_id"]: a for a in ads_raw.get("ads", [])}
    out = []
    for w in winners.get("winners", []):
        ad = ads.get(w["ad_id"])
        if not ad or ad.get("onscreen_hook") or ad.get("onscreen_no_text"):
            continue
        video = str(ad.get("format") or "").upper() == "VIDEO"
        if video and ad.get("spoken_hook"):
            continue
        path = next(
            (
                media_dir / f"{ad['ad_id']}{e}"
                for e in _MEDIA_EXTS
                if (media_dir / f"{ad['ad_id']}{e}").is_file()
            ),
            None,
        )
        if path is None:
            continue
        out.append(
            {"ad_id": ad["ad_id"], "role": "poster-frame" if video else "creative", "path": path}
        )
    return out


def check_item(item: dict[str, Any]) -> str | None:
    """Why a recorded read can't be used, or None. The hook must sit inside the full text.
    `no_text: true` (no hook, no text) records "there are no words on this image"."""
    hook, text = item.get("onscreen_hook"), item.get("onscreen_text")
    if item.get("no_text") is True:
        if str(hook or "").strip() or str(text or "").strip():
            return "no_text is true but onscreen_hook or onscreen_text has words in it"
        return None
    if not str(hook or "").strip():
        return "no onscreen_hook"
    if text and _norm(hook) not in _norm(text):
        return "onscreen_hook is not verbatim in onscreen_text"
    return None


def apply_onscreen(ads_raw: dict[str, Any], doc: dict[str, Any]) -> int:
    """Write recorded on-screen reads into ads.raw ads (by ad_id). Returns how many landed."""
    by_id = {str(i.get("ad_id")): i for i in doc.get("items", []) if check_item(i) is None}
    landed = 0
    for ad in ads_raw.get("ads", []):
        item = by_id.get(str(ad["ad_id"]))
        if item and item.get("no_text") is True:
            ad["onscreen_no_text"] = True
            landed += 1
        elif item and ad.get("onscreen_source") == "stealads":
            # StealAds' own read goes first; the agent's lines only widen the offer evidence.
            extra = item.get("onscreen_text") or item["onscreen_hook"]
            if _norm(extra) not in _norm(ad.get("onscreen_text")):
                ad["onscreen_text"] = f"{ad.get('onscreen_text') or ''}\n{extra}".strip()
            landed += 1
        elif item:
            ad["onscreen_text"] = item.get("onscreen_text") or item["onscreen_hook"]
            ad["onscreen_hook"] = item["onscreen_hook"]
            ad["onscreen_source"] = "agent-vision"
            landed += 1
        resolve_hooks(ad)
    return landed


def apply_file(run_dir: Path) -> tuple[int, list[str]]:
    """onscreen.json → ads.raw.json. Returns (landed, problems)."""
    doc = json.loads((run_dir / "onscreen.json").read_text())
    problems = [f"{i.get('ad_id')}: {why}" for i in doc.get("items", []) if (why := check_item(i))]
    ads_raw = json.loads((run_dir / "ads.raw.json").read_text())
    landed = apply_onscreen(ads_raw, doc)
    (run_dir / "ads.raw.json").write_text(json.dumps(ads_raw, indent=2, ensure_ascii=False))
    return landed, problems
