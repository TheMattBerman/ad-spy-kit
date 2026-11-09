import json
import os
import re
import shutil
import time
from datetime import datetime, timezone

from .actor_vision import vision_read_actor
from . import patterns
from . import ocr
from .asset_downloader import AssetDownloader, asset_summary
from .classification_cache import ClassificationCache
from .competitor_resolver import resolve_company_page
from .creator_baseline import annotate_overperformance
from .classifier import (
    ClassificationError,
    _insufficient_visual_result,
    classify_creative,
    classify_format,
    classify_mechanics,
    classify_message_frame,
)
from .diagnostic_capture import validate_diagnostic_capture
from .media_evidence import MediaEvidenceError, build_evidence_manifest
from .patterns import pattern_key
from .relevance import DEFAULT_RELEVANCE_THRESHOLD, apply_relevance
from .scrapecreators_client import ScrapeCreatorsClient, ScrapeCreatorsClientError
from .transcript import parse_vtt_opening
from .virlo_client import VirloClient, VirloClientError, _load_dotenv_if_needed


class LiveCaptureError(Exception):
    pass


def preflight_live_run(dcfg):
    """Fail before a live run spends any provider credits if a dependency is missing.

    Checks the Virlo + ScrapeCreators keys and the configured visual-analysis route. For a
    BYOK tier (openrouter/api_key) the route's API key must be present. For the local
    subscription route the agent verifies its own auth at call time, so we only confirm it is
    configured. Returns a small dict describing the resolved visual route.
    """
    for name in ("VIRLO_API_KEY", "SCRAPECREATORS_API_KEY"):
        _load_dotenv_if_needed(name)
    missing = [name for name in ("VIRLO_API_KEY", "SCRAPECREATORS_API_KEY") if not os.environ.get(name)]
    if missing:
        raise LiveCaptureError(
            "Live report not started. Set " + ", ".join(missing) + " before any provider pull, then rerun this command."
        )
    llm = getattr(dcfg, "llm", None)
    if not llm:
        raise LiveCaptureError("Live report not started. Configure a visual-analysis route before any provider pull.")
    if llm.tier == "subscription":
        return {"visual_route": "subscription", "model": "local subscription"}
    _load_dotenv_if_needed(llm.api_key_env)
    if not os.environ.get(llm.api_key_env):
        raise LiveCaptureError(
            f"Live report not started. {llm.api_key_env} is required for the configured {llm.tier} visual route. "
            "Set it before any provider pull, then rerun this command."
        )
    return {"visual_route": llm.tier, "model": llm.model}


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "diagnostic-run"


def run_virlo_smoke(client=None):
    client = client or VirloClient()
    orbits = client.list_orbits(limit=1)
    comets = client.list_comets(limit=1)
    return {
        "orbits_seen": len(orbits),
        "comets_seen": len(comets),
        "first_orbit": (orbits[0].get("name") if orbits else ""),
        "first_comet": (comets[0].get("name") if comets else ""),
        "calls": client.calls,
    }


def plan_virlo_surface(dcfg, orbit_id=None, comet_id=None, client=None, time_period="this_month", min_views=0):
    client = client or VirloClient()
    selected = _select_surface(client, dcfg, orbit_id=orbit_id, comet_id=comet_id)
    keywords = _keywords_for_config(dcfg)
    plan = {
        "selected_surface": selected,
        "keywords": keywords,
        "create_orbit_payload": {
            "name": f"wct-{slugify(dcfg.niche)}",
            "keywords": keywords,
            "time_period": time_period,
            "min_views": min_views,
            "platforms": ["instagram", "tiktok"],
        },
        "calls": client.calls,
    }
    if selected:
        plan["status"] = "existing_surface_found"
        plan["next_step"] = "Run live-report normally, or pin this surface with --virlo-comet-id/--virlo-orbit-id."
    else:
        plan["status"] = "no_existing_surface"
        plan["next_step"] = "Approve spend, then rerun with --create-orbit --confirm-paid-create."
    return plan


def plan_virlo_two_ring(
    dcfg,
    *,
    buyer_query="",
    interest_query="",
    buyer_orbit_id=None,
    buyer_comet_id=None,
    interest_orbit_id=None,
    interest_comet_id=None,
    client=None,
    time_period="this_month",
    min_views=0,
):
    buyer_query = _ring_query(dcfg, buyer_query, "buyer")
    interest_query = _ring_query(dcfg, interest_query, "interest")
    rings = {
        "buyer": _plan_ring(
            "buyer",
            buyer_query,
            orbit_id=buyer_orbit_id,
            comet_id=buyer_comet_id,
            time_period=time_period,
            min_views=min_views,
        ),
        "interest": _plan_ring(
            "interest",
            interest_query,
            orbit_id=interest_orbit_id,
            comet_id=interest_comet_id,
            time_period=time_period,
            min_views=min_views,
        ),
    }
    return {
        "virlo_model": "two_ring",
        "rings": rings,
        "status": "guided_two_ring_plan",
        "next_step": (
            "Pin existing ring surfaces or rerun with --create-buyer-orbit/--create-interest-orbit "
            "and --confirm-paid-create. Guided mode never creates Virlo surfaces."
        ),
        "calls": client.calls if client else [],
    }


