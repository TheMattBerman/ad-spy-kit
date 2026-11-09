from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ad_spy_kit.errors import (
    KitError,
    SourceError,
    missing_scrapecreators_key,
    scrapecreators_failed,
)
from ad_spy_kit.exclusions import check_not_excluded
from ad_spy_kit.paths import visible
from ad_spy_kit.sl_adapter import map_list_ads_response, map_scrapecreators_ad
from ad_spy_kit.stealads_text import load_saved


class ScrapeCreatorsClientError(SourceError):
    """A ScrapeCreators failure in plain words: bad key, no credits, rate limit or outage."""

    def __init__(self, message: str, status: int | None = None) -> None:
        err = scrapecreators_failed(status, message)
        super().__init__(err.message, fix=err.fix, code=err.code)
        self.status = status


def require_key() -> None:
    """Stop before quoting or spending when there is no ScrapeCreators key."""
    from cie.scrapecreators_client import _load_dotenv_if_needed

    _load_dotenv_if_needed("SCRAPECREATORS_API_KEY")
    if not os.environ.get("SCRAPECREATORS_API_KEY"):
        raise missing_scrapecreators_key()


def _client():
    require_key()
    from cie.scrapecreators_client import ScrapeCreatorsClient

    return ScrapeCreatorsClient()


def load_fixture_pull(fixture_dir: Path) -> dict[str, Any]:
    return json.loads((fixture_dir / "ads.raw.json").read_text())


