"""Fixes from the Burrow new-user test (2026-11-05): young ads never hide silently, `run`
falls back to the newest ads, no blank slices, dedupe, singular days, overflow checks,
rank-ref and "none of them" checks, small video previews and macOS `._*` files."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from ad_spy_kit import cli, sc_client
from ad_spy_kit.dedupe import creative_groups, distinct_creatives
from ad_spy_kit.errors import KitError
from ad_spy_kit.paths import is_junk, visible
from ad_spy_kit.render import (
    _frame_fields,
    build_context,
    render_html,
    screenshot_html,
    wall_caption,
)
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.validate import validate_doc
from ad_spy_kit.validate_run import (
    Report,
    board_html_errors,
    check_hidden_ads,
    check_rank_refs,
    slice_fill,
)

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "artifacts" / "screenshots"


def ad(i, *, days=1, var=1, headline="Plain", body="Plain body", **extra):
    return {
        "ad_id": str(i),
        "headline": headline,
        "body": body,
        "days_live": days,
        "variation_count": var,
        "is_active": True,
        "still_running": True,
        "start_date": f"2026-11-{5 - min(days, 4):02d}",
        "format": "IMAGE",
        **extra,
    }


# ---- 1. young ads never hide silently ---------------------------------------------------


def test_sale_ad_under_a_week_old_still_reaches_a_full_board():
    ads = [ad(i, var=4, group_id=f"g{i}", media_hash=f"h{i}") for i in range(1, 8)]
    ads.append(ad(99, headline="Up to 70% Off Warehouse", body="Last chance, up to 70% off."))
    w = score_winners(ads)
    ids = [x["ad_id"] for x in w["winners"]]
    assert len(ids) == 6 and "99" in ids
    sale = next(x for x in w["winners"] if x["ad_id"] == "99")
    assert sale["added_while_new"] is True and sale["strength_label"] == "testing"
    # An ad that is not on the board and not a copy of one is counted as hidden.
    assert w["hidden"] == []


def test_short_board_fills_up_with_the_newest_ads_and_hidden_ads_are_listed():
    ads = [ad(1, days=40, var=5, group_id="a"), ad(2, days=20, var=2, group_id="b")]
    ads.append(ad(3, days=9, var=1, group_id="c"))
    ads += [ad(10 + i, days=0, group_id=f"n{i}") for i in range(8)]
    w = score_winners(ads)
    assert len(w["winners"]) == 6
    assert [x["ad_id"] for x in w["winners"][:3]] == ["1", "2", "3"]
    assert all(x["added_while_new"] for x in w["winners"][3:])
    assert len(w["hidden"]) == 5 and len(w["quarantined"]) == 8
    assert {"ad_id", "headline", "bf_tag", "copies"} <= set(w["hidden"][0])


def test_a_week_old_ad_is_never_pushed_out_by_a_sale_ad():
    ads = [ad(i, days=9, var=1, group_id=f"g{i}") for i in range(1, 7)]
    ads.append(ad(50, headline="Black Friday sale", body="50% off"))
    w = score_winners(ads)
    assert "50" not in [x["ad_id"] for x in w["winners"]]
    assert [h["ad_id"] for h in w["hidden"]] == ["50"]


def test_board_says_how_many_newer_ads_are_not_shown(tmp_path):
    ctx = _ctx_for_burrow_like(tmp_path)
    html = render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "board.html",
    )
    assert ctx["hidden_count"] == 2
    assert "2 NEWER ADS NOT SHOWN" in html
    assert "2 newer ads not shown" in html  # the wall slice repeats it
    from ad_spy_kit.render import teardown_markdown

    md = teardown_markdown(ctx)
    assert "## 2 newer ads not shown" in md and "Hidden headline" in md


def _ctx_for_burrow_like(tmp_path, *, offer_map=None, longest=1):
    run = tmp_path / "run"
    (run / "media").mkdir(parents=True)
    ads = [
        ad(i, var=4, group_id=f"g{i}", media_hash=f"h{i}", headline=f"H{i}") for i in range(1, 7)
    ]
    ads += [ad(8, headline="Hidden headline", group_id="x1"), ad(9, group_id="x2")]
    for a in ads:
        Image.new("RGB", (400, 500), (200, 90, 40)).save(run / "media" / f"{a['ad_id']}.jpg")
        a["media"] = [{"path": f"media/{a['ad_id']}.jpg", "durable": True, "kind": "image"}]
        a["days_live"] = longest if a["days_live"] < 7 else a["days_live"]
        a["strength_label"] = "testing"
        a["hook_source"] = "copy"
        a["copy_hook"] = a["headline"]
    ads_raw = {"ads": ads, "total_available": len(ads), "pulled_at": "2026-11-05T12:00:00Z"}
    winners = score_winners(ads)
    analysis = {
        "competitor": "Burrow",
        "headline": {"bottom": "Only one of three ads names a sale."},
        "stats": [],
        "offer_map": offer_map or [],
        "hooks": [],
        "formats": [],
        "gaps": [
            {
                "gap": "None of the 6 ads on this board name Black Friday",
                "evidence_ad_ids": ["1", "2", "3", "4", "5", "6"],
                "counter_angle": "Say it",
            }
        ],
        "steal_this": [],
        "citations_ok": True,
    }
    counters = {
        "counters": [
            {
                "gap_ref": 0,
                "beats_ad_id": "1",
                "angle": "a",
                "headline": "Same as the hook",
                "hook": "Same as the hook",
                "offer": "o",
                "visual_direction": "v",
                "why_it_beats": "Their #01 ad leads with H1.",
                "aspect": "9:16",
                "status": "brief",
            }
        ]
    }
    return build_context(
        competitor={"page_name": "Burrow"},
        ads_raw=ads_raw,
        winners=winners,
        analysis=analysis,
        counters=counters,
        media_dir=run / "media",
        run_dir=run,
    )


# ---- A7: "none of them" against ads that are not on the board ---------------------------


def _docs(headline_bottom, *, off_board_copy="Up to 70% off Warehouse", gap=None):
    ads = [ad(1, var=4, group_id="g1"), ad(2, headline=off_board_copy, body=off_board_copy)]
    return {
        "analysis": {
            "headline": {"bottom": headline_bottom},
            "gaps": [{"gap": gap or "x", "evidence_ad_ids": ["1"], "counter_angle": "y"}],
        },
        "winners": {"winners": [{"ad_id": "1", "display_rank": 1}]},
        "ads.raw": {"ads": ads},
    }


def test_none_claim_is_flagged_when_a_hidden_ad_contradicts_it():
    rep = Report()
    check_hidden_ads(_docs("None of them name Black Friday or a price."), rep)
    assert len(rep.errors) == 1
    assert (
        rep.errors[0].startswith("A7 headline.bottom")
        and "'2'" in rep.errors[0]
        or "ad 2" in (rep.errors[0])
    )


def test_none_claim_limited_to_the_board_or_naming_the_ad_passes():
    for text in (
        "None of the 6 ads on this board name a price.",
        "Only one of six ads names a sale.",
        "One newer ad says up to 70% off.",
    ):
        rep = Report()
        check_hidden_ads(_docs(text), rep)
        assert rep.errors == [], text


def test_none_claim_is_fine_when_no_hidden_ad_says_it():
    rep = Report()
    check_hidden_ads(_docs("None of them name a price.", off_board_copy="Soft sofas"), rep)
    assert rep.errors == []


def test_gap_claims_are_checked_too():
    rep = Report()
    docs = _docs("Fine.", gap="No ad shows a discount")
    check_hidden_ads(docs, rep)
    assert rep.errors and rep.errors[0].startswith("A7 gaps[0].gap")


# ---- A8: rank refs -----------------------------------------------------------------------


def _rank_docs(why, beats="b"):
    return {
        "analysis": {"gaps": [], "steal_this": []},
        "winners": {
            "winners": [
                {"ad_id": "a", "display_rank": 1},
                {"ad_id": "b", "display_rank": 6},
            ]
        },
        "counters": {"counters": [{"why_it_beats": why, "beats_ad_id": beats}]},
    }


def test_rank_reference_must_exist_and_match_the_ad_it_answers():
    ok = Report()
    check_rank_refs(_rank_docs("Their #06 ad leads with a quote."), ok)
    assert ok.errors == []
    missing = Report()
    check_rank_refs(_rank_docs("Their #04 ad leads with a quote."), missing)
    assert "A8" in missing.errors[0] and "#04" in missing.errors[0]
    wrong = Report()
    check_rank_refs(_rank_docs("Their #01 ad leads with a quote."), wrong)
    assert "beats_ad_id is #06" in wrong.errors[0]


# ---- 3. no blank slices or sections -----------------------------------------------------


def test_empty_offer_map_skips_the_offers_slice_and_section(tmp_path):
    ctx = _ctx_for_burrow_like(tmp_path)
    assert [s["key"] for s in ctx["slices"]] == ["summary", "wall", "opening", "counter"]
    from ad_spy_kit.render import teardown_markdown

    assert "## Offers" not in teardown_markdown(ctx)


def test_an_offer_with_no_quote_makes_no_card(tmp_path):
    offers = [
        {"ad_id": "1", "offer_type": "none", "evidence": " "},
        {"ad_id": "2", "offer_type": "pct_off", "discount_depth": "20%", "evidence": "20% off"},
    ]
    ctx = _ctx_for_burrow_like(tmp_path, offer_map=offers)
    assert [o["ad_id"] for o in ctx["offers_shown"]] == ["2"]
    html = render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "b.html",
    )
    assert "none ·" not in html.lower().replace("none of", "")


def test_slice_fill_flags_a_blank_slice_and_a_hole(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (1080, 1350), (215, 216, 211)).save(blank)
    fill, gap = slice_fill(blank)
    assert fill == 0 and gap > 1000
    holey = Image.new("RGB", (1080, 1350), (215, 216, 211))
    holey.paste(Image.new("RGB", (900, 100), (0, 0, 0)), (60, 130))
    holey.save(tmp_path / "holey.png")
    fill, gap = slice_fill(tmp_path / "holey.png")
    assert 0 < fill < 0.12 and gap > 470


def test_shipped_boards_have_no_blank_slice():
    for p in SHOTS.glob("**/x-slices/*.png"):
        fill, gap = slice_fill(p)
        assert fill >= 0.12 and gap <= 470, p


# ---- 4. dedupe ---------------------------------------------------------------------------


def test_same_group_or_same_image_is_one_creative():
    ads = [
        ad(1, group_id="g", media_hash="a"),
        ad(2, group_id="g", media_hash="b"),
        ad(3, media_hash="b"),
        ad(4, media_hash="z", headline="Same", body="Same body"),
        ad(5, media_hash="y", headline="Same", body="Same body"),  # new picture: new creative
    ]
    assert distinct_creatives(ads) == 3
    assert [len(g) for g in creative_groups(ads)] == [3, 1, 1]


def test_wall_caption_counts_creatives_not_copies():
    ads = [ad(i, group_id="g") for i in range(1, 4)] + [ad(9, group_id="h")]
    raw = {"ads": ads, "total_available": 4}
    assert wall_caption(raw, 2) == "2 creatives from 4 ads"
    assert wall_caption({"ads": [ad(1)], "total_available": 1}, 1) == "1 ad"


def test_winner_says_how_many_versions(tmp_path):
    ctx = _ctx_for_burrow_like(tmp_path)
    assert ctx["winner_wall"][0]["versions"] == 4


# ---- 5. singular days, labels tile --------------------------------------------------------


def test_one_day_is_singular_and_the_gate_sees_through_markup(tmp_path):
    ctx = _ctx_for_burrow_like(tmp_path)
    html = render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "b.html",
    )
    assert ctx["longest_unit"] == "day"
    assert "<small> day</small>" in html and "<small> days</small>" not in html
    assert board_html_errors('<div class="v">1<small> days</small></div> https://stealads.ai')


def test_labels_tile_counts_only_ads_on_the_board(tmp_path):
    ctx = _ctx_for_burrow_like(tmp_path)
    assert sum(n for _, n in ctx["label_counts"]) == len(ctx["winner_wall"])


# ---- 6/7. overflow gate ------------------------------------------------------------------

SLICE_PAGE = """<!doctype html><html><body style="margin:0;width:1200px">
<section class="slice" style="position:absolute;left:0;top:0;width:1080px;height:1350px">
<div class="slice-inner" style="padding:56px;height:100%;position:relative">
<div class="slice-tag">X · Test</div>
<a class="slice-cta" style="white-space:{wrap};display:inline-block;font-size:26px">
StealAds can turn this brief into a finished ad. Your first one is free (early access at
stealads.ai) and it never stops talking
</a>
<div class="slice-note" style="position:absolute;bottom:92px">note</div>
</div></section></body></html>"""


@pytest.mark.parametrize(("wrap", "flagged"), [("nowrap", True), ("normal", False)])
def test_gate_detects_slice_text_running_off_the_edge(tmp_path, wrap, flagged):
    page = tmp_path / "p.html"
    page.write_text(SLICE_PAGE.replace("{wrap}", wrap))
    out = screenshot_html(page, tmp_path / "p.png", width=1200, height=750, check_overflow=True)
    assert any("slice text runs off the edge" in o for o in out) is flagged, out


def test_slice_cta_wraps_in_the_real_template():
    css = (ROOT / "templates" / "board" / "war-room-tokens.css").read_text()
    rule = next(line for line in css.splitlines() if line.startswith(".slice-cta"))
    assert "white-space: normal" in rule


def test_long_headline_shrinks_to_fit_and_a_huge_one_is_flagged(tmp_path):
    run = tmp_path / "r"
    ctx = _ctx_for_burrow_like(tmp_path)
    for text, flagged in (
        ("Only one of six ads names a sale: up to 70% off.", False),
        (
            "Nobody on this board sells the thing they all say they sell to everybody, and "
            "none of them ever will",
            True,
        ),
    ):
        ctx["title_line"] = text
        html = render_html(
            template="board/war-room.html.j2",
            context=ctx,
            templates_dir=ROOT / "templates",
            out_html=tmp_path / "h.html",
        )
        out = screenshot_html(
            tmp_path / "h.html", tmp_path / "h.png", width=1200, height=750, check_overflow=True
        )
        assert any("headline is cut off" in o for o in out) is flagged, (text, out)
    assert html and not run.exists()


# ---- 8. headline.top is optional ----------------------------------------------------------


def test_headline_top_is_optional_and_prints_on_the_summary_slice(tmp_path):
    doc = json.loads((SHOTS / "live" / "spacegoods" / "analysis.json").read_text())
    del doc["headline"]["top"]
    assert validate_doc("analysis", doc, root=ROOT) == []
    ctx = _ctx_for_burrow_like(tmp_path)
    ctx["headline_top"] = "Burrow has 3 ads on this board."
    html = render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "t.html",
    )
    assert '<div class="slice-top">Burrow has 3 ads on this board.</div>' in html


# ---- 11. teardown heading ----------------------------------------------------------------


def test_teardown_heading_has_one_parenthetical():
    for name in ("dewbar", "foldbrook", "fizzwell", "live/spacegoods"):
        for line in (SHOTS / name / "teardown.md").read_text().splitlines():
            if line.startswith("## Their"):
                assert line.count("(") <= 1, line


# ---- 14. small video previews -------------------------------------------------------------


def test_tiny_video_preview_is_marked_not_stretched(tmp_path):
    small, big = tmp_path / "s.jpg", tmp_path / "b.jpg"
    Image.new("RGB", (110, 138)).save(small)
    Image.new("RGB", (1080, 1920)).save(big)
    media = [{"kind": "video_preview"}]
    assert _frame_fields(small, "DCO", {"media": media})["tiny_preview"] is True
    assert _frame_fields(big, "DCO", {"media": media})["tiny_preview"] is False
    # A small still image is not a video preview: it keeps the normal frame.
    assert _frame_fields(small, "IMAGE", {"media": [{"kind": "image"}]})["tiny_preview"] is False


def test_cache_media_swaps_a_tiny_preview_for_the_widest_alternative(tmp_path):
    def fake(url, stem, max_bytes=0):
        size = {"small": (110, 138), "mid": (400, 500), "big": (800, 1000)}[url]
        path = stem.with_suffix(".jpg")
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size).save(path)
        return path, url

    ads = [
        {
            "ad_id": "7",
            "format": "VIDEO",
            "media": [
                {
                    "url": "small",
                    "kind": "video_preview",
                    "fallback_urls": ["mid", "big"],
                }
            ],
        }
    ]
    sc_client.cache_media(ads, tmp_path / "media", downloader=fake)
    saved = tmp_path / "media" / "7.jpg"
    assert Image.open(saved).size == (400, 500)  # first one wide enough wins
    assert not list((tmp_path / "media").glob("7.alt*"))
    assert ads[0]["media"][0]["path"] == "media/7.jpg"
    assert "fallback_urls" not in ads[0]["media"][0]


def test_original_image_is_preferred_over_the_resized_one():
    from ad_spy_kit.sl_adapter import sc_media

    snap = {
        "images": [
            {"resized_image_url": "https://x/resized.jpg", "original_image_url": "https://x/o.jpg"}
        ]
    }
    media = sc_media(snap)[0]
    assert media["url"] == "https://x/o.jpg" and media["fallback_urls"] == ["https://x/resized.jpg"]


# ---- 15. macOS ._ files -------------------------------------------------------------------


def test_junk_files_are_ignored_where_the_kit_lists_folders(tmp_path):
    assert is_junk(Path("._a.json")) and not is_junk(Path("a.json"))
    (tmp_path / "search_ads.json").write_text("{}")
    (tmp_path / "._search_ads.json").write_bytes(b"\x00\x05\x16\x07")
    assert [p.name for p in sc_client.saved_files(tmp_path, "search_ads")] == ["search_ads.json"]
    assert [p.name for p in visible(tmp_path.iterdir())] == ["search_ads.json"]


def test_category_and_tracked_skip_sidecar_files(tmp_path):
    from ad_spy_kit import category, tracked

    brands = tmp_path / "brands"
    (brands / "acme").mkdir(parents=True)
    (brands / "acme" / "competitor.json").write_text('{"page_name": "Acme", "page_id": "1"}')
    (brands / "acme" / "ads.raw.json").write_text('{"ads": [], "credits_spent": 2}')
    (brands / "._acme").write_bytes(b"\x00\x05\x16\x07")
    (brands / "acme" / "._ads.raw.json").write_bytes(b"\x00\x05\x16\x07")
    assert category._credits_in(tmp_path) == 2
    assert [b["name"] for b in category.load_saved(tmp_path, max_ads=3)] == ["Acme"]
    (tmp_path / "tracked_rival_ads.json").write_text("{}")
    (tmp_path / "._tracked_rival_ads.json").write_bytes(b"\x00\x05")
    assert [p.name for p in tracked.tracked_files(tmp_path)] == ["tracked_rival_ads.json"]


def test_stale_slices_are_cleared_and_sidecars_left_alone(tmp_path):
    from ad_spy_kit.slice import slice_board

    out = tmp_path / "x-slices"
    out.mkdir()
    (out / "05.png").write_bytes(b"old")
    (out / "._05.png").write_bytes(b"\x00\x05")
    html = tmp_path / "b.html"
    html.write_text(
        '<html><body><section id="slice-01" class="slice" '
        'style="position:absolute;left:-9999px;width:1080px;height:1350px">x'
        "</section></body></html>"
    )
    slice_board(html, out, repo_root=ROOT)
    assert [p.name for p in visible(out.iterdir())] == ["01.png"]
    assert (out / "._05.png").exists()


# ---- 2/12. run: newest fallback and --max-credits ------------------------------------------


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    monkeypatch.setattr("cie.scrapecreators_client._load_dotenv_if_needed", lambda *_: None)
    calls = []

    def fake_pull(comp, *, newest=False, **kw):
        calls.append({"page_id": comp["page_id"], "newest": newest})
        ads = [ad(1, days=1, group_id="g")] if newest else []
        return {
            "competitor_id": comp["page_id"],
            "pulled_at": "2026-11-05T12:00:00Z",
            "source": "scrapecreators",
            "collect_mode": "full",
            "total_available": len(ads),
            "import_cap_hit": False,
            "read_mode": "newest" if newest else "longest",
            "credits_spent": 1,
            # The longest read left out the brand's one new ad (live under 30 days).
            "dropped_too_new": 0 if newest else 1,
            "skipped": [],
            "ads": ads,
        }

    monkeypatch.setattr(sc_client, "pull_via_scrapecreators", fake_pull)
    return tmp_path, calls


def _run_args(out, query="612471195588500", **kw):
    base = {
        "query": query,
        "country": "US",
        "out": out,
        "max_ads": 30,
        "newest": False,
        "no_images": True,
        "yes": True,
        "max_credits": None,
    }
    return argparse.Namespace(**{**base, **kw})


def test_run_falls_back_to_newest_in_the_same_run_without_a_second_lookup(run_env, capsys):
    tmp, calls = run_env
    out = tmp / "burrow"
    assert cli.cmd_run(_run_args(out)) == 0
    assert calls == [
        {"page_id": "612471195588500", "newest": False},
        {"page_id": "612471195588500", "newest": True},
    ]
    text = capsys.readouterr().out
    assert "If none of their ads has run 30+ days" in text  # quoted up front
    assert "reading their newest ads instead" in text
    raw = json.loads((out / "ads.raw.json").read_text())
    assert raw["fallback_from"] == "longest" and raw["read_mode"] == "newest"
    assert raw["credits_spent"] == 2 and (out / "winners.json").exists()


def test_run_does_not_fall_back_when_newest_was_asked_for(run_env):
    tmp, calls = run_env
    cli.cmd_run(_run_args(tmp / "o", newest=True))
    assert [c["newest"] for c in calls] == [True]


def test_max_credits_caps_the_whole_run_and_prints_the_exact_retry(run_env, capsys):
    tmp, calls = run_env
    out = tmp / "capped"
    assert cli.cmd_run(_run_args(out, max_credits=1)) == 0
    assert [c["newest"] for c in calls] == [False]  # the second read never started
    text = capsys.readouterr().out
    assert "past --max-credits 1" in text
    assert "ad-spy-kit run 612471195588500 --newest --max-ads 30 --max-credits 1 --out" in text
    assert str(out) in text and "--yes" in text


def test_max_credits_below_the_first_read_spends_nothing(run_env):
    tmp, calls = run_env
    with pytest.raises(KitError) as e:
        cli.cmd_run(_run_args(tmp / "x", query="Burrow", max_credits=1))
    assert e.value.code == "run_over_cap" and calls == []


def test_run_parser_takes_max_credits():
    args = cli.build_parser().parse_args(["run", "Burrow", "--max-credits", "3"])
    assert args.max_credits == 3


# ---- winners CLI prints the hidden ads ------------------------------------------------------


def test_winners_command_lists_hidden_ads(tmp_path, capsys):
    ads = [ad(1, var=4, group_id="a"), ad(2, headline="Black Friday 20% off", group_id="b")]
    ads += [ad(10 + i, group_id=f"n{i}") for i in range(9)]
    raw = {"ads": ads, "total_available": len(ads), "pulled_at": "2026-11-05T12:00:00Z"}
    (tmp_path / "ads.raw.json").write_text(json.dumps(raw))
    cli.cmd_winners(argparse.Namespace(run_dir=tmp_path))
    text = capsys.readouterr().out
    assert "not on the board" in text and "'Plain'" in text


def test_ingest_dates_saved_replies_today(tmp_path):
    src = ROOT / "tests" / "data" / "stealads_prod_search_ads.md"
    shutil.copy(src, tmp_path / "search_ads.static.json")
    cli.cmd_ingest(argparse.Namespace(run_dir=tmp_path, import_cap_hit=False, no_images=True))
    pulled = json.loads((tmp_path / "ads.raw.json").read_text())["pulled_at"]
    assert not pulled.startswith("2026-10-28")


def test_run_stops_when_no_ads_came_back_at_all(run_env, monkeypatch, capsys):
    tmp, calls = run_env

    def empty_pull(comp, *, newest=False, **kw):
        calls.append({"page_id": comp["page_id"], "newest": newest})
        return {
            "competitor_id": comp["page_id"],
            "pulled_at": "2026-11-09T12:00:00Z",
            "source": "scrapecreators",
            "collect_mode": "full",
            "total_available": 0,
            "import_cap_hit": False,
            "read_mode": "longest",
            "credits_spent": 1,
            "dropped_too_new": 0,
            "skipped": [],
            "ads": [],
        }

    monkeypatch.setattr(sc_client, "pull_via_scrapecreators", empty_pull)
    out = tmp / "empty"
    assert cli.cmd_run(_run_args(out)) == cli.EXIT_GATE
    assert calls == [{"page_id": "612471195588500", "newest": False}]  # no second read
    text = capsys.readouterr().out
    assert "No live ads came back" in text and "--country" in text
    assert "reading their newest ads instead" not in text
    assert not (out / "winners.json").exists()


def test_run_quote_keeps_the_country_in_the_go_ahead_command(run_env, capsys):
    tmp, _ = run_env
    args = _run_args(tmp / "gb", country="GB", yes=False)
    assert cli.cmd_run(args) == 0
    text = capsys.readouterr().out
    assert "--country GB" in text
