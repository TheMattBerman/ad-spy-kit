"""Quote before spending. Every command that costs ScrapeCreators credits prints what it will
spend and runs only on a yes: `--yes` on the command line, or "y" at the prompt when a person
is at the terminal. Agents relay the quote to the user and rerun with `--yes` on their go.
"""

from __future__ import annotations

import math
import sys

# ScrapeCreators bills 1 credit per request. One request finds a brand's page. A brand's ads
# come a page at a time: the first page holds about 30 ads, each later page about 10
# (observed on company/ads in Oct 2026). A brand with fewer ads stops after one page.
CREDITS_PER_SEARCH = 1
FIRST_PAGE_ADS = 30
LATER_PAGE_ADS = 10


def pull_pages(max_ads: int) -> tuple[int, int]:
    """(fewest, most) requests to read up to `max_ads` of a brand's ads."""
    extra = max(0, max_ads - FIRST_PAGE_ADS)
    return 1, 1 + math.ceil(extra / LATER_PAGE_ADS)


def credit_range(low: int, high: int) -> str:
    if low == high:
        return f"{low} ScrapeCreators credit{'s' if low != 1 else ''}"
    return f"{low} to {high} ScrapeCreators credits"


def read_phrase(
    max_ads: int, newest: bool, read: str = "longest", min_days: int | None = None
) -> str:
    """What we read, in plain words. Default: ads live 30+ days, most-shown first."""
    from ad_spy_kit.labels import SOLID_MIN_DAYS

    if newest or read == "newest":
        return f"newest {max_ads} live ads"
    if read == "most-shown":
        return f"{max_ads} most-shown live ads (any age)"
    return f"{max_ads} most-shown ads that have been live {min_days or SOLID_MIN_DAYS}+ days"


def brand_quote(
    brand: str,
    *,
    max_ads: int,
    find_page: bool,
    newest: bool = False,
    fallback: bool = False,
    min_days: int | None = None,
) -> tuple[str, int, int]:
    """(quote, fewest credits, most credits). With `fallback` the quote also says what a
    second read costs when no ad has run 30+ days, and the most includes that read."""
    low, high = pull_pages(max_ads)
    what_ads = read_phrase(max_ads, newest, min_days=min_days)
    if find_page:
        low, high = low + CREDITS_PER_SEARCH, high + CREDITS_PER_SEARCH
        what = f"This finds the Facebook page for {brand} and reads up to its {what_ads}"
    else:
        what = f"This reads up to the {what_ads} from {brand}"
    quote = f"{what}: about {credit_range(low, high)}."
    if fallback and not newest:
        extra_low, extra_high = pull_pages(max_ads)
        quote += (
            f" If none of their ads has run 30+ days, it then reads their newest {max_ads} "
            f"live ads in the same run: {credit_range(extra_low, extra_high)} more, "
            f"{credit_range(low + extra_low, high + extra_high)} in all."
        )
        high += extra_high
    return quote, low, high


def confirm(quote: str, *, yes: bool, rerun: str) -> bool:
    """Print the quote. True means go: --yes, or a "y" from a person at the terminal."""
    print(quote)
    if yes:
        return True
    if sys.stdin.isatty() and sys.stdout.isatty():
        answer = input("Go? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            return True
    print(f"Nothing spent. To go ahead: {rerun}")
    return False


THIN_MIN_RUN_DAYS = 120
THIN_MIN_CREATIVE_SHARE = 0.8
THIN_READ_TARGET = 60


def thin_read_note(ads_raw: dict, run_dir: str = "<run_dir>") -> str | None:
    """A plain note when a single-brand read of 30 ads is too thin to say much, else None.

    Thin means the read hit its cap (the brand has more ads than were read) and either no ad
    has run 120+ days or fewer than 80% of the ads are different creatives (catalog and
    duplicate ads fill the pool). The note says what the next read costs. Only a
    ScrapeCreators read in the default "longest" mode: StealAds reads and newest-ads reads
    have no such cap to raise.
    """
    from ad_spy_kit.dedupe import distinct_creatives

    if ads_raw.get("source") != "scrapecreators" or ads_raw.get("read_mode") != "longest":
        return None
    cap = int(ads_raw.get("read_cap") or 0)
    ads = ads_raw.get("ads") or []
    if not ads or cap >= THIN_READ_TARGET or not ads_raw.get("import_cap_hit"):
        return None
    longest = max((int(a.get("days_live") or 0) for a in ads), default=0)
    creatives = distinct_creatives(ads)
    short_run = longest < THIN_MIN_RUN_DAYS
    repeats = creatives < THIN_MIN_CREATIVE_SHARE * len(ads)
    if not (short_run or repeats):
        return None
    reasons = []
    if short_run:
        reasons.append(f"the longest run is {longest} days")
    if repeats:
        reasons.append(f"the {len(ads)} ads are {creatives} different creatives")
    first = pull_pages(cap or FIRST_PAGE_ADS)[1]
    bigger = pull_pages(THIN_READ_TARGET)[1]
    extra = bigger - first
    return (
        f"Thin read: {' and '.join(reasons)}. This brand has more ads than the {cap} read, "
        f"so older runners may be missing. To read {THIN_READ_TARGET}, "
        f"run: ad-spy-kit pull {run_dir} --max-ads {THIN_READ_TARGET}. "
        f"That costs {credit_range(bigger, bigger)} in all, {extra} more than this read "
        f"(1 credit a request, about 30 ads on the first page and 10 on each after). "
        f"To read only ads already running {THIN_MIN_RUN_DAYS}+ days instead, add "
        f"--min-days {THIN_MIN_RUN_DAYS} at the same cost as this read."
    )
