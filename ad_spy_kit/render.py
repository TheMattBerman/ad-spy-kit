from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from ad_spy_kit.aspect import card_frame, css_ratio, image_size, is_video
from ad_spy_kit.hooks import HOOK_TAGS, best_hook, first_line
from ad_spy_kit.plain import BF_NAMES, FORMAT_NAMES, URGENCY_NAMES, VERDICT_NAMES
from ad_spy_kit.spend import thin_read_note
from ad_spy_kit.template_text import has_template, is_catalog_ad, scrub_text
from ad_spy_kit.validate import assert_valid


def _b64_file(path: Path) -> str:
    """A data URI for the board. Anything over 1200px on its long edge is embedded as a
    downscaled JPEG (a 6000px original made a 26 MB board.html)."""
    from ad_spy_kit.media import MAX_EDGE, shrink_bytes

    data = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    size = image_size(path)
    if size and (max(size) > MAX_EDGE or len(data) > 900_000):
        small = shrink_bytes(data)
        if small is not None:
            data, ext = small, "jpeg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext or "png"
    return f"data:image/{mime};base64,{base64.b64encode(data).decode('ascii')}"


_HIDDEN_SCORE_KEYS = frozenset({"gap_score", "opportunity_score", "score", "winner_score"})


def _without_scores(item: dict[str, Any]) -> dict[str, Any]:
    """Drop internal ranking scores so templates cannot render them."""
    return {k: v for k, v in item.items() if k not in _HIDDEN_SCORE_KEYS}


_MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _is_blank(path: Path) -> bool:
    """A black or flat video frame says nothing on the wall."""
    from PIL import Image, ImageStat

    with Image.open(path) as im:
        return ImageStat.Stat(im.convert("L").resize((32, 32))).stddev[0] < 6


def _small_b64(path: Path, width: int = 160) -> str:
    """A small JPEG data URI for the dense ad wall (keeps board.html light)."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = __import__("io").BytesIO()
        im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _ad_wall(ads_raw: dict[str, Any], media_dir: Path, cap: int = 48) -> list[dict[str, Any]]:
    """Every checked creative that has a saved image, longest-running first: the density wall.
    Near-identical creatives (same StealAds group or same image) get one tile, not one each."""
    from ad_spy_kit.dedupe import creative_groups

    ads = sorted(ads_raw.get("ads", []), key=lambda a: -(a.get("days_live") or 0))
    out = []
    for group in creative_groups(ads):
        for a in group:
            path = _media_file(media_dir, str(a.get("ad_id")))
            if path is None or _is_blank(path):
                continue
            out.append(
                {
                    "image_b64": _small_b64(path),
                    "label": a.get("strength_label") or "",
                    "copies": len(group),
                }
            )
            # A carousel shows its other cards beside the cover (at most 2 extra tiles).
            for card in (a.get("card_media") or [])[:2]:
                card_path = media_dir.parent / str(card.get("path") or "")
                if card_path.is_file() and not _is_blank(card_path):
                    out.append(
                        {
                            "image_b64": _small_b64(card_path),
                            "label": a.get("strength_label") or "",
                            "copies": 1,
                            "card": True,
                        }
                    )
            break
        if len([t for t in out if not t.get("card")]) >= cap:
            break
    return out


def wall_caption(ads_raw: dict[str, Any], shown: int) -> str:
    """The all-ads card title. 30 ads that are 21 different creatives say so."""
    from ad_spy_kit.dedupe import distinct_creatives

    n_ads = ads_raw.get("total_available") or len(ads_raw.get("ads", []))
    creatives = distinct_creatives(ads_raw.get("ads", [])) or n_ads
    if shown < creatives:
        return (
            f"{shown} of {creatives} creatives" if creatives < n_ads else f"{shown} of {n_ads} ads"
        )
    if creatives < n_ads:
        return f"{creatives} creatives from {n_ads} ads"
    return "1 ad" if n_ads == 1 else f"All {n_ads} ads"


def _label_counts(wall: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Label counts for the ads drawn on the board only, so the tile never says "30 testing"
    next to six ads."""
    from ad_spy_kit.labels import LABELS

    counts: dict[str, int] = {}
    for w in wall:
        label = w.get("strength_label")
        if label in LABELS:
            counts[label] = counts.get(label, 0) + 1
    return [(label, counts[label]) for label in LABELS if counts.get(label)]


