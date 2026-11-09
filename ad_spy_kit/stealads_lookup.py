"""Read a saved StealAds `search_advertisers` reply (response_format "json").

StealAds resolves a brand name, a domain, a Facebook page id or an Ad Library link. A hit
comes back in `advertisers` (`name`, `facebook_page_id`); a brand StealAds doesn't hold comes
back with `status: "not_indexed"`, `can_pull: false` and only fuzzy `suggestions`. Prod,
2026-11-06: "Space Goods", `spacegoods.com`, page 104163495557745 and its Ad Library link all
came back not_indexed. Pulling a missing brand through the MCP isn't live, so the kit says so
plainly and offers the ScrapeCreators path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ad_spy_kit.errors import KitError

STEALADS_APP = "https://app.stealads.ai/ad-library"


def read_reply(path: Path) -> dict[str, Any]:
    """The saved reply as a dict. Anything that isn't a JSON object is a KitError."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise KitError(
            f"{path} isn't a saved StealAds search_advertisers JSON reply ({exc}).",
            fix='Call search_advertisers with response_format "json" and save the reply as is.',
            code="lookup_unreadable",
        ) from exc
    if not isinstance(doc, dict):
        raise KitError(
            f"{path} isn't a StealAds search_advertisers reply.",
            fix='Call search_advertisers with response_format "json" and save the reply as is.',
            code="lookup_unreadable",
        )
    return doc


def classify(doc: dict[str, Any]) -> str:
    """`found` (one page), `choose` (several pages), or `not_indexed`."""
    advertisers = [a for a in doc.get("advertisers") or [] if isinstance(a, dict)]
    if str(doc.get("status") or "").lower() == "not_indexed" and not advertisers:
        return "not_indexed"
    if len(advertisers) == 1:
        return "found"
    if advertisers:
        return "choose"
    return "not_indexed"


def not_indexed_message(query: str, doc: dict[str, Any]) -> str:
    """What the user is told when StealAds doesn't hold the brand (plain words, no hedging)."""
    names = [
        str(s.get("name"))
        for s in (doc.get("suggestions") or [])[:3]
        if isinstance(s, dict) and s.get("name")
    ]
    typed = (query or "").strip()
    if typed.startswith(("http://", "https://")) or typed.isdigit():
        what = "that Facebook page"  # a link or page id reads badly in a sentence
    else:
        what = typed or "that brand"
    lines = [f"StealAds doesn't have {what} in its library yet."]
    if names:
        lines.append(f"It only found similar names: {', '.join(names)}. None is the same brand.")
    lines.append(
        "I can read it with a ScrapeCreators key instead. That costs ScrapeCreators credits, "
        "so I'll show the quote first and spend nothing until you say yes."
    )
    lines.append(
        "If you'd rather use StealAds, its own live fetch runs in the StealAds app "
        f"({STEALADS_APP}), not through this connection. Tell me when it's done and I'll "
        "read the brand from there."
    )
    return "\n".join(lines)


def advertiser_choices(doc: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"page_id": str(a.get("facebook_page_id") or ""), "page_name": str(a.get("name") or "")}
        for a in doc.get("advertisers") or []
        if isinstance(a, dict) and a.get("facebook_page_id")
    ]


def competitor_doc(query: str, choice: dict[str, str]) -> dict[str, Any]:
    """competitor.json (schemas/competitor.schema.json) from one StealAds advertiser hit."""
    return {
        "query": query or choice["page_name"],
        "page_id": choice["page_id"],
        "page_name": choice["page_name"],
        "country": "",
        "confidence": "exact",
        "alternates": [],
        "tracked": False,
        "source": "stealads",
    }
