"""StealAds JSON replies (response_format "json", row schema_version 1), read from real prod
replies recorded 2026-11-06 in tests/data/stealads_json (trimmed; the brand id is a placeholder).

Covers the row mapper (cta, landing domain, carousel cards, countries, platforms, group_id,
first/last seen, hooks, why, format names), null tolerance, `schema_version` in ads.raw.json,
the Markdown text fallback, the not_indexed lookup message, tracked pages and carousel tiles.
"""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from ad_spy_kit import cli, tracked
from ad_spy_kit.dedupe import creative_groups
from ad_spy_kit.sc_client import cache_media
from ad_spy_kit.sl_adapter import landing_domain, map_stealads_ad, unify_format

DATA = Path(__file__).parent / "data" / "stealads_json"
TEXT = Path(__file__).parent / "data" / "stealads_prod_search_ads.md"


def _doc(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def _rows(name: str) -> list[dict]:
    return _doc(name)["ads"]


# --- row mapper -------------------------------------------------------------------------


def test_search_row_maps_every_json_field():
    row = _rows("search_ads.quince.json")[0]  # a video row
    ad = map_stealads_ad(row)
    assert ad["cta"] == "Shop Now" and ad["landing_url"] == "https://quince.com/"
    assert ad["landing_domain"] == "quince.com"
    assert ad["format"] == "VIDEO"
    assert ad["platforms"][0] == "FACEBOOK" and "countries" not in ad  # null: left out
    assert ad["group_id"] == "1216758343881951" and ad["dedupe_key"] == "1216758343881951"
    assert ad["start_date"] == "2026-02-09" and ad["end_date"] is None
    assert ad["first_seen_at"] == "2026-10-15T18:53:59.767Z"
    assert ad["last_seen_at"] == "2026-10-15T18:53:59.767Z"
    assert ad["variation_count"] == 1 and ad["why"] == "Live 248 days · still running"
    assert ad["strength_label"] == "winner" and ad["label_source"] == "stealads"
    assert ad["days_live"] == 248 and ad["is_active"] is True
    assert ad["hook_type"] == "contrarian" and ad["hook_type_filter"] == "contrarian"
    assert ad["schema_version"] == 1
    assert ad["video_url"].endswith(".mp4")
    # image_url is the poster frame, the same picture as video_thumbnail_url: one media entry
    assert len(ad["media"]) == 1 and ad["media"][0]["kind"] == "video_preview"


def test_static_and_image_are_one_format():
    assert unify_format("static") == "IMAGE" and unify_format("image") == "IMAGE"
    assert unify_format("Video") == "VIDEO" and unify_format("DPA") == "DPA"
    assert unify_format(None) == ""
    static = map_stealads_ad(_rows("search_ads.quince.json")[1])
    assert static["format"] == "IMAGE"


def test_hook_type_filter_fills_a_missing_hook_type():
    row = dict(_rows("search_ads.quince.json")[1], hook_type=None)
    assert map_stealads_ad(row)["hook_type"] == "curiosity_gap"  # from hook_type_filter


def test_missing_and_null_fields_do_not_break_the_mapper():
    row = {"id": "x-1", "format": "static", "image_url": None, "hook": None, "why": None}
    ad = map_stealads_ad(row)
    assert ad["format"] == "IMAGE" and ad["headline"] == "" and ad["body"] == ""
    assert ad["cta"] == "" and ad["landing_domain"] == "" and ad["media"] == []
    assert ad["strength_label"] is None and ad["variation_count"] == 0
    for key in ("countries", "platforms", "card_image_urls"):
        assert key not in ad


def test_landing_domain():
    assert landing_domain("https://www.trueclassictees.com/p?utm_source=a") == "trueclassictees.com"
    assert landing_domain("https://itunes.apple.com/") == "itunes.apple.com"
    assert landing_domain(None) == "" and landing_domain("") == ""


def test_spoken_hook_and_on_screen_text_come_from_the_hook_object():
    ads = [map_stealads_ad(r) for r in _rows("list_tracked_rival_ads.bombas-spoken.json")]
    spoken = [a for a in ads if a.get("spoken_hook")]
    assert len(spoken) == 2 and spoken[0]["hook_source"] == "spoken"
    assert spoken[0]["spoken_hook"].startswith("If you're a Marvel fan")
    assert spoken[0]["spoken_hook_source"] == "stealads"
    unanalyzed = [a for a in ads if not a.get("spoken_hook")][0]
    assert unanalyzed["hook_source"] == "copy"
    # Unanalyzed in StealAds but with a real start date: labeled by the same rule locally.
    assert unanalyzed["label_source"] == "run_length" and unanalyzed["strength_label"] == "testing"


def test_hook_fields_agree_on_every_recorded_row():
    """Prod 2026-11-06: hook.type, hook_type and hook_type_filter never disagreed on a row."""
    for name in DATA.glob("*.json"):
        for row in _doc(name.name).get("ads") or []:
            hook = row.get("hook") or {}
            assert hook.get("type") == row.get("hook_type") == row.get("hook_type_filter")


def test_carousel_card_urls_become_wall_tiles(tmp_path):
    """Synthetic: no recorded prod row carried card_image_urls yet (all null on 234 rows)."""
    urls = [f"https://generated.stealads.ai/originals/x/card{n}.jpg" for n in range(1, 5)]
    row = dict(_rows("search_ads.quince.json")[1], card_image_urls=urls)
    ad = map_stealads_ad(row)
    assert ad["card_image_urls"] == urls and ad["format"] == "IMAGE"

    def fake(url, stem):
        path = stem.with_suffix(".jpg")
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (400, 400), (200, 30, 30))
        img.paste((20, 120, 220), (0, 0, 200, 200))  # not a flat frame
        img.save(path)
        return path, "hash-" + url[-9:]

    skipped = cache_media([ad], tmp_path / "media", downloader=fake)
    assert skipped == []
    assert "card_image_urls" not in ad  # remote links never stay in ads.raw.json
    paths = [c["path"] for c in ad["card_media"]]
    assert paths == [f"media/cards/{ad['ad_id']}-{n}.jpg" for n in (2, 3, 4)]
    assert all((tmp_path / p).is_file() for p in paths)
    assert ad["card_count"] == 4

    from ad_spy_kit.render import _ad_wall

    wall = _ad_wall({"ads": [ad], "total_available": 1}, tmp_path / "media")
    assert [bool(t.get("card")) for t in wall] == [False, True, True]  # cover + 2 cards


