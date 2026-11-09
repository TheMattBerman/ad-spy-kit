LONG_RUNNER_DAYS_THRESHOLD = 30
MIN_ORGANIC_SAMPLE_SIZE = 3
# Floor the follower denominator so a micro-account can't dominate the gap: a post with
# 11 followers and 5k views would otherwise score views/followers = ~500 and swamp genuinely
# high-reach posts. Absolute views stay in the numerator, so a real viral post (say 240k views
# from a 1k-follower account) is still correctly strong.
FOLLOWER_FLOOR = 5000
ORGANIC_SHRINKAGE_K = 4

from .taxonomy import validate_scoreable_format


class GapEngineError(Exception):
    pass


def _overperformance(record):
    value = record.get("overperformance")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def organic_strength_by_format(organic_records: list) -> dict:
    scoreable = [r for r in organic_records if validate_scoreable_format(r.get("format"))]
    # All-or-nothing scale: within-creator log-lift (~[-3,+3]) and the fallback views/follower
    # ratio (~[0.2,50]) are different units and MUST NOT be pooled/averaged together. Use the
    # over-performance metric only if EVERY scoreable record has it; otherwise fall back to the
    # floored ratio for all of them, so every score in the aggregation is on one scale.
    use_overperformance = bool(scoreable) and all(_overperformance(r) is not None for r in scoreable)
    scores = {}
    for r in scoreable:
        fmt = r["format"]
        if use_overperformance:
            score = float(r["overperformance"])
        else:
            views = r.get("views", 0) or 0
            followers = max(int(r.get("follower_count", 0) or 0), FOLLOWER_FLOOR)
            score = views / followers
        scores.setdefault(fmt, []).append(score)

    all_scores = [score for values in scores.values() for score in values]
    global_mean = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return {
        fmt: (len(values) * (sum(values) / len(values)) + ORGANIC_SHRINKAGE_K * global_mean)
        / (len(values) + ORGANIC_SHRINKAGE_K)
        for fmt, values in scores.items()
    }


def paid_strength_by_format(paid_records: list) -> dict:
    scores = {}
    for r in paid_records:
        fmt = r["format"]
        if not validate_scoreable_format(fmt):
            continue
        scores[fmt] = scores.get(fmt, 0.0) + r["days_active"]
    return scores


def dead_end_formats(paid_records: list) -> set:
    dead = set()
    for r in paid_records:
        if not validate_scoreable_format(r["format"]):
            continue
        if r["still_active"] and r["days_active"] >= LONG_RUNNER_DAYS_THRESHOLD:
            dead.add(r["format"])
    return dead


def rank_gaps(organic_records: list, paid_records: list) -> list:
    organic_scores = organic_strength_by_format(organic_records)
    paid_scores = paid_strength_by_format(paid_records)
    dead = dead_end_formats(paid_records)
    candidates = []
    for fmt, o_score in organic_scores.items():
        if fmt in dead:
            continue
        p_score = paid_scores.get(fmt, 0.0)
        candidates.append(
            {
                "format": fmt,
                "organic_strength": o_score,
                "paid_strength": p_score,
                "gap_score": o_score - p_score,
            }
        )
    candidates.sort(key=lambda c: c["gap_score"], reverse=True)
    return candidates


def pick_top_gap(organic_records: list, paid_records: list) -> dict:
    scoreable_organic_count = len([r for r in organic_records if validate_scoreable_format(r.get("format"))])
    if scoreable_organic_count < MIN_ORGANIC_SAMPLE_SIZE:
        raise GapEngineError(
            f"organic sample too thin to trust a gap read: {scoreable_organic_count} scoreable posts, need >= {MIN_ORGANIC_SAMPLE_SIZE}"
        )
    ranked = rank_gaps(organic_records, paid_records)
    if not ranked:
        raise GapEngineError("no underexplored probe survives (all organic formats already have sustained paid coverage)")
    if ranked[0]["gap_score"] <= 0:
        raise GapEngineError("no positive gap found yet; paid supply meets or exceeds sampled organic pull")
    return ranked[0]
