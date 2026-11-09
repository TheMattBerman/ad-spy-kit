from __future__ import annotations

import hashlib
from typing import Any

from ad_spy_kit.sl_adapter import normalize_headline, normalize_landing_url

try:
    import imagehash
    from PIL import Image
except ImportError:  # pragma: no cover - optional in minimal env
    imagehash = None
    Image = None


def _phash_from_bytes(data: bytes) -> str | None:
    if not imagehash or not Image:
        return None
    from io import BytesIO

    try:
        img = Image.open(BytesIO(data))
        return str(imagehash.phash(img))
    except Exception:
        return None


def media_hash_from_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def dedupe_key_for_ad(ad: dict[str, Any], *, image_bytes: bytes | None = None) -> tuple[str, str]:
    """Return (primary_key, key_type). Same image bytes beat same copy: a DCO ad can reuse
    one headline and body over several different pictures, and those are different creatives."""
    group_id = ad.get("group_id")
    if group_id:
        return f"group:{group_id}", "group_id"

    if image_bytes:
        ph = _phash_from_bytes(image_bytes)
        if ph:
            return f"phash:{ph}", "phash"

    cached = ad.get("media_hash")
    if cached:
        return f"phash:{cached}", "phash"

    hl = normalize_headline(ad.get("headline"))
    url = normalize_landing_url(ad.get("landing_url"))
    return f"text:{hl}|{url}", "headline_url"


def creative_keys(ad: dict[str, Any], *, image_bytes: bytes | None = None) -> list[str]:
    """Every key that says "this is the same creative": its StealAds group, its image hash,
    and (only with neither) its headline + body. Two ads sharing any key are one creative."""
    keys: list[str] = []
    if ad.get("group_id"):
        keys.append(f"group:{ad['group_id']}")
    if image_bytes:
        ph = _phash_from_bytes(image_bytes)
        if ph:
            keys.append(f"phash:{ph}")
    if ad.get("media_hash"):
        keys.append(f"phash:{ad['media_hash']}")
    if not keys:
        hl = normalize_headline(ad.get("headline"))
        body = normalize_headline(ad.get("body"))
        url = normalize_landing_url(ad.get("landing_url"))
        keys.append(f"text:{hl}|{body}|{url}")
    return keys


def creative_groups(ads: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group near-identical creatives (shared group id or image hash), in first-seen order."""
    parent: dict[int, int] = {}

    def find(i: int) -> int:
        while parent.setdefault(i, i) != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, ad in enumerate(ads):
        find(i)
        for key in creative_keys(ad):
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    groups: dict[int, list[dict[str, Any]]] = {}
    for i, ad in enumerate(ads):
        groups.setdefault(find(i), []).append(ad)
    return list(groups.values())


def distinct_creatives(ads: list[dict[str, Any]]) -> int:
    """How many different creatives these ads are (30 ads can be 21 creatives)."""
    return len(creative_groups(ads))


def merge_duplicates(
    ads: list[dict[str, Any]], *, media_bytes: dict[str, bytes | None] | None = None
) -> list[dict[str, Any]]:
    """Collapse duplicate creatives; keep best-ranked ad per creative."""
    media_bytes = media_bytes or {}

    def rank_key(a: dict[str, Any]) -> tuple:
        br = a.get("bangers_rank")
        br_sort = br if br is not None else 10_000
        return (
            br_sort,
            -(a.get("days_live") or 0),
            -(a.get("variation_count") or 0),
            -(a.get("effectiveness_score") or 0),
        )

    out: list[dict[str, Any]] = []
    for group in creative_groups(ads):
        keeper = group[0]
        for ad in group[1:]:
            if rank_key(ad) < rank_key(keeper):
                keeper = ad
        merged = {**keeper, "dupes_merged": [a["ad_id"] for a in group if a is not keeper]}
        merged["dedupe_key"] = dedupe_key_for_ad(
            merged, image_bytes=media_bytes.get(merged["ad_id"])
        )[0]
        out.append(merged)
    return out
