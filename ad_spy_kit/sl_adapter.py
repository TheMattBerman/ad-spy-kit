from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from ad_spy_kit.hooks import resolve_hooks
from ad_spy_kit.stealads_mcp import apply_winning_signals, strip_hidden_scores

STEALADS_FIELD_MAP: dict[str, str] = {
    "ad_id": "ad_id",
    "id": "ad_id",
    "ad_library_url": "ad_library_url",
    "adLibraryUrl": "ad_library_url",
    "start_date": "start_date",
    "startDate": "start_date",
    "end_date": "end_date",
    "endDate": "end_date",
    "first_seen_at": "first_seen_at",
    "firstSeenAt": "first_seen_at",
    "last_seen_at": "last_seen_at",
    "lastSeenAt": "last_seen_at",
    "days_live": "days_live",
    "daysLive": "days_live",
    "run_duration_days": "run_duration_days",
    "runDurationDays": "run_duration_days",
    "variation_count": "variation_count",
    "variationCount": "variation_count",
    "is_active": "is_active",
    "isActive": "is_active",
    "still_running": "still_running",
    "may_have_stopped": "may_have_stopped",
    "mayHaveStopped": "may_have_stopped",
    "format": "format",
    "headline": "headline",
    "original_headline": "headline",
    "body": "body",
    "body_text": "body",
    "cta": "cta",
    "original_cta": "cta",
    "landing_url": "landing_url",
    "landingUrl": "landing_url",
    "link_url": "landing_url",
    "destination_url": "destination_url",
    "destinationUrl": "destination_url",
    "hook_type": "hook_type",
    "hookType": "hook_type",
    "angle": "angle",
    "funnel_stage": "funnel_stage",
    "funnelStage": "funnel_stage",
    "bangers_rank": "bangers_rank",
    "why": "why",
    "group_id": "group_id",
    "groupId": "group_id",
    "collation_id": "group_id",
    "collationId": "group_id",
    # Real StealAds search_ads / find_bangers rows (dev MCP, 2026-10-28).
    "steal_caution": "steal_caution",
    "strength": "strength",
    "page_name": "page_name",
    "facebook_page_id": "facebook_page_id",
    "ad_format": "format_label",
    "for": "audience_label",
    # JSON reply rows (response_format "json", row schema_version 1, prod 2026-11-06).
    "first_seen": "first_seen_at",
    "last_seen": "last_seen_at",
    "hook_type_filter": "hook_type_filter",
    "platforms": "platforms",
    "countries": "countries",
    "schema_version": "schema_version",
    "video_url": "video_url",
    "card_image_urls": "card_image_urls",
}

REQUIRED_NORMALIZED_KEYS = {
    "ad_id",
    "ad_library_url",
    "start_date",
    "days_live",
    "variation_count",
    "is_active",
    "format",
    "headline",
    "body",
    "cta",
    "landing_url",
}


def normalize_landing_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip().lower())
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in qs.items() if not k.startswith("utm_") and k not in ("fbclid", "gclid")
    }
    clean_query = "&".join(f"{k}={v[0]}" for k, v in sorted(filtered.items()))
    path = parsed.path.rstrip("/") or parsed.path
    return urlunparse((parsed.scheme, parsed.netloc, path, "", clean_query, ""))


def normalize_headline(text: str | None) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text.strip().lower())
    return re.sub(r"[^\w\s%$]", "", t)


def unify_format(value: Any) -> str:
    """One name per format: StealAds says static / video (search rows) and image / video
    (older tracked rows); the kit says IMAGE / VIDEO. Other names (DPA, DCO) pass through."""
    text = str(value or "").strip().upper()
    if text in ("STATIC", "IMAGE", "PHOTO"):
        return "IMAGE"
    return text


