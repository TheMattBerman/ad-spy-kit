"""Fallback and error paths: every missing key or limit gives the user a next step."""

import json
from pathlib import Path

import pytest

from ad_spy_kit import cli, sc_client
from ad_spy_kit.errors import ExcludedBrand, MissingKey, explain_stealads_error
from ad_spy_kit.exclusions import check_not_excluded
from ad_spy_kit.sl_adapter import map_scrapecreators_ad

DATA = Path(__file__).parent / "data"


@pytest.fixture
def no_keys(monkeypatch):
    for var in ("SCRAPECREATORS_API_KEY",):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("cie.scrapecreators_client._load_dotenv_if_needed", lambda *_: None)


def test_scrapecreators_missing_key_names_the_fix(no_keys):
    with pytest.raises(MissingKey) as exc:
        sc_client.pull_via_scrapecreators({"page_id": "1", "page_name": "X"})
    text = exc.value.render()
    assert "SCRAPECREATORS_API_KEY isn't set" in text
    assert "scrapecreators.com" in text and ".env" in text
    assert "replay --sample foldbrook" in text
    # The StealAds route comes first, with the access placeholder and the MCP URL.
    assert text.index("StealAds") < text.index("ScrapeCreators key")
    assert "https://stealads.ai" in text
    assert "https://mcp.stealads.ai/mcp" in text


def test_cli_run_without_key_exits_2_with_message(no_keys, capsys):
    assert cli.main(["run", "Some Unknown Brand"]) == cli.EXIT_USER
    assert "SCRAPECREATORS_API_KEY isn't set" in capsys.readouterr().err


def test_cli_run_fixture_name_needs_no_key(no_keys, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "replay_fixture", lambda name, **_: calls.append(name) or tmp_path)
    assert cli.main(["run", "Foldbrook"]) == 0
    assert calls == ["foldbrook"]


@pytest.mark.parametrize(
    "code",
    [
        "vendor_search_limit_exceeded",
        "generation_limit_exceeded",
        "insufficient_credits",
        "daily_import_limit_exceeded",
    ],
)
def test_stealads_limits_map_to_a_fallback(code):
    text = explain_stealads_error(code)
    assert "→" in text and code not in text


def test_unknown_stealads_error_passes_through():
    assert "weird_code (detail)" in explain_stealads_error("weird_code", "detail")


def test_excluded_brand_hard_stops(tmp_path):
    cfg = tmp_path / "excluded.yaml"
    cfg.write_text("brands:\n  - name: Acme Gym\n  - {ig: '@acmestudio', domain: acme.example}\n")
    for ident in ("acme gym", "Acme-Gym", "ACMESTUDIO", "https://www.acme.example/"):
        with pytest.raises(ExcludedBrand):
            check_not_excluded(ident, path=cfg)
    check_not_excluded("Foldbrook", path=cfg)


def test_shipped_exclusion_list_is_empty():
    check_not_excluded("Your Client Co")  # the example ships commented out


def test_scrapecreators_snapshot_shape_maps_to_contract():
    rows = json.loads((DATA / "scrapecreators_company_ads.json").read_text())["results"]
    img, vid = (map_scrapecreators_ad(r) for r in rows)
    assert img["ad_id"] == "sc-1"
    assert img["start_date"] == "2025-10-01"
    assert img["headline"] == "Holiday sets ship free"
    assert img["body"].startswith("Gift the wallet that lasts.")
    assert img["cta"] == "Shop Now"
    assert img["variation_count"] == 4 and img["group_id"] == "998877"
    assert img["bangers_rank"] is None and img["days_live"] > 300
    assert img["media"] == [
        {
            "url": rows[0]["snapshot"]["images"][0]["resized_image_url"],
            "durable": False,
            "kind": "image",
        }
    ]
    assert vid["format"] == "VIDEO" and vid["media"] == []
    assert vid["days_live"] == 14  # ended ad: start → end, not start → today


def test_cache_media_drops_remote_urls_and_logs_skips(tmp_path):
    rows = json.loads((DATA / "scrapecreators_company_ads.json").read_text())["results"]
    ads = [map_scrapecreators_ad(r) for r in rows]

    def fake_download(url, stem):
        p = stem.with_suffix(".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"img")
        return p, "hash"

    skipped = sc_client.cache_media(ads, tmp_path / "media", downloader=fake_download)
    assert skipped == [{"ad_id": "sc-2", "reason": "video_no_preview"}]
    assert ads[0]["media"] == [{"path": "media/sc-1.jpg", "durable": False, "kind": "image"}]
    assert "fbcdn" not in json.dumps(ads)


def test_pick_company_confidence():
    exact = sc_client.pick_company(
        "foldbrook",
        [
            {"page_id": 1, "name": "Foldbrook", "likes": 10},
            {"page_id": 2, "name": "Foldbrook Wallet Fans", "likes": 99},
        ],
    )
    assert exact["confidence"] == "exact" and exact["page_id"] == "1"
    amb = sc_client.pick_company(
        "grain",
        [
            {"page_id": 1, "name": "Original Grain", "likes": 500},
            {"page_id": 2, "name": "Grain Co", "likes": 400},
        ],
    )
    assert amb["confidence"] == "ambiguous" and len(amb["alternates"]) == 1
    likely = sc_client.pick_company(
        "grain",
        [
            {"page_id": 1, "name": "Original Grain", "likes": 5000},
            {"page_id": 2, "name": "Grain Co", "likes": 4},
        ],
    )
    assert likely["confidence"] == "likely"


def test_cli_explain_prints_fallback(capsys):
    assert cli.main(["explain", "generation_limit_exceeded"]) == 0
    assert "→" in capsys.readouterr().out


def test_cli_ingest_builds_ads_raw_from_mcp_json(tmp_path):
    import shutil

    fx = Path(__file__).resolve().parents[1] / "fixtures" / "foldbrook"
    for f in ("stealads_list_ads.json", "find_bangers.json"):
        shutil.copy(fx / f, tmp_path / f)
    shutil.copytree(fx / "media", tmp_path / "media")
    assert cli.main(["ingest", str(tmp_path)]) == 0
    raw = json.loads((tmp_path / "ads.raw.json").read_text())
    assert raw["source"] == "stealads" and raw["ads"]
    assert any(a["bangers_rank"] == 1 for a in raw["ads"])


def test_cli_ingest_without_json_exits_2(tmp_path, capsys):
    assert cli.main(["ingest", str(tmp_path)]) == cli.EXIT_USER
    assert "has no StealAds ads saved" in capsys.readouterr().err
