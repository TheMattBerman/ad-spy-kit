import argparse
import json
import os

from .actor_synthesis import ActorSynthesisError, synthesize_actor_profile
from .diagnostic_capture import validate_diagnostic_capture
from .diagnostic_config import DiagnosticConfigError, load_diagnostic_config
from .diagnostic_report_html import watched_coverage, render_report_html
from .gap_engine import (
    GapEngineError,
    dead_end_formats,
    organic_strength_by_format,
    paid_strength_by_format,
    pick_top_gap,
)
from .live_capture import (
    LiveCaptureError,
    build_virlo_capture,
    plan_virlo_surface,
    plan_virlo_two_ring,
    preflight_live_run,
    run_virlo_smoke,
    slugify,
)
from .scrapecreators_client import ScrapeCreatorsClientError
from .taxonomy import VIDEO_FORMATS, tally_formats, tally_mechanics, tally_message_frames, validate_scoreable_format
from .virlo_client import VirloClientError

FORMAT_DISPLAY = {
    "yapper": "Talking-head operator clips",
    "faceless-demo": "Faceless demo",
    "founder-bts": "Founder behind-the-scenes",
    "authority-figure": "Authority figure",
    "narrative-vlog-ditl": "Day-in-the-life story",
    "native-photo-long-copy": "Native photo + long copy",
    "ui-mimic": "UI mimic",
    "carousel": "Carousel",
}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _abs_run_path(run_root, path):
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(run_root, path))


def _display_format(fmt):
    return FORMAT_DISPLAY.get(fmt, fmt)


def _display_text(value):
    return str(value or "").replace("—", "-").replace("–", "-").strip()


def _format_eligible_records(records):
    eligible = []
    for record in records:
        fmt = record.get("format")
        scope = record.get("visual_evidence_scope")
        if not fmt or fmt == "insufficient-evidence" or scope == "unwatched":
            continue
        if fmt in VIDEO_FORMATS and scope != "full-motion":
            continue
        eligible.append(record)
    return eligible


def _competitor_key(record):
    return record.get("competitor_name") or record.get("competitor_handle") or record.get("ad_id") or ""


def _count_paid_competitors_for_format(paid, fmt):
    names = {_competitor_key(r) for r in paid if r.get("format") == fmt and _competitor_key(r)}
    if names:
        return len(names)
    return len([r for r in paid if r.get("format") == fmt])


def _load_competitors(run_root, dcfg):
    path = os.path.join(run_root, "raw", "competitors.json")
    if not os.path.exists(path):
        return None, [{"name": name} for name in dcfg.competitors]

    competitors = _read_json(path)
    rows = []
    for item in competitors:
        handles = item.get("handles") or []
        rows.append(
            {
                "name": item.get("name", ""),
                "handle": handles[0] if handles else "",
                "seed_or_discovered": item.get("seed_or_discovered", ""),
                "ads_sampled_count": item.get("ads_sampled_count", 0),
                "organic_sampled_count": item.get("organic_sampled_count", 0),
                "note": "",
            }
        )
    return competitors, rows


def _load_run_meta(run_root):
    path = os.path.join(run_root, "raw", "run_meta.json")
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def _rivals_count(competitor_items, dcfg, paid):
    if competitor_items:
        names = {c.get("name") for c in competitor_items if c.get("name")}
    else:
        names = {r.get("competitor_name") for r in paid if r.get("competitor_name")}
        if not names:
            names = set(dcfg.competitors)
    return len(names)


def _initials(name):
    parts = [p for p in str(name or "").strip().split() if p]
    return "".join(p[0].upper() for p in parts[:2])


def _paid_baseline(paid):
    """Return the most persistent currently funded format in the paid sample.

    Meta does not expose spend or return. Active duration is therefore the best
    paid-market signal available here, not a performance claim.
    """
    formats = sorted({record.get("format") for record in paid if validate_scoreable_format(record.get("format"))})
    summaries = []
    for fmt in formats:
        records = [record for record in paid if record.get("format") == fmt]
        active = [record for record in records if record.get("still_active") is True]
        sustained = [record for record in active if (record.get("days_active") or 0) >= 30]
        summaries.append(
            {
                "format": fmt,
                "ad_rows": len(records),
                "active_rows": len(active),
                "sustained_rows": len(sustained),
                "longest_days": max((record.get("days_active") or 0 for record in active), default=0),
                "active_days": sum(record.get("days_active") or 0 for record in active),
            }
        )
    if not summaries:
        return None
    return max(
        summaries,
        key=lambda row: (row["sustained_rows"], row["active_days"], row["active_rows"], row["longest_days"], row["format"]),
    )


