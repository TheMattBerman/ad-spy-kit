"""Tracked-competitors mode: the ads a user's tracked rivals keep running, on one board.

The agent saves StealAds replies as `tracked_rival_ads*.json` (or `.md` / `.txt`) in a run
folder. `ad-spy-kit tracked <run_dir>` groups the ads by rival, saves one folder per rival
under `brands/` (competitor.json, ads.raw.json, media/), then draws the category board:
top 10 brands by number of ads live 30+ days, 3 ads each, the shared label rule.

Two kinds of saved reply are read, mixed freely:
- `list_tracked_rival_ads` JSON (`response_format: "json"`, free, row `schema_version` 1):
  the search_ads row fields (cta, landing_url, hook.*, why, strength_label, group_id,
  variation_count, start_date, still_running, card_image_urls, ...) plus `ad_id`,
  `competitor_id`, `rival_name`, `days_live`, `status`, `format_filter`. A page holds up to
  three rivals (unfiltered, `order: "recent"`) or one (`competitor_id`), up to 50 rows, with
  the caption in `body_text` (280 characters with `compact`, the default). Each `next_cursor`
  page is its own file. Older rows with `banger_band` / `format: image` still read.
- `search_ads` / `find_winning_ads` replies (Markdown text or JSON) called with
  `tracked_rivals_only: true` and `brand_id`: the fallback for a workspace too big for
  `list_tracked_rival_ads`.
An optional `list_competitors.json` adds each rival's Facebook page id and country.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ad_spy_kit.errors import KitError
from ad_spy_kit.paths import visible

TRACKED_STEM = "tracked_rival_ads"
COMPETITOR_FILES = ("list_competitors.json", "competitors.json")
SUFFIXES = (".json", ".md", ".txt")
BODY_KEYS = ("primary_text", "body_text", "body", "text", "caption")
RIVAL_TAG = re.compile(r"\s*\(your rival\)\s*$", re.IGNORECASE)
READ_LIMIT = "exceeds the tool"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "rival"


def tracked_files(run_dir: Path) -> list[Path]:
    """Saved tracked-rival replies in a stable order."""
    return sorted(
        p for p in visible(run_dir.glob(f"{TRACKED_STEM}*")) if p.is_file() and p.suffix in SUFFIXES
    )


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """A `list_tracked_rival_ads` row or a search row → the row shape `map_stealads_ad` reads."""
    out = dict(row)
    if out.get("id") is None and out.get("ad_id") is not None:
        out["id"] = out["ad_id"]
    if "rival_name" in out or "competitor_id" in out:
        out["page_name"] = out.pop("rival_name", None) or out.get("page_name") or ""
        if out.get("days_live") is not None:
            out["run_duration_days"] = out["days_live"]
        out["format"] = "VIDEO" if str(out.get("format") or "").lower() == "video" else "IMAGE"
        out["first_seen_at"] = out.pop("first_seen", "") or ""
        out["last_seen_at"] = out.pop("last_seen", "") or ""
        for key in BODY_KEYS:
            if out.get(key):
                out["body_text"] = out[key]
                break
    else:
        out["page_name"] = RIVAL_TAG.sub("", str(out.get("page_name") or ""))
    return out


def load_page(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows, the page's own fields) for one saved reply, JSON or Markdown text."""
    from ad_spy_kit.sl_adapter import unwrap_recording
    from ad_spy_kit.stealads_text import load_saved

    doc = unwrap_recording(load_saved(path))
    rows = [normalize_row(r) for r in doc.get("ads") or [] if isinstance(r, dict)]
    return [r for r in rows if r.get("id")], doc


def load_competitors(run_dir: Path) -> dict[str, dict[str, Any]]:
    """competitor id → {name, facebook_page_id, country_code, ads_tracked, count_status} from the
    saved `list_competitors` pages (`list_competitors.json`, `list_competitors.page2.json`, ...).

    A rival whose count isn't ready has `count_status: "pending"` and `ads_tracked: null`: kept
    as is, never read as zero."""
    paths = [run_dir / name for name in COMPETITOR_FILES]
    paths += sorted(visible(run_dir.glob("list_competitors.page*.json")))
    out: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        items = doc.get("competitors") if isinstance(doc, dict) else doc
        for c in items or []:
            if isinstance(c, dict) and c.get("id"):
                out.setdefault(str(c["id"]), c)
    return out


def _explain_empty(files: list[Path]) -> KitError:
    limit = any(READ_LIMIT in p.read_text(errors="replace") for p in files)
    if limit:
        return KitError(
            "StealAds refused the read: this brand's tracked set is over the tool's read limit.",
            fix=(
                "Pick the rivals to read (the user's names, or the biggest by ads_tracked in "
                "list_competitors), call search_ads or find_winning_ads for each with brand_id, "
                "competitor_id and tracked_rivals_only: true, save each reply as "
                "tracked_rival_ads.<rival>.md, then rerun."
            ),
            code="tracked_over_limit",
        )
    return KitError(
        f"{files[0].parent if files else 'The run folder'} holds no tracked ads.",
        fix=(
            "Save each list_tracked_rival_ads reply as tracked_rival_ads.json (next pages as "
            "tracked_rival_ads.page2.json and so on), then rerun."
        ),
        code="tracked_empty",
    )


