"""The one strength label rule (ad_spy_kit/labels.py): boundaries, pass-through, every route."""

import pytest

from ad_spy_kit import labels
from ad_spy_kit.labels import TOP_LABEL, label_from_run, normalize_label, strength_label
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.sl_adapter import map_scrapecreators_ad, map_stealads_ad


def live(days, versions=1):
    return {"days_live": days, "variation_count": versions, "is_active": True}


def stopped(days, versions=1):
    return {"days_live": days, "variation_count": versions, "is_active": False}


def test_constants_mirror_stealads_3343():
    assert TOP_LABEL == "winner"
    assert (labels.LIVE_TOP_MIN_DAYS, labels.LIVE_TOP_FAST_DAYS, labels.LIVE_TOP_FAST_VERSIONS) == (
        120,
        60,
        3,
    )
    assert (labels.SOLID_MIN_DAYS, labels.SOLID_FAST_DAYS, labels.SOLID_FAST_VERSIONS) == (
        30,
        14,
        3,
    )
    assert (labels.STOPPED_TOP_DAYS_WITH_VERSIONS, labels.STOPPED_TOP_DAYS) == (365, 540)


def test_legend_states_the_bars_in_plain_words():
    assert labels.LABEL_MEANINGS == {
        "winner": "live 120+ days, or 60+ days with 3+ versions",
        "solid": "30+ days, or 14+ days with 3+ versions",
        "testing": "live under 30 days",
    }


@pytest.mark.parametrize(
    ("ad", "want"),
    [
        (live(0), "testing"),
        (live(13, 5), "testing"),  # 3+ versions only counts from 14 days
        (live(14, 2), "testing"),
        (live(14, 3), "solid"),  # exception: 14+ days with 3+ versions
        (live(29), "testing"),
        (live(30), "solid"),
        (live(59, 3), "solid"),
        (live(60, 2), "solid"),
        (live(60, 3), TOP_LABEL),  # 60+ days with 3+ versions
        (live(119), "solid"),
        (live(120), TOP_LABEL),  # 120+ days
    ],
)
def test_live_boundaries(ad, want):
    assert label_from_run(ad) == want


@pytest.mark.parametrize(
    ("ad", "want"),
    [
        (stopped(5), None),  # not running, so not "testing"
        (stopped(29), None),
        (stopped(30), "solid"),
        (stopped(14, 3), "solid"),
        (stopped(200, 3), "solid"),  # a stopped ad doesn't get the live winner bar
        (stopped(364, 3), "solid"),
        (stopped(365, 3), TOP_LABEL),  # 365+ days with 3+ versions
        (stopped(365, 2), "solid"),
        (stopped(539), "solid"),
        (stopped(540), TOP_LABEL),  # 540+ days, any versions
    ],
)
def test_stopped_boundaries(ad, want):
    assert label_from_run(ad) == want


def test_live_counts_more_than_stopped():
    assert label_from_run(live(130)) == TOP_LABEL
    assert label_from_run(stopped(130)) == "solid"
    assert label_from_run(live(70, 3)) == TOP_LABEL
    assert label_from_run(stopped(70, 3)) == "solid"


def test_unknown_run_gets_no_label():
    assert label_from_run({"variation_count": 3, "is_active": True}) is None
    assert label_from_run({"days_live": 90, "variation_count": 3}) is None
    assert label_from_run({**live(90, 3), "run_length_unknown": True}) is None


@pytest.mark.parametrize(
    ("field", "value", "want"),
    [
        ("banger_band", "banger", TOP_LABEL),
        ("banger_band", "winner", TOP_LABEL),
        ("strength_label", "winner", TOP_LABEL),
        ("strength_label", "BANGER", TOP_LABEL),
        ("strengthLabel", "solid", "solid"),
        ("banger_band", "testing", "testing"),
        ("strength_label", None, None),  # unanalyzed in StealAds: no label
        ("strength_label", "legendary", None),  # unknown value: no label, no crash
    ],
)
def test_stealads_label_passes_through(field, value, want):
    raw = {"id": "a1", "days_live": 3, "variation_count": 9, "still_running": True, field: value}
    ad = map_stealads_ad(raw)
    assert ad["label_source"] == "stealads"
    assert strength_label(ad) == want  # never recomputed from run length


def test_stealads_row_without_label_is_unlabeled():
    ad = map_stealads_ad({"id": "a1", "days_live": 90, "variation_count": 9, "is_active": True})
    assert strength_label(ad) is None


def test_scrapecreators_rows_get_computed_labels_on_the_wall():
    rows = [
        {"ad_archive_id": "1", "start_date": "2020-01-01", "is_active": True, "collation_count": 4},
        {"ad_archive_id": "2", "start_date": "2020-01-01", "is_active": True, "collation_count": 1},
        {
            "ad_archive_id": "3",
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "is_active": False,
            "collation_count": 1,
        },
        {"ad_archive_id": "4", "is_active": True, "collation_count": 5},  # no start date
    ]
    ads = [map_scrapecreators_ad(r) for r in rows]
    # 1: live for years, 4 versions; 2: live for years; 3: stopped after 4 days; 4: no start.
    assert [a["strength_label"] for a in ads] == [TOP_LABEL, TOP_LABEL, None, None]
    winners = score_winners(ads)
    assert winners["rank_source"] == "fallback_runlength"
    shown = {w["ad_id"]: w["strength_label"] for w in winners["winners"]}
    assert shown["1"] == TOP_LABEL and shown["2"] == TOP_LABEL


def test_normalize_label_accepts_both_top_names():
    assert normalize_label(" Winner ") == normalize_label("banger") == TOP_LABEL