def _format_rows(run_root, organic, paid, gap):
    organic_scores = organic_strength_by_format(organic)
    paid_scores = paid_strength_by_format(paid)
    all_formats = sorted(set(organic_scores) | set(paid_scores))
    max_organic = max(organic_scores.values(), default=0.0)
    max_paid = max(paid_scores.values(), default=0.0)
    dead = dead_end_formats(paid)
    baseline = _paid_baseline(paid) or {}
    baseline_format = baseline.get("format")
    gap_format = gap["format"] if gap else None
    rows = []

    for fmt in all_formats:
        o_raw = organic_scores.get(fmt, 0.0)
        p_raw = paid_scores.get(fmt, 0.0)
        o_norm = round(100 * o_raw / max_organic) if max_organic else 0
        p_norm = round(100 * p_raw / max_paid) if max_paid else 0

        if fmt == baseline_format:
            verdict, verdict_class = "FUNDED BASELINE", "baseline"
        elif fmt == gap_format:
            verdict, verdict_class = "UNDEREXPLORED", "probe"
        elif fmt in dead:
            verdict, verdict_class = "SUSTAINED", "sustained"
        elif p_raw == 0 and o_norm > 0 and not gap:
            verdict, verdict_class = "NEEDS MORE SIGNAL", "signal"
        elif p_raw == 0 and o_norm > 0:
            verdict, verdict_class = "UNCLAIMED", "watch"
        elif p_norm >= 70:
            verdict, verdict_class = "IN MARKET", "sat"
        else:
            verdict, verdict_class = "CONTESTED", "con"

        organic_sample = next((r for r in organic if r.get("format") == fmt and r.get("thumbnail_local_path")), None)
        paid_sample = next((r for r in paid if r.get("format") == fmt and r.get("creative_local_path")), None)
        thumb_path = None
        if organic_sample:
            thumb_path = _abs_run_path(run_root, organic_sample.get("thumbnail_local_path"))
        elif paid_sample:
            thumb_path = _abs_run_path(run_root, paid_sample.get("creative_local_path"))

        rival_count = _count_paid_competitors_for_format(paid, fmt)
        rows.append(
            {
                "format": fmt,
                "desc": "",
                "thumb_path": thumb_path,
                "organic": o_norm,
                "paid": p_norm,
                "gap": f"{o_norm - p_norm:+d}",
                "verdict": verdict,
                "verdict_class": verdict_class,
                "sample_label": "sampled organic" if o_raw > 0 and p_raw == 0 else f"{rival_count} rivals",
            }
        )

    class_rank = {"probe": 0, "baseline": 1, "sustained": 2, "watch": 3, "signal": 3, "con": 4, "sat": 5}
    rows.sort(key=lambda row: (class_rank.get(row["verdict_class"], 9), -int(row["gap"])))
    return rows


def _sample_text(record):
    for key in ("hook_text", "headline", "primary_text"):
        value = _display_text(record.get(key))
        if value:
            return value
    return ""


def _message_frame_rows(organic, paid):
    frames = sorted(
        {
            record.get("message_frame")
            for record in list(organic) + list(paid)
            if record.get("message_frame")
        }
    )
    rows = []
    for frame in frames:
        organic_records = [record for record in organic if record.get("message_frame") == frame]
        paid_records = [record for record in paid if record.get("message_frame") == frame]
        sample_record = next(iter(organic_records or paid_records), {})
        rows.append(
            {
                "frame": frame,
                "organic": len(organic_records),
                "paid": len(paid_records),
                "sample": _sample_text(sample_record),
                "sample_source": "organic" if organic_records else "paid",
            }
        )
    rows.sort(key=lambda row: (-(row["organic"] + row["paid"]), row["frame"]))
    return rows


def _mechanic_rows(organic, paid):
    rows = []
    mechanics = sorted(
        {
            tag
            for record in list(organic) + list(paid)
            for tag in (record.get("mechanics") or [])
        }
    )
    for tag in mechanics:
        organic_records = [record for record in organic if tag in (record.get("mechanics") or [])]
        paid_records = [record for record in paid if tag in (record.get("mechanics") or [])]
        sample_record = next(iter(organic_records or paid_records), {})
        rows.append(
            {
                "mechanic": tag,
                "organic": len(organic_records),
                "paid": len(paid_records),
                "sample": _sample_text(sample_record),
                "sample_source": "organic" if organic_records else "paid",
            }
        )
    rows.sort(key=lambda row: (-(row["organic"] + row["paid"]), row["mechanic"]))
    return rows


