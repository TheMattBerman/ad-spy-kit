from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ad_spy_kit.dedupe import creative_keys, merge_duplicates
from ad_spy_kit.labels import strength_label
from ad_spy_kit.template_text import scrub_text

BFCM_LIVE = re.compile(
    r"\b(black\s*friday|cyber\s*monday|bfcm|doorbuster|%+\s*off|\d+%\s*off|"
    r"bundle|gift|ends|last\s*chance|holiday\s*sale)\b",
    re.I,
)
BFCM_TEASER = re.compile(
    r"\b(early\s*access|vip|waitlist|sms\s*list|launch\s*list|presale|pre-sale)\b",
    re.I,
)


def tag_bfcm(ad: dict[str, Any]) -> str:
    text = f"{ad.get('headline', '')} {ad.get('body', '')}"
    if BFCM_TEASER.search(text):
        return "bf_teaser"
    if BFCM_LIVE.search(text):
        return "bf_live"
    return "evergreen"


BOARD_SIZE = 6
MAX_SALE_PROMOTED = 2


def _newest_first(ad: dict[str, Any]) -> str:
    return str(ad.get("start_date") or ad.get("last_seen_at") or "")


def quarantine_entry(ad: dict[str, Any]) -> dict[str, Any]:
    """One quarantined ad, with enough copy that nobody has to open ads.raw.json to see
    whether it contradicts a headline ("none of them name a sale")."""
    return {
        "ad_id": ad["ad_id"],
        "reason": (
            f"<7d and <3 versions (days={ad.get('days_live', 0)}, "
            f"var={ad.get('variation_count', 0)})"
        ),
        "headline": scrub_text(ad.get("headline"))[0],
        "body": scrub_text(ad.get("body"))[0][:200],
        "days_live": ad.get("days_live") or 0,
        "variations": ad.get("variation_count") or 0,
        "bf_tag": tag_bfcm(ad),
    }


def eligible(ad: dict[str, Any]) -> bool:
    if not ad.get("is_active", True):
        return False
    days = ad.get("days_live") or 0
    var = ad.get("variation_count") or 0
    return days >= 7 or var >= 3


def winner_why_line(ad: dict[str, Any], *, rank: int) -> str:
    """Facts-only: MCP `why` when present; else StealAds adWinningSignals-style wording."""
    if ad.get("why"):
        return str(ad["why"])
    days = ad.get("run_duration_days")
    if days is None:
        days = ad.get("days_live")
    parts: list[str] = []
    still_running = ad.get("still_running")
    if still_running is None and ad.get("is_active") is not None:
        # ScrapeCreators rows say is_active, not still_running: a stopped ad "Ran", never "Live".
        still_running = bool(ad["is_active"])
    if days is not None:
        rounded = int(days)
        if still_running is False:
            verb = "Ran"
        else:
            verb = "Live"
        if rounded == 0:
            parts.append(f"{verb} less than a day")
        else:
            parts.append(f"{verb} {rounded} {'day' if rounded == 1 else 'days'}")
    vc = ad.get("variation_count") or 0
    if vc >= 2:
        parts.append(f"{int(vc)} versions")
    if still_running is True or (ad.get("is_active") and still_running is not False):
        parts.append("still running")
    return " · ".join(parts) if parts else f"#{rank}"