def landing_domain(url: str | None) -> str:
    """`https://www.trueclassictees.com/p?utm=1` -> `trueclassictees.com` (empty when no URL)."""
    host = urlparse(str(url or "").strip()).netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def card_urls(raw: dict[str, Any]) -> list[str]:
    """Carousel card pictures in card order (JSON rows: `card_image_urls`; null on single ads)."""
    value = raw.get("card_image_urls") or raw.get("cardImageUrls")
    if not isinstance(value, list):
        return []
    return [str(u) for u in value if isinstance(u, str) and u.startswith("http")]


def extract_media(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if "media" in raw and isinstance(raw["media"], list):
        return raw["media"]
    out: list[dict[str, Any]] = []
    mirror = raw.get("media_mirror") if isinstance(raw.get("media_mirror"), dict) else {}
    delivery = mirror.get("delivery_url") or mirror.get("source_url")
    if delivery:
        out.append(
            {
                "url": delivery,
                "durable": bool(mirror.get("durable")),
                "kind": "image",
            }
        )
    stealads_mirror = ("https://generated.stealads.ai/",)
    for key, kind in (
        ("image_url", "image"),
        ("imageUrl", "image"),
        ("video_preview_image_url", "video_preview"),
        ("videoPreviewImageUrl", "video_preview"),
        ("thumbnail_url", "video_preview"),
        ("thumbnailUrl", "video_preview"),
        ("video_thumbnail_url", "video_preview"),
    ):
        url = raw.get(key)
        if url:
            durable = bool(
                raw.get("durable")
                or raw.get("is_durable")
                or raw.get("isDurable")
                or str(url).startswith(stealads_mirror)
            )
            out.append({"url": url, "durable": durable, "kind": kind})
    if len(out) > 1:
        # image_url, then a different thumbnail: one picture to save, the rest as fallbacks.
        first, rest = out[0], [m["url"] for m in out[1:] if m["url"] != out[0]["url"]]
        out = [{**first, **({"fallback_urls": rest} if rest else {})}]
    return out


# Tolerant names for hook sources StealAds doesn't expose yet (docs/stealads-mcp.md lists
# what we've asked for). Dotted paths reach into nested analysis blocks. First hit wins.
TRANSCRIPT_KEYS = (
    "transcript",
    "video_transcript",
    "transcript_text",
    "audio_transcript",
    "spoken_text",
    "voiceover_text",
    "analysis_summary.transcript",
    "analysis_summary.audio.transcript",
    "analysis_summary.marketing.transcript",
    "analysis.transcript",
)
SPOKEN_HOOK_KEYS = (
    "spoken_hook",
    "verbal_hook",
    "voiceover_hook",
    "audio_hook",
    "analysis_summary.spoken_hook",
    "analysis_summary.marketing.spoken_hook",
    "analysis_summary.audio.hook",
)
ONSCREEN_KEYS = (
    "onscreen_text",
    "on_screen_text",
    "text_overlay",
    "overlay_text",
    "analysis_summary.visual.onscreen_text",
    "analysis_summary.visual.on_screen_text",
    "analysis_summary.visual.text_overlay",
    "image_text",
    "creative_text",
    "analysis_summary.visual.image_text",
    # Real dev get_ad (tracked competitor, 2026-10-28): the text printed on the creative.
    "analysis_summary.visual.headline",
)
ONSCREEN_HOOK_KEYS = (
    "onscreen_hook",
    "on_screen_hook",
    "image_headline",
    "visual_hook",
    "analysis_summary.visual.onscreen_hook",
    "analysis_summary.visual.on_screen_hook",
    "analysis_summary.visual.hook",
)
_FB_ID_IN_URL = re.compile(r"/(\d{12,20})-[0-9a-f]{16,}\.\w+(?:\?|$)")


def _dig(raw: dict[str, Any], path: str) -> Any:
    node: Any = raw
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _pick_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _dig(raw, key)
        if isinstance(value, list):
            value = " ".join(str(v.get("text") if isinstance(v, dict) else v) for v in value)
        if isinstance(value, dict):
            value = value.get("text") or value.get("transcript")
        if value and str(value).strip():
            return str(value).strip()
    return ""


def facebook_ad_id(raw: dict[str, Any]) -> str:
    """Meta Ad Library id for a StealAds row: the field, else the number in its image filename.

    StealAds mirrors creatives as `originals/<competitor>/<fb_ad_id>-<sha256>.jpg` (checked
    against `facebook_ad_id` on a dev get_ad row, 2026-10-28). Used only to fetch a
    transcript, never printed on the board.
    """
    if raw.get("facebook_ad_id"):
        return str(raw["facebook_ad_id"])
    m = _FB_ID_IN_URL.search(str(raw.get("image_url") or ""))
    return m.group(1) if m else ""


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def apply_stealads_hook(mapped: dict[str, Any], raw: dict[str, Any]) -> None:
    """StealAds' `hook` object (MCP PR #3163, on search_ads / find_bangers / get_ad rows).

    `hook.spoken` is the verbal opener (first ~5 s of speech, never inferred from overlays;
    null when silent or not yet extracted) → `spoken_opener`; resolve_hooks quotes its first
    sentence after the garbled check. `hook.on_screen` (≤3 opening overlay lines) →
    `onscreen_text` / `onscreen_hook`. On an image, `hook.written` is the text read off the
    creative, falling back to the caption headline; it counts as on-screen only when it
    differs from the caption headline. `hook.opening_visual` is StealAds' description of the
    first frame (kept for the agent, never quoted as a hook). Full transcripts are not sent.
    """
    hook = raw.get("hook")
    if not isinstance(hook, dict):
        return
    spoken = str(hook.get("spoken") or "").strip()
    if spoken:
        mapped["spoken_opener"] = spoken
    lines = [str(x).strip() for x in hook.get("on_screen") or [] if str(x or "").strip()]
    written = str(hook.get("written") or "").strip()
    if not lines and hook.get("source") == "image" and written:
        if _norm(written) != _norm(raw.get("original_headline") or raw.get("headline")):
            lines = [written]
    if lines:
        mapped["onscreen_text"] = "\n".join(lines)
        mapped["onscreen_hook"] = lines[0]
        mapped["onscreen_source"] = "stealads"
    if hook.get("opening_visual"):
        mapped["opening_visual"] = str(hook["opening_visual"]).strip()
    if not mapped.get("hook_type") and hook.get("type"):
        mapped["hook_type"] = str(hook["type"]).strip()


def apply_hook_fields(mapped: dict[str, Any], raw: dict[str, Any]) -> None:
    """Read transcript / spoken / on-screen hook fields if the source sent any, then rank.

    StealAds' `hook` object goes first; the tolerant legacy names only fill what it left empty.
    """
    apply_stealads_hook(mapped, raw)
    for out, keys in (
        ("transcript", TRANSCRIPT_KEYS),
        ("spoken_hook", SPOKEN_HOOK_KEYS),
        ("onscreen_text", ONSCREEN_KEYS),
        ("onscreen_hook", ONSCREEN_HOOK_KEYS),
    ):
        text = mapped.get(out) if out.startswith("onscreen") and mapped.get(out) else None
        mapped[out] = text or _pick_text(raw, keys) or mapped.get(out) or None
    if mapped.get("onscreen_hook") and not mapped.get("onscreen_source"):
        mapped["onscreen_source"] = "source"
    resolve_hooks(mapped)


def infer_format(raw: dict[str, Any]) -> str:
    """IMAGE or VIDEO for rows with no format enum.

    `_format_filter` is set by the loader from the search_ads `format` argument that returned
    the row (exact). Next `hook.source` (video | image, PR #3163). Otherwise the StealAds
    format label ("ugc video" → VIDEO).
    """
    hint = raw.get("_format_filter")
    if hint in ("static", "video"):
        return "VIDEO" if hint == "video" else "IMAGE"
    hook = raw.get("hook") if isinstance(raw.get("hook"), dict) else {}
    if hook.get("source") in ("video", "image"):
        return "VIDEO" if hook["source"] == "video" else "IMAGE"
    label = str(raw.get("ad_format") or "").lower()
    return "VIDEO" if "video" in label else "IMAGE"


def map_stealads_ad(raw: dict[str, Any], *, bangers_rank: int | None = None) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for src_key, value in raw.items():
        if src_key in (
            "banger_rank_key",
            "effectiveness_score",
            "effectivenessScore",
            "_references",
            "_format_filter",
        ):
            continue
        norm = STEALADS_FIELD_MAP.get(src_key)
        if norm and norm not in mapped:
            mapped[norm] = value
    if bangers_rank is not None and mapped.get("bangers_rank") is None:
        mapped["bangers_rank"] = bangers_rank
    # Real search_ads/find_bangers rows carry still_running (not is_active), no format enum,
    # no Ad Library URL, start date, CTA or landing URL, and original_headline is often null.
    if mapped.get("is_active") is None and raw.get("still_running") is not None:
        mapped["is_active"] = bool(raw["still_running"])
    if mapped.get("is_active") is None:
        # Neither field (null both): an ad with an end date stopped, one without is read as live.
        mapped["is_active"] = not raw.get("end_date")
    mapped["format"] = unify_format(mapped.get("format")) or infer_format(raw)
    if mapped.get("headline") is None:
        mapped["headline"] = ""
    if mapped.get("body") is None:
        mapped["body"] = ""
    mapped.setdefault("ad_library_url", "")
    mapped.setdefault("landing_url", "")
    mapped.setdefault("cta", "")
    mapped.setdefault("start_date", raw.get("startDate") or raw.get("start_date") or "")
    mapped.setdefault("first_seen_at", "")
    mapped.setdefault("last_seen_at", "")
    mapped.setdefault("destination_url", mapped.get("landing_url", ""))
    mapped.setdefault("may_have_stopped", False)
    mapped.setdefault("hook_type", None)
    if not mapped.get("hook_type") and mapped.get("hook_type_filter"):
        mapped["hook_type"] = mapped["hook_type_filter"]
    # JSON rows carry the angle inside `filters`.
    if not mapped.get("angle") and isinstance(raw.get("filters"), dict):
        mapped["angle"] = raw["filters"].get("angle")
    mapped.setdefault("angle", None)
    mapped.setdefault("funnel_stage", None)
    apply_winning_signals(mapped, raw)
    # A StealAds row with no label field is unanalyzed there. It gets a label below only
    # when StealAds sent a real start date; otherwise it stays unlabeled.
    mapped.setdefault("label_source", "stealads")
    mapped.setdefault("strength_label", None)
    if mapped.get("days_live") is None:
        mapped["days_live"] = 0
    if mapped.get("variation_count") is None:
        mapped["variation_count"] = 0
    # Unanalyzed in StealAds but with a real start date (prod sends null when unknown):
    # apply the same published rule locally instead of showing no label.
    if (
        mapped.get("strength_label") is None
        and raw.get("start_date")
        and raw.get("run_duration_days") is not None
    ):
        from ad_spy_kit.labels import label_from_run

        computed = label_from_run(mapped)
        if computed:
            mapped["strength_label"] = computed
            mapped["label_source"] = "run_length"
    mapped["media"] = extract_media(raw)
    cards = card_urls(raw)
    if cards:
        mapped["card_image_urls"] = cards
    else:
        mapped.pop("card_image_urls", None)
    for key in ("platforms", "countries"):
        if not mapped.get(key):
            mapped.pop(key, None)
    mapped["landing_domain"] = landing_domain(mapped.get("landing_url"))
    if str(mapped.get("format")).upper() == "VIDEO":
        # A video row's image_url is its preview frame, not the creative itself.
        for m in mapped["media"]:
            if m.get("kind") == "image":
                m["kind"] = "video_preview"
    mapped["dedupe_key"] = mapped.get("group_id") or ""
    mapped["facebook_ad_id"] = facebook_ad_id(raw) or None
    apply_hook_fields(mapped, raw)
    # Catalog and dynamic ads store `{{product.name}}`: treat it as empty, never quote it.
    from ad_spy_kit.template_text import scrub_ad

    scrub_ad(mapped)
    missing = REQUIRED_NORMALIZED_KEYS - set(mapped.keys())
    if missing:
        raise KeyError(f"StealAds adapter missing required fields after map: {sorted(missing)}")
    return strip_hidden_scores(mapped)


def unwrap_recording(doc: dict[str, Any]) -> dict[str, Any]:
    """Recorded fixtures wrap the tool response as {request, response}; live saves don't."""
    if isinstance(doc.get("response"), dict) and "request" in doc:
        return doc["response"]
    return doc


def map_list_ads_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    payload = unwrap_recording(payload)
    ads = payload.get("ads") or payload.get("items") or []
    return [map_stealads_ad(a) for a in ads]


def _sc_date(value: Any) -> str:
    """ScrapeCreators sends epoch seconds; older rows send YYYY-MM-DD. Normalize to YYYY-MM-DD."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or str(value).isdigit():
        from datetime import UTC, datetime

        return datetime.fromtimestamp(int(value), UTC).strftime("%Y-%m-%d")
    return str(value)[:10]


def _sc_first(container: dict[str, Any], list_key: str, keys: tuple[str, ...]) -> str:
    items = container.get(list_key) if isinstance(container.get(list_key), list) else []
    for item in items:
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    return str(item[key])
    return ""


def _sc_direct(container: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if isinstance(container.get(key), str) and container[key].startswith("http"):
            return container[key]
    return ""


def _sc_all(container: dict[str, Any], list_key: str, keys: tuple[str, ...]) -> list[str]:
    """Every URL under these keys, in key order (the first key is the preferred one)."""
    items = container.get(list_key) if isinstance(container.get(list_key), list) else []
    found = [str(item[k]) for k in keys for item in items if isinstance(item, dict) and item.get(k)]
    found += [
        container[k]
        for k in keys
        if isinstance(container.get(k), str) and container[k].startswith("http")
    ]
    return found


def sc_media(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Image first, then video preview. Same lookup order as CIE live_capture._creative_url,
    except the original image comes before the resized one (the larger file wins).

    Carousel and catalog (DPA) ads keep the picture on each card itself
    (cards[].resized_image_url), not under an images list, so both shapes are read. Every
    other usable URL rides along as `fallback_urls`: a video's preview frame can come back
    110px wide, and the caching step swaps in a bigger one when it can.
    """
    cards = [c for c in (snapshot.get("cards") or []) if isinstance(c, dict)]
    containers = cards + [snapshot]
    image_keys = ("original_image_url", "resized_image_url", "watermarked_resized_image_url")
    preview_keys = ("video_preview_image_url", "thumbnail_url")
    # Dynamic (DCO) ads can keep their pictures under extra_images.
    containers += [{"images": snapshot.get("extra_images") or []}]
    video_containers = containers + [{"videos": snapshot.get("extra_videos") or []}]
    images = [
        u
        for c in containers
        for u in (_sc_all(c, "images", image_keys) + _sc_all(c, "", image_keys))
    ]
    previews = [
        u
        for c in video_containers
        for u in (_sc_all(c, "videos", preview_keys) + _sc_all(c, "", preview_keys))
    ]
    if images:
        kind, ordered = "image", images + previews
    elif previews:
        kind, ordered = "video_preview", previews
    else:
        return []
    unique = list(dict.fromkeys(ordered))
    media: dict[str, Any] = {"url": unique[0], "durable": False, "kind": kind}
    if len(unique) > 1:
        media["fallback_urls"] = unique[1:5]
    return [media]


def sc_video_url(snapshot: dict[str, Any]) -> str:
    """The playable file (SD first: smaller to send). fbcdn links expire within hours."""
    containers = [c for c in (snapshot.get("cards") or []) if isinstance(c, dict)] + [snapshot]
    for c in containers + [{"videos": snapshot.get("extra_videos") or []}]:
        url = _sc_first(c, "videos", ("video_sd_url", "video_hd_url"))
        if url:
            return url
    return ""


def map_scrapecreators_ad(raw: dict[str, Any]) -> dict[str, Any]:
    """Port of the WCT/CIE extract path onto the same ads.raw.json contract as StealAds rows.

    Real ScrapeCreators rows nest creative under `snapshot` (body.text, title, cta_text,
    link_url, images/videos/cards). Flat rows are still accepted for older recordings.
    """
    snap = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else {}
    body = snap.get("body") if isinstance(snap.get("body"), dict) else {}
    card = next((c for c in snap.get("cards") or [] if isinstance(c, dict)), {})
    ad_id = str(raw.get("ad_archive_id") or raw.get("id") or raw.get("ad_id") or "")
    start = _sc_date(raw.get("start_date") or raw.get("startDate"))
    fmt = snap.get("display_format") or raw.get("display_format") or raw.get("format") or "IMAGE"
    mapped = map_stealads_ad(
        {
            "id": ad_id,
            "ad_library_url": raw.get("url")
            or raw.get("ad_library_url")
            or f"https://www.facebook.com/ads/library/?id={ad_id}",
            "start_date": start,
            "end_date": _sc_date(raw.get("end_date")),
            "variation_count": max(
                1, int(raw.get("collation_count") or raw.get("variation_count") or 1)
            ),
            "is_active": bool(raw.get("is_active", True)),
            "format": str(fmt).upper(),
            "headline": snap.get("title") or card.get("title") or raw.get("headline") or "",
            "body": body.get("text") or card.get("body") or raw.get("body") or "",
            "cta": snap.get("cta_text") or card.get("cta_text") or raw.get("cta") or "",
            "landing_url": snap.get("link_url")
            or card.get("link_url")
            or raw.get("link_url")
            or "",
            "media": sc_media(snap) if snap else (raw.get("media") or []),
            "group_id": str(raw["collation_id"]) if raw.get("collation_id") else None,
            "why": None,
            "run_duration_days": None,
            "facebook_ad_id": ad_id,
            # Present when the ad came from Ad Details with get_transcript=true.
            "transcript": raw.get("transcript") or snap.get("transcript") or None,
        },
        bangers_rank=None,
    )
    mapped["page_name"] = snap.get("page_name") or raw.get("page_name") or ""
    mapped["bangers_rank"] = None
    # Only the opt-in OpenRouter transcript path reads this; it is never rendered.
    if snap and mapped.get("format") == "VIDEO" and sc_video_url(snap):
        mapped["video_url"] = sc_video_url(snap)
    if start:
        from datetime import date

        # Fallback-only rule (spec §5): days_live = days since start_date, up to end_date
        # for ads that stopped. StealAds rows carry their own refreshed value.
        def _d(text: str) -> date:
            y, m, d = (int(x) for x in text.split("-")[:3])
            return date(y, m, d)

        end_text = mapped.get("end_date") or ""
        end = _d(end_text) if end_text and not mapped.get("is_active") else date.today()
        mapped["days_live"] = max(0, (end - _d(start)).days)
    else:
        mapped["run_length_unknown"] = True
    # ScrapeCreators sends no label: compute it with the shared rule (ad_spy_kit/labels.py).
    from ad_spy_kit.labels import strength_label

    mapped["label_source"] = "run_length"
    mapped.pop("strength_label", None)
    mapped["strength_label"] = strength_label(mapped)
    return mapped