def _decision_brief(organic, paid, gap):
    if not gap:
        return None

    gap_format = gap["format"]
    organic_count = sum(record.get("format") == gap_format for record in organic)
    paid_count = sum(record.get("format") == gap_format for record in paid)
    baseline = _paid_baseline(paid)
    baseline_format = baseline.get("format") if baseline else ""

    return {
        "gap_format": gap_format,
        "baseline_format": baseline_format,
        "organic_count": organic_count,
        "paid_count": paid_count,
        "baseline_title": f"{_display_format(baseline_format)} is what they keep running." if baseline else "No clear paid control showed up.",
        "baseline_detail": (
            f"{baseline['active_rows']} active ads. {baseline['sustained_rows']} have been live 30 days or longer. "
            f"The longest has been up {baseline['longest_days']} days. It is the thing to beat."
            if baseline
            else "Pull more paid ads before choosing what to test against."
        ),
        "challenger_title": "Put a real person on camera." if gap_format == "yapper" else f"Test {_display_format(gap_format)}.",
        "challenger_detail": (
            f"{organic_count} organic posts use it. Zero live ads in this sample do. "
            "That is a reason to test it, not proof that it works."
            if paid_count == 0
            else f"{organic_count} organic posts use it, alongside {paid_count} paid ads. Put it head to head with what competitors keep running."
        ),
        "test_title": "Run them head to head.",
        "test_detail": (
            f"Cell A: {_display_format(baseline_format)}. Cell B: {_display_format(gap_format)}. "
            "Change nothing else. Same offer, same claim, same audience, same landing page, same budget."
            if baseline
            else "Change nothing else. Keep the offer, claim, audience, landing page, and budget the same."
        ),
        "evidence_note": (
            "How long an ad stays up tells you a competitor keeps choosing it. It does not tell you what they spent or what it made. "
            "We count each live ad separately, so one idea can show up more than once."
        ),
    }


def _winner_data(run_root, organic, paid, narrative, gap):
    if not gap:
        return None
    fmt = gap["format"]
    samples = [r for r in organic if r.get("format") == fmt]
    sample = max(samples, key=lambda r: r.get("views", 0), default={})
    paid_rivals = _count_paid_competitors_for_format(paid, fmt)
    return {
        "image_path": _abs_run_path(run_root, sample.get("thumbnail_local_path")),
        "format": fmt,
        "cost_label": "Organic reach",
        "cost_value": sample.get("views", 0),
        "subs": "",
        "saturation": _paid_coverage_label(paid, paid_rivals),
        "headline": f"{_display_format(fmt)} is worth testing next.",
        "desc": sample.get("hook_text", ""),
        "desc_lede": "One format is all over organic and missing from the live ads. That makes it worth a test, not a sure thing.",
        "so_what": "People choose to watch this organically. That makes it worth putting up against the format competitors keep running.",
    }


def _engagement_ratio(record):
    followers = record.get("follower_count") or 0
    if not followers:
        return 0
    return record.get("views", 0) / followers


def _swipe_file_data(run_root, organic, paid):
    items = []

    organic_examples = sorted(
        [r for r in organic if r.get("thumbnail_local_path")],
        key=lambda r: (r.get("format") == "yapper", _engagement_ratio(r), r.get("views", 0)),
        reverse=True,
    )[:3]
    for record in organic_examples:
        items.append(
            {
                "source_type": "organic",
                "source_label": "Organic post",
                "format": record.get("format", ""),
                "message_frame": record.get("message_frame", ""),
                "mechanics": record.get("mechanics", []),
                "visual_evidence_scope": record.get("visual_evidence_scope"),
                "name": record.get("creator_handle", ""),
                "image_path": _abs_run_path(run_root, record.get("thumbnail_local_path")),
                "url": record.get("post_url", ""),
                "pulled_text": record.get("hook_text", ""),
                "metric_label": "Views",
                "metric_value": record.get("views", 0),
                "secondary_label": "Views / follower",
                "secondary_value": round(_engagement_ratio(record), 1),
            }
        )

    paid_examples = sorted(
        [r for r in paid if r.get("creative_local_path")],
        key=lambda r: (r.get("still_active") is True, r.get("days_active", 0)),
        reverse=True,
    )[:3]
    for record in paid_examples:
        items.append(
            {
                "source_type": "paid",
                "source_label": "Paid ad",
                "format": record.get("format", ""),
                "message_frame": record.get("message_frame", ""),
                "mechanics": record.get("mechanics", []),
                "visual_evidence_scope": record.get("visual_evidence_scope"),
                "name": record.get("competitor_name") or record.get("competitor_handle", ""),
                "image_path": _abs_run_path(run_root, record.get("creative_local_path")),
                "url": record.get("ad_library_url", ""),
                "pulled_text": record.get("headline", ""),
                "body_text": record.get("primary_text", ""),
                "metric_label": "Active days",
                "metric_value": record.get("days_active", 0),
                "secondary_label": "Status",
                "secondary_value": "active" if record.get("still_active") else "inactive",
            }
        )

    return items