def test_a_card_that_fails_to_download_is_skipped_quietly(tmp_path):
    row = dict(
        _rows("search_ads.quince.json")[1],
        card_image_urls=[
            "https://generated.stealads.ai/a.jpg",
            "https://generated.stealads.ai/b.jpg",
        ],
    )
    ad = map_stealads_ad(row)
    cache_media([ad], tmp_path / "media", downloader=lambda url, stem: None)
    assert "card_media" not in ad


# --- ingest: schema_version and the text fallback ---------------------------------------


def _ingest(tmp_path, *files: tuple[str, Path]) -> dict:
    for name, src in files:
        shutil.copy(src, tmp_path / name)
    assert cli.main(["ingest", str(tmp_path), "--no-images"]) == 0
    return json.loads((tmp_path / "ads.raw.json").read_text())


def test_ingest_records_schema_version_for_json_replies(tmp_path):
    raw = _ingest(
        tmp_path,
        ("search_ads.static.json", DATA / "search_ads.quince.json"),
        ("find_winning_ads.json", DATA / "find_winning_ads.true-classic.json"),
    )
    assert raw["schema_version"] == 1 and raw["reply_format"] == "json"
    assert raw["source"] == "stealads" and len(raw["ads"]) == 5
    assert {a["format"] for a in raw["ads"]} == {"IMAGE", "VIDEO"}  # the row's own format wins
    comp = json.loads((tmp_path / "competitor.json").read_text())
    assert comp["page_name"] == "Quince" and comp["page_id"] == "2240844056196530"


def test_ingest_still_reads_a_markdown_text_reply(tmp_path):
    raw = _ingest(tmp_path, ("search_ads.static.json", TEXT))
    assert raw["reply_format"] == "text" and raw["schema_version"] is None
    assert raw["ads"] and all(a["format"] == "IMAGE" for a in raw["ads"])


