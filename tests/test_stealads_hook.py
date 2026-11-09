"""StealAds MCP PR #3163 `hook` object, on the re-recorded live Spacegoods rows (no network)."""

import json
from pathlib import Path

from ad_spy_kit.hooks import evidence_text, resolve_hooks
from ad_spy_kit.onscreen import apply_onscreen
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.sl_adapter import infer_format, map_stealads_ad
from ad_spy_kit.transcripts import apply_transcripts, transcript_targets

LIVE = Path(__file__).resolve().parents[1] / "fixtures" / "live" / "spacegoods"
APOLOGY = "8873b3b7-6fb2-4e18-b436-442268ff1477"  # clean spoken opener + 3 overlay lines
EMILY = "22e33100-8ac2-4f8e-b0a1-f855b4fec499"  # opener starts mid-sentence (garbled)
SILENT = "6a8a11e1-ed95-4000-9d79-0bd02400832d"  # no speech, overlay only
STARTER = "52e3c9fa-d518-4f25-80c2-bf0689f5e0ba"  # image; text read off the creative
CAPTION_ONLY = "bdb5666b-ae10-487b-bc74-90af443d59de"  # image; `written` is the headline


def _rows(name="search_ads.json"):
    return {r["id"]: r for r in json.loads((LIVE / name).read_text())["response"]["ads"]}


def test_every_live_row_carries_the_hook_object():
    for name in (
        "search_ads.json",
        "search_ads.video.json",
        "search_ads.static.json",
        "find_bangers.json",
    ):
        for row in _rows(name).values():
            assert set(row["hook"]) == {
                "spoken",
                "on_screen",
                "opening_visual",
                "written",
                "type",
                "source",
            }


def test_spoken_opener_is_the_hook_and_tagged_stealads():
    ad = map_stealads_ad(_rows()[APOLOGY])
    assert ad["hook_source"] == "spoken" and ad["spoken_hook_source"] == "stealads"
    assert ad["spoken_hook"] == "Apology to everyone who bought Rainbow Dust from our videos."
    assert ad["spoken_opener"].startswith(ad["spoken_hook"])
    assert ad["onscreen_hook"] == "Sorry we messed up..." and ad["onscreen_source"] == "stealads"
    assert ad["onscreen_text"].splitlines() == [
        "Sorry we messed up...",
        "Apology to everyone",
        "Rainbow Dust",
    ]
    assert ad["opening_visual"] and ad["hook_type"] == "storytelling"
    assert ad["spoken_hook"] in evidence_text(ad, "spoken")


def test_first_sentence_only_from_a_long_opener():
    row = {**_rows()[APOLOGY]}
    row["hook"] = {**row["hook"], "spoken": "Want sharper focus? Take Lion's Mane. Want more?"}
    assert map_stealads_ad(row)["spoken_hook"] == "Want sharper focus?"


def test_garbled_opener_falls_back_and_says_why():
    ad = map_stealads_ad(_rows()[EMILY])
    assert ad["spoken_hook"] is None and ad["spoken_hook_rejected"] == "starts mid-sentence"
    assert ad["hook_source"] == "copy"  # StealAds has no overlay lines for it


def test_silent_video_uses_its_overlay():
    ad = map_stealads_ad(_rows()[SILENT])
    assert ad["spoken_hook"] is None and ad["spoken_hook_rejected"] is None
    assert ad["hook_source"] == "onscreen" and ad["onscreen_source"] == "stealads"


def test_image_written_text_counts_as_on_screen_only_when_not_the_caption():
    rows = _rows("search_ads.static.json")
    ad = map_stealads_ad({**rows[STARTER], "_format_filter": "static"})
    assert (ad["hook_source"], ad["onscreen_hook"]) == (
        "onscreen",
        "Get your starter pack for just today for just £34!",
    )
    caption = map_stealads_ad({**rows[CAPTION_ONLY], "_format_filter": "static"})
    assert caption["onscreen_hook"] is None and caption["hook_source"] == "copy"


def test_hook_source_decides_format_when_no_filter():
    assert infer_format({"ad_format": "text dominant", "hook": {"source": "video"}}) == "VIDEO"
    assert infer_format({"_format_filter": "static", "hook": {"source": "video"}}) == "IMAGE"


def test_no_transcript_credit_is_quoted_for_ads_with_a_stealads_opener():
    raw = build_ads_raw_from_fixture(LIVE)
    ads = {a["ad_id"]: a for a in raw["ads"]}
    winners = {"winners": [{"ad_id": i} for i in (APOLOGY, EMILY, SILENT)]}
    assert [a["ad_id"] for a in transcript_targets(raw, winners)] == [SILENT]
    assert ads[EMILY]["spoken_opener"]  # garbled, still not re-bought


def test_stealads_opener_beats_a_later_transcript_but_the_transcript_widens_evidence():
    ad = map_stealads_ad(_rows()[APOLOGY])
    doc = {
        "source": "scrapecreators",
        "items": [{"ad_id": APOLOGY, "transcript": "Different first line. 58% off."}],
    }
    apply_transcripts({"ads": [ad]}, doc)
    assert ad["spoken_hook_source"] == "stealads"
    assert ad["spoken_hook"].startswith("Apology")
    assert "58% off" in evidence_text(ad, "spoken")


def test_clean_transcript_rescues_a_garbled_opener():
    ad = map_stealads_ad(_rows()[EMILY])
    apply_transcripts(
        {"ads": [ad]},
        {
            "source": "scrapecreators",
            "items": [{"ad_id": EMILY, "transcript": "Spacegoods is great."}],
        },
    )
    assert (ad["spoken_hook"], ad["spoken_hook_source"]) == (
        "Spacegoods is great.",
        "scrapecreators",
    )


def test_agent_screen_read_keeps_the_stealads_hook_and_adds_its_lines():
    ad = map_stealads_ad(_rows()[APOLOGY])
    apply_onscreen(
        {"ads": [ad]},
        {
            "items": [
                {
                    "ad_id": APOLOGY,
                    "onscreen_hook": "58% OFF",
                    "onscreen_text": "58% OFF\nfree gifts",
                }
            ]
        },
    )
    assert ad["onscreen_hook"] == "Sorry we messed up..." and ad["onscreen_source"] == "stealads"
    assert "free gifts" in ad["onscreen_text"]


def test_agent_read_still_fills_ads_stealads_left_empty():
    ad = map_stealads_ad(_rows()[EMILY])
    apply_onscreen({"ads": [ad]}, {"items": [{"ad_id": EMILY, "onscreen_hook": "CODE EMILYN"}]})
    assert (ad["hook_source"], ad["onscreen_source"]) == ("onscreen", "agent-vision")


def test_resolve_is_idempotent():
    ad = map_stealads_ad(_rows()[APOLOGY])
    before = dict(ad)
    assert resolve_hooks(ad) == before
