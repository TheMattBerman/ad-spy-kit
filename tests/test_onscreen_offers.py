"""On-screen hooks read by the session agent, and offers quoted from what the ad says or shows."""

import json
from pathlib import Path

from ad_spy_kit import cli
from ad_spy_kit.hooks import resolve_hooks
from ad_spy_kit.onscreen import apply_onscreen, check_item, onscreen_targets
from ad_spy_kit.render import build_context
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.validate_run import Report, check_citations

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "fixtures" / "live" / "spacegoods"
C19 = "c19faa28-a1c8-4d0f-954e-8ddaa90e852a"
C19_HOOK = "Ordered it bro went for coffe flavour cant wait to get stuck in"


def _ad(**over) -> dict:
    base = {"ad_id": "a1", "format": "IMAGE", "headline": "", "body": "Caption.", "cta": ""}
    return resolve_hooks({**base, **over})


def _a3(ad: dict, **analysis) -> list[str]:
    rep = Report()
    docs = {
        "ads.raw": {"ads": [ad]},
        "winners": {"winners": [{"ad_id": ad["ad_id"]}]},
        "analysis": {"citations_ok": True, **analysis},
    }
    check_citations(docs, rep)
    return [e for e in rep.errors if e.startswith("A3")]


# --- the agent's own read of the image ------------------------------------------------


def _run(tmp_path) -> Path:
    run = tmp_path / "run"
    (run / "media").mkdir(parents=True)
    ads = [
        _ad(ad_id="i1"),
        _ad(ad_id="v1", format="VIDEO"),
        _ad(ad_id="v2", format="VIDEO", transcript="Said first. More."),
        _ad(ad_id="i2", onscreen_hook="ALREADY READ"),
        _ad(ad_id="i3"),  # no cached file
    ]
    for a in ads[:4]:
        (run / "media" / f"{a['ad_id']}.jpg").write_bytes(b"x")
    (run / "ads.raw.json").write_text(json.dumps({"ads": ads}))
    winners = {"winners": [{"ad_id": a["ad_id"]} for a in ads]}
    (run / "winners.json").write_text(json.dumps(winners))
    return run


def test_targets_are_winner_images_and_untranscribed_video_posters(tmp_path):
    run = _run(tmp_path)
    ads_raw = json.loads((run / "ads.raw.json").read_text())
    winners = json.loads((run / "winners.json").read_text())
    got = [(t["ad_id"], t["role"]) for t in onscreen_targets(ads_raw, winners, run / "media")]
    assert got == [("i1", "creative"), ("v1", "poster-frame")]


def test_apply_makes_the_recorded_read_the_hook(tmp_path):
    run = _run(tmp_path)
    doc = {
        "items": [
            {"ad_id": "i1", "onscreen_text": "BIG LINE\nsmall", "onscreen_hook": "BIG LINE"},
            {"ad_id": "v1", "onscreen_text": "Other", "onscreen_hook": "Not in the text"},
        ]
    }
    (run / "onscreen.json").write_text(json.dumps(doc))
    assert cli.main(["onscreen", str(run), "--apply"]) == 1  # v1's read is refused
    ads = {a["ad_id"]: a for a in json.loads((run / "ads.raw.json").read_text())["ads"]}
    assert (ads["i1"]["hook_source"], ads["i1"]["onscreen_hook"]) == ("onscreen", "BIG LINE")
    assert ads["v1"]["hook_source"] == "copy"


def test_a_spoken_hook_still_beats_a_poster_frame():
    ad = _ad(format="VIDEO", transcript="Hi there. Rest.")
    apply_onscreen({"ads": [ad]}, {"items": [{"ad_id": "a1", "onscreen_hook": "POSTER"}]})
    assert (ad["hook_source"], ad["onscreen_hook"]) == ("spoken", "POSTER")


def test_check_item_needs_a_hook_inside_the_text():
    assert check_item({"onscreen_hook": "A", "onscreen_text": "A\nB"}) is None
    assert check_item({"onscreen_hook": "", "onscreen_text": "A"}) == "no onscreen_hook"
    assert check_item({"onscreen_hook": "C", "onscreen_text": "A"})


def test_a3_checks_an_onscreen_hook_against_the_stored_onscreen_hook():
    ad = _ad(onscreen_text="HEADLINE\nsmall print", onscreen_hook="HEADLINE")
    ok = {"ad_id": "a1", "hook_text": "HEADLINE", "hook_source": "onscreen"}
    small = {**ok, "hook_text": "small print"}
    assert _a3(ad, hooks=[ok]) == []
    assert _a3(ad, hooks=[small])


# --- offers from any source -----------------------------------------------------------


def _offer(evidence: str, source: str | None = None) -> dict:
    row = {"ad_id": "a1", "offer_type": "pct_off", "evidence": evidence}
    return {**row, "evidence_source": source} if source else row


def test_offer_evidence_is_checked_in_its_claimed_source():
    ad = _ad(
        transcript="Right now you get 58% off plus free gifts.",
        onscreen_text="Stone 20% discount",
        onscreen_hook="Stone 20% discount",
    )
    assert _a3(ad, offer_map=[_offer("58% off plus free gifts", "spoken")]) == []
    assert _a3(ad, offer_map=[_offer("Stone 20% discount", "onscreen")]) == []
    assert _a3(ad, offer_map=[_offer("Caption.")]) == []  # no source = caption
    wrong = _a3(ad, offer_map=[_offer("58% off", "copy")])
    assert wrong and "copy" in wrong[0]
    assert _a3(ad, offer_map=[_offer("58% off", "onscreen")])
    assert "not in" in _a3(ad, offer_map=[_offer("x", "audio")])[0]


def test_numbers_said_in_a_video_may_print_in_a_gap():
    from ad_spy_kit.validate_run import allowed_numbers

    ads_raw = {"ads": [_ad(transcript="Up to 58% off."), _ad(ad_id="a2", onscreen_text="20%")]}
    nums = allowed_numbers(ads_raw, {"winners": []})
    assert {"58", "20"} <= nums


# --- live/spacegoods ------------------------------------------------------------------


def _ctx() -> dict:
    ads_raw = build_ads_raw_from_fixture(LIVE)
    return build_context(
        competitor=json.loads((LIVE / "competitor.json").read_text()),
        ads_raw=ads_raw,
        winners=score_winners(ads_raw["ads"]),
        analysis=json.loads((LIVE / "analysis.json").read_text()),
        counters={"counters": []},
        media_dir=LIVE / "media",
    )


def test_spacegoods_image_winner_uses_its_onscreen_hook():
    doc = json.loads((LIVE / "onscreen.json").read_text())
    assert doc["source"] == "agent-vision"
    card = next(w for w in _ctx()["winner_wall"] if w["ad_id"] == C19)
    assert (card["hook_tag"], card["hook_text"]) == ("on screen", C19_HOOK)


def test_spacegoods_offer_ladder_comes_from_the_videos():
    ctx = _ctx()
    assert ctx["deepest_offer"]["discount_depth"] == "58%"
    assert ctx["deepest_offer"]["evidence_tag"] == "said"
    tags = {o["evidence_tag"] for o in ctx["offer_map"]}
    assert tags == {"said", "on screen", "caption"}
