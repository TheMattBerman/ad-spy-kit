"""The recorded StealAds dev-MCP pull (fixtures/live/spacegoods) maps onto the kit's shapes."""

import json
from pathlib import Path

from ad_spy_kit.fixtures import fixture_names, is_live
from ad_spy_kit.render import _first_line, build_context, teardown_markdown
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.sl_adapter import infer_format, map_stealads_ad, unwrap_recording

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "fixtures" / "live" / "spacegoods"


def _row(**over):
    rows = json.loads((LIVE / "search_ads.json").read_text())["response"]["ads"]
    return {**rows[0], **over}


def test_live_fixture_is_discovered():
    assert "live/spacegoods" in fixture_names()
    assert is_live("live/spacegoods") and not is_live("foldbrook")


def test_recordings_carry_no_secrets_or_cursors():
    for path in [*LIVE.glob("search_ads*.json"), LIVE / "find_bangers.json"]:
        text = path.read_text()
        for needle in ("Bearer ", "api_key", "token", "r8_", "@gmail", "own_brand", "_references"):
            assert needle not in text, f"{path.name} contains {needle!r}"


def test_real_row_maps_without_list_ads_fields():
    ad = map_stealads_ad(_row())
    assert ad["is_active"] is True  # from still_running
    assert ad["ad_library_url"] == "" and ad["cta"] == "" and ad["landing_url"] == ""
    assert ad["headline"] == ""  # original_headline is null on the dev corpus
    assert ad["media"][0]["durable"] is True  # generated.stealads.ai mirror
    assert "_references" not in ad


def test_infer_format_prefers_the_search_filter():
    assert infer_format({"_format_filter": "static", "ad_format": "ugc video"}) == "IMAGE"
    assert infer_format({"_format_filter": "video"}) == "VIDEO"
    assert infer_format({"ad_format": "ugc video"}) == "VIDEO"
    assert infer_format({"ad_format": "text dominant"}) == "IMAGE"


def test_video_rows_mark_their_image_as_a_preview():
    ad = map_stealads_ad(_row(_format_filter="video"))
    assert ad["media"][0]["kind"] == "video_preview"


def test_steal_caution_and_strength_pass_through():
    caution = "Dynamic creative: its copy may describe a different card than this image."
    ad = map_stealads_ad(_row(steal_caution=caution, strength="Proven: 78 days"))
    assert ad["steal_caution"] == caution and ad["strength"] == "Proven: 78 days"


def test_unwrap_recording_returns_the_response():
    doc = {"recorded_from": "x", "request": {}, "response": {"ads": [1]}}
    assert unwrap_recording(doc) == {"ads": [1]}
    assert unwrap_recording({"ads": [2]}) == {"ads": [2]}


def test_other_advertisers_are_skipped(tmp_path):
    for f in ("competitor.json", "find_bangers.json"):
        (tmp_path / f).write_text((LIVE / f).read_text())
    doc = json.loads((LIVE / "search_ads.json").read_text())
    doc["response"]["ads"][0]["facebook_page_id"] = "999"
    (tmp_path / "search_ads.json").write_text(json.dumps(doc))
    raw = build_ads_raw_from_fixture(tmp_path)
    assert {"ad_id": doc["response"]["ads"][0]["id"], "reason": "other_advertiser"} in raw[
        "skipped"
    ]


def test_live_pull_unions_format_pages_and_keeps_bangers_order():
    raw = build_ads_raw_from_fixture(LIVE)
    assert len(raw["ads"]) == 24 and raw["source"] == "stealads"
    assert sorted({a["format"] for a in raw["ads"]}) == ["IMAGE", "VIDEO"]
    assert "mcp-dev.stealads.ai" in raw["recorded_from"]
    winners = score_winners(raw["ads"])
    assert winners["rank_source"] == "find_bangers"
    ranks = [w["bangers_rank"] for w in winners["winners"]]
    assert ranks == sorted(ranks)
    assert {w["strength_label"] for w in winners["winners"]} <= {"winner", "solid", "testing"}


def test_live_board_is_labeled_dev_mcp_and_quotes_copy():
    raw = build_ads_raw_from_fixture(LIVE)
    winners = score_winners(raw["ads"])
    analysis = json.loads((LIVE / "analysis.json").read_text())
    counters = json.loads((LIVE / "counters.json").read_text())
    competitor = json.loads((LIVE / "competitor.json").read_text())
    ctx = build_context(
        competitor=competitor,
        ads_raw=raw,
        winners=winners,
        analysis=analysis,
        counters=counters,
        media_dir=LIVE / "media",
    )
    assert ctx["source"] == "Meta Ad Library, via StealAds"
    assert set(ctx["rank_of"]) == {w["ad_id"] for w in winners["winners"]}
    assert all(w["hook_text"] for w in ctx["winner_wall"])
    assert "Careful:" not in teardown_markdown(ctx)  # no winner carries a steal_caution here


def test_first_line_is_a_verbatim_opening():
    body = "Reread the same email three times. Walked into a room.\n\nMore."
    assert _first_line(body) == "Reread the same email three times."
    assert _first_line("") == ""