def _surface_context(run_meta):
    selected = run_meta.get("selected_surface") if isinstance(run_meta.get("selected_surface"), dict) else {}
    rings = run_meta.get("rings") if isinstance(run_meta.get("rings"), dict) else {}
    interest = rings.get("interest") if isinstance(rings.get("interest"), dict) else {}
    if interest and isinstance(interest.get("surface"), dict):
        selected = interest["surface"]
    if not selected:
        return {}
    kind = _display_text(selected.get("kind") or "surface")
    name = _display_text(selected.get("name") or selected.get("id"))
    label = " ".join(part for part in (kind.title(), name) if part)
    return {
        "source_label": label,
        "source_kind": kind,
        "source_id": _display_text(selected.get("id")),
    }


def _paid_coverage_label(paid, rivals_in_lane):
    if not paid:
        return "No paid creative surfaced"
    return f"{rivals_in_lane} of {len(paid)} paid ads"


def _casting_call(profile):
    def mode(field, fallback):
        return _display_text((profile.get(field) or {}).get("mode")) or fallback

    age = mode("age_bracket", "age-unspecified")
    polish = mode("look_polish", "natural")
    setting = mode("setting", "everyday-life")
    styling = mode("styling", "casual")
    energy = mode("energy", "direct")
    gender = mode("gender_read", "mixed-ambiguous")
    gender_phrase = "" if gender == "mixed-ambiguous" else f" {gender}"
    return (
        f"Cast a{gender_phrase} {age} creator who feels {polish}, belongs naturally in {setting}, "
        f"shows up in {styling}, and delivers it with {energy} energy."
    )


def _cast_data(run_root, actor_batch, narrative, run_meta=None):
    # Legacy offline captures predate visual-read receipts. New live runs only
    # render explicitly completed reads, while old examples remain renderable.
    actor_batch = [item for item in actor_batch if item.get("actor_read_status") in (None, "", "complete")]
    if not actor_batch:
        return None
    try:
        profile = synthesize_actor_profile(actor_batch)
    except ActorSynthesisError:
        return None

    axis_map = (
        ("age_bracket", "Age"),
        ("energy", "Energy"),
        ("setting", "Setting"),
        ("look_polish", "Polish"),
        ("styling", "Wardrobe"),
        ("body_type", "Build"),
    )
    axes = []
    for field, label in axis_map:
        if field in profile:
            axes.append({"k": label, "v": profile[field]["mode"]})

    faces = []
    characters = []
    has_avatar = False
    for item in actor_batch[:8]:
        avatar_path = _abs_run_path(run_root, item.get("avatar_local_path"))
        thumbnail_path = _abs_run_path(run_root, item.get("top_thumbnail_local_path"))
        has_avatar = has_avatar or bool(item.get("avatar_local_path"))
        faces.append(
            {
                "handle": item.get("creator_handle", ""),
                "initials": _initials(item.get("creator_name", "")),
                "avatar_path": avatar_path,
            }
        )
        characters.append(
            {
                "handle": item.get("creator_handle", ""),
                "name": item.get("creator_name", ""),
                "avatar_path": avatar_path,
                "thumbnail_path": thumbnail_path,
                "age": item.get("age_bracket", ""),
                "energy": item.get("energy", ""),
                "setting": item.get("setting", ""),
                "polish": item.get("look_polish", ""),
                "styling": item.get("styling", ""),
                "build": item.get("body_type", ""),
                "provider": item.get("actor_read_provider", ""),
                "confidence": item.get("actor_read_confidence", ""),
            }
        )

    return {
        "faces": faces,
        "characters": characters,
        "casting_paragraph": _casting_call(profile),
        "axes": axes,
        "source": _surface_context(run_meta or {}),
        "face_note": "" if has_avatar else "Real creator faces populate on a live run.",
    }


