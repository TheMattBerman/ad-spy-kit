"""Catalog (DPA) and dynamic (DCO) ads store template text, not words: `{{product.name}}`,
`{{product.brand}}`. Meta fills the real product in per viewer, so nothing in the Ad Library
row is something a viewer read.

The rule: any text with `{{...}}` in it is empty. A headline that has one becomes "" and the
hook falls back to the first real line of the caption. A caption keeps its real lines and
loses the ones with a placeholder. The ad is marked `catalog: true` so cards can say so.
Nothing here ever quotes a placeholder.
"""

from __future__ import annotations

import re
from typing import Any

TEMPLATE = re.compile(r"\{\{|\}\}")
CATALOG_FORMATS = ("DPA", "DCO")
# Fields whose text can reach a board or a quote.
TEXT_FIELDS = (
    "headline",
    "body",
    "cta",
    "onscreen_text",
    "onscreen_hook",
    "transcript",
    "spoken_opener",
    "spoken_hook",
)


def has_template(text: Any) -> bool:
    return bool(TEMPLATE.search(str(text or "")))


def scrub_text(text: Any) -> tuple[str, bool]:
    """(text without its placeholder lines, whether any line had one)."""
    raw = str(text or "")
    if not has_template(raw):
        return raw, False
    kept = [ln for ln in raw.splitlines() if not has_template(ln)]
    return "\n".join(kept).strip(), True


def is_catalog_ad(ad: dict[str, Any]) -> bool:
    """A catalog or dynamic-creative ad: Meta fills in the product (or the picture) per viewer."""
    return bool(ad.get("catalog")) or str(ad.get("format") or "").upper() in CATALOG_FORMATS


def scrub_ad(ad: dict[str, Any]) -> bool:
    """Empty every placeholder in one mapped ad (in place) and re-pick its hooks.

    Returns True when anything changed. Safe to run twice."""
    changed = False
    for key in TEXT_FIELDS:
        if key not in ad or ad[key] in (None, ""):
            continue
        clean, hit = scrub_text(ad[key])
        if hit:
            ad[key] = clean if key in ("headline", "body", "cta") else (clean or None)
            changed = True
    if changed or str(ad.get("format") or "").upper() == "DPA":
        if not ad.get("catalog"):
            ad["catalog"] = True
            changed = True
    if changed:
        from ad_spy_kit.hooks import resolve_hooks

        resolve_hooks(ad)
    return changed


def scrub_ads_raw(ads_raw: dict[str, Any]) -> int:
    """Scrub every ad in an ads.raw.json dict. Returns how many ads changed."""
    return sum(1 for ad in ads_raw.get("ads", []) if scrub_ad(ad))


def leaks(text: Any) -> bool:
    """True when rendered text still carries a placeholder (gate C9)."""
    return has_template(text)