def build_virlo_capture(
    dcfg,
    out_dir,
    config_path,
    *,
    orbit_id=None,
    comet_id=None,
    max_videos=12,
    create_orbit=False,
    time_period="this_month",
    min_views=0,
    max_paid_competitors=None,
    max_ads_per_competitor=5,
    skip_paid=False,
    client=None,
    scrape_client=None,
    asset_downloader=None,
    confirm_paid_create=False,
    two_ring=False,
    buyer_query="",
    interest_query="",
    buyer_orbit_id=None,
    buyer_comet_id=None,
    interest_orbit_id=None,
    interest_comet_id=None,
    create_buyer_orbit=False,
    create_interest_orbit=False,
    classifier=None,
):
    client = client or VirloClient()
    scrape_client = scrape_client or ScrapeCreatorsClient()
    os.makedirs(os.path.join(out_dir, "raw"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)

    if two_ring:
        return _build_virlo_two_ring_capture(
            dcfg,
            out_dir,
            config_path,
            client=client,
            scrape_client=scrape_client,
            asset_downloader=asset_downloader,
            max_videos=max_videos,
            max_paid_competitors=max_paid_competitors,
            max_ads_per_competitor=max_ads_per_competitor,
            skip_paid=skip_paid,
            time_period=time_period,
            min_views=min_views,
            buyer_query=buyer_query,
            interest_query=interest_query,
            buyer_orbit_id=buyer_orbit_id,
            buyer_comet_id=buyer_comet_id,
            interest_orbit_id=interest_orbit_id,
            interest_comet_id=interest_comet_id,
            create_buyer_orbit=create_buyer_orbit,
            create_interest_orbit=create_interest_orbit,
            confirm_paid_create=confirm_paid_create,
            classifier=classifier,
        )

    selected = _select_surface(client, dcfg, orbit_id=orbit_id, comet_id=comet_id)
    if not selected and create_orbit:
        if not confirm_paid_create:
            raise LiveCaptureError(
                "No matching Virlo Orbit or Comet found. Creating a new Virlo Orbit may spend provider budget; "
                "rerun with --create-orbit --confirm-paid-create after approving the paid Orbit."
            )
        keywords = _keywords_for_config(dcfg)
        new_orbit_id, data = client.create_orbit(
            f"wct-{slugify(dcfg.niche)}",
            keywords,
            time_period=time_period,
            min_views=min_views,
        )
        selected = {"kind": "orbit", "id": new_orbit_id, "name": data.get("name", f"wct-{dcfg.niche}"), "created": True}

    if not selected:
        raise LiveCaptureError(
            "No matching Virlo Orbit or Comet found. Run `python -m cie live-report --guided ...` to inspect "
            "existing Virlo surfaces and get the explicit create-Orbit command."
        )

    videos, outliers = _fetch_surface(client, selected, max_videos=max_videos)
    if not videos:
        raise LiveCaptureError(f"Virlo {selected['kind']} {selected['id']} returned no videos")

    downloader = asset_downloader or AssetDownloader(out_dir)
    ring_query = dcfg.niche
    raw_organic = [
        _with_provenance(_organic_record(v, dcfg), selected, "interest", ring_query, "gap_input")
        for v in videos[:max_videos]
    ]
    organic, organic_drops = apply_relevance(raw_organic, dcfg.niche, dcfg.competitors)
    _download_organic_assets(organic, downloader, scrape_client)
    actor_batch, actor_drops = _actor_records(videos, outliers, dcfg, downloader, max_items=min(8, max_videos))
    _tag_records(actor_batch, selected, "interest", ring_query, "context_only")
    competitors = _competitor_records(dcfg, selected, videos)
    paid_pull_meta = {}
    raw_paid, paid_skips, competitor_resolution = _paid_records(
        scrape_client,
        competitors,
        dcfg,
        max_paid_competitors=max_paid_competitors,
        max_ads_per_competitor=max_ads_per_competitor,
        skip_paid=skip_paid,
        paid_pull_meta=paid_pull_meta,
    )
    paid, paid_drops = apply_relevance(raw_paid, dcfg.niche, dcfg.competitors, paid=True)
    _download_paid_assets(paid, downloader)
    own_brand_paid, own_brand_skips = _own_brand_paid_records(
        scrape_client, dcfg, max_ads_per_competitor=max_ads_per_competitor
    )
    _download_paid_assets(own_brand_paid, downloader)
    _apply_paid_counts(competitors, paid)
    media_manifest, classification_info = _classify_capture_records(
        out_dir, dcfg, (("organic", organic), ("paid", paid), ("paid", own_brand_paid)), classifier=classifier
    )
    own_brand_pattern_keys = {key for record in own_brand_paid if (key := pattern_key(record)) is not None}
    _annotate_organic_overperformance(organic, scrape_client)
    clustered_patterns = patterns.cluster_patterns(paid, organic)
    # Only compute the "absent from your paid" delta when own_brand is set AND we actually got
    # its ads. An empty set from a failed/empty own-brand pull would falsely mark every proven
    # pattern absent-from-own; pass None to omit the delta instead.
    proven_patterns = patterns.rank_proven(
        clustered_patterns,
        own_brand_pattern_keys if (getattr(dcfg, "own_brand", "") and own_brand_paid) else None,
    )
    proven_angles = {pattern["angle"] for pattern in proven_patterns}
    emerging_patterns = patterns.rank_emerging(clustered_patterns, proven_angles)
    _attach_emerging_scores(clustered_patterns, emerging_patterns, proven_angles)
    narrative = _narrative(dcfg, selected, organic, paid, actor_batch, paid_skips)
    all_calls = client.calls + ((scrape_client.calls if scrape_client else []))
    run_meta = _run_meta(
        selected,
        organic,
        paid,
        actor_batch,
        competitors,
        all_calls,
        paid_skips + own_brand_skips,
        asset_events=downloader.events,
        relevance_drops={"organic": organic_drops, "paid": paid_drops, "actors": actor_drops},
        llm_tier=(dcfg.llm.tier if dcfg.llm else "subscription"),
        media_manifest=media_manifest,
        classification_info=classification_info,
        paid_dco_video_unavailable=paid_pull_meta.get("paid_dco_video_unavailable", 0),
        own_brand_pattern_keys=own_brand_pattern_keys,
        pattern_summary=_pattern_summary(proven_patterns, emerging_patterns, clustered_patterns.excluded_count),
        competitor_resolution=competitor_resolution,
    )

    _write_json(out_dir, "organic", organic)
    _write_json(out_dir, "paid", paid)
    _write_json(out_dir, "actor_batch", actor_batch)
    _write_json(out_dir, "competitors", competitors)
    _write_json(out_dir, "narrative", narrative)
    _write_json(out_dir, "media-manifest", media_manifest)
    _write_json(out_dir, "patterns", clustered_patterns)
    _write_json(out_dir, "run_meta", run_meta)
    _copy_config(config_path, out_dir)

    errors = validate_diagnostic_capture(out_dir)
    if errors:
        raise LiveCaptureError("Virlo capture did not validate:\n" + "\n".join(f"- {e}" for e in errors))

    return {
        "selected": selected,
        "organic_count": len(organic),
        "paid_count": len(paid),
        "actor_count": len(actor_batch),
        "competitor_count": len(competitors),
        "competitor_resolution": competitor_resolution,
        "out_dir": out_dir,
    }


def _build_virlo_two_ring_capture(
    dcfg,
    out_dir,
    config_path,
    *,
    client,
    scrape_client,
    asset_downloader,
    max_videos,
    max_paid_competitors,
    max_ads_per_competitor,
    skip_paid,
    time_period,
    min_views,
    buyer_query,
    interest_query,
    buyer_orbit_id,
    buyer_comet_id,
    interest_orbit_id,
    interest_comet_id,
    create_buyer_orbit,
    create_interest_orbit,
    confirm_paid_create,
    classifier,
):
    if (create_buyer_orbit or create_interest_orbit) and not confirm_paid_create:
        raise LiveCaptureError(
            "Two-ring Virlo Orbit creation may spend provider budget; rerun with --confirm-paid-create "
            "after approving the run-created Orbit(s)."
        )

    buyer_query = _ring_query(dcfg, buyer_query, "buyer")
    interest_query = _ring_query(dcfg, interest_query, "interest")
    buyer_selected = _acquire_ring_surface(
        client,
        "buyer",
        buyer_query,
        orbit_id=buyer_orbit_id,
        comet_id=buyer_comet_id,
        create_orbit=create_buyer_orbit,
        time_period=time_period,
        min_views=min_views,
    )
    interest_selected = _acquire_ring_surface(
        client,
        "interest",
        interest_query,
        orbit_id=interest_orbit_id,
        comet_id=interest_comet_id,
        create_orbit=create_interest_orbit,
        time_period=time_period,
        min_views=min_views,
    )

    buyer_videos, buyer_outliers = _fetch_surface(client, buyer_selected, max_videos=max_videos)
    interest_videos, interest_outliers = _fetch_surface(client, interest_selected, max_videos=max_videos)
    if not interest_videos:
        raise LiveCaptureError(f"Virlo interest {interest_selected['kind']} {interest_selected['id']} returned no videos")

    downloader = asset_downloader or AssetDownloader(out_dir)
    raw_organic = [
        _with_provenance(_organic_record(v, dcfg), interest_selected, "interest", interest_query, "gap_input")
        for v in interest_videos[:max_videos]
    ]
    organic, organic_drops = apply_relevance(raw_organic, interest_query, dcfg.competitors)
    _download_organic_assets(organic, downloader, scrape_client)

    raw_buyer_context = [
        _with_provenance(_organic_record(v, dcfg), buyer_selected, "buyer", buyer_query, "context_only")
        for v in buyer_videos[:max_videos]
    ]
    buyer_context, buyer_context_drops = apply_relevance(raw_buyer_context, buyer_query, [])
    _download_context_assets(buyer_context, downloader)

    actor_batch, actor_drops = _actor_records(
        interest_videos,
        interest_outliers,
        dcfg,
        downloader,
        max_items=min(8, max_videos),
    )
    _tag_records(actor_batch, interest_selected, "interest", interest_query, "context_only")
    competitors = _configured_competitor_records(dcfg)
    paid_pull_meta = {}
    raw_paid, paid_skips, competitor_resolution = _paid_records(
        scrape_client,
        competitors,
        dcfg,
        max_paid_competitors=max_paid_competitors,
        max_ads_per_competitor=max_ads_per_competitor,
        skip_paid=skip_paid,
        paid_pull_meta=paid_pull_meta,
    )
    paid, paid_drops = apply_relevance(raw_paid, buyer_query, dcfg.competitors, paid=True)
    _download_paid_assets(paid, downloader)
    own_brand_paid, own_brand_skips = _own_brand_paid_records(
        scrape_client, dcfg, max_ads_per_competitor=max_ads_per_competitor
    )
    _download_paid_assets(own_brand_paid, downloader)
    _apply_paid_counts(competitors, paid)
    media_manifest, classification_info = _classify_capture_records(
        out_dir,
        dcfg,
        (("organic", organic), ("buyer_context", buyer_context), ("paid", paid), ("paid", own_brand_paid)),
        classifier=classifier,
    )
    own_brand_pattern_keys = {key for record in own_brand_paid if (key := pattern_key(record)) is not None}
    _annotate_organic_overperformance(organic, scrape_client)
    clustered_patterns = patterns.cluster_patterns(paid, organic)
    # Only compute the "absent from your paid" delta when own_brand is set AND we actually got
    # its ads. An empty set from a failed/empty own-brand pull would falsely mark every proven
    # pattern absent-from-own; pass None to omit the delta instead.
    proven_patterns = patterns.rank_proven(
        clustered_patterns,
        own_brand_pattern_keys if (getattr(dcfg, "own_brand", "") and own_brand_paid) else None,
    )
    proven_angles = {pattern["angle"] for pattern in proven_patterns}
    emerging_patterns = patterns.rank_emerging(clustered_patterns, proven_angles)
    _attach_emerging_scores(clustered_patterns, emerging_patterns, proven_angles)
    narrative = _two_ring_narrative(
        dcfg, buyer_query, interest_query, buyer_selected, interest_selected, organic, paid, buyer_context, actor_batch, paid_skips + own_brand_skips
    )
    all_calls = client.calls + ((scrape_client.calls if scrape_client else []))
    run_meta = _run_meta(
        interest_selected,
        organic,
        paid,
        actor_batch,
        competitors,
        all_calls,
        paid_skips + own_brand_skips,
        asset_events=downloader.events,
        relevance_drops={
            "organic": organic_drops,
            "paid": paid_drops,
            "actors": actor_drops,
            "buyer_context": buyer_context_drops,
        },
        llm_tier=(dcfg.llm.tier if dcfg.llm else "subscription"),
        virlo_model="two_ring",
        rings={
            "buyer": _ring_meta(buyer_selected, buyer_query, len(buyer_context), "raw/buyer_context.json"),
            "interest": _ring_meta(interest_selected, interest_query, len(organic), "raw/organic.json"),
        },
        buyer_context=buyer_context,
        media_manifest=media_manifest,
        classification_info=classification_info,
        paid_dco_video_unavailable=paid_pull_meta.get("paid_dco_video_unavailable", 0),
        own_brand_pattern_keys=own_brand_pattern_keys,
        pattern_summary=_pattern_summary(proven_patterns, emerging_patterns, clustered_patterns.excluded_count),
        competitor_resolution=competitor_resolution,
    )

    _write_json(out_dir, "organic", organic)
    _write_json(out_dir, "buyer_context", buyer_context)
    _write_json(out_dir, "paid", paid)
    _write_json(out_dir, "actor_batch", actor_batch)
    _write_json(out_dir, "competitors", competitors)
    _write_json(out_dir, "narrative", narrative)
    _write_json(out_dir, "media-manifest", media_manifest)
    _write_json(out_dir, "patterns", clustered_patterns)
    _write_json(out_dir, "run_meta", run_meta)
    _copy_config(config_path, out_dir)

    errors = validate_diagnostic_capture(out_dir)
    if errors:
        raise LiveCaptureError("Virlo capture did not validate:\n" + "\n".join(f"- {e}" for e in errors))

    return {
        "selected": interest_selected,
        "organic_count": len(organic),
        "paid_count": len(paid),
        "actor_count": len(actor_batch),
        "buyer_context_count": len(buyer_context),
        "competitor_count": len(competitors),
        "out_dir": out_dir,
    }


def _ring_query(dcfg, override, role):
    value = (override or "").strip()
    if value:
        return value
    configured = getattr(dcfg, f"{role}_query", "")
    if configured:
        return configured
    return dcfg.niche


def _plan_ring(role, query, *, orbit_id, comet_id, time_period, min_views):
    selected = _pinned_surface(role, orbit_id=orbit_id, comet_id=comet_id)
    payload = _orbit_payload(role, query, time_period=time_period, min_views=min_views)
    status = "pinned_surface" if selected else "needs_pinned_surface_or_create_flag"
    return {
        "role": role,
        "query": query,
        "selected_surface": selected,
        "create_orbit_payload": payload,
        "status": status,
    }


def _acquire_ring_surface(client, role, query, *, orbit_id, comet_id, create_orbit, time_period, min_views):
    selected = _pinned_surface(role, orbit_id=orbit_id, comet_id=comet_id)
    if selected:
        return selected
    if not create_orbit:
        raise LiveCaptureError(
            f"Two-ring {role} ring has no pinned Virlo surface. Pin --{role}-virlo-orbit-id/"
            f"--{role}-virlo-comet-id or approve a run-created Orbit with --create-{role}-orbit "
            "and --confirm-paid-create."
        )
    payload = _orbit_payload(role, query, time_period=time_period, min_views=min_views)
    new_orbit_id, data = client.create_orbit(
        payload["name"],
        payload["keywords"],
        platforms=payload["platforms"],
        time_period=time_period,
        min_views=min_views,
    )
    return {
        "kind": "orbit",
        "id": new_orbit_id,
        "name": data.get("name", payload["name"]),
        "created": True,
        "source_created": True,
        "created_for_run": True,
        "created_at": _utc_timestamp(),
        "ring_role": role,
        "config": payload,
    }


def _pinned_surface(role, *, orbit_id=None, comet_id=None):
    if orbit_id:
        return {
            "kind": "orbit",
            "id": orbit_id,
            "name": orbit_id,
            "created": False,
            "source_created": False,
            "created_for_run": False,
            "ring_role": role,
        }
    if comet_id:
        return {
            "kind": "comet",
            "id": comet_id,
            "name": comet_id,
            "created": False,
            "source_created": False,
            "created_for_run": False,
            "ring_role": role,
        }
    return None


def _orbit_payload(role, query, *, time_period, min_views):
    return {
        "name": f"wct-{role}-{slugify(query)}",
        "keywords": _keywords_for_query(query),
        "time_period": time_period,
        "min_views": min_views,
        "platforms": ["instagram", "tiktok"],
        "ring_role": role,
    }


def _select_surface(client, dcfg, orbit_id=None, comet_id=None):
    if orbit_id:
        return {"kind": "orbit", "id": orbit_id, "name": orbit_id, "created": False}
    if comet_id:
        return {"kind": "comet", "id": comet_id, "name": comet_id, "created": False}

    query = " ".join([dcfg.niche] + list(dcfg.competitors or []))
    comets = client.list_comets(limit=100)
    orbits = client.list_orbits(limit=100)
    candidates = []
    for item in comets:
        score = _surface_score(item, query)
        if score:
            candidates.append((score + 2, "comet", item))
    for item in orbits:
        score = _surface_score(item, query)
        if score:
            candidates.append((score, "orbit", item))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    _, kind, item = candidates[0]
    return {
        "kind": kind,
        "id": item.get("id") or item.get("orbit_id") or item.get("comet_id"),
        "name": item.get("name", ""),
        "created": False,
    }


def _fetch_surface(client, selected, max_videos):
    if selected["kind"] == "comet":
        videos = _paged_surface_videos(client.comet_videos, selected["id"], max_videos)
        outliers, _ = client.comet_outliers(selected["id"], limit=8)
        if not videos:
            videos = _videos_from_outliers(outliers, max_videos)
        return videos, outliers
    videos = _paged_surface_videos(client.orbit_videos, selected["id"], max_videos)
    outliers, _ = client.orbit_outliers(selected["id"], limit=8)
    if not videos:
        videos = _videos_from_outliers(outliers, max_videos)
    return videos, outliers


def _paged_surface_videos(fetch_page, surface_id, max_videos):
    """Fetch a large Virlo sample without exceeding its 100-video page limit."""
    remaining = max(0, int(max_videos))
    videos = []
    page = 1
    while remaining:
        page_size = min(100, remaining)
        page_videos, _ = fetch_page(surface_id, limit=page_size, page=page)
        videos.extend(page_videos)
        if len(page_videos) < page_size:
            break
        remaining = max_videos - len(videos)
        page += 1
    return videos[:max_videos]


def _surface_score(item, query):
    hay = " ".join(
        [
            str(item.get("name") or ""),
            " ".join(str(k) for k in item.get("keywords") or []),
        ]
    ).lower()
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    return sum(1 for w in words if w in hay)


def _keywords_for_config(dcfg):
    raw = [dcfg.niche] + list(dcfg.competitors or [])
    words = []
    for item in raw:
        item = str(item).strip()
        if item:
            words.append(item)
    return words[:10] or [dcfg.niche]


def _keywords_for_query(query):
    words = []
    for item in re.split(r"[,;\n]", str(query or "")):
        item = item.strip()
        if item:
            words.append(item)
    return words[:10] or [str(query or "").strip()]


def _utc_timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _videos_from_outliers(outliers, max_videos):
    videos = []
    for outlier in outliers:
        for video in outlier.get("videos") or []:
            copy = dict(video)
            copy.setdefault("platform", outlier.get("platform"))
            copy.setdefault("author", {"username": _handle_from_url(outlier.get("creator_url")), "followers": outlier.get("follower_count", 0)})
            videos.append(copy)
            if len(videos) >= max_videos:
                return videos
    return videos


def _organic_record(video, dcfg=None):
    author = video.get("author") or {}
    handle = author.get("username") or author.get("handle") or _handle_from_url(video.get("url")) or "unknown"
    views = _int(video.get("views") or video.get("view_count"))
    followers = _int(author.get("followers") or video.get("follower_count"))
    record = {
        "views": views,
        "follower_count": followers,
        "post_url": str(video.get("url") or ""),
        "creator_handle": _at(handle),
        "thumbnail_url": str(video.get("thumbnail_url") or ""),
        "hook_text": _text(video),
        "saves": _int(video.get("bookmarks")),
        "shares": _int(video.get("shares")),
        "comments": _int(video.get("comments")),
        "likes": _int(video.get("likes")),
        "publish_ts": _parse_ts(video.get("publish_date")),
    }
    return record


def _download_organic_assets(organic, downloader, scrape_client=None):
    for i, record in enumerate(organic, start=1):
        _attach_opening_line(record, scrape_client)
        local = downloader.download(record.get("thumbnail_url"), f"organic-{i}")
        if local:
            record["thumbnail_local_path"] = local
        # Prefer a ScrapeCreators-resolved direct video URL (robust for TikTok AND Instagram)
        # over handing the platform permalink to yt-dlp, which needs a login for Instagram.
        video_url = record.get("post_url")
        resolver = getattr(scrape_client, "post_video_url", None)
        if callable(resolver):
            resolved = resolver(record.get("post_url"))
            if resolved:
                record["organic_video_url"] = resolved
                video_url = resolved
        _attach_full_motion_evidence(record, downloader, f"organic-{i}", video_url)
        capture_opening = getattr(downloader, "download_opening_frames", None)
        record["opening_frame_local_paths"] = (
            capture_opening(video_url, f"organic-{i}") if callable(capture_opening) and video_url else []
        )


def _attach_opening_line(record, scrape_client):
    record["opening_line"] = ""
    post_url = str(record.get("post_url") or "")
    try:
        if "tiktok.com" in post_url:
            transcript = scrape_client.tiktok_transcript(post_url) if scrape_client else ""
        elif "instagram.com" in post_url:
            transcript = scrape_client.instagram_transcript(post_url) if scrape_client else ""
        else:
            transcript = ""
        record["opening_line"] = parse_vtt_opening(transcript)
    except Exception:
        pass


def _download_context_assets(records, downloader):
    for i, record in enumerate(records, start=1):
        local = downloader.download(record.get("thumbnail_url"), f"buyer-context-{i}")
        if local:
            record["thumbnail_local_path"] = local
        _attach_full_motion_evidence(record, downloader, f"buyer-context-{i}", record.get("post_url"))


def _download_paid_assets(paid, downloader):
    for i, record in enumerate(paid, start=1):
        local = downloader.download(record.get("creative_url"), f"paid-{i}")
        if local:
            record["creative_local_path"] = local
        if str(record.get("display_format") or "").upper() != "VIDEO":
            record["static_ocr_text"] = ""
            if local:
                # extract_image_text already collapses whitespace; the run dir makes the path
                # absolute (download() returns a run-dir-relative path).
                try:
                    record["static_ocr_text"] = ocr.extract_image_text(
                        _absolute_asset_path(getattr(downloader, "run_dir", ""), local)
                    )[:2000]
                except Exception:
                    record["static_ocr_text"] = ""
        _attach_full_motion_evidence(record, downloader, f"paid-{i}", record.get("creative_video_url"))
        # A DCO/VIDEO still-only record with a downloaded image card is a readable static ad: keep
        # it scoreable so its on-creative hook and format can be read (its headline IS the hook).
        # Only quarantine as an "unwatched" video when there is genuinely no image card to read;
        # a record with a real video URL we couldn't fetch is already marked "unwatched" upstream.
        if (
            record.get("visual_evidence_scope") == "still-only"
            and record.get("display_format") in ("DCO", "VIDEO")
            and not record.get("creative_local_path")
        ):
            record["visual_evidence_scope"] = "unwatched"


def _attach_full_motion_evidence(record, downloader, prefix, source_url):
    capture = getattr(downloader, "download_video_frames", None)
    had_video_url = bool(source_url)
    frames = capture(source_url, prefix) if callable(capture) and had_video_url else []
    if frames:
        record["frame_local_paths"] = frames
        record["visual_evidence_scope"] = "full-motion"
    else:
        record["frame_local_paths"] = []
        record["visual_evidence_scope"] = "unwatched" if had_video_url else "still-only"


def _actor_records(videos, outliers, dcfg, downloader, max_items):
    rows = []
    drops = []
    seen = set()
    for outlier in outliers:
        handle = _handle_from_url(outlier.get("creator_url")) or outlier.get("username") or outlier.get("handle")
        if handle and handle not in seen:
            seen.add(handle)
            row = _actor_record(
                handle,
                outlier.get("creator_url", ""),
                outlier.get("creator_avatar_url", ""),
                outlier.get("follower_count", 0),
                outlier.get("creator_topics") or [],
                dcfg,
                downloader,
            )
            if row:
                rows.append(row)
            else:
                drops.append({"creator_handle": _at(handle), "drop_reason": "No avatar or thumbnail available for actor read."})
        if len(rows) >= max_items:
            return rows, drops

    for video in videos:
        author = video.get("author") or {}
        handle = author.get("username") or _handle_from_url(video.get("url")) or "unknown"
        if handle in seen:
            continue
        seen.add(handle)
        row = _actor_record(
            handle,
            _profile_url(video.get("platform") or video.get("type"), handle),
            author.get("avatar_url", ""),
            author.get("followers", 0),
            video.get("hashtags") or [],
            dcfg,
            downloader,
            thumbnail_url=video.get("thumbnail_url", ""),
        )
        if row:
            rows.append(row)
        else:
            drops.append({"creator_handle": _at(handle), "drop_reason": "No avatar or thumbnail available for actor read."})
        if len(rows) >= max_items:
            return rows, drops
    return rows, drops


def _actor_record(handle, profile_url, avatar_url, follower_count, signals, dcfg, downloader, thumbnail_url=""):
    avatar_local_path = downloader.download(avatar_url, f"avatar-{handle}") if avatar_url else ""
    top_thumbnail_local_path = downloader.download(thumbnail_url, f"actor-thumb-{handle}") if thumbnail_url else ""
    if not avatar_local_path and not top_thumbnail_local_path:
        return None
    avatar_abs_path = os.path.join(downloader.run_dir, avatar_local_path) if avatar_local_path else ""
    top_thumbnail_abs_path = os.path.join(downloader.run_dir, top_thumbnail_local_path) if top_thumbnail_local_path else ""
    read = vision_read_actor(
        {
            "creator_name": str(handle or "").lstrip("@"),
            "signals": [str(s) for s in signals[:8] if str(s).strip()],
            "thumbnail_url": thumbnail_url,
            "avatar_abs_path": avatar_abs_path,
            "top_thumbnail_abs_path": top_thumbnail_abs_path,
        },
        dcfg,
    )
    return {
        **read,
        "creator_name": str(handle or "").lstrip("@"),
        "creator_handle": _at(handle),
        "profile_url": str(profile_url or ""),
        "avatar_url": str(avatar_url or ""),
        "top_thumbnail_url": str(thumbnail_url or ""),
        "avatar_local_path": avatar_local_path,
        "top_thumbnail_local_path": top_thumbnail_local_path,
        "why_included": "Pulled from Virlo creator/video discovery and retained because a local image asset was available.",
        "follower_count": _int(follower_count),
    }


def _competitor_records(dcfg, selected, videos):
    rows = []
    for name in dcfg.competitors:
        rows.append(
            {
                "name": name,
                "handles": [],
                "seed_or_discovered": "seed",
                "discovery_reason": "Named in diagnostic config",
                "ads_sampled_count": 0,
                "organic_sampled_count": 0,
            }
        )
    if not rows:
        handles = []
        for video in videos[:4]:
            author = video.get("author") or {}
            handle = author.get("username") or _handle_from_url(video.get("url"))
            if handle:
                handles.append(_at(handle))
        rows.append(
            {
                "name": selected.get("name") or "Virlo discovered set",
                "handles": handles[:4],
                "seed_or_discovered": "discovered",
                "discovery_reason": f"Selected {selected['kind']} from existing Virlo coverage",
                "ads_sampled_count": 0,
                "organic_sampled_count": len(videos),
            }
        )
    return rows


def _configured_competitor_records(dcfg):
    return [
        {
            "name": name,
            "handles": [],
            "seed_or_discovered": "seed",
            "discovery_reason": "Named in diagnostic config",
            "ads_sampled_count": 0,
            "organic_sampled_count": 0,
        }
        for name in dcfg.competitors
    ]


def _paid_records(
    scrape_client,
    competitors,
    dcfg,
    max_paid_competitors,
    max_ads_per_competitor,
    skip_paid,
    paid_pull_meta=None,
):
    paid_pull_meta = paid_pull_meta if paid_pull_meta is not None else {}
    paid_pull_meta["paid_dco_video_unavailable"] = 0
    resolution = {"resolved": [], "dropped": []}
    if skip_paid:
        return [], ["Paid ad pull skipped by --skip-paid."], resolution
    if not competitors:
        return [], ["Paid ad pull skipped because no competitors were configured or discovered."], resolution
    scrape_client = scrape_client or ScrapeCreatorsClient()

    paid = []
    skips = []
    target_competitors = competitors
    if max_paid_competitors is not None:
        target_competitors = competitors[:max(0, max_paid_competitors)]
        skipped = len(competitors) - len(target_competitors)
        if skipped:
            skips.append(f"Skipped paid pulls for {skipped} competitors because --max-paid-competitors was reached.")

    for competitor in target_competitors:
        name = competitor.get("name", "")
        if not name:
            continue
        try:
            candidates = scrape_client.facebook_search_companies(name)
            resolved = resolve_company_page(name, candidates)
        except Exception:
            resolved = None
        if resolved is None or resolved.get("page_id") in (None, ""):
            skips.append(f"Could not resolve '{name}' to an on-niche company page; dropped.")
            resolution["dropped"].append(name)
            continue
        resolution["resolved"].append(
            {
                "query": name,
                "resolved_name": resolved["name"],
                "page_id": resolved["page_id"],
                "category": resolved["category"],
            }
        )
        try:
            # Do not silently limit a scale-up run to the legacy 60-ad cap. The
            # client paginates until this requested sample size or provider supply.
            ads, _ = scrape_client.facebook_company_ads(
                page_id=resolved["page_id"],
                max_ads=max_ads_per_competitor,
            )
        except ScrapeCreatorsClientError as e:
            skips.append(f"Paid pull failed for {name}: {e}")
            continue
        records = [_paid_record(ad, resolved["name"], dcfg) for ad in ads]
        for record in records:
            record["competitor_name"] = resolved["name"]
        paid_pull_meta["paid_dco_video_unavailable"] += sum(
            1
            for ad, record in zip(ads, records)
            if _looks_like_video_ad(ad) and not record["creative_video_url"]
        )
        records.sort(key=lambda record: not bool(record["creative_video_url"]))
        kept_records = records[:max_ads_per_competitor]
        paid.extend(kept_records)
        kept = len(kept_records)
        if kept == 0:
            skips.append(f"No paid ads returned for {name}.")
    return paid, skips, resolution


def _own_brand_paid_records(scrape_client, dcfg, *, max_ads_per_competitor):
    own_brand = str(getattr(dcfg, "own_brand", "") or "").strip()
    if not own_brand:
        return [], []
    try:
        scrape_client = scrape_client or ScrapeCreatorsClient()
        ads, _ = scrape_client.facebook_company_ads(own_brand, max_ads=max_ads_per_competitor)
        records = [_paid_record(ad, own_brand, dcfg) for ad in ads]
        records.sort(key=lambda record: not bool(record["creative_video_url"]))
        records = records[:max_ads_per_competitor]
        skips = [] if records else [f"No paid ads returned for {own_brand}."]
        return records, skips
    except Exception as error:
        return [], [f"Own-brand paid pull failed for {own_brand}: {error}"]


def _looks_like_video_ad(ad):
    snapshot = ad.get("snapshot") if isinstance(ad.get("snapshot"), dict) else {}
    if str(snapshot.get("display_format") or "").upper() == "VIDEO":
        return True
    if isinstance(snapshot.get("videos"), list) or isinstance(snapshot.get("extra_videos"), list):
        return True
    return any(isinstance(card, dict) and isinstance(card.get("videos"), list) for card in snapshot.get("cards") or [])


def _paid_record(ad, competitor_name, dcfg=None):
    snapshot = ad.get("snapshot") if isinstance(ad.get("snapshot"), dict) else {}
    body = snapshot.get("body") if isinstance(snapshot.get("body"), dict) else {}
    first_card = _first_card(snapshot)
    text = str(body.get("text") or snapshot.get("body_text") or first_card.get("body") or "")
    headline = str(snapshot.get("title") or snapshot.get("link_description") or first_card.get("title") or first_card.get("link_description") or "")
    creative_url = _creative_url(snapshot)
    creative_video_url = _creative_video_url(snapshot)
    page_name = str(snapshot.get("page_name") or ad.get("page_name") or competitor_name)
    start_ts = _int(ad.get("start_date"))
    end_ts = _int(ad.get("end_date"))
    is_active = _as_bool(ad.get("is_active"))
    record = {
        "days_active": _days_active(start_ts, end_ts, is_active),
        "still_active": is_active,
        "variation_count": max(1, _int(ad.get("collation_count"))),
        "competitor_name": page_name or competitor_name,
        "competitor_handle": "",
        "ad_id": str(ad.get("ad_archive_id") or ad.get("id") or ""),
        "ad_library_url": str(ad.get("url") or _ad_library_url(ad)),
        "creative_url": creative_url,
        "creative_video_url": creative_video_url,
        "display_format": str(snapshot.get("display_format") or "").upper(),
        "headline": headline,
        "primary_text": text,
        "has_cards": bool(snapshot.get("cards")),
    }
    record.pop("has_cards", None)
    return record


def _apply_paid_counts(competitors, paid):
    for competitor in competitors:
        name = str(competitor.get("name") or "").lower()
        count = 0
        for ad in paid:
            ad_name = str(ad.get("competitor_name") or "").lower()
            if name and (name in ad_name or ad_name in name):
                count += 1
        competitor["ads_sampled_count"] = count


def _narrative(dcfg, selected, organic, paid, actor_batch, paid_skips=None):
    paid_note = _paid_evidence_note(paid, paid_skips)
    return {
        "casting_paragraph": _casting_paragraph(dcfg.niche, actor_batch),
        "gap_insight": (
            f"Virlo surfaced {len(organic)} live organic examples from {_clean_text(selected['name'] or selected['id'])}. "
            f"{paid_note}"
        ),
        "buyer_persona": _buyer_persona_from_evidence(organic, paid),
    }


def _two_ring_narrative(
    dcfg, buyer_query, interest_query, buyer_selected, interest_selected, organic, paid, buyer_context, actor_batch, paid_skips=None
):
    paid_note = _paid_evidence_note(paid, paid_skips)
    return {
        "casting_paragraph": _casting_paragraph(
            f"the interest ring ({interest_query})",
            actor_batch,
            context="format and casting intelligence, not a buyer-behavior claim",
        ),
        "gap_insight": (
            f"The interest ring retained {len(organic)} organic examples from {_clean_text(interest_selected['name'] or interest_selected['id'])}. "
            f"{paid_note}"
        ),
        "buyer_persona": _buyer_persona_from_evidence(buyer_context, paid),
        "buyer_context_note": (
            f"Buyer context came from the buyer ring ({buyer_query}) using {_clean_text(buyer_selected['name'] or buyer_selected['id'])}; "
            "it is stored separately from the gap input."
        ),
    }


def _casting_paragraph(source, actor_batch, context="directional intelligence, not a final buyer-behavior claim"):
    if any(row.get("actor_read_status") == "complete" for row in actor_batch):
        return f"This run sampled creators around {source}. Cast directly toward the completed visual actor reads below; they are observed creator patterns, {context}."
    return f"This run sampled creators around {source}. Casting read awaits visual analysis; do not treat the available assets as casting guidance."


def _paid_evidence_note(paid, paid_skips=None):
    if paid:
        return "The paid pull is in: this compares live organic pull with the competitor creative that actually surfaced."
    skips = " ".join(str(item) for item in (paid_skips or [])).lower()
    if "skipped by --skip-paid" in skips:
        return "Paid ads were deliberately skipped, so this is an organic lead, not a paid comparison."
    return "No paid creative surfaced from the named competitors in this pull. That leaves an open paid lane, not a reason to invent paid evidence."


def _buyer_persona_from_evidence(organic, paid):
    texts = []
    for row in list(organic or []) + list(paid or []):
        text = " ".join(str(row.get(k) or "") for k in ("hook_text", "headline", "primary_text"))
        if text.strip():
            texts.append(text)
    joined = " ".join(texts)
    patterns = (
        r"Most ([A-Za-z0-9][^.!?\n]{2,80}?) struggle",
        r"for ([A-Za-z0-9][^.!?\n]{2,80}?(?:owners|operators|teams|creators|founders|brands|agencies|schools|clinics|stores|families|parents))",
        r"([A-Za-z0-9][^.!?\n]{2,70}?(?:owners|operators|teams|creators|founders|brands|agencies|schools|clinics|stores|families|parents))",
    )
    for pattern in patterns:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            who = _clean_buyer_phrase(match.group(1))
            if who:
                return {
                    "who": who,
                    "appearance": "Inferred from retained source copy. Use the swipe file and creator reads before treating this as a final persona.",
                    "face_paths": [],
                }
    return None


def _clean_buyer_phrase(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip(" .,:;-")
    if not text:
        return ""
    return text[:1].upper() + text[1:120]


def _clean_text(text):
    return str(text or "").replace("—", "-")


def _run_meta(
    selected,
    organic,
    paid,
    actor_batch,
    competitors,
    calls,
    skips=None,
    asset_events=None,
    relevance_drops=None,
    llm_tier="subscription",
    virlo_model="single_surface",
    rings=None,
    buyer_context=None,
    media_manifest=None,
    classification_info=None,
    paid_dco_video_unavailable=0,
    own_brand_pattern_keys=None,
    pattern_summary=None,
    competitor_resolution=None,
):
    rows = []
    total = 0.0
    for call in calls:
        cost = _float(call.get("cost"))
        total += cost
        provider = call.get("provider", "")
        rows.append(
            {
                "vector": "paid supply" if provider == "scrapecreators" else "organic discovery",
                "tools": "ScrapeCreators" if provider == "scrapecreators" else "Virlo",
                "pulls": f"{call.get('method', 'GET')} {call.get('path', '')} status={call.get('status')}",
                "cost": cost,
                "cost_label": _cost_label(call),
                "credits_used": call.get("credits_used", "0"),
            }
        )
    asset_info = asset_summary(asset_events or [])
    drop_info = relevance_drops or {}
    return {
        "mode": "live",
        "virlo_model": virlo_model,
        "llm_tier": llm_tier,
        "provider": "virlo",
        "selected_surface": selected,
        "rings": rings or {},
        "provenance": {
            "organic": {"count": len(organic), "raw_file": "raw/organic.json"},
            "paid": {"count": len(paid), "raw_file": "raw/paid.json"},
            "actors": {"count": len(actor_batch), "raw_file": "raw/actor_batch.json"},
            "buyer_context": {"count": len(buyer_context or []), "raw_file": "raw/buyer_context.json"} if buyer_context is not None else {},
            "competitors": {"count": len(competitors), "raw_file": "raw/competitors.json"},
        },
        "assets": asset_info,
        "media_evidence": {
            "raw_file": "raw/media-manifest.json",
            "sha256": (media_manifest or {}).get("sha256", ""),
            "count": len((media_manifest or {}).get("evidence") or []),
        },
        "classification": classification_info or {},
        "competitor_resolution": competitor_resolution or {"resolved": [], "dropped": []},
        "paid_dco_video_unavailable": paid_dco_video_unavailable,
        "own_brand_pattern_keys": [list(key) for key in sorted(own_brand_pattern_keys or set())],
        "patterns": pattern_summary
        or {"proven_count": 0, "top_proven": [], "emerging_count": 0, "top_emerging": [], "excluded_leg_count": 0},
        "relevance": {
            "threshold": DEFAULT_RELEVANCE_THRESHOLD,
            "dropped_counts": {key: len(value or []) for key, value in drop_info.items()},
            "drops": drop_info,
        },
        "cost_log": {
            "rows": rows,
            "total": round(total, 4),
            "total_label": _total_label(rows, total),
            "skips": (skips or []) + _asset_skip_notes(asset_info) + _relevance_skip_notes(drop_info),
        },
    }


def _attach_emerging_scores(clustered_patterns, emerging_patterns, proven_angles):
    scores = {
        (pattern["angle"], pattern["format"]): pattern
        for pattern in emerging_patterns
    }
    for pattern in clustered_patterns:
        emerging = scores.get((pattern["angle"], pattern["format"]), {})
        pattern["emerging_score"] = emerging.get("emerging_score", 0.0)
        pattern["adjacent_to_proven"] = pattern["angle"] in proven_angles


def _pattern_summary(proven_patterns, emerging_patterns, excluded_count):
    return {
        "proven_count": len(proven_patterns),
        "top_proven": proven_patterns[:3],
        "emerging_count": len(emerging_patterns),
        "top_emerging": emerging_patterns[:3],
        "excluded_leg_count": excluded_count,
    }


def _ring_meta(selected, query, count, raw_file):
    return {
        "query": query,
        "count": count,
        "raw_file": raw_file,
        "surface": selected,
    }


def _with_provenance(record, selected, ring_role, ring_query, scoring_role):
    enriched = dict(record)
    enriched.update(_provenance_fields(selected, ring_role, ring_query, scoring_role))
    return enriched


def _tag_records(records, selected, ring_role, ring_query, scoring_role):
    for record in records:
        record.update(_provenance_fields(selected, ring_role, ring_query, scoring_role))


def _provenance_fields(selected, ring_role, ring_query, scoring_role):
    return {
        "ring_role": ring_role,
        "ring_query": ring_query,
        "source_provider": "virlo",
        "source_surface_kind": selected.get("kind", ""),
        "source_surface_id": selected.get("id", ""),
        "source_surface_name": selected.get("name", ""),
        "source_created": bool(selected.get("source_created", selected.get("created", False))),
        "scoring_role": scoring_role,
    }


def _classify_capture_records(out_dir, dcfg, record_sets, *, classifier=None):
    """Attach classifications only after retained records have local image receipts."""
    all_items = []
    rows = []
    for kind, records in record_sets:
        for index, record in enumerate(records, start=1):
            record_id = _record_media_id(kind, record, index)
            row = {"kind": kind, "record": record, "evidence": []}
            for local_path, role in _record_media_items(record, kind):
                item = {
                    "role": role,
                    "source_record_id": record_id,
                    "local_path": _absolute_asset_path(out_dir, local_path),
                }
                try:
                    build_evidence_manifest([item])
                except MediaEvidenceError:
                    pass
                else:
                    row["evidence"].append(item)
                    all_items.append(item)
            rows.append(row)

    media_manifest = build_evidence_manifest(all_items)
    configured = bool(getattr(dcfg, "llm", None))
    cache = ClassificationCache(os.path.join(out_dir, "raw", "classification-cache")) if configured else None
    cache_hits = 0
    for row in rows:
        record = row["record"]
        if not configured:
            _apply_legacy_classification(record, row["kind"])
            continue
        evidence = build_evidence_manifest(row["evidence"])
        try:
            result = (classifier or classify_creative)(record, row["kind"], evidence, dcfg, cache=cache)
        except ClassificationError as error:
            # One malformed model response must not abort a whole run: quarantine this record.
            tier = dcfg.llm.tier if getattr(dcfg, "llm", None) else "subscription"
            model = dcfg.llm.model if getattr(dcfg, "llm", None) else ""
            result = _insufficient_visual_result(
                f"Classification failed and was quarantined: {error}", provider=tier, model=model
            )
        record.update(result)
        if (result.get("classification_provenance") or {}).get("cache_hit"):
            cache_hits += 1
    return media_manifest, {
        "mode": "media-grounded" if configured else "legacy-local-rule",
        "cache_dir": "raw/classification-cache" if configured else "",
        "records_classified": len(rows),
        "cache_hits": cache_hits,
    }


def _annotate_organic_overperformance(organic, scrape_client):
    """Best-effort enhancement: baseline-provider trouble must not abort capture."""
    if not callable(getattr(scrape_client, "creator_recent_views", None)):
        return organic
    try:
        return annotate_overperformance(organic, scrape_client)
    except Exception:
        return organic


def _record_media_items(record, kind):
    frames = [(path, "video-frame") for path in (record.get("frame_local_paths") or []) if path]
    opening_frames = [(path, "opening-frame") for path in (record.get("opening_frame_local_paths") or []) if path]
    if frames:
        return frames + opening_frames
    if opening_frames:
        return opening_frames
    if kind == "paid":
        return [(record.get("creative_local_path", ""), "creative")]
    return [(record.get("thumbnail_local_path", ""), "thumbnail")]


def _record_media_id(kind, record, index):
    source = record.get("ad_id") if kind == "paid" else record.get("post_url")
    return f"{kind}:{source or index}"


def _absolute_asset_path(out_dir, local_path):
    return local_path if os.path.isabs(local_path) else os.path.join(out_dir, local_path)


def _apply_legacy_classification(record, kind):
    fallback = _classify_format({"description": record.get("hook_text", "")}) if kind != "paid" else "insufficient-evidence"
    record.update(classify_format(record, kind, fallback=fallback))
    record.update(classify_message_frame(record, kind))
    record.update(classify_mechanics(record, kind))
    # The legacy (no-LLM) path cannot read a hook from the opening; keep the dimension present.
    record.setdefault("hook_type", "hook-unknown")


def _asset_skip_notes(asset_info):
    skipped = asset_info.get("skipped") or []
    if not skipped:
        return []
    return [f"{len(skipped)} media assets could not be downloaded; see raw/run_meta.json assets.skipped."]


def _relevance_skip_notes(drop_info):
    notes = []
    for key, rows in (drop_info or {}).items():
        if rows:
            notes.append(f"Dropped {len(rows)} {key} records below relevance threshold.")
    return notes


def _cost_label(call):
    if call.get("provider") == "scrapecreators":
        credits = call.get("credits_used", "1")
        return f"{credits} credit" if str(credits) == "1" else f"{credits} credits"
    cost = _float(call.get("cost"))
    return "$0.00" if cost == 0 else f"${cost:.2f}"


def _total_label(rows, total):
    scrape_credits = 0
    for row in rows:
        if row.get("tools") == "ScrapeCreators":
            scrape_credits += _int(row.get("credits_used"))
    if scrape_credits and total == scrape_credits:
        return f"{scrape_credits} ScrapeCreators credits"
    return f"${total:.2f}"


def _classify_format(video):
    text = _text(video).lower()
    if any(w in text for w in ("app", "software", "dashboard", "tool", "screen", "demo")):
        return "faceless-demo"
    if any(w in text for w in ("pov", "day in the life", "ditl")):
        return "narrative-vlog-ditl"
    if any(w in text for w in ("founder", "building", "behind the scenes")):
        return "founder-bts"
    if any(w in text for w in ("how to", "tips", "advice", "owner", "business", "rant", "mistake", "lesson")):
        return "yapper"
    return "insufficient-evidence"


def _creative_url(snapshot):
    cards = snapshot.get("cards") if isinstance(snapshot.get("cards"), list) else []
    for card in cards:
        if not isinstance(card, dict):
            continue
        url = _creative_url_from_container(card)
        if url:
            return url
    return _creative_url_from_container(snapshot)


def _creative_video_url(snapshot):
    containers = list(snapshot.get("cards") or []) + [snapshot]
    for container in containers:
        if not isinstance(container, dict):
            continue
        videos = container.get("videos") if isinstance(container.get("videos"), list) else []
        for video in videos:
            if not isinstance(video, dict):
                continue
            for key in ("video_hd_url", "video_sd_url"):
                if video.get(key):
                    return str(video[key])
    for video in snapshot.get("extra_videos") or []:
        if not isinstance(video, dict):
            continue
        for key in ("video_hd_url", "video_sd_url"):
            if video.get(key):
                return str(video[key])
    return ""


def _creative_url_from_container(container):
    images = container.get("images") if isinstance(container.get("images"), list) else []
    for image in images:
        if not isinstance(image, dict):
            continue
        for key in ("resized_image_url", "original_image_url", "watermarked_resized_image_url"):
            if image.get(key):
                return str(image[key])
    for key in ("resized_image_url", "original_image_url", "watermarked_resized_image_url", "video_preview_image_url"):
        if container.get(key):
            return str(container[key])
    videos = container.get("videos") if isinstance(container.get("videos"), list) else []
    for video in videos:
        if not isinstance(video, dict):
            continue
        for key in ("video_preview_image_url", "thumbnail_url", "video_sd_url", "video_hd_url"):
            if video.get(key):
                return str(video[key])
    return ""


def _first_card(snapshot):
    cards = snapshot.get("cards") if isinstance(snapshot.get("cards"), list) else []
    for card in cards:
        if isinstance(card, dict):
            return card
    return {}


def _days_active(start_ts, end_ts, is_active):
    if not start_ts:
        return 0
    end = int(time.time()) if is_active or not end_ts else end_ts
    return max(0, int((end - start_ts) / 86400))


def _ad_library_url(ad):
    ad_id = ad.get("ad_archive_id") or ad.get("id")
    return f"https://www.facebook.com/ads/library?id={ad_id}" if ad_id else ""


def _text(video):
    return str(video.get("description") or video.get("title") or video.get("caption") or "").strip()


def _int(value):
    if isinstance(value, str):
        s = value.strip().lower().replace(",", "")
        mult = 1
        if s and s[-1] in "kmb":
            mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[s[-1]]
            s = s[:-1]
        try:
            return max(0, int(round(float(s) * mult))) if s else 0
        except (TypeError, ValueError):
            return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_ts(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _as_bool(value):
    # API booleans sometimes arrive as strings; bool("false") is True, which would mark
    # dead ads active and compute days-active through today.
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "active")
    return bool(value)


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _at(handle):
    handle = str(handle or "").strip()
    if not handle:
        return ""
    return handle if handle.startswith("@") else f"@{handle}"


def _handle_from_url(url):
    if not url:
        return ""
    match = re.search(r"(?:tiktok\.com/@|instagram\.com/)([^/?#]+)", str(url))
    return match.group(1) if match else ""


def _profile_url(platform, handle):
    handle = str(handle or "").lstrip("@")
    if platform == "instagram":
        return f"https://www.instagram.com/{handle}/"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if platform == "youtube":
        return f"https://www.youtube.com/@{handle}"
    return ""


def _write_json(out_dir, name, data):
    path = os.path.join(out_dir, "raw", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _copy_config(config_path, out_dir):
    if not config_path:
        return
    dst = os.path.join(out_dir, "config.toml")
    if os.path.abspath(config_path) != os.path.abspath(dst):
        shutil.copyfile(config_path, dst)