_MENTION_GAP = re.compile(
    r"^(\d+) of these ads mention (.+?), (?:and )?none leads? with it\.?$", re.I
)


def opening_parts(gap: str) -> tuple[str, int | None]:
    """(one headline-size line, how many ads mention it) for the board. "2 of these ads
    mention the 60-day guarantee, none leads with it" reads as "None lead with the 60-day
    guarantee." plus a big 2; any other gap is shown as written."""
    gap = gap.strip()
    m = _MENTION_GAP.match(gap)
    if m:
        return f"None lead with {m.group(2)}.", int(m.group(1))
    return (gap if gap.endswith((".", "!", "?")) else gap + "."), None


def _opening(analysis: dict[str, Any], counters: dict[str, Any]) -> list[dict[str, Any]]:
    """The one opening the board shows: the gap the first counter-ad answers, else the top gap."""
    gaps = analysis.get("gaps", [])
    first = (counters.get("counters") or [{}])[0]
    ref = first.get("gap_ref")
    picked = [gaps[ref]] if isinstance(ref, int) and 0 <= ref < len(gaps) else gaps[:1]
    out = []
    for g in picked:
        g = _without_scores(g)
        g["big"], g["mention_count"] = opening_parts(g.get("gap", ""))
        out.append(g)
    return out


FOOT_NOTE = "Running long doesn't prove an ad works. It shows what they keep paying for."


def _media_file(media_dir: Path, ad_id: str) -> Path | None:
    for ext in _MEDIA_EXTS:
        path = media_dir / f"{ad_id}{ext}"
        if path.is_file():
            return path
    return None


# A video's preview frame can come back tiny (110px wide). Drawn to fill a 236px hero it turns
# to mush, so a small one is shown at its own size on the card's plain ground instead.
TINY_PREVIEW_WIDTH = 300


def _frame_fields(img_path: Path | None, fmt: str | None, ad: dict[str, Any]) -> dict[str, Any]:
    kind = next((m.get("kind") for m in ad.get("media") or [] if m.get("kind")), None)
    video = is_video(fmt, kind) or kind == "video_preview"
    size = image_size(img_path)
    frame = card_frame(size, video=video)
    tiny = bool(video and size and size[0] < TINY_PREVIEW_WIDTH)
    return {"is_video": video, "frame": frame, "frame_css": css_ratio(frame), "tiny_preview": tiny}


def _depth_value(depth: Any) -> float:
    """'40%' → 40. Only percents share a scale, so '$20', 'VIP' and '3 full sizes' draw no
    bar (a $ amount next to a % would be a visual lie). Used for bar length, never printed."""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(depth or ""))
    return float(m.group(1)) if m else 0.0


# Plain words for the board. Internal codes never print (ad_spy_kit/plain.py).
def _label_meanings() -> dict[str, str]:
    from ad_spy_kit.labels import LABEL_MEANINGS

    return dict(LABEL_MEANINGS)


def label_legend() -> str:
    return "Labels: " + " · ".join(f"{k}: {v}" for k, v in _label_meanings().items())


def sample_chip(ads_raw: dict[str, Any]) -> str:
    """Header chip for sample boards only. A reader's own run shows no vendor chip."""
    if ads_raw.get("synthetic"):
        return "made-up sample brand"
    return ""


def data_line(ads_raw: dict[str, Any]) -> str:
    if ads_raw.get("synthetic"):
        return "data: made up for this sample"
    if "stealads.ai" in str(ads_raw.get("recorded_from") or "") or ads_raw.get("source") == (
        "stealads"
    ):
        return "data: Meta Ad Library, via StealAds"
    return "data: Meta Ad Library"


def sort_note(ads_raw: dict[str, Any], winners: dict[str, Any]) -> str:
    from ad_spy_kit.labels import SOLID_MIN_DAYS

    if ads_raw.get("synthetic"):
        return "sorted by how long each ad has run"
    if winners.get("rank_source") == "find_bangers":
        return "ranked by StealAds"
    if ads_raw.get("read_mode") == "newest":
        return "their newest live ads"
    return f"ads live {SOLID_MIN_DAYS}+ days, longest first"


def wall_title(ads_raw: dict[str, Any], winners: dict[str, Any], wall: list[dict]) -> str:
    """Never promise "keep running" when the wall is all new ads."""
    labels = [w.get("strength_label") for w in wall]
    if wall and all(label == "testing" for label in labels):
        return "Their newest ads (none has run 2 weeks)"
    if winners.get("rank_source") == "find_bangers" and not ads_raw.get("synthetic"):
        return "Their top ads, as StealAds ranks them"
    return "Their longest-running ads"


