"""Whole-category run: several brands' ads on one sorted board.

    ad-spy-kit category "black friday skincare"            # keyword: find the brands
    ad-spy-kit category "Spacegoods, Magic Mind, Everyday Dose"   # or name them
    ad-spy-kit category --from runs/category/skincare       # redraw saved data, no credits

Quotes the ScrapeCreators credits first and spends nothing without a yes. By default reads
each brand's ads that have been live 30+ days, most-shown first (up to `--max-ads`, 30);
`--newest` reads the newest live ads instead. Labels every ad with the shared rule,
embeds each image in the board so it survives being moved or shared, and runs the same
board checks as the single-brand board (validate_run.board_html_errors).
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ad_spy_kit.errors import KitError
from ad_spy_kit.exclusions import check_not_excluded
from ad_spy_kit.labels import LABEL_MEANINGS, LABELS, SOLID_MIN_DAYS, TOP_LABEL, strength_label
from ad_spy_kit.paths import is_junk, visible
from ad_spy_kit.score_winners import tag_bfcm, winner_why_line
from ad_spy_kit.spend import CREDITS_PER_SEARCH, credit_range, pull_pages, read_phrase

DEFAULT_MAX_ADS = 30
# A category board shows at most 10 brands (StealAds caps category pulls at 10 brands x 10
# ads). A longer scan (--brands-file) still reads every brand; the board shows the top 10.
MAX_BOARD_BRANDS = 10
DEFAULT_MAX_BRANDS = MAX_BOARD_BRANDS
TRACKED_MAX_ADS = 50
DEFAULT_SEARCH_PAGES = 2
CARDS_PER_BRAND = 3
# Pages that run category keywords but aren't brands (review, community and affiliate pages).
NOT_A_BRAND = re.compile(r"review|talk|community|journal|curfew|insider|^vsdv$", re.I)
LABEL_ORDER = {label: i for i, label in enumerate(LABELS)}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "brand"


def parse_target(target: str) -> tuple[str, list[str] | str]:
    """'a, b, c' → ('brands', [...]); anything else → ('keyword', text)."""
    parts = [p.strip() for p in re.split(r"[,;\n]", target) if p.strip()]
    if len(parts) > 1:
        return "brands", parts
    return "keyword", target.strip()


def quote(
    mode: str,
    target: list[str] | str,
    *,
    max_ads: int,
    max_brands: int,
    search_pages: int,
    newest: bool = False,
) -> tuple[str, int, int]:
    """What the run will spend, in plain words, plus the (low, high) credit range."""
    from ad_spy_kit.sc_client import page_id_from_query

    low_pull, high_pull = pull_pages(max_ads)
    what = read_phrase(max_ads, newest)
    if mode == "keyword":
        brands = max_brands
        low = 1 + brands * low_pull
        high = search_pages * CREDITS_PER_SEARCH + brands * high_pull
        text = (
            f"This searches the Ad Library for '{target}' to find up to {count_brands(brands)}, "
            f"then reads each brand's {what}: about {credit_range(low, high)}."
        )
        return text, low, high
    names = list(target)
    finds = sum(1 for n in names if not page_id_from_query(n))
    low = finds + len(names) * low_pull
    high = finds + len(names) * high_pull
    find = f"finds {brands_possessive(finds)} Facebook page and " if finds == 1 else ""
    if finds > 1:
        find = f"finds {finds} brands' Facebook pages and "
    text = (
        f"This {find}reads each of {brands_possessive(len(names))} {what}: "
        f"about {credit_range(low, high)}."
    )
    return text, low, high


# ---- live pulls (ScrapeCreators, only after a yes) -------------------------------------


def discover(client: Any, keyword: str, pages: int, country: str) -> list[dict[str, Any]]:
    from ad_spy_kit.sc_client import ScrapeCreatorsClientError
    from cie.scrapecreators_client import ScrapeCreatorsClientError as CieErr

    rows: list[dict[str, Any]] = []
    params: dict[str, Any] = {
        "query": keyword,
        "country": country,
        "status": "ACTIVE",
        "sort_by": "total_impressions",
        "trim": "true",
    }
    for _ in range(pages):
        try:
            body = client.request("/v1/facebook/adLibrary/search/ads", params=params)
        except CieErr as e:
            raise ScrapeCreatorsClientError(str(e), getattr(e, "status", None)) from e
        rows += body.get("searchResults") or []
        if not body.get("cursor"):
            break
        params = {**params, "cursor": body["cursor"]}
    return rows


def pick_brands(rows: list[dict[str, Any]], n: int, country: str = "US") -> list[dict[str, Any]]:
    """The pages that ran the most matching ads, skipping non-brands and excluded brands."""
    from ad_spy_kit.errors import ExcludedBrand

    hits: Counter[str] = Counter()
    names: dict[str, str] = {}
    for r in rows:
        pid, name = str(r.get("page_id") or ""), str(r.get("page_name") or "")
        if not pid or not name or NOT_A_BRAND.search(name):
            continue
        hits[pid] += 1
        names[pid] = name
    picked: list[dict[str, Any]] = []
    for pid, count in hits.most_common():
        try:
            check_not_excluded(names[pid], pid)
        except ExcludedBrand:
            continue
        picked.append(
            {"page_id": pid, "page_name": names[pid], "country": country, "matches": count}
        )
        if len(picked) >= n:
            break
    return picked


def load_brands_file(path: Path) -> list[dict[str, Any]]:
    """A CSV of brands to read: name, page_id, and optional country and sources columns."""
    import csv

    if not path.is_file():
        raise KitError(
            f"{path} isn't a file.",
            fix="Pass a CSV with name and page_id columns (country is optional).",
            code="brands_file_missing",
        )
    brands, seen = [], set()
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            pid = str(row.get("page_id") or "").strip()
            if not pid.isdigit() or pid in seen:
                continue
            seen.add(pid)
            brands.append(
                {
                    "page_id": pid,
                    "page_name": (row.get("name") or f"Page {pid}").strip(),
                    "country": (row.get("country") or "").strip().upper() or None,
                    "sources": row.get("sources") or "",
                    "source": "scrapecreators",
                }
            )
    if not brands:
        raise KitError(
            f"{path} has no rows with a numeric page_id.",
            fix="Columns needed: name, page_id (country optional).",
            code="brands_file_empty",
        )
    return brands


def brand_dir(out: Path, brand: dict[str, Any]) -> Path:
    name = slug(brand.get("page_name") or "brand")
    pid = brand.get("page_id") or ""
    return out / "brands" / (f"{name}-{pid}" if pid and pid not in name else name)


def already_read(out: Path, brand: dict[str, Any]) -> bool:
    """Resume: a brand whose ads.raw.json is saved is never read (or paid for) again."""
    return (brand_dir(out, brand) / "ads.raw.json").is_file()


def pull_brands(
    brands: list[dict[str, Any]],
    out: Path,
    *,
    max_ads: int,
    country: str,
    newest: bool = False,
    read: str | None = None,
    max_credits: int | None = None,
    workers: int = 1,
    images: bool = True,
    progress=print,
) -> list[str]:
    """Read each brand into out/brands/<name>-<page id>/. Returns one line per brand that
    failed or was left for later.

    Saved brands are skipped, so a rerun after a crash spends nothing twice. With
    max_credits, a brand only starts when its worst case still fits under the cap.
    Several workers read in parallel; each brand's own retries handle rate limits.
    Each ad's image is saved under the brand's media/ as it's read (Meta's links expire),
    using only the URLs already in the read; `images=False` skips that.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from ad_spy_kit.sc_client import image_counts, pull_via_scrapecreators

    read = read or ("newest" if newest else "longest")
    worst = pull_pages(max_ads)[1]
    todo = [b for b in brands if not already_read(out, b)]
    done_before = len(brands) - len(todo)
    if done_before:
        progress(f"  {done_before} brands already saved in {out}, skipping them (no credits).")
    lock = threading.Lock()
    state = {
        "spent": _credits_in(out) if out.exists() else 0,
        "reserved": 0,
        "n": 0,
        "images": 0,
        "image_failed": 0,
    }
    failed: list[str] = []
    fatal: list[KitError] = []

    def one(brand: dict[str, Any]) -> None:
        with lock:
            if fatal:
                return
            if max_credits is not None and (
                state["spent"] + state["reserved"] + worst > max_credits
            ):
                failed.append(f"{brand['page_name']}: left for later, credit cap {max_credits}")
                return
            state["reserved"] += worst
        run_dir = brand_dir(out, brand)
        run_dir.mkdir(parents=True, exist_ok=True)
        spent, note = 0, ""
        try:
            ads_raw = pull_via_scrapecreators(
                brand,
                country=brand.get("country") or country,
                max_ads=max_ads,
                media_dir=run_dir / "media" if images else None,
                read=read,
            )
            spent = int(ads_raw.get("credits_spent") or 1)
            (run_dir / "competitor.json").write_text(json.dumps(brand, indent=2) + "\n")
            (run_dir / "ads.raw.json").write_text(json.dumps(ads_raw, indent=2) + "\n")
            note = f"{len(ads_raw['ads'])} ads"
            if images and ads_raw["ads"]:
                n = image_counts(ads_raw["ads"], ads_raw.get("skipped") or [])
                note += f", {n['saved']} images"
                if n["failed"]:
                    note += f" ({n['failed']} wouldn't download)"
                with lock:
                    state["images"] += n["saved"]
                    state["image_failed"] += n["failed"]
        except KitError as e:
            spent = 1  # assume the failed call was billed; better to over-count
            failed.append(f"{brand['page_name']}: {e.message}")
            note = f"failed: {e.message}"
            if e.code in ("scrapecreators_key_rejected", "scrapecreators_no_credits"):
                with lock:
                    fatal.append(e)
        with lock:
            state["reserved"] -= worst
            state["spent"] += spent
            state["n"] += 1
            progress(
                f"  [{done_before + state['n']}/{len(brands)}] {brand['page_name']}: {note} "
                f"({state['spent']} credits so far)"
            )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, todo))
    if fatal:
        raise fatal[0]
    if images and state["n"]:
        failed_note = (
            f", {state['image_failed']} wouldn't download (left off the board)"
            if state["image_failed"]
            else ""
        )
        progress(f"  Saved {state['images']} ad images{failed_note}.")
    return failed