def _evidence_data(run_root, organic, paid, actor_batch, competitor_items, run_meta):
    is_two_ring = run_meta.get("virlo_model") == "two_ring"
    buyer_context = {}
    buyer_context_path = os.path.join(run_root, "raw", "buyer_context.json")
    if os.path.exists(buyer_context_path):
        buyer_context = _read_json(buyer_context_path)
    raw_counts = {
        "organic": len(organic),
        "paid": len(paid),
        "actors": len(actor_batch),
        "buyer_context": len(buyer_context or []),
        "competitors": len(competitor_items or []),
    }
    provenance = run_meta.get("provenance") if isinstance(run_meta.get("provenance"), dict) else {}
    if is_two_ring:
        rows = [
            {"label": "Interest organic", "value": raw_counts["organic"], "source": "raw/organic.json"},
            {"label": "Paid ads", "value": raw_counts["paid"], "source": "raw/paid.json"},
            {"label": "Interest creator reads", "value": raw_counts["actors"], "source": "raw/actor_batch.json"},
            {"label": "Buyer context", "value": raw_counts["buyer_context"], "source": "raw/buyer_context.json"},
            {"label": "Competitors", "value": raw_counts["competitors"], "source": "raw/competitors.json"},
        ]
    else:
        rows = [
            {"label": "Organic posts", "value": raw_counts["organic"], "source": "raw/organic.json"},
            {"label": "Paid ads", "value": raw_counts["paid"], "source": "raw/paid.json"},
            {"label": "Creator reads", "value": raw_counts["actors"], "source": "raw/actor_batch.json"},
            {"label": "Competitors", "value": raw_counts["competitors"], "source": "raw/competitors.json"},
        ]
    for row in rows:
        key = {
            "Organic posts": "organic",
            "Interest organic": "organic",
            "Paid ads": "paid",
            "Creator reads": "actors",
            "Interest creator reads": "actors",
            "Buyer context": "buyer_context",
            "Competitors": "competitors",
        }[row["label"]]
        meta_row = provenance.get(key)
        if isinstance(meta_row, dict):
            row["value"] = meta_row.get("count", row["value"])
            row["source"] = meta_row.get("raw_file", row["source"])

    cost_log = run_meta.get("cost_log") if isinstance(run_meta.get("cost_log"), dict) else {}
    return {
        "rows": rows,
        "cost_rows": cost_log.get("rows", []),
        "cost_total": cost_log.get("total"),
        "cost_total_label": cost_log.get("total_label"),
        "skips": cost_log.get("skips", []),
        "rings": run_meta.get("rings", {}) if is_two_ring else {},
        "note": "" if cost_log else "No live cost log was provided for this run.",
    }


def _creative_index(organic, paid):
    """Map every creative ref the pattern engine could emit back to its record."""
    index = {}
    for record in paid:
        for key in ("ad_id", "ad_library_url", "creative_url"):
            ref = record.get(key)
            if ref:
                index.setdefault(ref, ("paid", record))
    for record in organic:
        for key in ("post_url", "video_url", "thumbnail_url"):
            ref = record.get(key)
            if ref:
                index.setdefault(ref, ("organic", record))
    return index


def _resolve_creative(run_root, ref, index):
    entry = index.get(ref)
    if not entry:
        return None
    kind, record = entry
    if kind == "paid":
        image = record.get("creative_local_path") or (record.get("frame_local_paths") or [None])[0]
        url = record.get("ad_library_url") or record.get("creative_url") or ""
        who = record.get("competitor_name") or ""
    else:
        image = record.get("thumbnail_local_path") or (record.get("frame_local_paths") or [None])[0]
        url = record.get("post_url") or ""
        who = record.get("creator_handle") or ""
    if not image:
        return None
    return {
        "kind": kind,
        "image_path": _abs_run_path(run_root, image),
        "url": url,
        "who": who,
        "hook_type": record.get("hook_type", ""),
        "hook_text": (record.get("hook_text") or record.get("opening_line") or "").strip(),
    }


def _enrich_pattern(run_root, pattern, index):
    enriched = dict(pattern)
    resolved = [_resolve_creative(run_root, ref, index) for ref in (pattern.get("creatives") or [])]
    enriched["resolved_creatives"] = [creative for creative in resolved if creative][:4]
    return enriched