def pretty_date(text: str) -> str:
    from datetime import date

    try:
        d = date.fromisoformat(str(text)[:10])
    except ValueError:
        return str(text)
    return f"{d:%b} {d.day}, {d.year}"


def live_30(ads_raw: dict[str, Any]) -> tuple[int, str]:
    """The 30+ day counter and its label.

    StealAds library rows can send `still_running: null` (delivery unknown). Those ads ran
    30+ days but can't be called live, so any such row switches the tile to "ran 30+ days".
    """
    from ad_spy_kit.labels import SOLID_MIN_DAYS

    long_runners = [
        a for a in ads_raw.get("ads", []) if (a.get("days_live") or 0) >= SOLID_MIN_DAYS
    ]
    if any("still_running" in a and a["still_running"] is None for a in long_runners):
        return len(long_runners), "ran 30+ days"

    def live(a: dict[str, Any]) -> bool:
        return bool(a.get("still_running", a.get("is_active", True)))

    return sum(1 for a in long_runners if live(a)), "live 30+ days"


OFFER_LABELS = {
    "pct_off": "% off",
    "dollar_off": "$ off",
    "gift_with_purchase": "gift w/ order",
    "free_shipping": "free ship",
    "early_access": "early access",
    "price_drop": "price drop",
    "price_claim": "price claim",
    "bogo": "buy one get one",
    "bundle": "bundle",
    "guarantee": "guarantee",
}
# A price comparison ("up to 80% less than you'd expect") is not a discount: it never feeds the
# TOP DISCOUNT number or an offer bar.
NO_DEPTH_TYPES = ("price_claim",)

# Text boxes on the board whose content is wider/taller than their box (spec §12 runtime gate).
_OVERFLOW_JS = """
() => {
  const out = [];
  const h1 = document.querySelector('h1.verdict');
  if (h1 && h1.scrollWidth > h1.clientWidth + 1)
    out.push('headline is cut off at the board width: ' + h1.textContent.trim().slice(0, 60));
  const fold = window.innerHeight - 28;  // footer strip
  for (const el of document.querySelectorAll('.board-root .card *, .verdict .line, .foot span')) {
    if (el.children.length || !el.textContent.trim()) continue;
    const clips = getComputedStyle(el).overflow !== 'visible';
    if (clips && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1))
      out.push('clipped ' + (el.className || el.tagName) + ': '
               + el.textContent.trim().slice(0, 60));
  }
  // Carousel slices sit off-canvas: text must stay inside its slice and clear the footer lines.
  for (const sl of document.querySelectorAll('.slice')) {
    const sr = sl.getBoundingClientRect();
    const inner = sl.querySelector('.slice-inner');
    const note = sl.querySelector('.slice-note');
    const label = sl.querySelector('.slice-tag')?.textContent.trim().slice(-30) || sl.id;
    const noteTop = note ? note.getBoundingClientRect().top : sr.bottom;
    for (const el of sl.querySelectorAll('*')) {
      if (el.children.length || !el.textContent.trim()) continue;
      const r = el.getBoundingClientRect();
      if (r.right > sr.right - 40 || r.left < sr.left)
        out.push('slice text runs off the edge (' + label + '): '
                 + el.textContent.trim().slice(0, 60));
      if (!el.closest('.slice-note, .slice-handle') && r.bottom > noteTop - 4)
        out.push('slice text collides with the footer (' + label + '): '
                 + el.textContent.trim().slice(0, 60));
    }
    if (inner && inner.scrollHeight > inner.clientHeight + 1)
      out.push('slice content taller than the slice (' + label + ')');
  }
  // The counter-ad panel's text must stop above its pinned StealAds line.
  const cta = document.querySelector('.counter .cad-cta');
  if (cta) {
    const top = cta.getBoundingClientRect().top;
    for (const el of document.querySelectorAll('.counter .cad-txt p')) {
      if (el.getBoundingClientRect().bottom > top + 1)
        out.push('counter-ad text runs under the StealAds line: '
                 + el.textContent.trim().slice(0, 50));
    }
  }
  for (const card of document.querySelectorAll('.main-grid .card')) {
    const r = card.getBoundingClientRect();
    if (r.bottom > fold)
      out.push('below the fold: ' + (card.querySelector('.ttl b')?.textContent || card.className));
  }
  return out;
}
"""