def test_ingest_marks_a_json_plus_text_run_as_mixed(tmp_path):
    raw = _ingest(
        tmp_path,
        ("search_ads.static.json", DATA / "search_ads.quince.json"),
        ("search_ads.video.page2.json", TEXT),
    )
    assert raw["reply_format"] == "mixed" and raw["schema_version"] == 1


def test_a_carousel_group_id_dedupes_search_and_tracked_copies():
    one = map_stealads_ad(_rows("search_ads.quince.json")[2])
    twin = dict(_rows("search_ads.quince.json")[3], group_id=one["group_id"])
    groups = creative_groups([one, map_stealads_ad(twin)])
    assert len(groups) == 1 and len(groups[0]) == 2


# --- brand lookup: found / several / not_indexed ----------------------------------------


def test_not_indexed_says_so_plainly_and_names_the_fallback(tmp_path, capsys):
    for name in (
        "search_advertisers.not_indexed.space-goods.json",
        "search_advertisers.not_indexed.spacegoods-pageid.json",
    ):
        code = cli.main(["advertiser", str(DATA / name), "--query", "Space Goods"])
        out = capsys.readouterr().out
        assert code == 2
        assert "doesn't have Space Goods in its library yet" in out
        assert "ScrapeCreators" in out and "quote first" in out
        assert "StealAds app" in out and "not through this connection" in out
        assert "—" not in out  # no em dashes
    assert not (tmp_path / "competitor.json").exists()


def test_not_indexed_for_a_link_or_page_id_says_that_page(capsys):
    reply = DATA / "search_advertisers.not_indexed.spacegoods-pageid.json"
    link = "https://www.facebook.com/ads/library/?view_all_page_id=104163495557745"
    for typed in (link, "104163495557745"):
        assert cli.main(["advertiser", str(reply), "--query", typed]) == 2
        out = capsys.readouterr().out
        assert out.startswith("StealAds doesn't have that Facebook page in its library yet.")
        assert "view_all_page_id" not in out


def test_not_indexed_lists_similar_names_without_picking_one(capsys):
    cli.main(["advertiser", str(DATA / "search_advertisers.not_indexed.space-goods.json")])
    out = capsys.readouterr().out
    assert "The Hearing Space" in out and "None is the same brand" in out


def test_one_advertiser_hit_writes_competitor_json(tmp_path, capsys):
    reply = tmp_path / "search_advertisers.json"
    reply.write_text(
        '{"suggestions":[],"advertisers":[{"name":"Quince","facebook_page_id":"2240844056196530",'
        '"schema_version":1}],"next_cursor":null,"has_more":false,"source":"ad_library"}'
    )
    assert cli.main(["advertiser", str(reply), "--query", "Quince"]) == 0
    comp = json.loads((tmp_path / "competitor.json").read_text())
    assert comp["page_id"] == "2240844056196530" and comp["source"] == "stealads"
    assert comp["confidence"] == "exact"


def test_several_advertiser_hits_ask_which(tmp_path, capsys):
    reply = tmp_path / "search_advertisers.json"
    reply.write_text(
        '{"suggestions":[],"advertisers":[{"name":"Ridge","facebook_page_id":"1"},'
        '{"name":"The Ridge","facebook_page_id":"2"}],"has_more":false,"source":"ad_library"}'
    )
    assert cli.main(["advertiser", str(reply), "--query", "ridge"]) == 2
    assert "Which one is it?" in capsys.readouterr().out
    assert not (tmp_path / "competitor.json").exists()


def test_an_unreadable_reply_is_a_clear_error(tmp_path, capsys):
    bad = tmp_path / "search_advertisers.json"
    bad.write_text("1. Quince\n   Image: https://x")
    assert cli.main(["advertiser", str(bad)]) == 2
    assert 'response_format "json"' in capsys.readouterr().err


# --- tracked pages ----------------------------------------------------------------------


@pytest.fixture
def tracked_run(tmp_path):
    shutil.copy(
        DATA / "list_tracked_rival_ads.montessori.page1.json", tmp_path / "tracked_rival_ads.json"
    )
    shutil.copy(
        DATA / "list_tracked_rival_ads.bombas-spoken.json",
        tmp_path / "tracked_rival_ads.page2.json",
    )
    shutil.copy(DATA / "list_competitors.page1.json", tmp_path / "list_competitors.json")
    return tmp_path


