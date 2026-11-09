"""The blocking gate must pass real fixture runs and catch each failure it claims to catch."""

import json
import shutil
from pathlib import Path

import pytest

from ad_spy_kit.fixtures import fixture_names
from ad_spy_kit.validate_run import validate_run

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = fixture_names()


def _rendered(name: str) -> Path:
    run = ROOT / "artifacts" / "screenshots" / name
    if not (run / "board.html").exists():
        pytest.skip("run `ad-spy-kit replay-all` first")
    return run


@pytest.fixture
def ridge_run(tmp_path):
    dst = tmp_path / "foldbrook"
    shutil.copytree(_rendered("foldbrook"), dst)
    return dst


def _edit(run: Path, name: str, fn) -> None:
    path = run / f"{name}.json"
    doc = json.loads(path.read_text())
    fn(doc)
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize("name", FIXTURES)
def test_committed_fixture_runs_pass_the_gate(name):
    report = validate_run(_rendered(name), corrections=[])
    assert report.ok, report.errors


def test_non_verbatim_evidence_blocks(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["offer_map"][0].update(evidence="50% off everything"))
    assert any(
        e.startswith("A3 offer_map[0]") for e in validate_run(ridge_run, corrections=[]).errors
    )


def test_citing_a_non_winner_blocks(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["gaps"][0].update(evidence_ad_ids=["ad-8"]))
    errors = validate_run(ridge_run, corrections=[]).errors
    assert any("not a winner" in e for e in errors)


def test_uncited_number_in_headline_blocks(ridge_run):
    _edit(
        ridge_run,
        "analysis",
        lambda d: d["headline"].update(top="Foldbrook spent $93,000 on BFCM."),
    )
    errors = validate_run(ridge_run, corrections=[]).errors
    assert any(e.startswith("A4 uncited number 93") for e in errors)


def test_hedging_copy_blocks(ridge_run):
    _edit(
        ridge_run, "analysis", lambda d: d["headline"].update(bottom="They might be missing gifts.")
    )
    assert any(
        e.startswith("E1 hedging 'might'") for e in validate_run(ridge_run, corrections=[]).errors
    )


def test_hidden_score_in_winners_blocks(ridge_run):
    _edit(ridge_run, "winners", lambda d: d["winners"][0].update(effectiveness_score=91))
    assert any(e.startswith("B1 winners") for e in validate_run(ridge_run, corrections=[]).errors)


def test_out_of_order_bangers_blocks(ridge_run):
    _edit(ridge_run, "winners", lambda d: d["winners"].reverse())
    assert any(e.startswith("B4") for e in validate_run(ridge_run, corrections=[]).errors)


def test_bad_band_blocks(ridge_run):
    _edit(ridge_run, "winners", lambda d: d["winners"][0].update(strength_label="legend"))
    assert any(e.startswith("B3") for e in validate_run(ridge_run, corrections=[]).errors)


@pytest.mark.parametrize(
    ("swap", "code"),
    [
        (("</footer>", "<span>spend unknown</span></footer>"), "E2"),
        (("</footer>", "<span>Steal the structure, don't copy the ad</span></footer>"), "E2"),
        (("</footer>", "<span>Spend is unknown</span></footer>"), "E2"),
        (("</footer>", "<span>ad-1</span></footer>"), "C7"),
        (("https://stealads.ai", "https://example.com"), "C2"),
        (("<footer", '<img src="https://scontent.fbcdn.net/x.jpg"><footer'), "C4"),
        (("based on ", "gap score 8 · based on "), "B1"),
    ],
)
def test_board_html_regressions_block(ridge_run, swap, code):
    html = ridge_run / "board.html"
    before = html.read_text()
    assert swap[0] in before, f"anchor {swap[0]!r} is gone from the board"
    html.write_text(before.replace(*swap))
    assert any(e.startswith(code) for e in validate_run(ridge_run, corrections=[]).errors)


def test_wrong_png_size_blocks(ridge_run):
    from PIL import Image

    Image.new("RGB", (1200, 750)).save(ridge_run / "board.png")
    assert any(
        "board.png is (1200, 750)" in e for e in validate_run(ridge_run, corrections=[]).errors
    )


