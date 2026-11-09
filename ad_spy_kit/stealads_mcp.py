"""StealAds field shapes (strength_label / banger_band, why, group_id, run_duration_days)."""

from __future__ import annotations

from typing import Any

from ad_spy_kit.labels import source_label

FORBIDDEN_PUBLIC_KEYS = frozenset({"banger_rank_key", "effectiveness_score"})


def apply_winning_signals(mapped: dict[str, Any], raw: dict[str, Any]) -> None:
    """Map StealAds winning-ad fields; days_live follows run_duration_days when present.

    A label StealAds sent (strength_label or banger_band; "banger" or "winner") is passed
    through as `strength_label` with `label_source: "stealads"`. It is never recomputed.
    """
    sent, label = source_label(raw)
    if sent:
        mapped["strength_label"] = label
        mapped["label_source"] = "stealads"
    mapped["why"] = raw.get("why")
    group = (
        raw.get("group_id")
        or raw.get("groupId")
        or raw.get("collation_id")
        or raw.get("collationId")
    )
    mapped["group_id"] = group
    run_days = raw.get("run_duration_days")
    if run_days is None and raw.get("runDurationDays") is not None:
        run_days = raw.get("runDurationDays")
    mapped["run_duration_days"] = run_days
    if run_days is not None and isinstance(run_days, (int, float)):
        mapped["days_live"] = int(run_days)
    var = raw.get("variation_count")
    if var is not None:
        mapped["variation_count"] = var


def strip_hidden_scores(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that must never appear on public boards."""
    out = {k: v for k, v in doc.items() if k not in FORBIDDEN_PUBLIC_KEYS}
    return out