def load_stealads_list_fixture(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "stealads_list_ads.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


# Saved StealAds responses. The agent saves each tool response as raw JSON in the run folder.
# `search_ads.json` / `search_ads.video.json` / `search_ads.static.json` (and `.page2` style
# extra pages) hold search_ads pages. `find_winning_ads*.json` is the prod ranking call;
# `find_bangers*.json` is the old dev name and still works.
SEARCH_STEM = "search_ads"
RANK_STEMS = ("find_winning_ads", "find_bangers")


def saved_files(run_dir: Path, *stems: str) -> list[Path]:
    """Saved tool responses for these stems, in a stable order (stems first, then name)."""
    out: list[Path] = []
    for stem in stems:
        out += sorted(p for p in visible(run_dir.glob(f"{stem}*.json")) if p not in out)
    return out


def _format_filter(path: Path, doc: dict[str, Any]) -> str | None:
    """The search's `format` argument: from the recorded request, else the file name."""
    fmt = ((doc.get("request") or {}).get("arguments") or {}).get("format")
    if fmt in ("static", "video"):
        return str(fmt)
    parts = path.name.lower().split(".")
    for name in ("video", "static"):
        if name in parts:
            return name
    return None


def unfetched_pages(run_dir: Path) -> list[str]:
    """Saved pages that say `has_more` and whose `next_cursor` was never fetched and saved.

    Only a hint for the agent: a 24-row sample is usually enough, so this is never an error.
    """
    from ad_spy_kit.sl_adapter import unwrap_recording

    docs = [(p, load_saved(p)) for p in saved_files(run_dir, SEARCH_STEM)]
    fetched = set()
    for _, d in docs:
        fetched.add(((d.get("request") or {}).get("arguments") or {}).get("cursor"))
    fetched.discard(None)
    notes = []
    for path, doc in docs:
        resp = unwrap_recording(doc)
        cursor = resp.get("next_cursor")
        if resp.get("has_more") and cursor and cursor not in fetched:
            notes.append(path.name)
    return notes


def _load_search_recordings(run_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Union the saved search_ads pages (prod has no list_ads tool).

    Files named `search_ads*.json`; extra pages fetched with `cursor` are saved as more
    `search_ads*.json` files and unioned here. A file called with format=static|video (in its
    recorded request, or `.static.` / `.video.` in its name) gets an exact IMAGE/VIDEO label.
    Rows dedupe on the StealAds ad id.
    """
    from ad_spy_kit.sl_adapter import unwrap_recording

    rows: dict[str, dict[str, Any]] = {}
    pulled_at = ""
    for path in saved_files(run_dir, SEARCH_STEM):
        doc = load_saved(path)
        fmt = _format_filter(path, doc)
        pulled_at = pulled_at or str(doc.get("recorded_at") or "")
        for ad in unwrap_recording(doc).get("ads") or []:
            row = rows.setdefault(str(ad["id"]), dict(ad))
            if doc.get("_from_text"):
                row["_from_text"] = True
            if fmt:
                row["_format_filter"] = fmt
    return list(rows.values()), pulled_at


def reply_schema(rows: list[dict[str, Any]], *, from_text: bool = False) -> dict[str, Any]:
    """What the saved replies were: the JSON rows' `schema_version` (highest seen), or None
    for Markdown text rows, which carry none. Written to ads.raw.json so a later reader knows
    which reply shape the board was built from."""
    versions = [int(r["schema_version"]) for r in rows if isinstance(r.get("schema_version"), int)]
    if versions and from_text:
        kind = "mixed"
    elif versions:
        kind = "json"
    else:
        kind = "text" if from_text or rows else "none"
    return {"schema_version": max(versions) if versions else None, "reply_format": kind}


def _recorded_from(run_dir: Path) -> str:
    """Where the saved StealAds responses came from ('' for hand-written fixtures)."""
    for path in [*saved_files(run_dir, SEARCH_STEM), run_dir / "stealads_list_ads.json"]:
        if path.exists():
            origin = load_saved(path).get("recorded_from")
            if origin:
                return str(origin)
    return ""


def build_ads_raw_from_fixture(fixture_dir: Path) -> dict[str, Any]:
    """Saved source responses → ads.raw.json, plus saved transcripts.json / onscreen.json."""
    from ad_spy_kit.onscreen import apply_onscreen
    from ad_spy_kit.transcripts import apply_transcripts

    ads_raw = _build_ads_raw(fixture_dir)
    for name, apply in (("transcripts", apply_transcripts), ("onscreen", apply_onscreen)):
        path = fixture_dir / f"{name}.json"
        if path.exists():
            apply(ads_raw, json.loads(path.read_text()))
    return ads_raw


def _build_ads_raw(fixture_dir: Path) -> dict[str, Any]:
    from ad_spy_kit.sl_adapter import map_stealads_ad, unwrap_recording

    live_path = fixture_dir / "stealads_list_ads.json"
    searched = saved_files(fixture_dir, SEARCH_STEM)
    schema: dict[str, Any] = {"schema_version": None, "reply_format": "none"}
    if live_path.exists():
        live = unwrap_recording(json.loads(live_path.read_text()))
        ads = map_list_ads_response(live) if live else []
        pulled_at = live.get("pulled_at", "2026-10-28T12:00:00Z")
        competitor_id = live.get("competitor_id", "fixture")
        schema = reply_schema(live.get("ads") or [])
    elif searched:
        rows, pulled_at = _load_search_recordings(fixture_dir)
        ads = [map_stealads_ad(r) for r in rows]
        competitor_id = ""
        schema = reply_schema(rows, from_text=any(r.get("_from_text") for r in rows))
    elif (fixture_dir / "ads.raw.json").exists():
        return load_fixture_pull(fixture_dir)
    else:
        ads, pulled_at, competitor_id = [], "2026-10-28T12:00:00Z", "fixture"

    skipped: list[dict[str, Any]] = []
    comp_path = fixture_dir / "competitor.json"
    page_id = json.loads(comp_path.read_text()).get("page_id") if comp_path.exists() else None
    if page_id:
        competitor_id = competitor_id or str(page_id)
        # search_ads' page filter is a ranking hint, not a hard filter: keep the page's own
        # ads (creator partnership ads run on the brand's page and keep its page id).
        other = [a for a in ads if a.get("facebook_page_id") not in (None, "", str(page_id))]
        skipped += [{"ad_id": a["ad_id"], "reason": "other_advertiser"} for a in other]
        ads = [a for a in ads if a not in other]

    # Rank order: find_winning_ads (prod) first, then find_bangers (old dev name). A saved
    # response with no `ads` list ranks nothing. Order is the file order, then row order.
    rank_map: dict[str, int] = {}
    for rank_path in saved_files(fixture_dir, *RANK_STEMS):
        ranked = unwrap_recording(load_saved(rank_path))
        for item in ranked.get("ads") or ranked.get("bangers") or []:
            if page_id and item.get("facebook_page_id") not in (None, "", str(page_id)):
                continue
            aid = item.get("ad_id") or item.get("id")
            if aid and aid not in rank_map:
                rank_map[aid] = len(rank_map) + 1
    for ad in ads:
        if ad["ad_id"] in rank_map:
            ad["bangers_rank"] = rank_map[ad["ad_id"]]
    return {
        "competitor_id": competitor_id or "fixture",
        "pulled_at": pulled_at or "2026-10-28T12:00:00Z",
        "source": "stealads",
        **schema,
        "recorded_from": _recorded_from(fixture_dir),
        "collect_mode": "full",
        "total_available": len(ads),
        "import_cap_hit": False,
        "skipped": skipped,
        "ads": ads,
    }


def pick_company(query: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    """CIE competitor_resolver heuristics: exact name/IG handle first, then followers."""
    q = query.strip().lower().lstrip("@")
    live = [m for m in matches if not m.get("page_is_deleted")]
    if not live:
        raise SourceError(
            f"ScrapeCreators found no Facebook page for '{query}'.",
            fix=(
                "Paste the brand's Ad Library page link (it has view_all_page_id= in it) or "
                "its page ID instead of the name."
            ),
            code="competitor_not_found",
        )

    def likes(m: dict[str, Any]) -> int:
        return int(m.get("likes") or m.get("followers") or 0)

    exact = [
        m
        for m in live
        if q in {str(m.get("name") or "").lower(), str(m.get("ig_username") or "").lower()}
    ]
    ranked = sorted(exact or live, key=likes, reverse=True)
    top = ranked[0]
    others = [m for m in sorted(live, key=likes, reverse=True) if m is not top]
    if exact:
        confidence = "exact"
    elif others and likes(others[0]) * 2 > likes(top):
        confidence = "ambiguous"
    else:
        confidence = "likely"
    return {
        "query": query,
        "competitor_id": None,
        "page_id": str(top.get("page_id") or ""),
        "page_name": str(top.get("name") or query),
        "ig_username": top.get("ig_username") or None,
        "followers": likes(top),
        "country": "US",
        "confidence": confidence,
        "alternates": [
            {"page_id": str(m.get("page_id") or ""), "page_name": str(m.get("name") or "")}
            for m in others[:3]
        ],
        "tracked": False,
        "source": "scrapecreators",
    }


NAMED_PAGE = re.compile(r"^(.+?)\s*\((\d{5,})\)$")  # "Brand Name (1234567890)"


def page_id_from_query(query: str) -> str | None:
    """A numeric page ID or a page link → the page ID. A brand name → None.

    Accepts a bare page ID, an Ad Library page link (`view_all_page_id=`), and a
    `profile.php?id=` page link. A link to one ad (`/ads/library/?id=`) names an ad, not a
    page, so it stops with the steps to get the page link instead.
    """
    from urllib.parse import parse_qs, urlparse

    q = query.strip()
    named = NAMED_PAGE.match(q)
    if named:
        return named.group(2)
    if q.isdigit() and len(q) >= 5:
        return q
    if not (q.startswith("http") or "facebook.com" in q):
        return None
    url = urlparse(q if q.startswith("http") else f"https://{q}")
    params = parse_qs(url.query)
    for key in ("view_all_page_id", "page_id"):
        if params.get(key, [""])[0].isdigit():
            return params[key][0]
    if url.path.rstrip("/").endswith("profile.php") and params.get("id", [""])[0].isdigit():
        return params["id"][0]
    if "/ads/library" in url.path and params.get("id"):
        raise KitError(
            "That link points at one ad, not at the brand's page.",
            fix=(
                "Open it, click the brand's name, and copy the link of their Ad Library page "
                "(it has view_all_page_id= in it). Or paste the brand's name."
            ),
            code="ad_link_not_page",
        )
    return None


def competitor_from_page_id(page_id: str, query: str, country: str) -> dict[str, Any]:
    """competitor.json for a page the user named exactly. No search, no credit spent."""
    check_not_excluded(query, page_id)
    named = NAMED_PAGE.match(query.strip())
    return {
        "query": query,
        "competitor_id": None,
        "page_id": page_id,
        "page_name": named.group(1) if named else f"Page {page_id}",
        "page_name_from_ads": not named,  # the read fills in the real name from the ads
        "ig_username": None,
        "followers": 0,
        "country": country,
        "confidence": "exact",
        "alternates": [],
        "tracked": False,
        "source": "scrapecreators",
    }


def resolve_via_scrapecreators(query: str, *, country: str = "US") -> dict[str, Any]:
    page_id = page_id_from_query(query)
    if page_id:
        return competitor_from_page_id(page_id, query, country)
    check_not_excluded(query)
    client = _client()
    from cie.scrapecreators_client import ScrapeCreatorsClientError as CieErr

    try:
        matches = client.facebook_search_companies(query, country=country)
    except CieErr as e:
        raise ScrapeCreatorsClientError(str(e), getattr(e, "status", None)) from e
    competitor = pick_company(query, matches)
    competitor["country"] = country
    check_not_excluded(competitor["page_name"], competitor["page_id"], competitor["ig_username"])
    return competitor


# Ad images: several at once, each capped, so a 30-ad read adds seconds, not minutes.
IMAGE_WORKERS = 8
IMAGE_MAX_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT_SECONDS = 20


def _download(
    url: str, dest_stem: Path, max_bytes: int = IMAGE_MAX_BYTES
) -> tuple[Path, str] | None:
    """One ad image (or video preview frame) → dest_stem.<ext>. None when the link fails,
    isn't an image, or is bigger than max_bytes. Never raises for a bad link."""
    import httpx

    try:
        with httpx.stream("GET", url, timeout=IMAGE_TIMEOUT_SECONDS, follow_redirects=True) as r:
            r.raise_for_status()
            kind = r.headers.get("content-type", "").lower()
            if kind and not kind.startswith("image/"):
                return None
            if int(r.headers.get("content-length") or 0) > max_bytes:
                return None
            data = bytearray()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > max_bytes:
                    return None
    except (httpx.HTTPError, ValueError, OSError):
        return None
    if not data:
        return None
    ext = ".png" if "png" in kind else ".webp" if "webp" in kind else ".jpg"
    path = dest_stem.with_suffix(ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return path, hashlib.sha256(data).hexdigest()


def _download_video(url: str, dest: Path, max_bytes: int = 20 * 1024 * 1024) -> bool:
    import httpx

    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            data = b""
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > max_bytes:
                    return False
    except httpx.HTTPError:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


SMALL_IMAGE_WIDTH = 300


def _width(path: Path) -> int:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size[0]
    except (OSError, ValueError):
        return 0


def _larger_preview(
    path: Path,
    digest: str,
    fallbacks: list[str],
    ad: dict[str, Any],
    media_dir: Path,
    downloader,
) -> tuple[Path, str]:
    """A small first image (a 110px video preview) is swapped for the widest other picture
    the same ad carries. Nothing else is fetched: these URLs were already in the read."""
    best, best_digest = path, digest
    if _width(path) >= SMALL_IMAGE_WIDTH:
        return path, digest
    for n, url in enumerate(fallbacks):
        try:
            got = downloader(url, media_dir / f"{ad['ad_id']}-alt{n}")
        except Exception:
            got = None
        if got is None:
            continue
        alt, alt_digest = got
        if _width(alt) > _width(best):
            if best != path:
                best.unlink(missing_ok=True)
            best, best_digest = alt, alt_digest
        else:
            alt.unlink(missing_ok=True)
        if _width(best) >= SMALL_IMAGE_WIDTH:
            break
    if best != path:
        final = path.with_suffix(best.suffix)
        if final != path:
            path.unlink(missing_ok=True)
        best.replace(final)
        return final, best_digest
    return path, digest


MAX_CARDS = 4


def _save_cards(
    ad: dict[str, Any], media_dir: Path, downloader, keep_originals: bool = False
) -> None:
    """A carousel's card pictures → media/cards/<ad_id>-<n>.jpg (the dense wall shows them).
    The cover is the ad's own image; this saves cards 2 to MAX_CARDS + 1. A bad link is skipped."""
    from ad_spy_kit.media import shrink_image

    urls = ad.pop("card_image_urls", None) or []
    saved: list[dict[str, Any]] = []
    for n, url in enumerate(urls[1 : MAX_CARDS + 1], start=2):
        try:
            got = downloader(url, media_dir / "cards" / f"{ad['ad_id']}-{n}")
        except Exception:
            got = None
        if got is None:
            continue
        path = shrink_image(got[0], keep_originals=keep_originals)
        saved.append({"path": f"media/cards/{path.name}", "kind": "card"})
    if saved:
        ad["card_media"] = saved
    if urls:
        ad["card_count"] = len(urls)


def cache_media(
    ads: list[dict[str, Any]],
    media_dir: Path,
    downloader=_download,
    *,
    fetch_videos: bool = False,
    video_downloader=_download_video,
    workers: int = IMAGE_WORKERS,
    keep_originals: bool = False,
) -> list[dict]:
    """Download each ad's image (or video preview frame) now, because fbcdn links expire,
    and drop the remote URL.

    Uses only the URLs already in the read; no extra API calls. Downloads run in parallel
    (`workers`), each capped in size. A link that fails is skipped quietly and counted.
    Returns the `skipped` list for ads.raw.json. Stored media points at the local copy only.
    With `fetch_videos` (the opt-in OpenRouter transcript path) each video that clears the
    winner floor (7+ days or 3+ versions) is also saved as media/<ad_id>.mp4 for that step.
    The video URL itself is never stored. Every image is saved at most 1200px on its long
    edge as JPEG (ad_spy_kit/media.py); `keep_originals` also keeps the full-size file under
    media/originals/.
    """
    from concurrent.futures import ThreadPoolExecutor

    from ad_spy_kit.score_winners import eligible

    skipped: dict[int, dict[str, Any]] = {}

    def one(i: int, ad: dict[str, Any]) -> None:
        video_url = ad.pop("video_url", None)
        if fetch_videos and video_url and eligible(ad):
            video_downloader(video_url, media_dir / f"{ad['ad_id']}.mp4")
        _save_cards(ad, media_dir, downloader, keep_originals)
        media = ad.get("media") or []
        remote = next((m for m in media if m.get("url")), None)
        if remote is None:
            if not any(m.get("path") for m in media):
                reason = "video_no_preview" if ad.get("format") == "VIDEO" else "no_media"
                skipped[i] = {"ad_id": ad["ad_id"], "reason": reason}
            return
        try:
            got = downloader(remote["url"], media_dir / ad["ad_id"])
        except Exception:  # a broken link never stops the run
            got = None
        if got is None:
            skipped[i] = {"ad_id": ad["ad_id"], "reason": "media_download_failed"}
            ad["media"] = []
            return
        path, digest = got
        path, digest = _larger_preview(
            path, digest, remote.get("fallback_urls") or [], ad, media_dir, downloader
        )
        from ad_spy_kit.media import shrink_image

        path = shrink_image(path, keep_originals=keep_originals)
        ad["media"] = [
            {
                "path": f"media/{path.name}",
                "durable": bool(remote.get("durable")),
                "kind": remote.get("kind") or "image",
            }
        ]
        ad["media_hash"] = digest

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, range(len(ads)), ads))
    return [skipped[i] for i in sorted(skipped)]


def image_counts(ads: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, int]:
    """Saved / failed / none counts for one read, for the run's progress line."""
    reasons = Counter(s.get("reason") for s in skipped)
    return {
        "saved": sum(1 for a in ads if any(m.get("path") for m in a.get("media") or [])),
        "failed": reasons.get("media_download_failed", 0),
        "none": reasons.get("no_media", 0) + reasons.get("video_no_preview", 0),
    }


def credits_spent(client: Any) -> int:
    """Credits this client spent, from ScrapeCreators' x-credits-used header (1 per call when
    the header is missing)."""
    total = 0
    for call in getattr(client, "calls", []):
        try:
            total += int(float(call.get("credits_used") or 1))
        except (TypeError, ValueError):
            total += 1
    return total


READ_MODES = ("longest", "most-shown", "newest")
# Rate limits and server hiccups: wait and try again (a 429 is not an answer).
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_WAIT_SECONDS = (3, 10, 30)


def read_params(
    *,
    newest: bool = False,
    today: date | None = None,
    read: str = "longest",
    min_days: int | None = None,
) -> dict[str, str]:
    """Ad Library filters for the read modes (see pull_via_scrapecreators).

    longest: live ads already running 30 days ago, most-shown first (date filter).
    most-shown: live ads of any age, most-shown first (no date filter).
    newest: the newest live ads.

    ScrapeCreators' company/ads endpoint has exactly two sorts: `total_impressions` (most
    shown first) and `relevancy_monthly_grouped` (most recent). There is no oldest-first or
    longest-running sort (docs.scrapecreators.com, checked 2026-11-05). The only lever on run
    length is the date filter, which is overlap-based: with status=ACTIVE, an `end_date` of
    N days ago returns only ads that were already running then. `min_days` moves that cutoff
    (default 30, the "solid" floor), so `--min-days 120` reads only ads live 120+ days at the
    same cost per page. It is opt-in, not the default: a brand with few ads that old would
    come back nearly empty, and the board's labels need the 30-day pool.
    """
    from ad_spy_kit.labels import SOLID_MIN_DAYS

    if newest or read == "newest":
        return {"status": "ACTIVE", "sort_by": "relevancy_monthly_grouped"}
    if read == "most-shown":
        return {"status": "ACTIVE", "sort_by": "total_impressions"}
    cutoff = (today or date.today()) - timedelta(days=min_days or SOLID_MIN_DAYS)
    return {
        "status": "ACTIVE",
        "sort_by": "total_impressions",
        "start_date": "2010-01-01",
        "end_date": cutoff.isoformat(),
    }


def pull_via_scrapecreators(
    competitor: dict[str, Any] | str,
    *,
    country: str = "US",
    max_ads: int = 30,
    media_dir: Path | None = None,
    newest: bool = False,
    today: date | None = None,
    read: str = "longest",
    retries: int = 3,
    min_days: int | None = None,
    keep_originals: bool = False,
) -> dict[str, Any]:
    """ScrapeCreators read → ads.raw.json dict. Raises MissingKey with a fix line when no key.

    Default: live ads that were already running 30+ days ago, most-shown first. The Ad
    Library has no "longest running" sort, but its date filter is overlap-based, so
    status=ACTIVE with end_date = 30 days ago returns only ads live 30+ days. Ads under 30
    days that slip through are dropped here too. `newest=True` reads the newest live ads.
    """
    if isinstance(competitor, str):
        competitor = resolve_via_scrapecreators(competitor, country=country)
    client = _client()
    from cie.scrapecreators_client import ScrapeCreatorsClientError as CieErr

    if newest:
        read = "newest"
    params = read_params(today=today, read=read, min_days=min_days)
    for attempt in range(retries + 1):
        try:
            # trim=False: the trimmed snapshot has no creative URLs, so nothing could be cached.
            raw_ads, _ = client.facebook_company_ads(
                page_id=competitor["page_id"],
                country=country,
                trim=False,
                max_ads=max_ads,
                extra_params=params,
            )
            break
        except CieErr as e:
            status = getattr(e, "status", None)
            if attempt < retries and status in RETRY_STATUSES:
                time.sleep(RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)])
                continue
            raise ScrapeCreatorsClientError(str(e), status) from e
    ads = [map_scrapecreators_ad(a) for a in raw_ads]
    from ad_spy_kit.labels import SOLID_MIN_DAYS

    floor = min_days or SOLID_MIN_DAYS
    too_new = []
    if read == "longest":
        too_new = [a for a in ads if (a.get("days_live") or 0) < floor]
        ads = [a for a in ads if a not in too_new]
    if competitor.get("page_name_from_ads"):
        name = next((a["page_name"] for a in ads if a.get("page_name")), "")
        if name:
            competitor["page_name"] = name
            competitor.pop("page_name_from_ads", None)
            check_not_excluded(name, competitor["page_id"])
    from ad_spy_kit.transcribe import current_mode

    fetch_videos = current_mode().effective == "openrouter"
    skipped = (
        cache_media(ads, media_dir, fetch_videos=fetch_videos, keep_originals=keep_originals)
        if media_dir is not None
        else []
    )
    for ad in ads:
        ad.pop("video_url", None)
    return {
        "competitor_id": competitor["page_id"],
        "pulled_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "scrapecreators",
        "collect_mode": "full",
        "total_available": len(ads),
        "import_cap_hit": len(raw_ads) >= max_ads,
        "read_mode": read,
        "read_cap": max_ads,
        "read_min_days": floor if read == "longest" else None,
        "requests": len(getattr(client, "calls", [])),
        "credits_spent": credits_spent(client),
        "dropped_too_new": len(too_new),
        "skipped": skipped,
        "ads": ads,
    }
