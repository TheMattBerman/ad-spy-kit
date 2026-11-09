"""Pure persistence and clustering logic for observed creative patterns."""

import math
import time
from collections import Counter

from .gap_engine import FOLLOWER_FLOOR, organic_strength_by_format


STILL_ACTIVE_BONUS = 1.5
COMPETITOR_BREADTH_WEIGHT = 0.5
MIN_PROVEN_PERSISTENCE = 30.0
# Revealed preference needs >=2 advertisers.
MIN_PROVEN_COMPETITORS = 2
RECENCY_HALFLIFE_DAYS = 21.0
ADJACENT_ANGLE_BOOST = 1.5
MIN_EMERGING_CREATORS = 2


def pattern_key(record):
    angle = record.get("message_frame")
    fmt = record.get("format")
    legs = (angle, fmt)
    if any(not isinstance(leg, str) or not leg.strip() for leg in legs):
        return None
    if any(leg == "insufficient-evidence" for leg in legs):
        return None
    return angle, fmt


def paid_persistence(record):
    days_active = record.get("days_active", 0) or 0
    variation_count = max(1, record.get("variation_count", 1) or 1)
    active_multiplier = STILL_ACTIVE_BONUS if record.get("still_active") else 1.0
    return days_active * active_multiplier * (1 + math.log2(variation_count))


class PatternClusters(list):
    def __init__(self, patterns, excluded_count):
        super().__init__(patterns)
        self.excluded_count = excluded_count


def cluster_patterns(paid, organic):
    grouped = {}
    excluded_count = 0
    for source, records in (("paid", paid), ("organic", organic)):
        for record in records:
            key = pattern_key(record)
            if key is None:
                excluded_count += 1
                continue
            grouped.setdefault(key, {"paid": [], "organic": []})[source].append(record)

    patterns = []
    for (angle, fmt), records in grouped.items():
        paid_records = records["paid"]
        organic_records = records["organic"]
        hook_types = Counter(
            record.get("hook_type")
            for rows in records.values()
            for record in rows
            if record.get("hook_type") not in {"hook-unknown", "insufficient-evidence", None}
        )
        organic_scores = organic_strength_by_format(organic_records)
        dates = [record.get("publish_date") for record in organic_records if record.get("publish_date")]
        recency = max(dates) if dates else max((record.get("days_active", 0) or 0 for record in paid_records), default=0)
        patterns.append(
            {
                "angle": angle,
                "format": fmt,
                "hook_types": dict(hook_types),
                # Sort by count desc, then hook name asc, so top_hooks is stable across runs even
                # when the scraper returns records in a different order (equal-frequency ties).
                "top_hooks": [hook for hook, _ in sorted(hook_types.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
                "paid_count": len(paid_records),
                "organic_count": len(organic_records),
                "distinct_competitors": len({r.get("competitor_name") for r in paid_records if r.get("competitor_name")}),
                "distinct_creators": len({r.get("creator_handle") for r in organic_records if r.get("creator_handle")}),
                "paid_persistence": sum(paid_persistence(record) for record in paid_records),
                "organic_strength": organic_scores.get(fmt, 0.0),
                "recency": recency,
                "organic_records": organic_records,
                "creatives": [_creative_ref(record, source) for source, rows in records.items() for record in rows],
            }
        )
    return PatternClusters(patterns, excluded_count)


def _creative_ref(record, source):
    if source == "paid":
        return record.get("ad_id") or record.get("ad_library_url") or record.get("creative_url") or ""
    return record.get("post_url") or record.get("video_url") or record.get("thumbnail_url") or ""


def proven_score(pattern):
    return pattern["paid_persistence"] * (
        1 + COMPETITOR_BREADTH_WEIGHT * (pattern.get("distinct_competitors", 0) - 1)
    )


def rank_proven(patterns, own_brand_keys=None):
    ranked = []
    for pattern in patterns:
        if pattern.get("paid_persistence", 0.0) < MIN_PROVEN_PERSISTENCE:
            continue
        if pattern.get("distinct_competitors", 0) < MIN_PROVEN_COMPETITORS:
            continue
        result = dict(pattern)
        result["proven_score"] = proven_score(result)
        if own_brand_keys is not None:
            result["absent_from_own"] = (result["angle"], result["format"]) not in own_brand_keys
        ranked.append(result)
    return sorted(ranked, key=lambda pattern: pattern["proven_score"], reverse=True)


def engagement_rate(record):
    return ((record.get("saves") or 0) + (record.get("shares") or 0)) / max(record.get("views", 0) or 0, 1)


def recency_weight(publish_ts, now_ts):
    if publish_ts is None:
        return 1.0
    # A single run is a snapshot, so recency is only a proxy for a true time-series slope.
    age_days = max(0, (now_ts - publish_ts) / 86400)
    return 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)


def emerging_score(pattern, now_ts, use_overperformance=None):
    if pattern.get("distinct_creators", 0) < MIN_EMERGING_CREATORS:
        return 0.0
    records = pattern.get("organic_records", [])
    if use_overperformance is None:
        # Standalone call: decide over this pattern's own records. rank_emerging passes a global
        # decision so cross-pattern scores stay on one scale.
        use_overperformance = bool(records) and all(_overperformance(record) is not None for record in records)
    return sum(
        max(0, _organic_contribution(record, use_overperformance))
        * engagement_rate(record)
        * recency_weight(record.get("publish_ts"), now_ts)
        for record in records
    )


def rank_emerging(patterns, proven_angles, now_ts=None):
    now_ts = time.time() if now_ts is None else now_ts
    # Decide the log-lift-vs-ratio scale ONCE across every pattern's records, so the cross-pattern
    # sort compares one scale (mirrors gap_engine.organic_strength_by_format's global all-or-nothing).
    # If any record anywhere lacks a creator-baseline overperformance, fall back to the ratio scale
    # for all patterns rather than pooling two incomparable units into one sort.
    all_records = [rec for pattern in patterns for rec in pattern.get("organic_records", [])]
    use_overperformance = bool(all_records) and all(_overperformance(rec) is not None for rec in all_records)
    ranked = []
    for pattern in patterns:
        result = dict(pattern)
        adjacent = result.get("angle") in proven_angles
        score = emerging_score(result, now_ts, use_overperformance)
        if adjacent:
            score *= ADJACENT_ANGLE_BOOST
        if score <= 0:
            continue
        result["emerging_score"] = score
        result["adjacent_to_proven"] = adjacent
        ranked.append(result)
    return sorted(ranked, key=lambda pattern: pattern["emerging_score"], reverse=True)


def _overperformance(record):
    value = record.get("overperformance")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _organic_contribution(record, use_overperformance):
    if use_overperformance:
        return record["overperformance"]
    return (record.get("views", 0) or 0) / max(int(record.get("follower_count", 0) or 0), FOLLOWER_FLOOR)