def _pulled_at(rows: list[dict[str, Any]]) -> str:
    seen = max((str(r.get("last_seen_at") or "") for r in rows), default="")
    return seen or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_brand_folders(
    run_dir: Path, *, images: bool = True, brand_id: str | None = None
) -> dict[str, Any]:
    """tracked_rival_ads* → brands/<rival>/{competitor.json, ads.raw.json, media/}."""
    from ad_spy_kit.competitor_rows import competitor_from_ads
    from ad_spy_kit.sc_client import cache_media, reply_schema
    from ad_spy_kit.sl_adapter import map_stealads_ad

    files = tracked_files(run_dir)
    if not files:
        raise KitError(
            f"{run_dir} has no tracked_rival_ads files.",
            fix="Save each list_tracked_rival_ads reply there as tracked_rival_ads*.json.",
            code="tracked_empty",
        )
    rows: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for path in files:
        page, doc = load_page(path)
        for r in page:
            rows.setdefault(str(r["id"]), r)
        if doc.get("has_more") and doc.get("next_cursor"):
            pending.append(path.name)
    if not rows:
        raise _explain_empty(files)

    competitors = load_competitors(run_dir)
    by_page = {
        str(c["facebook_page_id"]): c for c in competitors.values() if c.get("facebook_page_id")
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows.values():
        cid = str(r.get("competitor_id") or "")
        info = competitors.get(cid) or by_page.get(str(r.get("facebook_page_id") or "")) or {}
        if info.get("id") and not cid:
            r["competitor_id"] = str(info["id"])
            cid = str(info["id"])
        if info.get("facebook_page_id") and not r.get("facebook_page_id"):
            r["facebook_page_id"] = str(info["facebook_page_id"])
        key = cid or str(r.get("facebook_page_id") or "") or slug(r.get("page_name") or "")
        groups[key].append(r)

    brands_dir = run_dir / "brands"
    if brands_dir.exists():
        # Derived output, always rebuilt from the saved replies. Ignore errors: external
        # drives leave "._name" metadata files that vanish while the tree is being removed.
        shutil.rmtree(brands_dir, ignore_errors=True)
    used: set[str] = set()
    written: list[str] = []
    for key, rs in groups.items():
        ads = [map_stealads_ad(r) for r in rs]
        info = competitors.get(key) or by_page.get(key) or {}
        name = str(info.get("name") or Counter(r["page_name"] for r in rs).most_common(1)[0][0])
        folder = slug(name)
        if folder in used:
            folder = f"{folder}-{slug(key)[:12]}"
        used.add(folder)
        bdir = brands_dir / folder
        comp = competitor_from_ads(
            ads,
            query=name,
            country=str(info.get("country_code") or ""),
            competitor_id=str(rs[0].get("competitor_id") or "") or None,
            brand_id=brand_id,
            tracked=True,
        )
        comp["page_name"] = name
        skipped: list[dict[str, Any]] = []
        if images:
            remote = [a for a in ads if any("url" in m for m in a.get("media") or [])]
            no_media = [a for a in ads if not a.get("media")]
            skipped = cache_media(remote + no_media, bdir / "media")
        else:
            for a in ads:
                a["media"] = []
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "competitor.json").write_text(json.dumps(comp, indent=2) + "\n")
        raw = {
            "competitor_id": key,
            "pulled_at": _pulled_at(rs),
            "source": "stealads",
            **reply_schema(rs),
            "recorded_from": "list_tracked_rival_ads",
            "collect_mode": "full",
            "total_available": len(ads),
            "import_cap_hit": False,
            "skipped": skipped,
            "ads": ads,
        }
        (bdir / "ads.raw.json").write_text(json.dumps(raw, indent=2) + "\n")
        written.append(name)
    return {"rivals": written, "ads": len(rows), "pages_with_more": pending}


def run(
    run_dir: Path,
    *,
    title: str | None = None,
    images: bool = True,
    board_brands: int | None = None,
    brand_id: str | None = None,
) -> int:
    """Saved tracked replies → brand folders → category board (PNG, X slices, summary, csv)."""
    from ad_spy_kit import category

    info = write_brand_folders(run_dir, images=images, brand_id=brand_id)
    print(f"read {info['ads']} tracked ads from {len(info['rivals'])} rivals")
    for name in info["pages_with_more"]:
        print(
            f"note: {name} says more results exist (has_more). Fetch its next_cursor and save "
            "it as another tracked_rival_ads*.json to read the next rival.",
        )
    return category.draw_saved(
        run_dir,
        title=title or run_dir.name.replace("-", " ").title(),
        max_ads=category.TRACKED_MAX_ADS,
        board_brands=board_brands or category.MAX_BOARD_BRANDS,
        rank="long",
    )