def _ad_lookup(ads_raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["ad_id"]: a for a in ads_raw.get("ads", [])}


_first_line = first_line  # kept for callers that import it from here


def _wall_hook(ad_id: str, ad: dict[str, Any], analysis: dict[str, Any]) -> dict[str, str]:
    """The analysed hook for this winner, else the ad's best hook by priority. A catalog
    ad with no written copy has no hook: the card says so instead of quoting a template."""
    for h in analysis.get("hooks", []):
        if h.get("ad_id") == ad_id and h.get("hook_text"):
            text, source = h["hook_text"], h.get("hook_source") or "copy"
            break
    else:
        text, source = best_hook(ad)
    if has_template(text):
        text = ""
    return {"hook_text": text, "hook_source": source, "hook_tag": HOOK_TAGS[source]}


NO_COPY_NOTE = "No written copy. Meta fills in the product."


def _version_lines(w: dict[str, Any], ads_by_id: dict[str, dict[str, Any]]) -> list[str]:
    """The distinct opening lines among an ad's merged versions (same picture, other copy)."""
    seen: dict[str, str] = {}
    for ad_id in [w["ad_id"], *(w.get("dupes_merged") or [])]:
        ad = ads_by_id.get(ad_id) or {}
        line, _ = best_hook(ad) if ad else ("", "copy")
        if line and not has_template(line):
            seen.setdefault(" ".join(line.lower().split()), line)
    return list(seen.values())


def _tile_grid(count: int) -> tuple[int, int]:
    """(columns, tiles to draw) for the summary slice: a whole number of full rows, so the
    last row is never half empty. Up to 6 tiles sit in one row; more pick the column count
    (3 to 5 under 12 tiles, else 5 to 8) that drops the fewest, wider breaking a tie."""
    if count <= 6:
        return max(count, 1), count
    span = range(3, 6) if count < 12 else range(5, 9)
    best = min(span, key=lambda c: (count % c, -c))
    return best, count - count % best