def score_winners(ads: list[dict[str, Any]], *, rule_version: str = "w2") -> dict[str, Any]:
    has_bangers = any(a.get("bangers_rank") is not None for a in ads)
    rank_source = "find_bangers" if has_bangers else "fallback_runlength"

    pool = list(ads)
    quarantined: list[dict[str, Any]] = []
    eligible_ads: list[dict[str, Any]] = []

    for ad in pool:
        if eligible(ad):
            eligible_ads.append(ad)
        else:
            quarantined.append(quarantine_entry(ad))

    def sort_key(a: dict[str, Any]) -> tuple:
        br = a.get("bangers_rank")
        if rank_source == "find_bangers" and br is not None:
            return (0, br)
        if rank_source == "find_bangers" and br is None:
            return (
                1,
                -(a.get("days_live") or 0),
                -(a.get("variation_count") or 0),
                -(a.get("effectiveness_score") or 0),
            )
        return (
            0,
            -(a.get("days_live") or 0),
            -(a.get("variation_count") or 0),
            -(a.get("effectiveness_score") or 0),
        )

    eligible_ads.sort(key=sort_key)

    deduped = merge_duplicates(eligible_ads)

    winners_out: list[dict[str, Any]] = []
    formats_seen: set[str] = set()
    thin = len(deduped) < 3

    if thin:
        fallback = sorted(
            pool, key=lambda a: a.get("last_seen_at") or a.get("start_date") or "", reverse=True
        )
        pick = fallback[:6]
    else:
        pick = []
        for ad in deduped:
            if len(pick) >= BOARD_SIZE:
                break
            pick.append(ad)

        # Show at least one ad per format in the eligible set. When the wall is full, the
        # lowest-ranked ad whose format is already shown twice or more makes room.
        def fmt_of(a: dict[str, Any]) -> str:
            return (a.get("format") or "OTHER").upper()

        for fmt in sorted({fmt_of(a) for a in deduped}):
            if any(fmt_of(w) == fmt for w in pick):
                continue
            cand = next((a for a in deduped if fmt_of(a) == fmt and a not in pick), None)
            if cand is None:
                continue
            if len(pick) < 6:
                pick.append(cand)
                continue
            for i in range(len(pick) - 1, -1, -1):
                if sum(fmt_of(w) == fmt_of(pick[i]) for w in pick) > 1:
                    pick[i] = cand
                    break

    # Young ads (under 7 days, under 3 versions) are held back as noise, with two exceptions
    # so the board never silently misleads. Sale and early-access copy is the point of a
    # Black Friday teardown, so up to MAX_SALE_PROMOTED of those go on the board, labeled
    # testing. And a board under six ads fills up with the newest live ads, sale ads first.
    topped_up: set[str] = set()
    shown = {a.get("dedupe_key") or creative_keys(a)[0] for a in pick}
    shown_ids_now = {a["ad_id"] for a in pick}
    young = [
        a
        for a in pool
        if not eligible(a) and a.get("is_active", True) and a["ad_id"] not in shown_ids_now
    ]
    young.sort(key=_newest_first, reverse=True)
    young.sort(key=lambda a: {"bf_live": 0, "bf_teaser": 1}.get(tag_bfcm(a), 2))
    fresh = [a for a in merge_duplicates(young) if (a.get("dedupe_key") or "") not in shown]
    fresh = [
        a
        for a in fresh
        if not (set(creative_keys(a)) & {k for p in pick for k in creative_keys(p)})
    ]
    sale = [a for a in fresh if tag_bfcm(a) in ("bf_live", "bf_teaser")][:MAX_SALE_PROMOTED]
    # A sale ad takes a free spot, else the place of an ad that is just as young. It never
    # pushes out an ad that has run a week or more.
    for ad in sale:
        if len(pick) >= BOARD_SIZE:
            swap = next(
                (i for i in range(len(pick) - 1, -1, -1) if (pick[i].get("days_live") or 0) < 7),
                None,
            )
            if swap is None or pick[swap]["ad_id"] in topped_up:
                continue
            pick.pop(swap)
        pick.append(ad)
        topped_up.add(ad["ad_id"])
    if len(pick) < BOARD_SIZE:
        taken = {a["ad_id"] for a in pick}
        for ad in fresh:
            if len(pick) >= BOARD_SIZE:
                break
            if ad["ad_id"] not in taken:
                pick.append(ad)
                topped_up.add(ad["ad_id"])

    for idx, ad in enumerate(pick, start=1):
        fmt = (ad.get("format") or "OTHER").upper()
        formats_seen.add(fmt)
        winners_out.append(
            {
                "ad_id": ad["ad_id"],
                "bangers_rank": ad.get("bangers_rank"),
                "strength_label": strength_label(ad),
                "days_live": ad.get("days_live", 0),
                "variations": ad.get("variation_count", 0),
                "may_have_stopped": ad.get("may_have_stopped", False),
                "dupes_merged": ad.get("dupes_merged", []),
                "added_while_new": ad["ad_id"] in topped_up,
                "bf_tag": tag_bfcm(ad),
                "why": winner_why_line(ad, rank=idx),
                "format": fmt,
                "display_rank": idx,
            }
        )

    format_mix: dict[str, int] = {}
    for w in winners_out:
        f = w.get("format") or "OTHER"
        format_mix[f] = format_mix.get(f, 0) + 1

    # Quarantined creatives that are not on the board (a copy of a shown creative is not
    # hidden, it is the same ad). The board counts these and the analysis step reads them.
    on_board = {w["ad_id"] for w in winners_out}
    shown_ids = on_board | {i for a in pick for i in a.get("dupes_merged", [])}
    known_keys = {k for a in pool if eligible(a) for k in creative_keys(a)} | {
        k for a in pick for k in creative_keys(a)
    }
    held_back = [
        ad
        for ad in pool
        if ad["ad_id"] not in shown_ids
        and not eligible(ad)
        and not (set(creative_keys(ad)) & known_keys)
    ]
    hidden = []
    for ad in merge_duplicates(held_back):
        entry = quarantine_entry(ad)
        entry["copies"] = 1 + len(ad.get("dupes_merged", []))
        hidden.append(entry)

    return {
        "rule_version": rule_version,
        "computed_at": datetime.now(UTC).isoformat(),
        "pool_size": len(pool),
        "rank_source": rank_source,
        "thin_signal": thin,
        "winners": winners_out,
        "analysis_pool": deduped[:12],
        "quarantined": quarantined,
        "hidden": hidden,
        "format_mix": format_mix,
    }
