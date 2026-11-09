"""Ingest reads the prod StealAds file names (find_winning_ads, extra search pages)/dev ones."""

import json
import shutil
from pathlib import Path

from ad_spy_kit.cli import main
from ad_spy_kit.sc_client import build_ads_raw_from_fixture, saved_files, unfetched_pages
from ad_spy_kit.score_winners import score_winners

LIVE = Path(__file__).resolve().parents[1] / "fixtures" / "live" / "spacegoods"


def _prod_run(tmp_path, *, rank_name="find_winning_ads.json", wrapped=True):
    """A run folder as an agent saves it on prod: competitor + search pages + the rank file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(LIVE / "competitor.json", tmp_path / "competitor.json")
    for name in ("search_ads.static.json", "search_ads.video.json"):
        shutil.copy(LIVE / name, tmp_path / name)
    doc = json.loads((LIVE / "find_bangers.json").read_text())
    doc["request"]["tool"] = "find_winning_ads"
    if not wrapped:
        doc = doc["response"]
    (tmp_path / rank_name).write_text(json.dumps(doc))
    return tmp_path


def test_find_winning_ads_file_sets_the_rank_order(tmp_path):
    run = _prod_run(tmp_path)
    raw = build_ads_raw_from_fixture(run)
    winners = score_winners(raw["ads"])
    assert winners["rank_source"] == "find_bangers"  # internal name for StealAds rank order
    ranks = [w["bangers_rank"] for w in winners["winners"]]
    assert ranks and ranks == sorted(ranks)


def test_prod_name_gives_the_same_ranks_as_the_old_dev_name(tmp_path):
    prod = build_ads_raw_from_fixture(_prod_run(tmp_path / "prod"))
    dev_run = tmp_path / "dev"
    _prod_run(dev_run, rank_name="find_bangers.json")
    dev = build_ads_raw_from_fixture(dev_run)
    assert [(a["ad_id"], a.get("bangers_rank")) for a in prod["ads"]] == [
        (a["ad_id"], a.get("bangers_rank")) for a in dev["ads"]
    ]


def test_unwrapped_raw_saves_work(tmp_path):
    """An agent saves the bare tool response, with no {request, response} wrapper."""
    run = tmp_path
    shutil.copy(LIVE / "competitor.json", run / "competitor.json")
    for name in ("search_ads.static.json", "search_ads.video.json"):
        doc = json.loads((LIVE / name).read_text())
        (run / name).write_text(json.dumps(doc["response"]))  # request args gone
    rank = json.loads((LIVE / "find_bangers.json").read_text())["response"]
    (run / "find_winning_ads.json").write_text(json.dumps(rank))
    raw = build_ads_raw_from_fixture(run)
    assert sorted({a["format"] for a in raw["ads"]}) == ["IMAGE", "VIDEO"]  # from file names
    assert any(a.get("bangers_rank") for a in raw["ads"])


def test_both_rank_files_union_with_prod_first(tmp_path):
    run = _prod_run(tmp_path)
    dev = json.loads((LIVE / "find_bangers.json").read_text())
    dev["response"]["ads"] = list(reversed(dev["response"]["ads"]))
    (run / "find_bangers.json").write_text(json.dumps(dev))
    assert [p.name for p in saved_files(run, "find_winning_ads", "find_bangers")] == [
        "find_winning_ads.json",
        "find_bangers.json",
    ]
    prod_only = build_ads_raw_from_fixture(_prod_run(tmp_path / "solo"))
    both = build_ads_raw_from_fixture(run)
    assert [a.get("bangers_rank") for a in both["ads"]] == [
        a.get("bangers_rank") for a in prod_only["ads"]
    ]


def test_extra_cursor_pages_are_unioned_and_deduped(tmp_path):
    run = _prod_run(tmp_path)
    page1 = json.loads((run / "search_ads.video.json").read_text())
    rows = page1["response"]["ads"]
    # page 2 repeats one row and carries the first page's cursor in its request
    page1["response"]["has_more"], page1["response"]["next_cursor"] = True, "CUR1"
    (run / "search_ads.video.json").write_text(json.dumps(page1))
    page2 = {
        "request": {"tool": "search_ads", "arguments": {"cursor": "CUR1", "format": "video"}},
        "response": {"ads": [rows[0]], "has_more": False, "next_cursor": None},
    }
    (run / "search_ads.video.page2.json").write_text(json.dumps(page2))
    raw = build_ads_raw_from_fixture(run)
    ids = [a["ad_id"] for a in raw["ads"]]
    assert len(ids) == len(set(ids))
    assert unfetched_pages(run) == []  # the cursor was fetched


def test_unfetched_cursor_is_reported(tmp_path):
    run = _prod_run(tmp_path)
    page = json.loads((run / "search_ads.video.json").read_text())
    page["response"]["has_more"], page["response"]["next_cursor"] = True, "CUR9"
    (run / "search_ads.video.json").write_text(json.dumps(page))
    assert unfetched_pages(run) == ["search_ads.video.json"]


def test_ingest_cli_on_prod_names(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("ad_spy_kit.sc_client.cache_media", lambda ads, media_dir: [])
    run = _prod_run(tmp_path)
    page = json.loads((run / "search_ads.video.json").read_text())
    page["response"]["has_more"], page["response"]["next_cursor"] = True, "CUR9"
    (run / "search_ads.video.json").write_text(json.dumps(page))
    assert main(["ingest", str(run)]) == 0
    assert "search_ads.video.json says more results exist" in capsys.readouterr().err
    raw = json.loads((run / "ads.raw.json").read_text())
    assert raw["source"] == "stealads" and raw["ads"]
    assert any(a.get("bangers_rank") for a in raw["ads"])