def resolve_brands(names: list[str], country: str) -> list[dict[str, Any]]:
    from ad_spy_kit.sc_client import resolve_via_scrapecreators

    out = []
    for name in names:
        comp = resolve_via_scrapecreators(name, country=country)
        if comp["confidence"] == "ambiguous":
            print(f"  '{name}' matched more than one page; using {comp['page_name']}.")
        out.append(comp)
    return out


# ---- the board (from saved brand folders; no network) ----------------------------------


def hook_line(ad: dict[str, Any]) -> str:
    """The ad's own words: headline, else the first sentence of the caption."""
    head = (ad.get("headline") or "").strip()
    is_link = bool(re.fullmatch(r"(https?://)?(www\.)?[\w-]+(\.[\w-]+)+/?\S*", head))
    if head and not head.startswith("{{") and not is_link:
        text = head
    else:
        body = re.sub(r"\s+", " ", ad.get("body") or "").strip()
        text = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0] if body else ""
    text = text.strip().strip('"\u201c\u201d').strip()  # the board adds its own quote marks
    return text if len(text) <= 90 else text[:87].rstrip() + "…"


def _image_path(brand_dir: Path, ad: dict[str, Any]) -> Path | None:
    """The ad's saved image if it opens as an image; else None (the card shows no box)."""
    from PIL import Image, UnidentifiedImageError

    for m in ad.get("media") or []:
        path = brand_dir / m["path"] if m.get("path") else None
        if path and path.is_file():
            try:
                with Image.open(path) as im:
                    im.verify()
            except (UnidentifiedImageError, OSError):
                continue
            return path
    return None


def select(
    ads: list[dict[str, Any]], n: int, *, newest: bool = False, read: str | None = None
) -> list[dict[str, Any]]:
    """longest (default): live ads run 30+ days, longest first. newest: newest live ads.
    most-shown: live ads of any age in the order the Ad Library returned (most-shown first)."""
    read = read or ("newest" if newest else "longest")
    live = [a for a in ads if a.get("is_active", True)]
    if read == "most-shown":
        return live[:n]
    if read == "newest":
        return sorted(live, key=lambda a: str(a.get("start_date") or ""), reverse=True)[:n]
    long = [a for a in live if (a.get("days_live") or 0) >= SOLID_MIN_DAYS]
    return sorted(long, key=lambda a: -(a.get("days_live") or 0))[:n]


def _credits_in(folder: Path) -> int:
    total = 0
    brands_dir = folder / "brands"
    files = brands_dir.glob("*/ads.raw.json") if brands_dir.is_dir() else []
    for p in (f for f in files if not is_junk(f.parent) and not is_junk(f)):
        total += int(json.loads(p.read_text()).get("credits_spent") or 0)
    return total