def build_context(
    *,
    competitor: dict[str, Any],
    ads_raw: dict[str, Any],
    winners: dict[str, Any],
    analysis: dict[str, Any],
    counters: dict[str, Any],
    media_dir: Path,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    run_dir = run_dir or media_dir.parent
    ads_by_id = _ad_lookup(ads_raw)
    wall: list[dict[str, Any]] = []
    dropped: list[str] = []
    for w in winners.get("winners", []):
        if len(wall) >= 6:
            break
        ad = ads_by_id.get(w["ad_id"], {})
        img_path = _media_file(media_dir, w["ad_id"])
        if img_path is None:
            # Spec §4.6: never render a broken image; the next winner moves up.
            dropped.append(w["ad_id"])
            continue
        hook = _wall_hook(w["ad_id"], ad, analysis)
        lines = _version_lines(w, ads_by_id)
        wall.append(
            {
                **_without_scores(w),
                "headline": "" if has_template(ad.get("headline")) else ad.get("headline", ""),
                **hook,
                # Badge true catalog (DPA) ads, and any dynamic ad with no written copy.
                "catalog": (
                    str(ad.get("format") or w.get("format") or "").upper() == "DPA"
                    or ((is_catalog_ad(ad) or bool(ad.get("catalog"))) and not hook["hook_text"])
                ),
                "no_copy": not hook["hook_text"],
                "no_copy_note": NO_COPY_NOTE,
                "version_lines": lines,
                "versions_differ": len(lines) > 1,
                "image_b64": _b64_file(img_path),
                **_frame_fields(img_path, w.get("format") or ad.get("format"), ad),
                "ad_library_url": ad.get("ad_library_url", ""),
                "cta": str(ad.get("cta") or "").strip(),
                "landing_domain": str(ad.get("landing_domain") or "").strip(),
                "steal_caution": ad.get("steal_caution") or "",
                "versions": max(
                    int(w.get("variations") or 0), 1 + len(w.get("dupes_merged") or [])
                ),
            }
        )

    skipped = ads_raw.get("skipped") or []
    offer_map = analysis.get("offer_map", [])
    depths = [
        0.0 if o.get("offer_type") in NO_DEPTH_TYPES else _depth_value(o.get("discount_depth"))
        for o in offer_map
    ]
    deepest = max((d for d in depths if d), default=0)
    ladder = [
        {
            **o,
            "discount_depth": ""
            if o.get("offer_type") in NO_DEPTH_TYPES
            else o.get("discount_depth"),
            "bar_pct": round(100 * d / deepest) if d and deepest else 0,
            "evidence_tag": HOOK_TAGS[o.get("evidence_source") or "copy"],
        }
        for o, d in zip(offer_map, depths, strict=True)
    ]
    # An offer with no quote has nothing to show: no "none · caption" card, no empty section.
    # The same quote from several ads shows once, with the other ads named ("also #05").
    rank_by_id = {
        w["ad_id"]: f"#{int(w['display_rank']):02d}"
        for w in winners.get("winners", [])
        if w.get("display_rank") is not None
    }
    offers_shown: list[dict[str, Any]] = []
    by_quote: dict[tuple[str, str], dict[str, Any]] = {}
    for o in ladder:
        if not str(o.get("evidence") or "").strip():
            continue
        key = (" ".join(str(o["evidence"]).lower().split()), str(o.get("offer_type")))
        if key in by_quote:
            other = rank_by_id.get(str(o.get("ad_id")))
            if other and other not in by_quote[key]["also"]:
                by_quote[key]["also"].append(other)
            continue
        o["also"] = []
        by_quote[key] = o
        offers_shown.append(o)
    for o in offers_shown:
        path = _media_file(media_dir, str(o.get("ad_id")))
        o["thumb"] = _small_b64(path, 240) if path is not None and not _is_blank(path) else ""
    formats = analysis.get("formats", [])
    fmt_total = sum(int(f.get("count") or 0) for f in formats)
    bf_tagged = sum(
        1 for w in winners.get("winners", []) if w.get("bf_tag") in ("bf_live", "bf_teaser")
    )
    pulled = ads_raw.get("pulled_at", "")[:10]
    opening = _opening(analysis, counters)
    opening_ids = [i for g in opening for i in g.get("evidence_ad_ids", [])]
    opening_thumbs = []
    for ad_id in dict.fromkeys(opening_ids):
        path = _media_file(media_dir, str(ad_id))
        rank = {w["ad_id"]: f"#{int(w['display_rank']):02d}" for w in winners.get("winners", [])}
        if path is not None and not _is_blank(path) and ad_id in rank:
            opening_thumbs.append({"image_b64": _small_b64(path, 220), "rank": rank[ad_id]})
    ad_wall = _ad_wall(ads_raw, media_dir)
    hidden = winners.get("hidden") or []
    longest = max((int(a.get("days_live") or 0) for a in ads_raw.get("ads", [])), default=0)
    mention_shown = any(g.get("mention_count") for g in opening)
    slices = [("summary", "Summary")]
    if wall:
        slices.append(("wall", wall_title(ads_raw, winners, wall)))
    # Offers earns a slide with a discount to lead on, or three offers to list. One thin
    # offer would leave the slide mostly blank, so it stays on the board and in teardown.md.
    if offers_shown and (deepest or len(offers_shown) >= 3):
        slices.append(("offers", "Offers"))
    if opening:
        slices.append(("opening", "The opening"))
    if counters.get("counters"):
        slices.append(("counter", "Counter-ad brief"))
    live_30_count, live_30_label = live_30(ads_raw)
    return {
        "competitor_name": competitor.get("page_name")
        or analysis.get("competitor")
        or "Competitor",
        "checked_date": pretty_date(pulled or datetime.now(UTC).strftime("%Y-%m-%d")),
        "ads_checked": ads_raw.get("total_available") or len(ads_raw.get("ads", [])),
        "live_30": live_30_count,
        "live_30_label": live_30_label,
        "longest_days": longest,
        "longest_unit": "day" if longest == 1 else "days",
        "label_counts": _label_counts(wall),
        "ad_wall": ad_wall,
        "wall_caption": wall_caption(ads_raw, sum(1 for t in ad_wall if not t.get("card"))),
        "tile_cols": max(3, min(10, round((len(ad_wall) * 2.0) ** 0.5))),
        "slice_tile_cols": _tile_grid(len(ad_wall))[0],
        "slice_tiles": ad_wall[: _tile_grid(len(ad_wall))[1]],
        "catalog_count": sum(1 for a in ads_raw.get("ads", []) if is_catalog_ad(a)),
        "read_note": thin_read_note(ads_raw, "<this folder>"),
        "hidden_count": len(hidden),
        "hidden_ads": hidden,
        "slices": [{"key": k, "title": t} for k, t in slices],
        "opening_thumbs": opening_thumbs[:6],
        "evi_cols": max(3, min(6, len(opening_thumbs))),
        "opening_checked": len(set(opening_ids)),
        "nums_shown": mention_shown or bool(deepest),
        "title_line": analysis.get("headline", {}).get("bottom")
        or analysis.get("headline", {}).get("top", ""),
        "opening": opening,
        "foot_note": FOOT_NOTE,
        "bf_tagged": bf_tagged,
        "rank_source": winners.get("rank_source"),
        "sort_note": sort_note(ads_raw, winners),
        "wall_title": wall_title(ads_raw, winners, wall),
        "sample_chip": sample_chip(ads_raw),
        "data_line": data_line(ads_raw),
        "thin_signal": winners.get("thin_signal", False),
        "cleared_count": max(
            0, int(winners.get("pool_size") or 0) - len(winners.get("quarantined") or [])
        ),
        "bf_names": BF_NAMES,
        "verdict_names": VERDICT_NAMES,
        "urgency_names": URGENCY_NAMES,
        "format_names": FORMAT_NAMES,
        "label_legend": label_legend(),
        "label_meanings": _label_meanings(),
        "headline_top": analysis.get("headline", {}).get("top", ""),
        "headline_bottom": analysis.get("headline", {}).get("bottom", ""),
        "stats": analysis.get("stats", []),
        "offer_map": ladder,
        "offers_shown": offers_shown,
        "offer_rows": min(len(offers_shown), 3 if deepest else 4),
        "offer_labels": OFFER_LABELS,
        "deepest_offer": next(
            (o for o, d in zip(ladder, depths, strict=True) if d and d == deepest), None
        ),
        "hooks": [
            {**h, "hook_tag": HOOK_TAGS[h.get("hook_source") or "copy"]}
            for h in analysis.get("hooks", [])[:6]
        ],
        "formats": [
            {
                **f,
                "share_pct": round(100 * int(f.get("count") or 0) / fmt_total) if fmt_total else 0,
            }
            for f in formats
        ],
        # Gap engine order is kept; numeric scores are internal-only and never rendered.
        "gaps": [_without_scores(g) for g in analysis.get("gaps", [])[:3]],
        "steal_this": analysis.get("steal_this", []),
        "winner_wall": wall,
        "counters": counters.get("counters", []),
        "counter_assets": {
            str(c.get("gap_ref", i)): _b64_file(run_dir / c["asset_path"])
            for i, c in enumerate(counters.get("counters", []))
            if c.get("asset_path") and (run_dir / c["asset_path"]).is_file()
        },
        "video_skipped": sum(1 for s in skipped if s.get("reason") == "video_no_preview"),
        "dropped_no_media": dropped,
        "source": sample_chip(ads_raw) or data_line(ads_raw).removeprefix("data: "),
        # The board names ads by their winner rank (#01), never by raw ad id.
        "id_of_rank": {
            f"#{int(w['display_rank']):02d}": w["ad_id"]
            for w in winners.get("winners", [])
            if w.get("display_rank") is not None
        },
        "rank_of": {
            w["ad_id"]: f"#{int(w['display_rank']):02d}"
            for w in winners.get("winners", [])
            if w.get("display_rank") is not None
        },
    }


def keep_words(text: str) -> Markup:
    """Headline text where a hyphenated word ("60-day") never splits across lines."""
    return Markup(" ").join(
        Markup('<span class="nw">{}</span>').format(w) if "-" in w else escape(w)
        for w in str(text).split(" ")
    )


def render_html(
    *,
    template: str,
    context: dict[str, Any],
    templates_dir: Path,
    out_html: Path,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["keep_words"] = keep_words
    tpl = env.get_template(template)
    html = tpl.render(**context, ds=context)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html)
    return html


def screenshot_html(
    html_path: Path,
    png_path: Path,
    *,
    width: int,
    height: int,
    device_scale_factor: float = 1.0,
    check_overflow: bool = False,
) -> list[str]:
    """Screenshot the page. With check_overflow, return text boxes whose content is clipped."""
    from playwright.sync_api import sync_playwright

    png_path.parent.mkdir(parents=True, exist_ok=True)
    uri = html_path.resolve().as_uri()
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=device_scale_factor,
        )
        page.goto(uri, wait_until="networkidle")
        page.screenshot(path=str(png_path), type="png")
        overflow = page.evaluate(_OVERFLOW_JS) if check_overflow else []
        browser.close()
    return overflow


