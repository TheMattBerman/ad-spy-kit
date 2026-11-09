"""Run the kit on a saved Meta Ad Library pull (no network, no paid calls).

    uv run python scripts/demo/bfcm_archive_run.py /path/to/src --out /workspace/bfcm-run/archive

Reads data/raw/track_{b,b2,c,c2}_*.jsonl and visuals/ads/ under the source dir, keeps rows
matched to a brand in brands.csv, labels each ad with the shared rule
(ad_spy_kit/labels.py), and writes category.json (the shape record_v3_demo.py reads)
outside the repo. $ spent is 0: nothing is fetched.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

from ad_spy_kit.archive_import import index_images, load_library_rows, map_library_row
from ad_spy_kit.labels import TOP_LABEL, strength_label
from ad_spy_kit.score_winners import winner_why_line

TRACKS = ["track_b_us_live", "track_b2_us_live", "track_c_eu_2025", "track_c2_eu_2025"]
# Newest snapshot first, so its dates win when an ad appears in more than one track.
US_LIVE_TRACKS = ["track_e_us_resnap", "track_b2_us_live", "track_b_us_live"]
BAND_ORDER = {TOP_LABEL: 0, "solid": 1, "testing": 2, None: 3}


def hook_line(ad: dict) -> str:
    head = (ad.get("headline") or "").strip()
    if head and not head.startswith("{{"):
        text = head
    else:
        body = re.sub(r"\s+", " ", ad.get("body") or "").strip()
        text = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0] if body else ""
    return text if len(text) <= 90 else text[:87].rstrip() + "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--brand-dirs",
        type=Path,
        default=None,
        help="also write per-brand folders for `ad-spy-kit category --from` (live US tracks)",
    )
    ap.add_argument("--top-brands", type=int, default=14, help="with --brand-dirs: N brands")
    args = ap.parse_args()
    t0 = time.monotonic()
    rows = load_library_rows([args.src / "data/raw" / f"{t}.jsonl" for t in TRACKS])
    images = index_images(args.src / "visuals/ads")
    ads = []
    for r in rows:
        if not r.get("brand_csv_match"):
            continue
        a = map_library_row(r, images)
        a["band"] = strength_label(a)
        a["versions"] = a["variation_count"]
        a["hook"] = hook_line(a)
        a["why"] = winner_why_line(a, rank=0)
        ads.append(a)
    ads.sort(key=lambda a: (BAND_ORDER[a["band"]], -a["versions"], -a["days_live"], a["ad_id"]))
    top3, seen = [], set()  # the ones they keep running: longest run first, one per brand
    for a in sorted(ads, key=lambda a: (-a["days_live"], -a["versions"], a["ad_id"])):
        if a["band"] == TOP_LABEL and a["image"] and a["hook"] and a["brand"] not in seen:
            top3.append(a)
            seen.add(a["brand"])
        if len(top3) == 3:
            break
    brands = sorted({a["brand"] for a in ads})
    pulled = max(d for a in ads if a["is_active"] and (d := a["end_date"]))
    n = lambda f: sum(1 for a in ads if f(a))  # noqa: E731
    summary = {
        "ads": len(ads),
        "brands": len(brands),
        "top_label": TOP_LABEL,
        "top": n(lambda a: a["band"] == TOP_LABEL),
        "bangers": n(lambda a: a["band"] == TOP_LABEL),  # key the demo renderers read
        "solid": n(lambda a: a["band"] == "solid"),
        "testing": n(lambda a: a["band"] == "testing"),
        "no_label": n(lambda a: a["band"] is None),
        "live": n(lambda a: a["is_active"]),
        "ended": n(lambda a: not a["is_active"]),
        "with_image": n(lambda a: a["image"]),
        "bfcm_strict": n(lambda a: a["bfcm_strict"]),
        "verticals": sorted({a["vertical"] for a in ads}),
        "rows_in_pull": len(rows),
        "usd": 0.0,
        "paid_calls": 0,
    }
    summary["seconds"] = round(time.monotonic() - t0, 2)
    result = {
        "source": "saved Meta Ad Library pull (ScrapeCreators), tracks " + ", ".join(TRACKS),
        "pulled_date": date.fromisoformat(pulled).strftime("%b %-d, %Y"),
        "summary": summary,
        "top3": top3,
        "brands": [{"name": b, "ads": sum(a["brand"] == b for a in ads)} for b in brands],
        "events": ads,
    }
    if args.brand_dirs:
        from collections import Counter

        from ad_spy_kit.archive_import import write_brand_dirs

        us_rows = load_library_rows([args.src / "data/raw" / f"{t}.jsonl" for t in US_LIVE_TRACKS])
        live_us = [
            map_library_row(r, images)
            for r in us_rows
            if r.get("brand_csv_match") and r.get("is_active") and r.get("country") == "US"
        ]
        # Brands with the most ads live 30+ days first, then the most live ads.
        long = Counter(a["brand"] for a in live_us if a["days_live"] >= 30)
        total = Counter(a["brand"] for a in live_us)
        ranked = sorted(total, key=lambda b: (-long[b], -total[b], b))[: args.top_brands]
        write_brand_dirs([a for a in live_us if a["brand"] in set(ranked)], args.brand_dirs)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "category.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summary.items() if k != "verticals"}), summary["verticals"])
    for t in top3:
        print(
            t["brand"],
            "|",
            t["hook"],
            "|",
            t["why"],
            "|",
            t["country"],
            t["start_date"],
            t["end_date"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