def _patterns_data(run_root, organic, paid, run_meta):
    """Assemble the Proven / Emerging / Hypothesis tiers for the report.

    Proven and Emerging come from run_meta's ranked summaries; Hypothesis is every other
    clustered pattern that still carries signal (paid or organic), highest-persistence first.
    """
    summary = (run_meta or {}).get("patterns") or {}
    patterns_path = os.path.join(run_root, "raw", "patterns.json")
    all_patterns = _read_json(patterns_path) if os.path.exists(patterns_path) else []
    if isinstance(all_patterns, dict):
        all_patterns = all_patterns.get("patterns", [])
    proven = summary.get("top_proven") or []
    emerging = summary.get("top_emerging") or []
    if not proven and not emerging and not all_patterns:
        return None
    ranked_keys = {(p.get("angle"), p.get("format")) for p in proven + emerging}
    hypothesis = [
        p for p in (all_patterns or [])
        if (p.get("angle"), p.get("format")) not in ranked_keys
        and (p.get("paid_count") or p.get("organic_count"))
    ]
    hypothesis.sort(key=lambda p: (p.get("paid_persistence", 0) or 0, p.get("emerging_score", 0) or 0), reverse=True)
    index = _creative_index(organic, paid)
    return {
        "proven": [_enrich_pattern(run_root, p, index) for p in proven],
        "emerging": [_enrich_pattern(run_root, p, index) for p in emerging],
        "hypothesis": [_enrich_pattern(run_root, p, index) for p in hypothesis[:4]],
        "counts": {
            "proven": summary.get("proven_count", len(proven)),
            "emerging": summary.get("emerging_count", len(emerging)),
            "excluded_leg": summary.get("excluded_leg_count", 0),
        },
    }


def _build_report_data(run_root, dcfg, organic, paid, actor_batch, narrative, gap=None, gap_error=""):
    scored_organic = _format_eligible_records(organic)
    scored_paid = _format_eligible_records(paid)
    competitor_items, competitors = _load_competitors(run_root, dcfg)
    run_meta = _load_run_meta(run_root)
    open_lane = _display_format(gap["format"]) if gap else "none yet"

    top_fmt = gap["format"] if gap else None
    rivals_in_lane = _count_paid_competitors_for_format(scored_paid, top_fmt) if top_fmt else 0
    baseline = _paid_baseline(scored_paid)
    baseline_name = _display_format(baseline["format"]) if baseline else "none yet"
    buyer_persona = narrative.get("buyer_persona") if isinstance(narrative.get("buyer_persona"), dict) else None
    stats = (
        [
            {"label": "What to test", "value": open_lane, "sub": "shows up in organic, missing from live ads", "tone": "g"},
            {"label": "What they keep running", "value": baseline_name, "sub": "longest-running paid format", "tone": "h"},
            {"label": "Paid ads sampled", "value": len(paid), "sub": "from the competitors above", "tone": "b"},
            {"label": "Organic posts sampled", "value": len(organic), "sub": "from the selected source", "tone": None},
        ]
        if gap
        else [
            {"label": "The gap", "value": "none yet", "sub": "", "tone": None},
            {"label": "Next move", "value": "more signal", "sub": "competitors / adjacent niche", "tone": "b"},
            {"label": "Paid ads sampled", "value": len(paid), "sub": "from the competitors above", "tone": None},
            {"label": "Organic posts sampled", "value": len(organic), "sub": "from the selected source", "tone": None},
        ]
    )

    return {
        "niche": dcfg.niche,
        "ads_scanned": len(paid),
        "organic_count": len(organic),
        "rivals_count": _rivals_count(competitor_items, dcfg, paid),
        "stats": stats,
        "competitors": competitors,
        "winner": _winner_data(run_root, scored_organic, scored_paid, narrative, gap),
        "formats": _format_rows(run_root, scored_organic, scored_paid, gap),
        "paid_baseline": baseline,
        "decision_brief": _decision_brief(scored_organic, scored_paid, gap),
        "message_frames": _message_frame_rows(organic, paid),
        "mechanics": _mechanic_rows(organic, paid),
        "swipe_file": _swipe_file_data(run_root, organic, paid),
        "buyer_persona": buyer_persona,
        "cast": _cast_data(run_root, actor_batch, narrative, run_meta),
        "gap": {"format": gap["format"], "paid_evidence": _paid_coverage_label(scored_paid, rivals_in_lane)} if gap else None,
        "gap_error": gap_error,
        "gap_insight": narrative.get("gap_insight", ""),
        "evidence": _evidence_data(run_root, organic, paid, actor_batch, competitor_items, run_meta),
        "virlo_model": run_meta.get("virlo_model", "legacy"),
        "rings": run_meta.get("rings", {}),
        "watched_coverage": {
            "paid": watched_coverage(paid),
            "organic": watched_coverage(organic),
        },
        "patterns": _patterns_data(run_root, organic, paid, run_meta),
    }


