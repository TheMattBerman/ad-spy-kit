import json
from pathlib import Path

import pytest

from ad_spy_kit.dedupe import merge_duplicates
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.sl_adapter import map_stealads_ad
from ad_spy_kit.validate import assert_valid

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_maps_pending_mcp_fields():
    raw = {
        "id": "abc",
        "headline": "Test",
        "body": "Black Friday 40% off",
        "daysLive": 10,
        "variationCount": 4,
        "isActive": True,
        "format": "VIDEO",
        "landingUrl": "https://example.com/p?utm_source=x",
        "adLibraryUrl": "https://facebook.com/ads/library/?id=abc",
        "startDate": "2026-10-01",
        "banger_band": "banger",
        "why": "StealAds why line",
        "groupId": "grp-1",
    }
    ad = map_stealads_ad(raw, bangers_rank=1)
    assert ad["strength_label"] == "winner"
    assert ad["group_id"] == "grp-1"
    assert ad["why"] == "StealAds why line"


def test_group_id_dedupe():
    ads = [
        {"ad_id": "a1", "group_id": "g1", "days_live": 10, "variation_count": 3, "bangers_rank": 2},
        {"ad_id": "a2", "group_id": "g1", "days_live": 10, "variation_count": 3, "bangers_rank": 1},
    ]
    merged = merge_duplicates(ads)
    assert len(merged) == 1
    assert merged[0]["ad_id"] == "a2"


def test_fixture_replay_schemas():
    from ad_spy_kit.sc_client import build_ads_raw_from_fixture

    raw = build_ads_raw_from_fixture(ROOT / "fixtures" / "foldbrook")
    winners = score_winners(raw["ads"])
    assert_valid("winners", winners, root=ROOT)
    ranks = [w["bangers_rank"] for w in winners["winners"] if w.get("bangers_rank")]
    assert ranks == sorted(ranks)


def test_sl_adapter_live_fixture_keys():
    live = ROOT / "fixtures" / "foldbrook" / "stealads_list_ads.json"
    if not live.exists():
        pytest.skip("fixtures missing")
    payload = json.loads(live.read_text())
    for ad in payload["ads"]:
        assert "id" in ad or "ad_id" in ad
