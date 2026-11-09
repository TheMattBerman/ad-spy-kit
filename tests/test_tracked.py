"""Tracked-competitors mode, the 10-brand cap, plural fixes, competitor.json from rows and the
counter-ad check. Recorded replies from the live StealAds MCP (2026-11-05) sit in
tests/data/tracked:
list_tracked_rival_ads JSON (Bellroy, from the Ridge workspace), search_ads / find_winning_ads text
for tracked rivals (Quince, True Classic, Atlas Coffee Club, Jenni Bag, Baisi Hair), and a trimmed
list_competitors."""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from ad_spy_kit import category, cli, tracked
from ad_spy_kit.errors import KitError
from ad_spy_kit.stealads_text import parse_stealads_text
from ad_spy_kit.validate_run import COUNTERS_FIX, Report, check_counters

DATA = Path(__file__).parent / "data" / "tracked"


@pytest.fixture
def run(tmp_path):
    """A run folder with the recorded tracked replies."""
    for f in DATA.iterdir():
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def _brand_names(run):
    return sorted(
        json.loads(p.read_text())["page_name"] for p in (run / "brands").glob("*/competitor.json")
    )


def test_json_rows_map_to_ads_with_stealads_labels(run):
    info = tracked.write_brand_folders(run, images=False)
    assert info["ads"] == 16 and len(info["rivals"]) == 6
    raw = json.loads(next((run / "brands").glob("bellroy/ads.raw.json")).read_text())
    assert raw["source"] == "stealads" and len(raw["ads"]) == 6
    top = raw["ads"][0]
    assert top["ad_id"] == "73941409-ae63-4f54-bd49-5e1d9da01928"
    assert top["format"] == "VIDEO" and top["days_live"] == 230
    assert top["strength_label"] == "winner" and top["label_source"] == "stealads"
    assert top["variation_count"] == 2 and top["is_active"] is True
    assert top["headline"] == "Your iPhone, your choice"
    # banger_band null: unanalyzed there, so no label here
    unlabeled = [a for a in raw["ads"] if a["ad_id"].startswith("3b5916a4")][0]
    assert unlabeled["strength_label"] is None
    # Rows from list_tracked_rival_ads carry no start date; the board never invents one.
    assert top["start_date"] == ""


def test_competitor_json_comes_from_the_rows_and_list_competitors(run):
    tracked.write_brand_folders(run, images=False)
    bell = json.loads((run / "brands" / "bellroy" / "competitor.json").read_text())
    assert bell["page_name"] == "Bellroy" and bell["tracked"] is True
    assert bell["competitor_id"] == "d3ca5db4-b0d5-4917-b533-c7d2fcaaf336"
    assert bell["source"] == "stealads" and bell["page_id"] == ""  # unknown: not in the rows
    quince = json.loads((run / "brands" / "quince" / "competitor.json").read_text())
    assert quince["page_id"] == "2240844056196530" and quince["country"] == "US"
    assert quince["competitor_id"] == "55fa47d3-da1f-4a40-88dd-06c6f34ebbb1"
    # the page name in the rows ("The Ridge" would also do) never carries the "(your rival)" tag
    assert all("(your rival)" not in n for n in _brand_names(run))


def test_text_rows_name_the_rival_and_keep_the_page_id(run):
    doc = parse_stealads_text((run / "tracked_rival_ads.quince.md").read_text())
    first = doc["ads"][0]
    assert first["page_name"] == "Quince (your rival)"
    assert first["facebook_page_id"] == "2240844056196530"
    rows, _ = tracked.load_page(run / "tracked_rival_ads.quince.md")
    assert rows[0]["page_name"] == "Quince"


def test_trailer_lines_never_land_in_an_ads_caption():
    doc = parse_stealads_text((DATA / "tracked_rival_ads.true-classic.md").read_text())
    body = doc["ads"][-1]["body_text"]
    assert "More results" not in body and "cursor" not in body
    assert doc["has_more"] is True and doc["next_cursor"] == "mcp-c1.recorded-cursor"


def test_board_is_ten_brands_three_ads_each_ranked_by_long_runs(run, tmp_path, monkeypatch):
    # 12 rivals: the 6 recorded ones plus 6 synthetic one-ad rivals.
    rows = []
    for i in range(6):
        rows.append(
            {
                "ad_id": f"00000000-0000-4000-8000-00000000000{i}",
                "competitor_id": f"c0000000-0000-4000-8000-00000000000{i}",
                "rival_name": f"Filler {i}",
                "banger_band": "solid",
                "days_live": 31 + i,
                "still_running": True,
                "status": "live",
                "variation_count": 1,
                "format": "image",
                "headline": f"Filler headline {i}",
                "image_url": "",
            }
        )
    (run / "tracked_rival_ads.filler.json").write_text(json.dumps({"ads": rows}))
    monkeypatch.setattr(
        "ad_spy_kit.sc_client.cache_media", lambda ads, media_dir, **kw: _fake_media(ads, media_dir)
    )
    assert cli.main(["tracked", str(run), "--title", "BFCM test"]) == 0
    cat = json.loads((run / "category.json").read_text())
    assert cat["summary"]["brands"] == 12  # everything read
    names = [b["name"] for b in cat["brands"]]
    # most ads live 30+ days first: Bellroy 6, Atlas 4, Quince 3, then the one-ad rivals
    assert names[:2] == ["Bellroy", "Atlas Coffee Club"]
    html = (run / "board.html").read_text()
    assert html.count('class="grp"') == 10  # at most 10 brands on the board
    assert (
        max(html.split('<div class="grp">')[i].count('<img class="t ') for i in range(1, 11)) <= 3
    )
    assert "What 10 brands keep running" in html
    assert "The board shows the top 10 of 12 brands." in (run / "summary.md").read_text()
    assert json.loads((run / "validation.json").read_text())["ok"] is True
    slices = sorted(p.name for p in (run / "x-slices").glob("*.png"))
    assert slices and len(slices) <= 4