def _render_diagnostic_report(config_path, capture_root, out_dir=None):
    try:
        dcfg = load_diagnostic_config(config_path)
    except DiagnosticConfigError as e:
        print(f"invalid config: {e}")
        return 2
    errors = validate_diagnostic_capture(capture_root)
    if errors:
        print("invalid capture:")
        for e in errors:
            print(f"  - {e}")
        return 2

    organic = _read_json(os.path.join(capture_root, "raw", "organic.json"))
    paid = _read_json(os.path.join(capture_root, "raw", "paid.json"))
    actor_batch = _read_json(os.path.join(capture_root, "raw", "actor_batch.json"))
    narrative = _read_json(os.path.join(capture_root, "raw", "narrative.json"))

    scored_organic = _format_eligible_records(organic)
    scored_paid = _format_eligible_records(paid)
    organic_tally = tally_formats(scored_organic)
    paid_tally = tally_formats(scored_paid)
    organic_frame_tally = tally_message_frames(organic)
    paid_frame_tally = tally_message_frames(paid)
    organic_mechanics_tally = tally_mechanics(organic)
    paid_mechanics_tally = tally_mechanics(paid)
    print(f"niche={dcfg.niche} competitors={dcfg.competitors}")
    print(f"organic format tally: {organic_tally}")
    print(f"paid format tally: {paid_tally}")
    print(f"organic message frame tally: {organic_frame_tally}")
    print(f"paid message frame tally: {paid_frame_tally}")
    print(f"organic mechanics tally: {organic_mechanics_tally}")
    print(f"paid mechanics tally: {paid_mechanics_tally}")
    print(f"actor profile: {synthesize_actor_profile(actor_batch)}")

    gap = None
    gap_error = ""
    try:
        gap = pick_top_gap(scored_organic, scored_paid)
        print(f"gap: {gap}")
    except GapEngineError as e:
        gap_error = str(e)
        print(f"gap: none ({e})")

    if out_dir:
        report_data = _build_report_data(capture_root, dcfg, organic, paid, actor_batch, narrative, gap, gap_error)
        html_out = render_report_html(report_data)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "report.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"report written to {out_path}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cie")
    sub = parser.add_subparsers(dest="command", required=True)

    dr = sub.add_parser(
        "diagnostic-report",
        help="validate a diagnostic-report capture, print the tally/profile/gap, and optionally render report.html",
    )
    dr.add_argument("--config", required=True, help="path to the diagnostic config TOML (niche + optional competitors)")
    dr.add_argument("--fixtures", required=True, help="capture directory (raw/organic.json, raw/paid.json, raw/actor_batch.json, raw/narrative.json)")
    dr.add_argument("--out", help="optional output directory; if given, also renders and writes report.html")

    smoke = sub.add_parser("virlo-smoke", help="free Virlo connectivity smoke test using the repo-owned HTTP client")
    smoke.add_argument("--json", action="store_true", help="print machine-readable JSON")

    live = sub.add_parser("live-report", help="build a live Virlo + ScrapeCreators capture and render report.html")
    live.add_argument("--config", required=True, help="path to the diagnostic config TOML")
    live.add_argument("--out", help="run directory to write; defaults to runs/<niche-slug>")
    live.add_argument("--virlo-orbit-id", help="use a specific existing Virlo Orbit")
    live.add_argument("--virlo-comet-id", help="use a specific existing Virlo Comet")
    live.add_argument("--two-ring", action="store_true", help="use separate buyer context and interest gap-input rings")
    live.add_argument("--buyer-query", help="buyer-context ring query; defaults to config rings.buyer_query or niche")
    live.add_argument("--interest-query", help="interest-ring query for raw/organic.json; defaults to config rings.interest_query or niche")
    live.add_argument("--buyer-virlo-orbit-id", help="use a specific existing Virlo Orbit for the buyer ring")
    live.add_argument("--buyer-virlo-comet-id", help="use a specific existing Virlo Comet for the buyer ring")
    live.add_argument("--interest-virlo-orbit-id", help="use a specific existing Virlo Orbit for the interest ring")
    live.add_argument("--interest-virlo-comet-id", help="use a specific existing Virlo Comet for the interest ring")
    live.add_argument("--max-videos", type=int, default=12, help="max Virlo videos to retain in raw/organic.json")
    live.add_argument("--create-orbit", action="store_true", help="create a paid Virlo Orbit if no existing surface matches")
    live.add_argument("--create-buyer-orbit", action="store_true", help="create a run-created Virlo Orbit for the buyer ring")
    live.add_argument("--create-interest-orbit", action="store_true", help="create a run-created Virlo Orbit for the interest ring")
    live.add_argument("--time-period", default="this_month", help="Virlo time_period when --create-orbit is used")
    live.add_argument("--min-views", type=int, default=0, help="Virlo min_views when --create-orbit is used")
    live.add_argument("--max-paid-competitors", type=int, help="max competitors to pull paid Meta ads for")
    live.add_argument("--max-ads-per-competitor", type=int, default=5, help="max paid ads to retain per competitor")
    live.add_argument("--skip-paid", action="store_true", help="skip ScrapeCreators paid-ad pulls")
    live.add_argument("--no-render", action="store_true", help="only write raw capture files; skip report.html")
    live.add_argument("--guided", action="store_true", help="inspect Virlo surfaces and print the next safe command")
    live.add_argument("--confirm-paid-create", action="store_true", help="confirm approval to create a paid Virlo Orbit")

    args = parser.parse_args(argv)

    if args.command == "diagnostic-report":
        return _render_diagnostic_report(args.config, args.fixtures, args.out)

    if args.command == "virlo-smoke":
        try:
            result = run_virlo_smoke()
        except VirloClientError as e:
            print(f"virlo smoke failed: {e}")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("virlo smoke ok")
            print(f"orbits_seen={result['orbits_seen']} first_orbit={result['first_orbit']}")
            print(f"comets_seen={result['comets_seen']} first_comet={result['first_comet']}")
            for call in result["calls"]:
                print(
                    f"{call['method']} {call['path']} status={call['status']} "
                    f"cost={call['cost']} credits={call['credits_used']}"
                )
        return 0

    if args.command == "live-report":
        try:
            dcfg = load_diagnostic_config(args.config)
        except DiagnosticConfigError as e:
            print(f"invalid config: {e}")
            return 2
        out_dir = args.out or os.path.join("runs", slugify(dcfg.niche))
        if args.guided:
            try:
                if args.two_ring:
                    plan = plan_virlo_two_ring(
                        dcfg,
                        buyer_query=args.buyer_query or "",
                        interest_query=args.interest_query or "",
                        buyer_orbit_id=args.buyer_virlo_orbit_id,
                        buyer_comet_id=args.buyer_virlo_comet_id,
                        interest_orbit_id=args.interest_virlo_orbit_id or args.virlo_orbit_id,
                        interest_comet_id=args.interest_virlo_comet_id or args.virlo_comet_id,
                        time_period=args.time_period,
                        min_views=args.min_views,
                    )
                else:
                    plan = plan_virlo_surface(
                        dcfg,
                        orbit_id=args.virlo_orbit_id,
                        comet_id=args.virlo_comet_id,
                        time_period=args.time_period,
                        min_views=args.min_views,
                    )
            except VirloClientError as e:
                print(f"virlo guided preflight failed: {e}")
                return 2
            print(json.dumps(plan, indent=2))
            return 0
        try:
            preflight = preflight_live_run(dcfg)
            print(f"preflight ok: visual route = {preflight['visual_route']} ({preflight['model']})")
            result = build_virlo_capture(
                dcfg,
                out_dir,
                args.config,
                orbit_id=args.virlo_orbit_id,
                comet_id=args.virlo_comet_id,
                max_videos=args.max_videos,
                create_orbit=args.create_orbit,
                time_period=args.time_period,
                min_views=args.min_views,
                max_paid_competitors=args.max_paid_competitors,
                max_ads_per_competitor=args.max_ads_per_competitor,
                skip_paid=args.skip_paid,
                confirm_paid_create=args.confirm_paid_create,
                two_ring=args.two_ring,
                buyer_query=args.buyer_query or "",
                interest_query=args.interest_query or "",
                buyer_orbit_id=args.buyer_virlo_orbit_id,
                buyer_comet_id=args.buyer_virlo_comet_id,
                interest_orbit_id=args.interest_virlo_orbit_id or args.virlo_orbit_id,
                interest_comet_id=args.interest_virlo_comet_id or args.virlo_comet_id,
                create_buyer_orbit=args.create_buyer_orbit,
                create_interest_orbit=args.create_interest_orbit or (args.create_orbit and args.two_ring),
            )
        except (LiveCaptureError, VirloClientError, ScrapeCreatorsClientError) as e:
            print(f"live report failed: {e}")
            return 2
        selected = result["selected"]
        print(f"live capture written to {out_dir}")
        print(f"virlo {selected['kind']}={selected['id']} name={selected.get('name', '')}")
        print(
            f"organic={result['organic_count']} paid={result['paid_count']} "
            f"actors={result['actor_count']} buyer_context={result.get('buyer_context_count', 0)} "
            f"competitors={result['competitor_count']}"
        )
        resolution = result.get("competitor_resolution") or {}
        resolved_pages = resolution.get("resolved") or []
        dropped = resolution.get("dropped") or []
        if resolved_pages or dropped:
            print(f"competitor pages: resolved {len(resolved_pages)}, dropped {len(dropped)}")
            if dropped:
                print(f"  dropped (no on-niche company page found): {', '.join(dropped)}")
        if args.no_render:
            return 0
        return _render_diagnostic_report(os.path.join(out_dir, "config.toml"), out_dir, out_dir)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
