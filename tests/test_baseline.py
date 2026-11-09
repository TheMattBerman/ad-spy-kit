from evals.compare_baseline import score_text


def test_baseline_metrics_flag_invented_numbers_and_quotes():
    ads_raw = {"ads": [{"ad_id": "ad-1", "headline": "30% off sets", "body": "Ships free."}]}
    vanilla = 'They are probably spending $40k. ad-1 says "50% off everything".'
    m = score_text(vanilla, ads_raw, {"winners": []})
    assert m["cited_ids"] == 1
    assert m["quotes"] == 1 and m["verbatim_quotes"] == 0
    assert m["uncited_numbers"] >= 1 and m["hedges"] == 1
    kit = score_text('ad-1 "30% off sets"', ads_raw, {"winners": []})
    assert kit == {
        "cited_ids": 1,
        "quotes": 1,
        "verbatim_quotes": 1,
        "uncited_numbers": 0,
        "hedges": 0,
    }


def test_ad_ids_are_not_counted_as_numbers():
    ads_raw = {"ads": [{"ad_id": "ad-5", "headline": "Free shipping", "body": ""}]}
    assert score_text("Free shipping (ad-5)", ads_raw, {"winners": []})["uncited_numbers"] == 0


def test_quotes_count_as_verbatim_from_any_source():
    ads_raw = {
        "ads": [{"ad_id": "v1", "headline": "", "body": "", "transcript": "Said this line."}]
    }
    assert score_text('"Said this line"', ads_raw, {"winners": []})["verbatim_quotes"] == 1


def test_every_fixture_is_compared_including_live_ones():
    from evals.compare_baseline import fixture_names, vanilla_path

    names = fixture_names()
    assert {"foldbrook", "dewbar", "fizzwell", "live/spacegoods"} <= set(names)
    assert vanilla_path("live/spacegoods").name == "live-spacegoods.md"


def test_recorded_vanilla_answers_are_genuine_captures():
    from evals.compare_baseline import fixture_names, vanilla_path

    for name in fixture_names():
        first = vanilla_path(name).read_text().splitlines()[0]
        assert first.startswith("<!-- vanilla capture: ") and "no kit installed" in first


def test_kit_fails_when_vanilla_scores_better():
    from evals.compare_baseline import verdict

    clean = dict(cited_ids=2, quotes=2, verbatim_quotes=2, uncited_numbers=0, hedges=0)
    assert verdict(clean, None) == []
    assert verdict(clean, {**clean, "uncited_numbers": 9}) == []
    worse = {**clean, "verbatim_quotes": 1}
    assert verdict(worse, clean) == ["kit breaks pass criteria 1-2", "vanilla quotes more verbatim"]
