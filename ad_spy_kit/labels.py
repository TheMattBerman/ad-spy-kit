"""One strength label rule for every route: the single-brand board, the category board and the
saved Ad Library import all call `strength_label()`.

Labels describe what a brand keeps paying for, never whether an ad worked:
- winner: still running 120+ days, or 60+ days with 3+ versions; stopped after 365+ days
  with 3+ versions, or 540+ days.
- solid: 30+ days, or 14+ days with 3+ versions.
- testing: still running, under 30 days (and not solid).
- None: not analyzed by StealAds, or an unknown start date.

StealAds rows carry their own label (`strength_label`, or the older `banger_band`). It is
passed through, never recomputed; "banger" and "winner" both mean the top label. Every other
route (ScrapeCreators pulls, saved Ad Library rows) computes the label from run length and
versions with the thresholds below, which mirror StealAds PR #3343 (interim until it merges).
"""

from __future__ import annotations

from typing import Any

# Display name of the top label. Confirmed by Matt and StealAds.
TOP_LABEL = "winner"
SOLID = "solid"
TESTING = "testing"
LABELS = (TOP_LABEL, SOLID, TESTING)
# Names StealAds (or older kit files) may send for the top label.
TOP_ALIASES = frozenset({"winner", "banger", TOP_LABEL})

# mirrors StealAds #3343, update when it merges
SOLID_MIN_DAYS = 30  # 30+ days is solid; anything live under this is testing...
SOLID_FAST_DAYS = 14  # ...unless it has run 14+ days
SOLID_FAST_VERSIONS = 3  # ...with 3+ versions, which counts as solid
# mirrors StealAds #3343, update when it merges
LIVE_TOP_MIN_DAYS = 120  # still running 120+ days: winner
LIVE_TOP_FAST_DAYS = 60  # or still running 60+ days
LIVE_TOP_FAST_VERSIONS = 3  # with 3+ versions
# mirrors StealAds #3343, update when it merges
STOPPED_TOP_DAYS_WITH_VERSIONS = 365  # stopped: ran 365+ days with 3+ versions
STOPPED_TOP_MIN_VERSIONS = 3
STOPPED_TOP_DAYS = 540  # or ran 540+ days

# Plain-words legend for boards and docs. Built from the constants so it can't drift.
LABEL_MEANINGS = {
    TOP_LABEL: (
        f"live {LIVE_TOP_MIN_DAYS}+ days, or {LIVE_TOP_FAST_DAYS}+ days with "
        f"{LIVE_TOP_FAST_VERSIONS}+ versions"
    ),
    SOLID: (
        f"{SOLID_MIN_DAYS}+ days, or {SOLID_FAST_DAYS}+ days with {SOLID_FAST_VERSIONS}+ versions"
    ),
    TESTING: f"live under {SOLID_MIN_DAYS} days",
}


def normalize_label(value: Any) -> str | None:
    """A label from StealAds or an older file → one of LABELS, or None. Never raises."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in TOP_ALIASES:
        return TOP_LABEL
    if text in (SOLID, TESTING):
        return text
    return None  # unknown label: show no label rather than crash the run


def source_label(raw: dict[str, Any]) -> tuple[bool, str | None]:
    """(StealAds sent a label field, the normalized label). Field names: strength_label,
    strengthLabel, banger_band, bangerBand. A field sent as null means unanalyzed: no label."""
    for key in ("strength_label", "strengthLabel", "banger_band", "bangerBand"):
        if key in raw:
            return True, normalize_label(raw[key])
    return False, None


def _is_live(ad: dict[str, Any]) -> bool | None:
    if ad.get("still_running") is not None:
        return bool(ad["still_running"])
    if ad.get("is_active") is not None:
        return bool(ad["is_active"])
    return None


def _solid(days: float, versions: int) -> bool:
    return days >= SOLID_MIN_DAYS or (days >= SOLID_FAST_DAYS and versions >= SOLID_FAST_VERSIONS)


def label_from_run(ad: dict[str, Any]) -> str | None:
    """The computed label from facts on the ad: live or stopped, days run, versions.

    On the ScrapeCreators route every ad with a known start date counts as analyzed; an
    unknown start date (or live/stopped status) gets no label.
    """
    if ad.get("run_length_unknown"):
        return None
    days = ad.get("days_live")
    live = _is_live(ad)
    if days is None or live is None:
        return None
    days = float(days)
    versions = int(ad.get("variation_count") or 1)
    if live:
        if days >= LIVE_TOP_MIN_DAYS or (
            days >= LIVE_TOP_FAST_DAYS and versions >= LIVE_TOP_FAST_VERSIONS
        ):
            return TOP_LABEL
        return SOLID if _solid(days, versions) else TESTING
    if (
        days >= STOPPED_TOP_DAYS_WITH_VERSIONS and versions >= STOPPED_TOP_MIN_VERSIONS
    ) or days >= STOPPED_TOP_DAYS:
        return TOP_LABEL
    # A stopped ad isn't running, so it can't be "testing"; short stopped runs get no label.
    return SOLID if _solid(days, versions) else None


def strength_label(ad: dict[str, Any]) -> str | None:
    """The one label rule. StealAds label when StealAds sent one, else computed."""
    if ad.get("label_source") == "stealads":
        return normalize_label(ad.get("strength_label"))
    return label_from_run(ad)


def label_source_name(ads: list[dict[str, Any]]) -> str:
    """'stealads' when any ad's label came from StealAds, else 'run_length'."""
    return "stealads" if any(a.get("label_source") == "stealads" for a in ads) else "run_length"
