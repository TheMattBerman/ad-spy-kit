"""Build competitor.json from saved StealAds rows, so the agent never hand-writes it.

A StealAds read already says which Facebook page ran each ad and what the page is called.
`competitor_from_ads` takes the page that ran most of the rows (search_ads' page filter is
only a ranking hint, so a few rows from other pages can come along).
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _most_common(values: list[str]) -> str:
    counts = Counter(v for v in values if v)
    return counts.most_common(1)[0][0] if counts else ""


def competitor_from_ads(
    ads: list[dict[str, Any]],
    *,
    query: str = "",
    country: str = "",
    competitor_id: str | None = None,
    brand_id: str | None = None,
    tracked: bool = False,
) -> dict[str, Any]:
    """competitor.json (schemas/competitor.schema.json) from mapped ads.

    `page_id` and `page_name` are the most common ones on the rows. `country` is only what the
    caller knows (a tracked competitor's country_code); StealAds search rows carry none, so it
    stays "" rather than a guess. `confidence` is "likely": it comes from rows, not a lookup.
    """
    page_id = _most_common([str(a.get("facebook_page_id") or "") for a in ads])
    page_name = _most_common([str(a.get("page_name") or "") for a in ads]) or query
    doc: dict[str, Any] = {
        "query": query or page_name,
        "page_id": page_id,
        "page_name": page_name,
        "country": country,
        "confidence": "likely",
        "alternates": [],
        "tracked": tracked,
        "source": "stealads",
    }
    if competitor_id:
        doc["competitor_id"] = competitor_id
    if brand_id:
        doc["brand_id"] = brand_id
    return doc
