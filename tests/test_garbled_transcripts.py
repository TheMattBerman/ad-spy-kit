"""A garbled transcript opening is not quoted as the spoken hook; the ad falls back."""

import json
from pathlib import Path

import pytest

from ad_spy_kit.hooks import garbled_reason, resolve_hooks
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.transcripts import transcript_targets
from ad_spy_kit.validate_run import Report, check_citations

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "fixtures" / "live" / "spacegoods"
GARBLED = "As this face because isn't just like a January reset, I absolutely love it."


@pytest.mark.parametrize(
    ("hook", "why"),
    [
        (GARBLED, "missing subject"),
        ("[Music] Okay so this changed everything.", "speech-to-text tag"),
        ("the the best coffee I have had.", "starts mid-sentence"),
        ("I tried tried everything for focus.", "repeated word"),
        ("♪ ♪", "speech-to-text tag"),
        ("... ...", "no words"),
    ],
)
def test_garbled_openings_are_caught(hook, why):
    assert why in (garbled_reason(hook) or "")


@pytest.mark.parametrize(
    "hook",
    [
        "Apology to everyone who bought Rainbow Dust from our videos.",
        "Want sharper focus, take lion's mane.",
        "Right now, you can get a double discount on Rainbow Dust.",
        "My husband replaced his morning coffee with Rainbow Dust and lost a stone.",
        "I've carried the same wallet for six years.",
        "Okay, two jars in and my skin barrier finally stopped flaking.",
        "Stop scrolling.",
        "Hi.",
        "That is why I switched, because it is cheaper.",
    ],
)
def test_clean_openings_pass(hook):
    assert garbled_reason(hook) is None


def test_low_source_confidence_rejects_the_hook():
    assert "confidence" in garbled_reason("Clean words here.", 0.4)
    assert garbled_reason("Clean words here.", 0.9) is None
    assert garbled_reason("Clean words here.", "n/a") is None


def _ad(**over) -> dict:
    base = {"ad_id": "a1", "format": "VIDEO", "headline": "", "body": "Caption. More.", "cta": ""}
    return resolve_hooks({**base, **over})


def test_fallback_is_onscreen_then_caption():
    ad = _ad(transcript=GARBLED + " Rest.", onscreen_text="BIG HEADLINE")
    assert (ad["hook_source"], ad["spoken_hook"]) == ("onscreen", None)
    assert ad["spoken_hook_rejected"].startswith("missing subject")
    ad = _ad(transcript=GARBLED)
    assert (ad["hook_source"], ad["copy_hook"]) == ("copy", "Caption.")
    ad = _ad(transcript="Clean start. Rest.", transcript_confidence=0.3)
    assert ad["hook_source"] == "copy"


def test_a_source_supplied_spoken_hook_is_checked_too():
    ad = _ad(spoken_hook="[inaudible] get yours", transcript=None)
    assert ad["hook_source"] == "copy" and ad["spoken_hook_rejected"]


def _a3(ad: dict, hook: dict) -> list[str]:
    rep = Report()
    docs = {
        "ads.raw": {"ads": [ad]},
        "winners": {"winners": [{"ad_id": ad["ad_id"]}]},
        "analysis": {"citations_ok": True, "hooks": [{"ad_id": ad["ad_id"], **hook}]},
    }
    check_citations(docs, rep)
    return [e for e in rep.errors if e.startswith("A3")]


def test_a3_refuses_a_garbled_spoken_quote_and_accepts_the_caption():
    ad = _ad(transcript=GARBLED)
    errors = _a3(ad, {"hook_text": "As this face", "hook_source": "spoken"})
    assert errors and "garbled" in errors[0]
    assert _a3(ad, {"hook_text": "Caption.", "hook_source": "copy"}) == []


def test_a_garbled_transcript_is_not_requoted_for_credits():
    ad = _ad(transcript=GARBLED, facebook_ad_id="123")
    assert transcript_targets({"ads": [ad]}, {"winners": [{"ad_id": "a1"}]}) == []


def test_spacegoods_02_falls_back_to_its_poster_frame_headline():
    ads = {a["ad_id"]: a for a in build_ads_raw_from_fixture(LIVE)["ads"]}
    two = ads["22e33100-8ac2-4f8e-b0a1-f855b4fec499"]
    assert two["spoken_hook_rejected"] and two["hook_source"] == "onscreen"
    assert two["onscreen_hook"] == (
        "@spacegoods is my cheat code for productivity! Get 20% off their starter kit "
        "with my exclusive code: EMILYN"
    )
    clean = [a for a in ads.values() if a.get("transcript") and a["ad_id"] != two["ad_id"]]
    assert len(clean) == 4 and all(a["hook_source"] == "spoken" for a in clean)
    doc = json.loads((LIVE / "onscreen.json").read_text())
    assert {i["role"] for i in doc["items"]} == {"creative", "poster-frame"}