def chromium_fix() -> str:
    kit = Path(__file__).resolve().parents[1]
    return f'uv sync --project "{kit}" && uv run --project "{kit}" playwright install chromium'


def launch_chromium(p: Any) -> Any:
    """Start headless Chromium, or stop with a plain message and the one-line fix."""
    from playwright.sync_api import Error as PlaywrightError

    from ad_spy_kit.errors import KitError

    try:
        return p.chromium.launch()
    except PlaywrightError as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            raise KitError(
                "The browser that draws the board (Chromium) isn't installed yet.",
                fix=f"Run this once, then try again: {chromium_fix()}",
                code="chromium_missing",
            ) from e
        raise


def _library_link(url: str) -> str:
    """Ad Library links only for real (numeric) ad IDs; sample ads have none."""
    import re

    return url if url and re.search(r"[?&]id=\d{6,}", url) else ""


def _wall_heading(ctx: dict[str, Any]) -> str:
    """Section title for the wall. A title that already carries its own note in brackets
    ("Their newest ads (none has run 2 weeks)") gets no second bracket."""
    title = ctx["wall_title"]
    return title if "(" in title else f"{title} ({ctx['sort_note']})"


def teardown_markdown(ctx: dict[str, Any]) -> str:
    """Swipe file: the board as text, every quote tied to an ad. Scores never appear (gate B1)."""
    lines = [
        f"# {ctx['competitor_name']} teardown (checked {ctx['checked_date']}, {ctx['source']})",
        "",
        (f"{ctx['headline_top']} " if ctx["headline_top"] else "") + f"{ctx['label_legend']}.",
        "",
        f"**{ctx['headline_bottom']}**",
        "",
        f"## {_wall_heading(ctx)}",
    ]
    for w in ctx["winner_wall"]:
        band = f" · {w['strength_label']}" if w.get("strength_label") else ""
        url = _library_link(w.get("ad_library_url", ""))
        link = f" · [Ad Library]({url})" if url else ""
        cat = " · catalog ad" if w.get("catalog") else ""
        if w.get("no_copy"):
            lines.append(
                f"{w.get('display_rank', '')}. **{w['ad_id']}**{band}{cat}: {w['no_copy_note']}"
            )
        else:
            lines.append(
                f'{w.get("display_rank", "")}. **{w["ad_id"]}**{band}{cat}: "{w["hook_text"]}"'
                f" ({w['hook_tag']})"
            )
        lines.append(f"   {w.get('why') or ''}{link}")
        if w.get("versions_differ"):
            others = " / ".join(f'"{x}"' for x in w["version_lines"])
            lines.append(f"   {w['versions']} versions, different captions: {others}")
        if w.get("steal_caution"):
            lines.append(f"   Careful: {w['steal_caution']}")
    if ctx["catalog_count"]:
        n = ctx["catalog_count"]
        of = f"All {n}" if n >= ctx["ads_checked"] else f"{n} of the {ctx['ads_checked']}"
        lines += [
            "",
            f"{of} ads checked are catalog or dynamic ads: Meta fills in the product per "
            "viewer, so they carry no copy of their own.",
        ]
    if ctx.get("read_note"):
        lines += ["", ctx["read_note"]]
    if ctx["hidden_ads"]:
        n = ctx["hidden_count"]
        noun = "ad" if n == 1 else "ads"
        lines += ["", f"## {n} newer {noun} not shown (under 7 days old, under 3 versions)"]
        for h in ctx["hidden_ads"]:
            copies = f" (+{h['copies'] - 1} copies)" if h.get("copies", 1) > 1 else ""
            lines.append(f'- {h["ad_id"]}: "{h.get("headline") or "no headline"}"{copies}')
    if ctx["offers_shown"]:
        lines += ["", "## Offers"]
        for o in ctx["offers_shown"]:
            ids = ", ".join([o["ad_id"], *(ctx["id_of_rank"].get(r, r) for r in o["also"])])
            kind = OFFER_LABELS.get(o["offer_type"], o["offer_type"])
            depth = f", {o['discount_depth']}" if o.get("discount_depth") else ""
            lines.append(f'- {ids}: {kind}{depth} · "{o["evidence"]}" ({o["evidence_tag"]})')
    lines += ["", "## Hooks (word for word)"]
    lines += [
        f'- {h["ad_id"]}: "{h["hook_text"]}" ({h["hook_tag"]}; {h["pattern"]})'
        for h in ctx["hooks"]
    ]
    lines += ["", "## The opening (what none of these ads say)"]
    for g in ctx["gaps"]:
        lines.append(f"- {g['gap']} (checked against {', '.join(g['evidence_ad_ids'])})")
        for e in (g.get("mentions") or {}).get("evidence") or []:
            lines.append(f'  - {e["ad_id"]} ({HOOK_TAGS[e["source"]]}): "{e["quote"]}"')
        if g.get("counter_angle"):
            lines.append(f"  Your angle: {g['counter_angle']}")
    lines += ["", "## Steal / skip"]
    for st in ctx["steal_this"]:
        lines += [f"- Steal: {st['template']}", f"  Skip: {st['dont_copy']}"]
    if ctx["counters"]:
        lines += ["", "## Your counter-ad briefs"]
        for c in ctx["counters"]:
            theirs = ctx["rank_of"].get(c.get("beats_ad_id"), "theirs")
            lines += [
                f"### {c['headline']}",
                f'- Hook: "{c["hook"]}"',
                f"- What to show: {c['visual_direction']}",
                f"- Why it's different from {theirs}: {c['why_it_beats']}",
            ]
        lines += [
            "",
            "StealAds can turn this brief into a finished ad. Your first one is free "
            "(early access at stealads.ai).",
        ]
    lines += [
        "",
        FOOT_NOTE,
        "",
        "---",
        f"{ctx['data_line']} · checked {ctx['checked_date']} · https://stealads.ai",
        "",
    ]
    return "\n".join(lines)