def test_layout_overflow_blocks(ridge_run):
    _edit(ridge_run, "render", lambda d: d.update(text_overflow=["below the fold: Hooks"]))
    assert any(e.startswith("C5 layout") for e in validate_run(ridge_run, corrections=[]).errors)


def test_captured_correction_is_enforced(ridge_run):
    rule = {
        "id": "900",
        "rule": "must_not_contain",
        "pattern": r"stocking stuffers",
        "reason": "test correction",
    }
    errors = validate_run(ridge_run, corrections=[rule]).errors
    assert errors == ["K900 correction violated (test correction): /stocking stuffers/"]


def test_correction_also_covers_the_swipe_file(ridge_run):
    md = ridge_run / "teardown.md"
    md.write_text(md.read_text() + "\nGap score: 8/10\n")
    errors = validate_run(ridge_run).errors
    assert any(e.startswith("K001") for e in errors)


def test_repo_corrections_pass_on_fixtures():
    for name in FIXTURES:
        assert validate_run(_rendered(name)).ok


def test_gap_without_evidence_fails_schema(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["gaps"][0].update(evidence_ad_ids=[]))
    assert any(e.startswith("A1 analysis") for e in validate_run(ridge_run, corrections=[]).errors)


def test_unknown_puppet_string_fails_schema(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["hooks"][0].update(puppet_string="greed"))
    assert any(e.startswith("A1 analysis") for e in validate_run(ridge_run, corrections=[]).errors)


def test_fixture_board_is_labelled_synthetic(tmp_path):
    from ad_spy_kit.pipeline import replay_fixture

    run_dir = replay_fixture("foldbrook", output_dir=tmp_path / "foldbrook")
    html = (run_dir / "board.html").read_text()
    assert "MADE-UP SAMPLE BRAND" in html
    md = (run_dir / "teardown.md").read_text()
    assert "made-up sample brand" in md and "stealads.ai" in md
    assert "spend unknown" not in md.lower() and "don't copy" not in md.lower()
    assert "/10" not in md and "gap_score" not in md


def test_invented_format_slug_blocks(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["formats"][0].update(format="ugc-video"))
    assert any(
        e.startswith("A5 formats[0]") for e in validate_run(ridge_run, corrections=[]).errors
    )


@pytest.mark.parametrize("phrase", ["spend unknown", "Don't copy the ad", "do not copy this"])
def test_banned_hedge_copy_in_teardown_blocks(ridge_run, phrase):
    md = ridge_run / "teardown.md"
    md.write_text(md.read_text() + f"\n{phrase}\n")
    errors = validate_run(ridge_run, corrections=[]).errors
    assert any(e.startswith("E2") and "teardown.md" in e for e in errors)


def test_banned_hedge_copy_in_analysis_blocks(ridge_run):
    _edit(ridge_run, "analysis", lambda d: d["steal_this"][0].update(dont_copy="Don't copy it"))
    assert any(e.startswith("E1") for e in validate_run(ridge_run, corrections=[]).errors)


def test_saved_correction_bans_hedge_copy(ridge_run):
    from ad_spy_kit.validate_run import load_corrections

    html = ridge_run / "board.html"
    html.write_text(html.read_text().replace("</footer>", "<span>spend unknown</span></footer>"))
    errors = validate_run(ridge_run, corrections=load_corrections()).errors
    assert any(e.startswith("K002") for e in errors)


def test_counter_must_beat_a_winner(ridge_run):
    _edit(ridge_run, "counters", lambda d: d["counters"][0].update(beats_ad_id="not-a-winner"))
    assert any(e.startswith("A2 counters[0]") for e in validate_run(ridge_run).errors)


def test_counter_brief_fields_are_hedge_checked(ridge_run):
    _edit(
        ridge_run,
        "counters",
        lambda d: d["counters"][0].update(why_it_beats="This might work better, probably."),
    )
    assert any(e.startswith("E1") for e in validate_run(ridge_run, corrections=[]).errors)
