"""Prod search_ads / find_winning_ads reply in Markdown text; ingest reads it (2026-11-05)."""

import json
from pathlib import Path

from ad_spy_kit.sc_client import build_ads_raw_from_fixture, unfetched_pages
from ad_spy_kit.stealads_text import load_saved, parse_stealads_text

DATA = Path(__file__).parent / "data" / "stealads_prod_search_ads.md"
EMPTY = "Public library ads from the selected advertiser.\nNo ads found for this search."


def test_text_rows_parse_to_the_fields_the_adapter_reads():
    doc = parse_stealads_text(DATA.read_text())
    first, second = doc["ads"]
    assert first["id"] == "d1b6ed84-74d1-4150-9c74-4833de9982c9"
    assert first["facebook_page_id"] == "225674437474430"
    assert first["page_name"] == "Integralmedica Sports Nutrition"
    assert first["run_duration_days"] == 46 and first["still_running"] is True
    assert first["strength_label"] == "solid" and first["hook_type"] == "Myth or belief reversal"
    assert first["body_text"].startswith("Beef Protein")
    assert second["run_duration_days"] == 63
    assert doc["has_more"] is True and doc["next_cursor"] == "mcp-c1.abc_DEF-123"


def test_no_ads_found_is_an_empty_list():
    doc = parse_stealads_text(EMPTY)
    assert doc["ads"] == [] and doc["has_more"] is False


def test_json_saves_still_load_as_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"ads": [{"id": "a"}]}))
    assert load_saved(p) == {"ads": [{"id": "a"}]}


def test_ingest_reads_a_text_run_folder(tmp_path):
    (tmp_path / "competitor.json").write_text(json.dumps({"page_id": "225674437474430"}))
    (tmp_path / "search_ads.static.json").write_text(DATA.read_text())
    (tmp_path / "find_winning_ads.json").write_text(DATA.read_text())
    raw = build_ads_raw_from_fixture(tmp_path)
    # The second row is another advertiser's page, so it is dropped as before.
    assert [a["ad_id"] for a in raw["ads"]] == ["d1b6ed84-74d1-4150-9c74-4833de9982c9"]
    ad = raw["ads"][0]
    assert ad["format"] == "IMAGE" and ad["days_live"] == 46
    assert ad["strength_label"] == "solid" and ad["label_source"] == "stealads"
    assert ad["bangers_rank"] == 1
    assert unfetched_pages(tmp_path) == ["search_ads.static.json"]
