"""Gate A6: a lane that counts who says something is counted across every source."""

import json
from pathlib import Path

import pytest

from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.validate_run import Report, check_lanes, is_mention_claim

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "fixtures" / "live" / "spacegoods"
A01 = "8873b3b7-6fb2-4e18-b436-442268ff1477"
A03 = "27ba1684-9218-4a9d-9aee-d50003d1badb"
TERMS = ["money-back guarantee", "money back", "full refund", "refund", "guarantee"]


def _docs(gap: dict) -> dict:
    ads_raw = build_ads_raw_from_fixture(LIVE)
    return {
        "ads.raw": ads_raw,
        "winners": score_winners(ads_raw["ads"]),
        "analysis": {"gaps": [{"evidence_ad_ids": [A03], "counter_angle": "x", **gap}]},
    }


def _a6(gap: dict) -> list[str]:
    rep = Report()
    check_lanes(_docs(gap), rep)
    return [e for e in rep.errors if e.startswith("A6")]


GOOD = {
    "gap": "2 of these ads mention the 60-day guarantee, none leads with it",
    "mentions": {
        "terms": TERMS,
        "ad_ids": [A01, A03],
        "leads": [],
        "evidence": [
            {"ad_id": A01, "source": "spoken", "quote": "60-day money-back guarantee"},
            {"ad_id": A03, "source": "spoken", "quote": "60-day money-back guarantee"},
            {"ad_id": A03, "source": "copy", "quote": "full refund if nothing shifts"},
        ],
    },
}


def _with(**over) -> dict:
    return {**GOOD, "mentions": {**GOOD["mentions"], **over}}


def test_the_spacegoods_guarantee_lane_passes():
    assert _a6(GOOD) == []
    shipped = json.loads((LIVE / "analysis.json").read_text())["gaps"][2]
    assert shipped["gap"] == GOOD["gap"]
    assert _a6(shipped) == []


def test_the_old_caption_only_lane_cannot_ship_without_mentions():
    errors = _a6({"gap": "Only 1 winner puts the refund in its copy"})
    assert errors and "no `mentions`" in errors[0]


def test_a_caption_only_count_is_caught():
    errors = _a6(
        {
            "gap": "Only 1 winner mentions the refund",
            "mentions": {
                "terms": TERMS,
                "ad_ids": [A03],
                "evidence": [{"ad_id": A03, "source": "copy", "quote": "full refund"}],
            },
        }
    )
    assert any("every source says" in e for e in errors)
    assert any("says 1 but 2" in e for e in errors)
    assert any("no evidence for" in e and "(said)" in e for e in errors)


def test_evidence_must_be_verbatim_in_its_source():
    bad = _with(
        evidence=[
            *GOOD["mentions"]["evidence"][:2],
            {"ad_id": A03, "source": "spoken", "quote": "full refund if nothing shifts"},
        ]
    )
    errors = _a6(bad)
    assert any("not a verbatim said quote" in e for e in errors)
    assert any("no evidence for" in e and "(caption)" in e for e in errors)


def test_leads_is_checked_against_the_opening_lines():
    errors = _a6(_with(leads=[A03]))
    assert errors and "opening lines say []" in errors[0]


def test_a_zero_count_lane_is_checked_too():
    lane = {
        "gap": "No winner says 58% off",
        "mentions": {"terms": ["58%"], "ad_ids": [], "evidence": []},
    }
    errors = _a6(lane)
    assert any("every source says" in e for e in errors)


@pytest.mark.parametrize(
    ("text", "claim"),
    [
        ("No winner names Black Friday", True),
        ("Only 1 winner puts the refund in its copy", True),
        ("2 winners mention the 60-day guarantee; none leads with it", True),
        ("No winner frames Foldbrook as a holiday gift", False),
        ("No winner shows a visible before and after", False),
        ("No winner puts Fizzwell at a holiday table or party", False),
        ("Most ads share one caption", False),
    ],
)
def test_which_lanes_are_mention_claims(text, claim):
    assert is_mention_claim(text) is claim