def load_saved(
    folder: Path, *, max_ads: int, newest: bool = False, read: str | None = None
) -> list[dict[str, Any]]:
    """folder/brands/<slug>/{competitor.json, ads.raw.json, media/} → brand dicts."""
    brands_dir = folder / "brands"
    if not brands_dir.is_dir():
        raise KitError(
            f"{folder} has no brands/ folder, so there's nothing to draw.",
            fix="Point --from at the folder a category run saved (it has brands/ inside).",
            code="category_nothing_saved",
        )
    brands = []
    dirs = [p for p in brands_dir.iterdir() if not is_junk(p) and p.is_dir()]
    for d in sorted(p for p in dirs if (p / "ads.raw.json").is_file()):
        comp = json.loads((d / "competitor.json").read_text())
        ads_raw = json.loads((d / "ads.raw.json").read_text())
        brands.append(
            {
                "name": comp.get("page_name") or d.name,
                "page_id": comp.get("page_id") or "",
                "dir": d,
                "pulled_at": ads_raw.get("pulled_at") or "",
                "ads": select(ads_raw.get("ads") or [], max_ads, newest=newest, read=read),
            }
        )
    return brands


def _card_order(ad: dict[str, Any]) -> tuple:
    live = bool(ad.get("is_active", True))
    return (LABEL_ORDER.get(ad["label"], len(LABELS)), not live, -ad["days_live"], -ad["versions"])


def is_catalog(ad: dict[str, Any]) -> bool:
    """A catalog ad: Meta fills in the product from the store feed, so there's no written
    copy (the text is a template like {{product.name}}). It can run for months as one
    campaign, which says nothing about a specific ad, so it never fills a card."""
    text = f"{ad.get('headline') or ''} {ad.get('body') or ''}"
    return (
        bool(ad.get("catalog") and not ad.get("copy_hook"))
        or "{{" in text
        or str(ad.get("format") or "").upper() == "DPA"
    )


# What the newsletter asks: does the ad say Black Friday, and does it say "up to X% off"?
BLACK_FRIDAY = re.compile(
    r"black[\s-]*friday|cyber[\s-]*monday|black[\s-]*week|cyber[\s-]*week|\bbfcm\b", re.I
)
UP_TO_OFF = re.compile(r"\bup\s*to\s*\d{1,3}\s*%(\s*off)?", re.I)


def mention_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts by age (live 30+ days vs under 30) of ads that say Black Friday (or Cyber
    Monday / Black Week) and ads that say "up to X% off". Catalog ads count when their
    caption says it; a template product name can't."""

    def bucket(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "ads": len(rows),
            "black_friday": sum(bool(BLACK_FRIDAY.search(r["text"])) for r in rows),
            "up_to_off": sum(bool(UP_TO_OFF.search(r["text"])) for r in rows),
        }

    live = [e for e in events if e.get("is_active", True)]
    return {
        "live_30_plus": bucket([e for e in live if e["days_live"] >= SOLID_MIN_DAYS]),
        "live_under_30": bucket([e for e in live if e["days_live"] < SOLID_MIN_DAYS]),
        "all": bucket(events),
    }


