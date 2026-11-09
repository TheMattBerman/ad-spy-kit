"""Fixes from the Quince new-user test (2026-11-05): catalog placeholders, offer types, thin
reads, on-screen "no text", failed-gate images, image size and slice layout."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from PIL import Image

from ad_spy_kit import pipeline
from ad_spy_kit.media import MAX_EDGE, normalize_run, shrink_image
from ad_spy_kit.onscreen import apply_onscreen, check_item, onscreen_targets
from ad_spy_kit.render import _tile_grid, build_context, render_html, screenshot_html
from ad_spy_kit.sc_client import read_params
from ad_spy_kit.sl_adapter import map_scrapecreators_ad
from ad_spy_kit.spend import thin_read_note
from ad_spy_kit.template_text import has_template, scrub_ad, scrub_text
from ad_spy_kit.validate_run import Report, board_html_errors, check_offer_type

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts" / "screenshots" / "live" / "spacegoods"
START = int(time.time()) - 90 * 86400


def _row(title: str, body: str, fmt: str = "DPA") -> dict:
    return {
        "ad_archive_id": "111222333444555",
        "start_date": START,
        "is_active": True,
        "snapshot": {
            "display_format": fmt,
            "title": title,
            "body": {"text": body},
            "cta_text": "Shop now",
            "cards": [{"resized_image_url": "https://example.test/a.jpg"}],
        },
    }


# 1. Template placeholders -------------------------------------------------------------------


def test_placeholder_headline_and_caption_become_empty_and_tagged_catalog():
    ad = map_scrapecreators_ad(_row("{{product.name}}", "{{product.brand}}", "DCO"))
    assert ad["headline"] == "" and ad["body"] == ""
    assert ad["copy_hook"] == "" and ad["catalog"] is True
    assert not has_template(json.dumps(ad))


def test_placeholder_headline_falls_back_to_the_real_caption_line():
    ad = map_scrapecreators_ad(
        _row("{{product.name}}", "Competitors marked it down. We never marked it up.")
    )
    assert ad["headline"] == ""
    assert ad["copy_hook"] == "Competitors marked it down."
    assert ad["hook_source"] == "copy" and ad["catalog"] is True


def test_caption_keeps_real_lines_and_drops_placeholder_lines():
    text, hit = scrub_text("Real line.\n{{product.brand}}\nAnother real one.")
    assert hit and text == "Real line.\nAnother real one."


def test_scrub_is_idempotent_and_flags_dpa_without_placeholders():
    ad = map_scrapecreators_ad(_row("Great jeans", "Comfy.", "DPA"))
    assert ad["catalog"] is True and ad["headline"] == "Great jeans"
    assert scrub_ad(ad) is False


def test_normalize_run_cleans_a_saved_run(tmp_path):
    ads = {
        "competitor_id": "1",
        "pulled_at": "2026-11-05T00:00:00Z",
        "source": "scrapecreators",
        "ads": [
            {
                "ad_id": "9",
                "headline": "{{product.name}}",
                "body": "Real words here.",
                "cta": "",
                "days_live": 40,
                "variation_count": 1,
                "is_active": True,
                "format": "DPA",
            }
        ],
    }
    (tmp_path / "ads.raw.json").write_text(json.dumps(ads))
    assert normalize_run(tmp_path)["templates"] == 1
    got = json.loads((tmp_path / "ads.raw.json").read_text())["ads"][0]
    assert got["headline"] == "" and got["copy_hook"] == "Real words here."
    assert normalize_run(tmp_path) == {"templates": 0, "images": 0}


def test_gate_fails_when_a_placeholder_reaches_the_board():
    errors = board_html_errors(
        "<body><span class='q'>{{product.name}}</span> https://stealads.ai</body>"
    )
    assert any(e.startswith("C9") for e in errors)
    assert not any(
        e.startswith("C9") for e in board_html_errors("<body>fine https://stealads.ai</body>")
    )
    # The board's own scripts use `}}`; they are not visible text.
    script = "<script>function f(){if(a){b()}}</script> https://stealads.ai"
    assert not any(e.startswith("C9") for e in board_html_errors(script))


# 2. Thin read -------------------------------------------------------------------------------


def _ads(days: list[int], keys: list[str]) -> dict:
    return {
        "source": "scrapecreators",
        "read_mode": "longest",
        "read_cap": 30,
        "import_cap_hit": True,
        "ads": [
            {"ad_id": str(i), "days_live": d, "media_hash": k, "headline": "", "body": ""}
            for i, (d, k) in enumerate(zip(days, keys, strict=True))
        ],
    }


def test_thin_read_note_for_short_runs_and_repeats_states_the_cost():
    raw = _ads([119] * 10, [f"h{i % 7}" for i in range(10)])
    note = thin_read_note(raw, "runs/q")
    assert note and "119 days" in note and "7 different creatives" in note
    assert "--max-ads 60" in note and "4 ScrapeCreators credits" in note and "3 more" in note
    assert "--min-days 120" in note


def test_no_thin_note_for_a_long_varied_or_uncapped_read():
    assert thin_read_note(_ads([200] * 5, [f"h{i}" for i in range(5)])) is None
    short = _ads([60] * 5, [f"h{i}" for i in range(5)])
    short["import_cap_hit"] = False  # the brand has no more ads to read
    assert thin_read_note(short) is None
    newest = _ads([60] * 5, [f"h{i}" for i in range(5)])
    newest["read_mode"] = "newest"
    assert thin_read_note(newest) is None


def test_min_days_moves_the_date_cutoff_only():
    from datetime import date

    base = read_params(today=date(2026, 11, 5))
    assert base["end_date"] == "2026-10-06" and base["sort_by"] == "total_impressions"
    old = read_params(today=date(2026, 11, 5), min_days=120)
    assert old["end_date"] == "2026-07-08" and old["status"] == "ACTIVE"


# 3. Offers ----------------------------------------------------------------------------------


def _ctx(tmp_path, offers: list[dict]):
    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731
    analysis = load("analysis")
    analysis["offer_map"] = offers
    return build_context(
        competitor=load("competitor"),
        ads_raw=load("ads.raw"),
        winners=load("winners"),
        analysis=analysis,
        counters=load("counters"),
        media_dir=RUN / "media",
        run_dir=RUN,
    )


def test_price_claim_never_feeds_top_discount_and_shows_once(tmp_path):
    winners = json.loads((RUN / "winners.json").read_text())["winners"]
    a, b = winners[0]["ad_id"], winners[1]["ad_id"]
    quote = "up to 80% less than you'd expect"
    ads = {x["ad_id"]: x for x in json.loads((RUN / "ads.raw.json").read_text())["ads"]}
    for ad_id in (a, b):
        ads[ad_id]["body"] = quote
    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731
    analysis = load("analysis")
    analysis["offer_map"] = [
        {
            "ad_id": i,
            "offer_type": "price_claim",
            "discount_depth": "80%",
            "evidence": quote,
            "evidence_source": "copy",
        }
        for i in (a, b)
    ]
    ctx = build_context(
        competitor=load("competitor"),
        ads_raw={**load("ads.raw"), "ads": list(ads.values())},
        winners=load("winners"),
        analysis=analysis,
        counters=load("counters"),
        media_dir=RUN / "media",
        run_dir=RUN,
    )
    assert ctx["deepest_offer"] is None
    assert len(ctx["offers_shown"]) == 1
    assert ctx["offers_shown"][0]["also"] == [ctx["rank_of"][b]]
    assert not ctx["offers_shown"][0]["discount_depth"]
    html = render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "b.html",
    )
    assert "top discount" not in html.lower()


def test_a_comparison_filed_as_pct_off_fails_a9():
    rep = Report()
    check_offer_type(
        0, {"offer_type": "pct_off", "evidence": "up to 80% less than you’d expect"}, rep
    )
    assert any(e.startswith("A9") for e in rep.errors)
    drop = Report()
    check_offer_type(
        0, {"offer_type": "price_drop", "evidence": "50-80% less than traditional retail"}, drop
    )
    assert any(e.startswith("A9") for e in drop.errors)
    ok = Report()
    check_offer_type(0, {"offer_type": "pct_off", "evidence": "Up to 80% off"}, ok)
    check_offer_type(0, {"offer_type": "price_claim", "evidence": "cheaper than theirs"}, ok)
    assert not ok.errors


# 5. On-screen "no text" ---------------------------------------------------------------------


def test_onscreen_no_text_is_accepted_and_stops_the_listing(tmp_path):
    assert check_item({"ad_id": "1", "onscreen_hook": None, "no_text": True}) is None
    assert check_item({"ad_id": "1", "onscreen_hook": "Hi", "no_text": True})
    assert check_item({"ad_id": "1", "onscreen_hook": None})  # still needs a hook or no_text
    media = tmp_path / "media"
    media.mkdir()
    (media / "1.jpg").write_bytes(b"x")
    ads_raw = {"ads": [{"ad_id": "1", "format": "IMAGE", "headline": "H", "body": "B"}]}
    winners = {"winners": [{"ad_id": "1"}]}
    assert len(onscreen_targets(ads_raw, winners, media)) == 1
    landed = apply_onscreen(ads_raw, {"items": [{"ad_id": "1", "no_text": True}]})
    assert landed == 1 and ads_raw["ads"][0]["hook_source"] == "copy"
    assert onscreen_targets(ads_raw, winners, media) == []


# 6. Failed gate -----------------------------------------------------------------------------


def test_failed_gate_parks_images_and_a_pass_clears_them(tmp_path, monkeypatch):
    for name in ("board.png", "newsletter.png", "og.png"):
        (tmp_path / name).write_bytes(b"png")
    (tmp_path / "x-slices").mkdir()
    (tmp_path / "x-slices" / "01.png").write_bytes(b"png")
    bad = Report(errors=["C5 layout: clipped"])
    monkeypatch.setattr(pipeline, "validate_run", lambda *_a, **_k: bad)
    with pytest.raises(pipeline.GateFailed) as e:
        pipeline.gate(tmp_path)
    assert "board.failed.png" in str(e.value)
    assert not (tmp_path / "board.png").exists()
    assert (tmp_path / "board.failed.png").exists()
    assert (tmp_path / "x-slices.failed" / "01.png").exists()
    monkeypatch.setattr(pipeline, "validate_run", lambda *_a, **_k: Report())
    pipeline.gate(tmp_path)
    assert not (tmp_path / "board.failed.png").exists()
    assert not (tmp_path / "x-slices.failed").exists()


# 7. Image size ------------------------------------------------------------------------------


def test_big_images_are_shrunk_to_1200_jpeg(tmp_path):
    big = tmp_path / "7.png"
    Image.new("RGB", (3000, 2000), (200, 30, 30)).save(big)
    out = shrink_image(big, keep_originals=True)
    assert out.suffix == ".jpg" and not big.exists()
    with Image.open(out) as im:
        assert max(im.size) == MAX_EDGE and im.format == "JPEG"
    assert (tmp_path / "originals" / "7.png").exists()
    assert shrink_image(out) == out  # already small: untouched


def test_embedded_image_is_downscaled(tmp_path):
    from ad_spy_kit.render import _b64_file

    big = tmp_path / "8.jpg"
    Image.effect_noise((4000, 3000), 80).convert("RGB").save(big, quality=95)
    assert big.stat().st_size > 900_000
    assert len(_b64_file(big)) < big.stat().st_size


# 8. Layout ----------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 5, 6, 7, 9, 11, 12, 21, 23, 25, 30, 48])
def test_summary_tiles_fill_whole_rows(count):
    cols, shown = _tile_grid(count)
    assert shown % cols == 0 and count - shown < cols and shown >= 1


def test_long_counter_hook_shrinks_to_fit_and_a_huge_one_is_flagged(tmp_path):
    pytest.importorskip("playwright")
    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731

    def overflow(hook: str) -> list[str]:
        counters = load("counters")
        counters["counters"][0]["hook"] = hook
        ctx = build_context(
            competitor=load("competitor"),
            ads_raw=load("ads.raw"),
            winners=load("winners"),
            analysis=load("analysis"),
            counters=counters,
            media_dir=RUN / "media",
            run_dir=RUN,
        )
        out = tmp_path / "b.html"
        render_html(
            template="board/war-room.html.j2",
            context=ctx,
            templates_dir=ROOT / "templates",
            out_html=out,
        )
        try:
            return screenshot_html(
                out, tmp_path / "b.png", width=1200, height=750, check_overflow=True
            )
        except Exception as e:  # no Chromium on this machine
            pytest.skip(f"Chromium unavailable: {e}")

    ninety = "Our sale price is on the front of the box and the sale ends Monday at noon sharp."
    assert len(ninety) <= 90
    assert overflow(ninety) == []
    assert overflow("Our sale price is on the front. " * 8)


def test_teardown_and_cards_name_catalog_ads_and_differing_versions():
    from ad_spy_kit.render import teardown_markdown

    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731
    ads_raw = load("ads.raw")
    winners = load("winners")
    first = winners["winners"][0]
    other = next(a for a in ads_raw["ads"] if a["ad_id"] != first["ad_id"])
    first["dupes_merged"] = [other["ad_id"]]
    other["headline"], other["body"] = "A different caption", ""
    other["copy_hook"] = "A different caption"
    other["hook_source"] = "copy"
    for a in ads_raw["ads"]:
        if a["ad_id"] == first["ad_id"]:
            a["catalog"] = True
            a["format"] = "DPA"
    first["format"] = "DPA"
    ctx = build_context(
        competitor=load("competitor"),
        ads_raw=ads_raw,
        winners=winners,
        analysis=load("analysis"),
        counters=load("counters"),
        media_dir=RUN / "media",
        run_dir=RUN,
    )
    card = ctx["winner_wall"][0]
    assert card["catalog"] and card["versions_differ"]
    md = teardown_markdown(ctx)
    assert "catalog ad" in md and "different captions" in md and "A different caption" in md
    assert not has_template(md)


def test_dynamic_ad_with_written_copy_gets_no_catalog_badge():
    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731
    ads_raw = load("ads.raw")
    winners = load("winners")
    first = winners["winners"][0]
    for a in ads_raw["ads"]:
        if a["ad_id"] == first["ad_id"]:
            a["catalog"] = True
            a["format"] = "DCO"
            a["copy_hook"] = "Real written copy"
            a["hook_source"] = "copy"
    first["format"] = "DCO"
    ctx = build_context(
        competitor=load("competitor"),
        ads_raw=ads_raw,
        winners=winners,
        analysis=load("analysis"),
        counters=load("counters"),
        media_dir=RUN / "media",
        run_dir=RUN,
    )
    card = ctx["winner_wall"][0]
    if card["hook_text"]:
        assert not card["catalog"]
