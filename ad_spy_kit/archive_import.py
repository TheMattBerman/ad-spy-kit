"""Import a saved Meta Ad Library pull (ScrapeCreators JSONL rows) into kit ad dicts.

No network calls. Rows are what `scrapecreators:facebook_ad_library` returned and was saved
to disk earlier; this module only reads them. Images come from a local folder whose file
names end in `-<ad_archive_id>.<ext>`; ads with no local image keep `image=None`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ad_spy_kit.paths import visible

IMG_RE = re.compile(r"-(\d{8,})\.(?:jpe?g|png|webp)$", re.I)


def index_images(folder: Path | None) -> dict[str, Path]:
    if not folder or not folder.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in visible(sorted(folder.iterdir())):  # skips macOS "._" sidecar files
        m = IMG_RE.search(p.name)
        if m:
            out.setdefault(m.group(1), p)
    return out


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def map_library_row(row: dict[str, Any], images: dict[str, Path]) -> dict[str, Any]:
    ad_id = str(row["ad_archive_id"])
    start, end = _d(row.get("start_date")), _d(row.get("end_date"))
    days = max(0, (end - start).days) if start and end else 0
    fmt = "VIDEO" if row.get("video_urls") else "IMAGE"
    return {
        "ad_id": ad_id,
        "brand": row.get("brand_csv_match") or row.get("page_name") or "",
        "page_name": row.get("page_name") or "",
        "vertical": row.get("vertical") or "",
        "country": row.get("country") or "",
        "headline": row.get("title") or "",
        "body": row.get("body_text") or "",
        "format": fmt,
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "is_active": bool(row.get("is_active")),
        "label_source": "run_length",
        "still_running": bool(row.get("is_active")),
        "days_live": days,
        "variation_count": int(row.get("collation_count") or 1),
        "bfcm_strict": bool(row.get("bfcm_strict")),
        "image": str(images[ad_id]) if ad_id in images else None,
        "run_length_unknown": not (start and end),
    }


def load_library_rows(paths: list[Path]) -> list[dict[str, Any]]:
    """Union JSONL files, first row per ad_archive_id wins."""
    seen: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open() as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    seen.setdefault(str(row["ad_archive_id"]), row)
    return list(seen.values())


def write_brand_dirs(ads: list[dict[str, Any]], out: Path) -> list[Path]:
    """Saved rows → out/brands/<slug>/{competitor.json, ads.raw.json, media/}, the folder
    shape `ad-spy-kit category --from out` draws. Images are copied in; nothing is fetched."""
    import shutil

    by_brand: dict[str, list[dict[str, Any]]] = {}
    for ad in ads:
        by_brand.setdefault(ad.get("brand") or ad.get("page_name") or "Unknown", []).append(ad)
    dirs = []
    for brand, rows in sorted(by_brand.items()):
        d = out / "brands" / (re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-") or "brand")
        (d / "media").mkdir(parents=True, exist_ok=True)
        kit_ads = []
        for ad in rows:
            ad = dict(ad)
            img = ad.pop("image", None)
            ad["media"] = []
            if img and Path(img).is_file():
                dest = d / "media" / f"{ad['ad_id']}{Path(img).suffix.lower()}"
                shutil.copy2(img, dest)
                ad["media"] = [{"path": f"media/{dest.name}", "durable": True, "kind": "image"}]
            kit_ads.append(ad)
        seen = [a["end_date"] for a in kit_ads if a.get("is_active") and a.get("end_date")]
        (d / "competitor.json").write_text(
            json.dumps({"page_name": brand, "page_id": "", "source": "saved"}, indent=2) + "\n"
        )
        (d / "ads.raw.json").write_text(
            json.dumps(
                {
                    "source": "saved Meta Ad Library pull",
                    "pulled_at": max(seen, default=""),
                    "ads": kit_ads,
                },
                indent=1,
                ensure_ascii=False,
            )
            + "\n"
        )
        dirs.append(d)
    return dirs