def test_tracked_pages_make_brand_folders_with_the_new_fields(tracked_run):
    info = tracked.write_brand_folders(tracked_run, images=False)
    assert info["ads"] == 9 and sorted(info["rivals"]) == ["Bombas", "Montessori Generation"]
    raw = json.loads(
        (tracked_run / "brands" / "montessori-generation" / "ads.raw.json").read_text()
    )
    assert raw["schema_version"] == 1 and raw["reply_format"] == "json"
    first = raw["ads"][0]
    assert first["cta"] == "Shop Now" and first["landing_domain"] == "montessorigeneration.com"
    assert first["format"] == "IMAGE" and first["hook_type"] == "offer"
    assert first["strength_label"] == "solid" and first["variation_count"] == 2
    assert first["group_id"] == "1116508847733465" and first["is_active"] is True
    unanalyzed = raw["ads"][1]
    assert unanalyzed["hook_type"] is None
    assert unanalyzed["label_source"] == "run_length" and unanalyzed["strength_label"] == "solid"
    video = [a for a in raw["ads"] if a["format"] == "VIDEO"]
    assert video and all(a["days_live"] >= 31 for a in raw["ads"])


def test_tracked_reads_hooks_and_spoken_openers_from_rows(tracked_run):
    tracked.write_brand_folders(tracked_run, images=False)
    raw = json.loads((tracked_run / "brands" / "bombas" / "ads.raw.json").read_text())
    assert sum(bool(a.get("spoken_hook")) for a in raw["ads"]) == 2


def test_compact_rows_keep_their_ellipsis_and_the_full_text_replaces_it():
    compact = _rows("list_tracked_rival_ads.compact-truncated.json")
    cut = [r for r in compact if r["body_text_truncated"]]
    assert cut and all(r["body_text"].endswith("…") for r in cut)
    ad = map_stealads_ad(cut[0])
    assert ad["body"].endswith("…")  # the board quotes what StealAds sent; compact:false is full


def test_pending_counts_do_not_stop_the_tracked_reader(tracked_run):
    comps = tracked.load_competitors(tracked_run)
    pending = [c for c in comps.values() if c.get("count_status") == "pending"]
    assert pending and all(c["ads_tracked"] is None for c in pending)
    assert any(c.get("ads_tracked_capped") for c in comps.values())
    tracked.write_brand_folders(tracked_run, images=False)  # no KeyError, no TypeError


def test_angle_is_read_from_filters():
    from ad_spy_kit.sl_adapter import map_stealads_ad

    row = {"id": "a1", "filters": {"angle": "educational"}, "format": "static"}
    assert map_stealads_ad(row)["angle"] == "educational"


def test_unknown_delivery_counts_as_ran_not_live():
    from ad_spy_kit.render import live_30

    ads = {
        "ads": [
            {"days_live": 248, "still_running": None, "is_active": True},
            {"days_live": 44, "still_running": None, "is_active": True},
            {"days_live": 5, "still_running": None, "is_active": True},
        ]
    }
    assert live_30(ads) == (2, "ran 30+ days")


def test_known_delivery_stays_live():
    from ad_spy_kit.render import live_30

    ads = {
        "ads": [
            {"days_live": 90, "still_running": True},
            {"days_live": 90, "still_running": False},
            {"days_live": 90, "is_active": True},
        ]
    }
    assert live_30(ads) == (2, "live 30+ days")


def test_multi_brand_folder_validate_and_render(tmp_path, capsys):
    import argparse
    import json

    import pytest

    from ad_spy_kit import cli
    from ad_spy_kit.errors import KitError

    (tmp_path / "category.json").write_text("{}")
    (tmp_path / "validation.json").write_text(json.dumps({"ok": True, "errors": []}))
    args = argparse.Namespace(run_dir=tmp_path)
    assert cli.cmd_validate(args) == 0
    assert '"ok": true' in capsys.readouterr().out
    with pytest.raises(KitError, match="already drawn"):
        cli.cmd_render(args)
