from pathlib import Path

from ad_spy_kit.archive_import import index_images, map_library_row
from ad_spy_kit.labels import strength_label


def test_map_and_band(tmp_path: Path) -> None:
    (tmp_path / "US_live-brand-123456789012.jpg").write_bytes(b"x")
    imgs = index_images(tmp_path)
    row = {
        "ad_archive_id": "123456789012",
        "page_name": "P",
        "start_date": "2025-11-01",
        "end_date": "2025-12-31",
        "is_active": False,
        "collation_count": 2,
        "title": "T",
    }
    ad = map_library_row(row, imgs)
    assert ad["days_live"] == 60 and ad["variation_count"] == 2 and ad["image"]
    # Stopped after 60 days: 30+ days, so "solid". Same shared rule as every other route.
    assert strength_label(ad) == "solid"
    assert strength_label({**ad, "days_live": 3, "variation_count": 1}) is None
    assert strength_label({**ad, "days_live": 400, "variation_count": 3}) == "winner"
    assert strength_label({**ad, "is_active": True, "still_running": True, "days_live": 5}) == (
        "testing"
    )
    no_dates = map_library_row({**row, "end_date": None}, imgs)
    assert strength_label(no_dates) is None