def _fake_media(ads, media_dir):
    """Stand-in for the image download: a tiny real image per ad, saved like the real one."""
    media_dir.mkdir(parents=True, exist_ok=True)
    for ad in ads:
        path = media_dir / f"{ad['ad_id']}.jpg"
        Image.new("RGB", (40, 50), (200, 40, 40)).save(path, "JPEG")
        ad["media"] = [{"path": f"media/{path.name}", "durable": True, "kind": "image"}]
    return []


def test_one_brand_never_reads_1_brands(run, monkeypatch, tmp_path):
    only = tmp_path / "one"
    only.mkdir()
    shutil.copy(DATA / "tracked_rival_ads.json", only / "tracked_rival_ads.json")
    monkeypatch.setattr(
        "ad_spy_kit.sc_client.cache_media", lambda ads, media_dir, **kw: _fake_media(ads, media_dir)
    )
    assert cli.main(["tracked", str(only), "--title", "1 brand test"]) == 0
    html = (only / "board.html").read_text()
    assert "What Bellroy keeps running" in html
    assert "1 brands" not in html and "1 brands" not in (only / "summary.md").read_text()
    assert '<div class="k">brand</div>' in html


def test_plural_helpers():
    assert category.count_brands(1) == "1 brand" and category.count_brands(2) == "2 brands"
    assert category.brands_possessive(1) == "1 brand's"
    assert category.brands_possessive(3) == "3 brands'"


def test_board_check_catches_one_brands():
    from ad_spy_kit.validate_run import board_html_errors

    page = '<p>What 1 brands keep running</p><a href="https://stealads.ai">x</a>'
    assert any(e.startswith("G1") for e in board_html_errors(page))


def test_over_the_read_limit_tells_the_agent_what_to_do(tmp_path):
    (tmp_path / "tracked_rival_ads.json").write_text(
        "This tracked set exceeds the tool's read limit. Use a smaller brand workspace."
    )
    with pytest.raises(KitError) as err:
        tracked.write_brand_folders(tmp_path, images=False)
    assert "tracked_rivals_only" in str(err.value.fix) and err.value.code == "tracked_over_limit"


def test_ingest_points_a_tracked_folder_at_the_tracked_board(run, monkeypatch, capsys):
    monkeypatch.setattr(
        "ad_spy_kit.sc_client.cache_media", lambda ads, media_dir, **kw: _fake_media(ads, media_dir)
    )
    assert cli.main(["ingest", str(run)]) == 0
    assert "tracked-competitors board" in capsys.readouterr().out
    assert (run / "board.png").exists()


def test_category_names_over_ten_brands_are_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    names = ", ".join(f"Brand {i}" for i in range(11))
    with pytest.raises(KitError) as err:
        category.run(names, out=tmp_path / "o", yes=False)
    assert err.value.code == "category_too_many_brands"
    assert category.DEFAULT_MAX_BRANDS == 10 and category.MAX_BOARD_BRANDS == 10


# ---- competitor.json from the saved rows (ingest) ------------------------------------------


def test_ingest_writes_competitor_json_when_missing(tmp_path, capsys):
    prod = Path(__file__).parent / "data" / "stealads_prod_search_ads.md"
    (tmp_path / "search_ads.static.json").write_text(prod.read_text())
    assert cli.main(["ingest", str(tmp_path), "--no-images"]) == 0
    comp = json.loads((tmp_path / "competitor.json").read_text())
    assert comp["page_id"] == "225674437474430"
    assert comp["page_name"] == "Integralmedica Sports Nutrition"
    assert comp["source"] == "stealads" and comp["confidence"] == "likely"
    assert comp["country"] == ""  # StealAds search rows carry no country: never guessed
    assert "competitor.json written from the saved rows" in capsys.readouterr().err
    raw = json.loads((tmp_path / "ads.raw.json").read_text())
    # The saved page's second row is another advertiser's, so the page filter drops it.
    assert len(raw["ads"]) == 1


def test_ingest_keeps_a_competitor_json_the_agent_wrote(tmp_path):
    prod = Path(__file__).parent / "data" / "stealads_prod_search_ads.md"
    (tmp_path / "search_ads.static.json").write_text(prod.read_text())
    mine = {"page_id": "225674437474430", "page_name": "My Name", "country": "BR"}
    (tmp_path / "competitor.json").write_text(json.dumps(mine))
    assert cli.main(["ingest", str(tmp_path), "--no-images"]) == 0
    assert json.loads((tmp_path / "competitor.json").read_text()) == mine


# ---- the empty YOUR COUNTER-AD panel -------------------------------------------------------


def test_empty_counters_fail_with_a_message_that_says_what_to_add(tmp_path):
    docs = {
        "winners": {"winners": [{"ad_id": "a1"}]},
        "analysis": {"gaps": [{"gap": "g"}]},
        "counters": {"counters": []},
    }
    rep = Report()
    check_counters(docs, rep)
    msg = next(e for e in rep.errors if e.startswith("A3"))
    assert "YOUR COUNTER-AD panel would be empty" in msg
    assert "gap_ref" in msg and "why_it_beats" in msg and "skills/ad-spy-kit-counter" in msg


def test_render_without_counters_json_stops_before_drawing(tmp_path, monkeypatch):
    for name in ("competitor", "ads.raw", "winners", "analysis"):
        (tmp_path / f"{name}.json").write_text("{}")
    with pytest.raises(KitError) as err:
        cli.cmd_render(type("A", (), {"run_dir": tmp_path})())
    assert err.value.fix == COUNTERS_FIX