def build(
    brands: list[dict[str, Any]],
    *,
    title: str,
    query: str = "",
    newest: bool = False,
    read: str | None = None,
    rank: str = "labels",
) -> dict[str, Any]:
    """Label every ad, pick each brand's top cards, count the labels. No ad IDs leave here
    except under `_ad_id` (joins only, never rendered).

    `rank` orders the brands: "labels" (winners, then solids, then written ads) or "long"
    (most ads live 30+ days first, the tracked-competitors board)."""
    read = read or ("newest" if newest else "longest")
    newest = read == "newest"
    events: list[dict[str, Any]] = []
    out_brands: list[dict[str, Any]] = []
    empty: list[str] = []
    for b in brands:
        rows = []
        for a in b["ads"]:
            img = _image_path(b["dir"], a)
            rows.append(
                {
                    "brand": b["name"],
                    "label": strength_label(a),
                    "why": winner_why_line(a, rank=0),
                    "hook": hook_line(a),
                    "leads": lead_kinds(opening_line(a)),
                    "bf_tag": tag_bfcm(a),
                    "format": a.get("format"),
                    "is_active": a.get("is_active", True),
                    "days_live": int(a.get("days_live") or 0),
                    "versions": int(a.get("variation_count") or 1),
                    "image": str(img) if img else None,
                    "catalog": is_catalog(a),
                    "text": f"{a.get('headline') or ''} {a.get('body') or ''}",
                    "start_date": a.get("start_date") or "",
                    "cta": a.get("cta") or "",
                    "landing_domain": a.get("landing_domain") or "",
                    "spoken_hook": bool(a.get("spoken_hook")),
                    "page_id": b.get("page_id") or "",
                    "_ad_id": a.get("ad_id"),
                }
            )
        if not rows:
            empty.append(b["name"])
            continue
        top, seen = [], set()
        written = [r for r in rows if not r["catalog"]]
        for r in sorted(written, key=_card_order):  # one card per distinct ad, not per version
            key = r["hook"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            top.append(r)
            if len(top) == CARDS_PER_BRAND:
                break
        counts = Counter(r["label"] for r in written)
        out_brands.append(
            {
                "name": b["name"],
                "ads": len(rows),
                "written": len(written),
                "catalog": len(rows) - len(written),
                "long_run": sum(
                    1 for r in rows if r["is_active"] and r["days_live"] >= SOLID_MIN_DAYS
                ),
                "counts": counts,
                "top": top,
            }
        )
        events += rows
    if not events:
        if read != "longest":
            raise KitError(
                "None of these brands has a live ad right now.",
                fix="Try a broader keyword, or name the brands yourself.",
                code="category_empty",
            )
        raise KitError(
            f"None of these brands has an ad that's been live {SOLID_MIN_DAYS}+ days.",
            fix="Add --newest to see their newest live ads instead.",
            code="category_empty",
        )
    pulled = max((b["pulled_at"] for b in brands if b.get("pulled_at")), default="")
    if rank == "long":
        out_brands.sort(
            key=lambda b: (-b["long_run"], -b["counts"].get(TOP_LABEL, 0), -b["ads"], b["name"])
        )
    else:
        out_brands.sort(
            key=lambda b: (
                -b["counts"].get(TOP_LABEL, 0),
                -b["counts"].get("solid", 0),
                -b["written"],
                b["name"],
            )
        )
    return {
        "title": title,
        "rank": rank,
        "query": query,
        "newest": newest,
        "read": read,
        "checked_date": _pretty_date(pulled),
        "stats": mention_stats(events),
        "max_ads": max((len(b["ads"]) for b in brands), default=0),
        "summary": _summary(events, len(out_brands)),
        "brands": out_brands,
        "no_ads": empty,
        "events": events,
    }


def _summary(events: list[dict[str, Any]], brands: int) -> dict[str, Any]:
    """The counts the board and summary print, for these events and this many brands."""
    counts = Counter(e["label"] for e in events)
    written = [e for e in events if not e["catalog"]]
    wcounts = Counter(e["label"] for e in written)
    ccounts = Counter(e["label"] for e in events if e["catalog"])
    return {
        "ads": len(events),
        "brands": brands,
        **{label: counts.get(label, 0) for label in LABELS},
        "no_label": counts.get(None, 0),
        "black_friday": sum(e["bf_tag"] == "bf_live" for e in events),
        "written": len(written),
        "catalog": len(events) - len(written),
        "written_labels": {label: wcounts.get(label, 0) for label in LABELS},
        "catalog_labels": {label: ccounts.get(label, 0) for label in LABELS},
    }


def board_view(result: dict[str, Any], board_brands: int = MAX_BOARD_BRANDS) -> dict[str, Any]:
    """The result cut to the brands the board shows (never more than 10), with every count
    recomputed for just those brands, so the numbers on the image match the pictures."""
    n = max(1, min(board_brands, MAX_BOARD_BRANDS))
    top = result["brands"][:n]
    names = {b["name"] for b in top}
    events = [e for e in result.get("events") or [] if e["brand"] in names]
    summary = {**result["summary"], **_summary(events, len(top))}
    return {
        **result,
        "brands": top,
        "events": events,
        "summary": summary,
        "stats": mention_stats(events),
    }


def count_brands(n: int) -> str:
    """'1 brand', '2 brands'."""
    return f"{n} brand" if n == 1 else f"{n} brands"


def brands_possessive(n: int) -> str:
    """ "1 brand's", "2 brands'"."""
    return f"{n} brand's" if n == 1 else f"{n} brands'"


def _pretty_date(text: str) -> str:
    try:
        d = date.fromisoformat(str(text)[:10])
    except ValueError:
        d = datetime.now(UTC).date()
    return f"{d:%b} {d.day}, {d.year}"


def _thumb_b64(path: str, width: int = 360) -> str:
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def headline(result: dict[str, Any], *, cap: int) -> tuple[str, str]:
    """(title line, subtitle) that never promise more than the ads show."""
    s = result["summary"]
    n = s["brands"]
    # One brand reads as that brand ("What Bellroy keeps running"), never "1 brands".
    one = result["brands"][0]["name"] if n == 1 and result.get("brands") else ""
    each = f"{one}'s" if one else "Each brand's"
    if result.get("read") == "most-shown":
        st = result.get("stats") or {}
        old = (st.get("live_30_plus") or {}).get("ads", 0)
        new = (st.get("live_under_30") or {}).get("ads", 0)
        who = f"What {one} is" if one else f"What {count_brands(n)} are"
        return (
            f"{who} showing most right now",
            f"{each} {cap} most-shown live ads, any age: {s['ads']} ads in all. "
            f"{old} have run {SOLID_MIN_DAYS}+ days and {new} are under {SOLID_MIN_DAYS} days.",
        )
    if result.get("newest"):
        young = s.get("testing", 0)
        return (
            f"The newest ads from {one or count_brands(n)}",
            f"{each} newest {cap} live ads. {young} of {s['ads']} have been live under "
            f"{SOLID_MIN_DAYS} days, so this shows what they're trying, not what they keep "
            "running.",
        )
    upto = "" if result.get("rank") == "long" else f" (up to {cap})"
    sub = (
        f"{each} ads that have been live {SOLID_MIN_DAYS}+ days{upto}, longest "
        f"first. {s['ads']} ads in all."
    )
    if s.get("catalog"):
        sub += (
            f" {s['catalog']} of them are catalog ads: Meta fills in the product from the "
            "store, so there are no words to quote."
        )
    return (f"What {one} keeps running" if one else f"What {count_brands(n)} keep running", sub)


def _no_ads_phrase(result: dict[str, Any]) -> str:
    if result.get("read") == "longest":
        return f"No ads live {SOLID_MIN_DAYS}+ days"
    return "No live ads"


# What an ad leads with, read off its opening line (headline, else first sentence). Each
# kind names a contrast: the lead nobody uses is the gap a founder can take.
LEADS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "review_count",
        "a giant review count",
        re.compile(
            r"\d[\d,.]*\s*[km]?\s*\+?\s*(?:five|5)[\s-]*stars?\b"
            r"|\d[\d,.]*\s*[km]?\s*\+\s*(?:reviews|ratings|customers)"
            r"|\d{1,3}(?:,\d{3})+\s*(?:reviews|ratings|customers|happy customers)",
            re.I,
        ),
    ),
    (
        "one_review",
        "a single real review",
        re.compile(
            r'^\s*["\u201c].{12,}["\u201d]|\u2605{4,}|\bverified (?:buyer|customer|review)', re.I
        ),
    ),
    ("percent_off", "a percent off", re.compile(r"\d{1,2}\s*%\s*off|\bsave\s+\d{1,2}\s*%", re.I)),
    ("free", "something free", re.compile(r"\bfree\b", re.I)),
)
LEAD_CONTRAST = {
    "review_count": "one_review",
    "one_review": "review_count",
    "percent_off": "free",
    "free": "percent_off",
}
LEAD_NAMES = {key: name for key, name, _ in LEADS}


def opening_line(ad: dict[str, Any]) -> str:
    """The raw first thing the ad says (quote marks kept, so a quoted review reads as one)."""
    head = (ad.get("headline") or "").strip()
    if head and not head.startswith("{{"):
        return head
    body = re.sub(r"\s+", " ", ad.get("body") or "").strip()
    return re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0] if body else ""


def lead_kinds(text: str) -> list[str]:
    return [key for key, _, rx in LEADS if rx.search(text or "")]


