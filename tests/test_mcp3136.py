import json
from pathlib import Path

import pytest

from ad_spy_kit.labels import TOP_LABEL, normalize_label
from ad_spy_kit.sl_adapter import map_stealads_ad

ROOT = Path(__file__).resolve().parents[1]


def test_pr3136_list_ads_row():
    raw = {
        "id": "ad-1",
        "status": "ANALYZED",
        "headline": "Sale",
        "body_text": "Black Friday 40% off",
        "original_cta": "Shop",
        "link_url": "https://example.com/p",
        "format": "VIDEO",
        "is_active": True,
        "still_running": True,
        "run_duration_days": 180,
        "variation_count": 6,
        "banger_band": "banger",
        "why": "Live 180 days · 6 versions · still running",
        "group_id": "meta-123",
        "ad_library_url": "https://facebook.com/ads/library/?id=ad-1",
        "start_date": "2026-04-01",
    }
    ad = map_stealads_ad(raw, bangers_rank=1)
    assert ad["ad_id"] == "ad-1"
    assert ad["days_live"] == 180
    assert ad["group_id"] == "meta-123"
    assert ad["strength_label"] == TOP_LABEL and ad["label_source"] == "stealads"
    assert ad["why"] == "Live 180 days · 6 versions · still running"
    assert "effectiveness_score" not in ad
    assert normalize_label("solid") == "solid"
    assert normalize_label("winner") == normalize_label("banger") == TOP_LABEL
    assert normalize_label("mystery") is None


def test_live_fixture_maps():
    live = ROOT / "fixtures" / "foldbrook" / "stealads_list_ads.json"
    if not live.exists():
        pytest.skip("fixtures missing")
    payload = json.loads(live.read_text())
    for row in payload["ads"]:
        ad = map_stealads_ad(row)
        assert ad["strength_label"] in (TOP_LABEL, "solid", "testing")
        if ad["why"]:
            assert "rank" not in ad["why"].lower()


def test_board_has_stealads_link():
    html = ROOT / "artifacts" / "screenshots" / "foldbrook" / "board.html"
    if not html.exists():
        pytest.skip("run replay first")
    text = html.read_text()
    assert "https://stealads.ai" in text
    assert "effectiveness_score" not in text
    assert "banger_rank_key" not in text