def render_board_bundle(
    run_dir: Path,
    *,
    repo_root: Path | None = None,
    template: str = "board/war-room.html.j2",
) -> dict[str, Any]:
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    from ad_spy_kit.media import normalize_run

    normalize_run(run_dir)  # catalog placeholders emptied, big images shrunk; idempotent
    competitor = json.loads((run_dir / "competitor.json").read_text())
    ads_raw = json.loads((run_dir / "ads.raw.json").read_text())
    winners = json.loads((run_dir / "winners.json").read_text())
    analysis = json.loads((run_dir / "analysis.json").read_text())
    counters = json.loads((run_dir / "counters.json").read_text())
    # A winners.json written before the placeholder fix still carries `{{product.name}}` in
    # its held-back ads. Empty it here so a stale run can't print one.
    for entry in (winners.get("hidden") or []) + (winners.get("quarantined") or []):
        for key in ("headline", "body"):
            if key in entry:
                entry[key] = scrub_text(entry[key])[0]

    for name, doc in (
        ("competitor", competitor),
        ("ads.raw", ads_raw),
        ("winners", winners),
        ("analysis", analysis),
        ("counters", counters),
    ):
        assert_valid(name, doc, root=repo_root)

    media_dir = run_dir / "media"
    ctx = build_context(
        competitor=competitor,
        ads_raw=ads_raw,
        winners=winners,
        analysis=analysis,
        counters=counters,
        media_dir=media_dir,
        run_dir=run_dir,
    )
    templates_dir = repo_root / "templates"
    out_html = run_dir / "board.html"
    render_html(template=template, context=ctx, templates_dir=templates_dir, out_html=out_html)
    board_png = run_dir / "board.png"
    overflow = screenshot_html(
        out_html, board_png, width=1200, height=750, device_scale_factor=2.0, check_overflow=True
    )
    newsletter = run_dir / "newsletter.png"
    # The whole board at 1x: a shorter crop cut the winner wall and stranded the footer.
    screenshot_html(out_html, newsletter, width=1200, height=750, device_scale_factor=1.0)
    og = run_dir / "og.png"
    screenshot_html(out_html, og, width=1200, height=630, device_scale_factor=1.0)

    (run_dir / "teardown.md").write_text(teardown_markdown(ctx))

    from ad_spy_kit.slice import slice_board

    slice_board(run_dir / "board.html", run_dir / "x-slices", repo_root=repo_root)

    manifest = {
        "rendered_at": datetime.now(UTC).isoformat(),
        "board_html": out_html.name,
        "board_png": board_png.name,
        "template": template,
        "text_overflow": overflow,
        "dropped_no_media": ctx["dropped_no_media"],
    }
    (run_dir / "render.json").write_text(json.dumps(manifest, indent=2))
    return manifest