def _join_names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def pattern_lines(result: dict[str, Any]) -> list[str]:
    """What several brands lead with in common, and what none of them lead with. Only
    written ads count (a catalog headline is a template). Nothing when no lead is shared
    by 2+ brands: no filler."""
    by_kind: dict[str, set[str]] = {key: set() for key in LEAD_NAMES}
    brands = set()
    for ev in result.get("events") or []:
        if ev.get("catalog"):
            continue
        brands.add(ev["brand"])
        for kind in ev.get("leads") or []:
            by_kind[kind].add(ev["brand"])
    shared = [k for k in LEAD_NAMES if len(by_kind[k]) >= 2 and len(by_kind[k]) < len(brands)]
    if len(brands) < 3 or not shared:
        return []
    top = max(shared, key=lambda k: len(by_kind[k]))  # ties: LEADS order
    names = sorted(by_kind[top])
    lines = [f"{len(names)} brands lead with {LEAD_NAMES[top]}: {_join_names(names)}."]
    other = LEAD_CONTRAST.get(top)
    if other and not by_kind[other]:
        lines.append(f"None lead with {LEAD_NAMES[other]}.")
    return [" ".join(lines)]


WALL_CAP = 240  # tiles on the density wall


def _brand_wall(result: dict[str, Any]) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Every brand with a picture, each with up to 3 distinct ads (label, then run length).
    Pictures carry the board; the brand name is the only words over them."""
    events = result.get("events") or []
    groups = []
    left = WALL_CAP
    for b in result["brands"]:
        if left <= 0:
            break
        seen: set[str] = set()
        pics = []
        for ev in sorted((x for x in events if x["brand"] == b["name"]), key=_card_order):
            key = ev["image"] or ""
            if ev.get("image") and key not in seen:
                seen.add(key)
                pics.append(ev)
            if len(pics) == CARDS_PER_BRAND:
                break
        pics = pics[:left]
        if pics:
            groups.append((b, pics))
            left -= len(pics)
    return groups


def board_html(result: dict[str, Any], *, cap: int, board_brands: int = MAX_BOARD_BRANDS) -> str:
    """The board is pictures and big numbers only. Anything a viewer couldn't read in a
    2-second video frame (label meanings, per-ad quotes, dates, brands with nothing live)
    lives in summary.md and ads.csv. At most 10 brands; every count is for those brands."""
    e = html.escape
    result = board_view(result, board_brands)
    s = result["summary"]
    events = result.get("events") or []

    def pill(label: str | None) -> str:
        return f'<span class="lab {e(label)}">{e(label)}</span>' if label else ""

    groups = _brand_wall(result)
    shown = sum(len(pics) for _, pics in groups)
    group_html = "".join(
        '<div class="grp">'
        f'<h2><span class="q">{e(b["name"])}</span>'
        '</h2><div class="tiles">'
        + "".join(
            f'<img class="t {e(ev["label"] or "none")}" '
            f'src="{_thumb_b64(ev["image"], 160)}" alt="">'
            for ev in pics
        )
        + "</div></div>"
        for b, pics in groups
    )
    title, _ = headline(result, cap=cap)
    longest = max((ev["days_live"] for ev in events), default=0)
    label_ctr = "".join(
        f'<span class="lc"><b>{s.get(label, 0)}</b>{pill(label)}</span>'
        for label in LABELS
        if s.get(label)
    )
    wall_block = (
        f'<section class="wall"><div class="wh"><b>ads with a picture</b>'
        f"<span>{shown} of {s['ads']} shown</span></div>"
        f'<div class="groups">{group_html}</div></section>'
        if groups
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{e(title)}</title><style>
*{{box-sizing:border-box}}
body{{margin:0;background:#d7d8d3;color:#0b0b0b;font-family:"Helvetica Neue",Helvetica,Arial,Inter,
sans-serif;padding:44px 48px 36px}}
.ctr .k,.wh,footer{{font-family:"SF Mono",Menlo,"JetBrains Mono","DejaVu Sans Mono",
monospace}}
.eyebrow b{{display:inline-block;background:#0b0b0b;color:#fff;font-size:32px;font-weight:700;
letter-spacing:-.01em;padding:6px 16px}}
h1{{font-size:108px;font-weight:700;letter-spacing:-.05em;line-height:1;margin:16px 0 26px}}
.ctrs{{display:grid;grid-template-columns:1fr 1fr 1.15fr 1.9fr;gap:16px;margin-bottom:24px}}
.ctr{{background:#fafaf7;border:3px solid #0b0b0b;padding:12px 20px 10px}}
.ctr.blk{{background:#0b0b0b;color:#fff}}
.ctr .k{{font-size:26px;text-transform:uppercase;letter-spacing:.06em;opacity:.8}}
.ctr .v{{font-family:"SF Mono",Menlo,monospace;font-weight:700;font-size:80px;line-height:1.05;
letter-spacing:-.03em;display:flex;gap:22px;align-items:center;white-space:nowrap}}
.ctr .v small{{font-size:32px;font-weight:400;letter-spacing:0}}
.lc{{display:inline-flex;align-items:center;gap:10px}}
.lab{{display:inline-block;font-family:"SF Mono",Menlo,monospace;font-weight:700;font-size:28px;
text-transform:uppercase;letter-spacing:.04em;padding:4px 12px;border:3px solid #0b0b0b;
background:#fafaf7;color:#0b0b0b;line-height:1.1}}
.lab.winner{{background:#d4ff3a}} .lab.solid{{background:#0b0b0b;color:#fff}}
.pattern{{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1.15;margin:4px 0 26px;
max-width:1500px}}
.wall{{background:#fafaf7;border:3px solid #0b0b0b;padding:16px 18px 6px}}
.wh{{display:flex;justify-content:space-between;font-size:26px;text-transform:uppercase;
letter-spacing:.06em;margin-bottom:14px}}
.groups{{display:grid;grid-template-columns:1fr 1fr;column-gap:28px}}
.grp{{display:grid;grid-template-columns:230px 1fr;gap:18px;padding:12px 0;
border-top:2px solid #0b0b0b}}
.grp:nth-child(-n+2){{border-top:0;padding-top:0}}
h2{{font-size:40px;line-height:1.05;letter-spacing:-.035em;margin:0}}
.tiles{{display:grid;grid-template-columns:repeat(3,150px);gap:6px;align-content:start}}
.tiles img{{width:100%;aspect-ratio:4/5;object-fit:cover;display:block}}
.tiles img.winner{{outline:5px solid #d4ff3a;outline-offset:-5px}}
footer{{margin-top:22px;display:flex;justify-content:flex-end}}
footer span{{background:#0b0b0b;color:#fff;font-size:30px;font-weight:700;padding:6px 16px}}
footer a{{color:#d4ff3a;text-decoration:none}}
</style></head><body>
<div class="eyebrow"><b>{e(result["title"])}</b></div>
<h1>{e(title)}</h1>
<div class="ctrs">
<div class="ctr blk"><div class="k">ads</div><div class="v">{s["ads"]}</div></div>
<div class="ctr blk"><div class="k">{"brand" if s["brands"] == 1 else "brands"}</div>
<div class="v">{s["brands"]}</div></div>
<div class="ctr"><div class="k">longest run</div>
<div class="v">{longest}<small>days</small></div></div>
<div class="ctr"><div class="k">labels</div><div class="v">{label_ctr}</div></div>
</div>
{"".join(f'<div class="pattern">{e(x)}</div>' for x in pattern_lines(result))}
{wall_block}
<footer><span>data: Meta Ad Library · <a href="https://stealads.ai">stealads.ai</a></span></footer>
</body></html>"""


def summary_markdown(
    result: dict[str, Any], *, cap: int, board_brands: int = MAX_BOARD_BRANDS
) -> str:
    s = result["summary"]
    title, subtitle = headline(result, cap=cap)
    shown = min(max(board_brands, 1), MAX_BOARD_BRANDS)
    lines = [
        f"# {result['title']}: {title} (checked {result['checked_date']})",
        "",
        subtitle,
        "",
        *(
            [f"The board shows the top {shown} of {count_brands(s['brands'])}.", ""]
            if s["brands"] > shown
            else []
        ),
        "Written ads: "
        + ", ".join(f"{s['written_labels'][label]} {label}" for label in LABELS)
        + ".",
        "",
        *pattern_lines(result),
        "",
        "Labels: " + "; ".join(f"{k}: {v}" for k, v in LABEL_MEANINGS.items()) + ".",
        "",
    ]
    if s.get("catalog"):
        lines += [
            f"{s['written']} written ads and {s['catalog']} catalog ads (Meta fills in the "
            "product from the store, so there are no words to quote).",
            "",
        ]
    if result.get("no_ads"):
        lines += [f"{_no_ads_phrase(result)}: {', '.join(result['no_ads'])}.", ""]
    for b in result["brands"]:
        lines.append(f"## {b['name']} ({b['written']} written, {b.get('catalog', 0)} catalog)")
        for ad in b["top"]:
            label = f"{ad['label']} · " if ad["label"] else ""
            lines.append(f'- {label}"{ad["hook"]}" ({ad["why"]})')
        lines.append("")
    lines += [
        "Running long doesn't prove an ad works. It shows what they keep paying for.",
        "",
        "---",
        f"data: Meta Ad Library · checked {result['checked_date']} · https://stealads.ai",
        "",
    ]
    return "\n".join(lines)


def write_csv(result: dict[str, Any], path: Path) -> None:
    """Every ad, one row each: the full data behind the board."""
    import csv

    cols = [
        "brand",
        "page_id",
        "ad_library_id",
        "label",
        "live",
        "days_live",
        "versions",
        "catalog",
        "black_friday",
        "up_to_off",
        "format",
        "start_date",
        "cta",
        "landing_domain",
        "spoken_hook",
        "hook",
        "text",
    ]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for e in result["events"]:
            w.writerow(
                {
                    "brand": e["brand"],
                    "page_id": e.get("page_id", ""),
                    "ad_library_id": e.get("_ad_id", ""),
                    "label": e["label"] or "",
                    "live": e.get("is_active", True),
                    "days_live": e["days_live"],
                    "versions": e["versions"],
                    "catalog": e["catalog"],
                    "black_friday": bool(BLACK_FRIDAY.search(e["text"])),
                    "up_to_off": bool(UP_TO_OFF.search(e["text"])),
                    "format": e.get("format") or "",
                    "start_date": e.get("start_date", ""),
                    "cta": e.get("cta", ""),
                    "landing_domain": e.get("landing_domain", ""),
                    "spoken_hook": e.get("spoken_hook", False),
                    "hook": e["hook"],
                    "text": re.sub(r"\s+", " ", e["text"]).strip(),
                }
            )


SLICE_ROWS = (2, 3, 3, 3)  # rows per X slice: slice 1 also carries the title


def slices_html(result: dict[str, Any], *, cap: int, board_brands: int = MAX_BOARD_BRANDS) -> str:
    """Up to four 1080x1350 slices for an X post (X allows four images): the title and the
    counts over the first two brands, then three brands a slice. Each brand shows its
    top three ads large, with the run length under each."""
    e = html.escape
    view = board_view(result, board_brands)
    s = view["summary"]
    title, _ = headline(view, cap=cap)
    longest = max((ev["days_live"] for ev in view["events"]), default=0)
    brands = view["brands"]

    def tile(ad: dict[str, Any]) -> str:
        if ad.get("image"):
            pic = f'<img src="{_thumb_b64(ad["image"], 480)}" alt="">'
        else:
            pic = f'<div class="ph">&ldquo;{e(ad["hook"])}&rdquo;</div>'
        pill = f'<span class="lab {e(ad["label"])}">{e(ad["label"])}</span>' if ad["label"] else ""
        days = f"{ad['days_live']} day" + ("" if ad["days_live"] == 1 else "s")
        return f'<div class="tile">{pic}<div class="cap">{pill}<b>{days}</b></div></div>'

    def count_line(b: dict[str, Any]) -> str:
        n = b["ads"]
        noun = "ad" if n == 1 else "ads"
        what = f"live {SOLID_MIN_DAYS}+ days" if view.get("read") == "longest" else "live"
        return f"{n} {noun} {what}"

    def pair_row(a: dict[str, Any], b: dict[str, Any]) -> str:
        half = "".join(
            f'<div class="half">{tile(x["top"][0]) if x["top"] else ""}<div class="who">'
            f'<h2>{e(x["name"])}</h2><div class="n">{count_line(x)}</div></div></div>'
            for x in (a, b)
        )
        return f'<div class="row pair">{half}</div>'

    def brand_row(b: dict[str, Any]) -> str:
        return (
            '<div class="row"><div class="who">'
            f'<h2>{e(b["name"])}</h2><div class="n">{count_line(b)}</div>'
            f'</div><div class="tiles">{"".join(tile(a) for a in b["top"])}</div></div>'
        )

    def header(first: bool) -> str:
        if not first:
            return f'<div class="eyebrow"><b>{e(result["title"])}</b></div>'
        return (
            f'<div class="eyebrow"><b>{e(result["title"])}</b></div><h1>{e(title)}</h1>'
            '<div class="ctrs">'
            f'<div class="ctr"><div class="k">ads</div><div class="v">{s["ads"]}</div></div>'
            f'<div class="ctr"><div class="k">{"brand" if s["brands"] == 1 else "brands"}</div>'
            f'<div class="v">{s["brands"]}</div></div>'
            f'<div class="ctr"><div class="k">longest run</div>'
            f'<div class="v">{longest}<small>days</small></div></div></div>'
        )

    rows: list[str] = []
    i = 0
    while i < len(brands):
        one = len(brands[i]["top"]) <= 1
        if one and i + 1 < len(brands) and len(brands[i + 1]["top"]) <= 1:
            rows.append(pair_row(brands[i], brands[i + 1]))
            i += 2
        else:
            rows.append(brand_row(brands[i]))
            i += 1
    chunks: list[list[str]] = []
    start = 0
    for size in SLICE_ROWS:
        chunks.append(rows[start : start + size])
        start += size
    chunks[-1] += rows[start:]
    sections = []
    for i, chunk in enumerate(c for c in chunks if c):
        sections.append(
            f'<section class="slice" id="slice-{i + 1:02d}">{header(i == 0)}'
            f'<div class="rows">{"".join(chunk)}</div>'
            "<footer>data: Meta Ad Library &middot; "
            '<a href="https://stealads.ai">stealads.ai</a></footer></section>'
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{e(title)}</title><style>
*{{box-sizing:border-box}}
body{{margin:0;background:#888;font-family:"Helvetica Neue",Helvetica,Arial,Inter,sans-serif;
color:#0b0b0b}}
.slice{{position:absolute;left:-9999px;top:0;width:1080px;height:1350px;background:#d7d8d3;
padding:48px 44px 40px;display:flex;flex-direction:column}}
.eyebrow b{{display:inline-block;background:#0b0b0b;color:#fff;font-size:30px;font-weight:700;
padding:6px 16px}}
h1{{font-size:84px;font-weight:700;letter-spacing:-.045em;line-height:1;margin:16px 0 18px}}
.ctrs{{display:grid;grid-template-columns:1fr 1fr 1.3fr;gap:12px;margin-bottom:6px}}
.ctr{{background:#fafaf7;border:3px solid #0b0b0b;padding:8px 16px}}
.ctr .k{{font-family:"SF Mono",Menlo,monospace;font-size:24px;text-transform:uppercase;
letter-spacing:.06em}}
.ctr .v{{font-family:"SF Mono",Menlo,monospace;font-weight:700;font-size:60px;line-height:1.1;
letter-spacing:-.03em}}
.ctr .v small{{font-size:28px;font-weight:400;margin-left:8px}}
.rows{{flex:1;display:flex;flex-direction:column;justify-content:flex-start;gap:0;margin-top:14px}}
.row{{display:grid;grid-template-columns:250px 1fr;gap:18px;padding:14px 0;
border-top:3px solid #0b0b0b}}
h2{{font-size:44px;line-height:1.02;letter-spacing:-.035em;margin:0 0 10px}}
.n{{font-family:"SF Mono",Menlo,monospace;font-size:25px;line-height:1.2}}
.tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.tile img,.tile .ph{{width:100%;aspect-ratio:4/5;object-fit:cover;display:block;background:#fafaf7}}
.tile .ph{{padding:14px;font-size:24px;line-height:1.2;overflow:hidden}}
.cap{{display:flex;flex-direction:column;align-items:flex-start;gap:4px;margin-top:6px;
font-family:"SF Mono",Menlo,monospace;font-size:25px}}
.pair{{grid-template-columns:1fr 1fr;gap:28px}}
.half{{display:grid;grid-template-columns:200px 1fr;gap:14px}}
.half h2{{font-size:38px}}
.lab{{display:inline-block;font-weight:700;font-size:22px;text-transform:uppercase;
letter-spacing:.04em;padding:2px 8px;border:3px solid #0b0b0b;background:#fafaf7}}
.lab.winner{{background:#d4ff3a}} .lab.solid{{background:#0b0b0b;color:#fff}}
footer a{{color:inherit;text-decoration:none}}
footer{{margin-top:auto;padding-top:10px;font-family:"SF Mono",Menlo,monospace;font-size:24px;
text-align:right}}
</style></head><body>{"".join(sections)}</body></html>"""


def render(
    result: dict[str, Any], out: Path, *, cap: int, board_brands: int = MAX_BOARD_BRANDS
) -> dict[str, Any]:
    """board.html (top 10 brands) + board.png + x-slices/ + summary.md + ads.csv +
    category.json (every brand); then the shared board checks."""
    from ad_spy_kit.render import launch_chromium
    from ad_spy_kit.slice import slice_board
    from ad_spy_kit.validate_run import board_html_errors

    out.mkdir(parents=True, exist_ok=True)
    page = board_html(result, cap=cap, board_brands=board_brands)
    slices = slices_html(result, cap=cap, board_brands=board_brands)
    write_csv(result, out / "ads.csv")
    ids = [e["_ad_id"] for e in result["events"]]
    errors = board_html_errors(page, ids)
    errors += [f"slices: {x}" for x in board_html_errors(slices, ids)]
    (out / "board.html").write_text(page)
    (out / "slices.html").write_text(slices)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_chromium(p)
        tab = browser.new_page(viewport={"width": 1600, "height": 900})
        tab.goto((out / "board.html").resolve().as_uri(), wait_until="networkidle")
        tab.screenshot(path=str(out / "board.png"), full_page=True)
        browser.close()
    slice_dir = out / "x-slices"
    for stale in visible(slice_dir.glob("[0-9]*.png")) if slice_dir.is_dir() else []:
        stale.unlink(missing_ok=True)
    slice_board(out / "slices.html", slice_dir, repo_root=out)
    (out / "summary.md").write_text(summary_markdown(result, cap=cap, board_brands=board_brands))
    public = {k: v for k, v in result.items() if k != "events"}
    public["brands"] = [
        {**b, "counts": {str(k): v for k, v in b["counts"].items()}} for b in result["brands"]
    ]
    (out / "category.json").write_text(json.dumps(public, indent=2, default=str) + "\n")
    report = {"ok": not errors, "errors": errors}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def run(
    target: str | None,
    *,
    out: Path,
    yes: bool,
    from_dir: Path | None = None,
    title: str | None = None,
    max_ads: int = DEFAULT_MAX_ADS,
    max_brands: int = DEFAULT_MAX_BRANDS,
    search_pages: int = DEFAULT_SEARCH_PAGES,
    country: str = "US",
    newest: bool = False,
    read: str | None = None,
    brands_file: Path | None = None,
    max_credits: int | None = None,
    workers: int = 1,
    board_brands: int = MAX_BOARD_BRANDS,
    images: bool = True,
    rerun: str = "",
) -> int:
    from ad_spy_kit.spend import confirm

    read = read or ("newest" if newest else "longest")
    board_brands = min(board_brands, MAX_BOARD_BRANDS)
    max_brands = min(max_brands, MAX_BOARD_BRANDS)
    started = time.monotonic()
    if from_dir is None:
        from ad_spy_kit.sc_client import _client, require_key

        if brands_file is not None:
            brands = load_brands_file(brands_file)
            require_key()
            todo = [b for b in brands if not already_read(out, b)]
            worst = pull_pages(max_ads)[1]
            low, high = len(todo), len(todo) * worst
            skip = (
                f" ({len(brands) - len(todo)} already saved, no charge)" if todo != brands else ""
            )
            text = (
                f"This reads {brands_possessive(len(todo))}{skip} "
                f"{read_phrase(max_ads, False, read)}: "
                f"about {credit_range(low, high)}."
            )
            print(text)
            print(
                f"Estimated time: about {estimate_minutes(len(todo), workers)} minutes with "
                f"{workers} worker{'s' if workers != 1 else ''}."
            )
            if max_credits is not None and high > max_credits:
                print(
                    f"That's more than --max-credits {max_credits}. The run stops starting new "
                    "brands at the cap; rerun with the same --out to finish later."
                )
            if not _go(yes, rerun):
                return 0
            for line in pull_brands(
                brands,
                out,
                max_ads=max_ads,
                country=country,
                read=read,
                max_credits=max_credits,
                workers=workers,
                images=images,
            ):
                print(f"  skipped {line}")
            from_dir = out
            title = title or count_brands(len(brands))
        else:
            if not target:
                raise KitError(
                    "Tell me a keyword or a list of brands.",
                    fix='e.g. ad-spy-kit category "black friday skincare"',
                    code="category_no_target",
                )
            mode, parsed = parse_target(target)
            if mode == "brands" and len(parsed) > MAX_BOARD_BRANDS:
                raise KitError(
                    f"A category board shows {MAX_BOARD_BRANDS} brands and you named "
                    f"{len(parsed)}.",
                    fix=(
                        f"Name {MAX_BOARD_BRANDS} or fewer, or put the long list in a CSV and use "
                        "--brands-file (it reads them all and the board shows the top "
                        f"{MAX_BOARD_BRANDS})."
                    ),
                    code="category_too_many_brands",
                )
            require_key()
            text, _, _ = quote(
                mode,
                parsed,
                max_ads=max_ads,
                max_brands=max_brands,
                search_pages=search_pages,
                newest=read == "newest",
            )
            if not confirm(text, yes=yes, rerun=rerun):
                return 0
            if mode == "keyword":
                rows = discover(_client(), str(parsed), search_pages, country)
                brands = pick_brands(rows, max_brands, country)
                if not brands:
                    raise KitError(
                        f"No brands are running ads that match '{parsed}' right now.",
                        fix="Try a broader keyword, or name the brands yourself.",
                        code="category_no_brands",
                    )
            else:
                brands = resolve_brands(list(parsed), country)
            print(f"Reading {len(brands)} brands: " + ", ".join(b["page_name"] for b in brands))
            for line in pull_brands(
                brands,
                out,
                max_ads=max_ads,
                country=country,
                read=read,
                max_credits=max_credits,
                workers=workers,
                images=images,
            ):
                print(f"  skipped {line}")
            from_dir = out
            title = title or (
                str(parsed).title() if mode == "keyword" else count_brands(len(brands))
            )
    return draw_saved(
        from_dir,
        out=out,
        title=title,
        query=target or "",
        max_ads=max_ads,
        read=read,
        board_brands=board_brands,
        started=started,
    )


def draw_saved(
    from_dir: Path,
    *,
    out: Path | None = None,
    title: str | None = None,
    query: str = "",
    max_ads: int = DEFAULT_MAX_ADS,
    read: str = "longest",
    board_brands: int = MAX_BOARD_BRANDS,
    rank: str = "labels",
    started: float | None = None,
) -> int:
    """Saved brand folders (from_dir/brands/*) → the board, X slices, summary and csv."""
    started = time.monotonic() if started is None else started
    out = out or from_dir
    board_brands = min(board_brands, MAX_BOARD_BRANDS)
    spent = _credits_in(from_dir)
    saved = load_saved(from_dir, max_ads=max_ads, read=read)
    result = build(
        saved,
        title=title or from_dir.name.replace("-", " ").title(),
        query=query,
        read=read,
        rank=rank,
    )
    result["summary"]["credits_spent"] = spent
    result["summary"]["seconds"] = round(time.monotonic() - started, 1)
    report = render(result, out, cap=max_ads, board_brands=board_brands)
    s = board_view(result, board_brands)["summary"]
    if result["summary"]["brands"] > s["brands"]:
        print(
            f"Read {count_brands(result['summary']['brands'])}; the board shows the top "
            f"{s['brands']}."
        )
    print(
        f"{s['ads']} ads from {count_brands(s['brands'])} ({s['written']} written, "
        f"{s['catalog']} catalog). Written: "
        + ", ".join(f"{s['written_labels'][label]} {label}" for label in LABELS)
        + f". {time.monotonic() - started:.0f}s."
        + (f" {spent} ScrapeCreators credits spent reading them." if spent else "")
    )
    for line in pattern_lines(result):
        print(line)
    if not report["ok"]:
        print("The board didn't pass its checks:\n  " + "\n  ".join(report["errors"]))
        return 1
    print(
        f"Board: {out / 'board.png'}  ·  X slices: {out / 'x-slices'}  ·  "
        f"text version: {out / 'summary.md'}  ·  every ad: {out / 'ads.csv'}"
    )
    return 0


# Observed: about 2.5 seconds per brand read one at a time (Nov 5 run, 14 brands, 35 s).
SECONDS_PER_BRAND = 2.5


def estimate_minutes(brands: int, workers: int) -> int:
    return max(1, round(brands * SECONDS_PER_BRAND / max(1, workers) / 60))


def _go(yes: bool, rerun: str) -> bool:
    """The quote is already printed; True means spend."""
    import sys

    if yes:
        return True
    if sys.stdin.isatty() and sys.stdout.isatty():
        if input("Go? [y/N] ").strip().lower() in ("y", "yes"):
            return True
    print(f"Nothing spent. To go ahead: {rerun}")
    return False
