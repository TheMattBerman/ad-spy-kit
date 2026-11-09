"""Rendered outputs (board, carousel slices, newsletter/og crops) must never show a numeric score.

Board, slices, newsletter and og PNGs are all screenshots of the same board.html, so asserting on
its visible text covers every rendered surface. teardown.md is checked too.
"""

import json
import re
from pathlib import Path

import pytest

from ad_spy_kit.fixtures import fixture_names
from ad_spy_kit.render import _opening, build_context, render_html
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = fixture_names()

SCORE_WORD = re.compile(r"score", re.IGNORECASE)
NUMERIC_SCORE = re.compile(r"score\D{0,12}[-+]?\d", re.IGNORECASE)


def _visible_text(html: str) -> str:
    html = re.sub(r"data:[^'\")\s]+", "", html)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


def _render_fixture(name: str, tmp_path: Path) -> str:
    fixture_dir = ROOT / "fixtures" / name
    ads_raw = build_ads_raw_from_fixture(fixture_dir)
    winners = score_winners(ads_raw.get("ads", []))
    analysis = json.loads((fixture_dir / "analysis.json").read_text())
    counters = json.loads((fixture_dir / "counters.json").read_text())
    ctx = build_context(
        competitor=json.loads((fixture_dir / "competitor.json").read_text()),
        ads_raw=ads_raw,
        winners=winners,
        analysis=analysis,
        counters=counters,
        media_dir=fixture_dir / "media",
    )
    return render_html(
        template="board/war-room.html.j2",
        context=ctx,
        templates_dir=ROOT / "templates",
        out_html=tmp_path / name / "board.html",
    )


@pytest.mark.parametrize("name", FIXTURES)
def test_board_html_has_no_score_text(name, tmp_path):
    html = _render_fixture(name, tmp_path)
    text = _visible_text(html)
    assert not NUMERIC_SCORE.search(text), NUMERIC_SCORE.search(text).group(0)
    assert not SCORE_WORD.search(text), text[max(0, SCORE_WORD.search(text).start() - 60) :][:120]
    assert "gap_score" not in html


@pytest.mark.parametrize("name", FIXTURES)
def test_open_lane_shows_evidence_not_score(name, tmp_path):
    html = _render_fixture(name, tmp_path)
    analysis = json.loads((ROOT / "fixtures" / name / "analysis.json").read_text())
    # The evidence line rides on the opening slice (too small for the board itself).
    metas = re.findall(r'<div class="slice-sub slice-meta">(.*?)</div>', html)
    counters = json.loads((ROOT / "fixtures" / name / "counters.json").read_text())
    # The board shows one opening: the gap the first counter-ad answers (teardown.md lists all).
    gaps = _opening(analysis, counters)
    assert len(metas) == len(gaps)
    for meta, gap in zip(metas, gaps, strict=True):
        ids = gap["evidence_ad_ids"]
        assert meta.startswith("based on ") and meta.count("#") == len(ids)
        for ad_id in ids:
            assert ad_id not in meta and ad_id[:6] not in meta
        assert re.findall(r"#\d{2}", meta), meta  # cited by winner rank
        residue = re.sub(r"#\d{2}", "", meta.replace(str(len(ids)), "", 1))
        assert str(gap.get("gap_score")) not in residue


@pytest.mark.parametrize("name", FIXTURES)
def test_committed_artifacts_have_no_score_text(name):
    run_dir = ROOT / "artifacts" / "screenshots" / name
    if not (run_dir / "board.html").exists():
        pytest.skip("artifacts not rendered")
    text = _visible_text((run_dir / "board.html").read_text())
    assert not SCORE_WORD.search(text)
    teardown = run_dir / "teardown.md"
    if teardown.exists():
        assert not SCORE_WORD.search(teardown.read_text())


HEDGE_COPY = re.compile(r"spend\s*(is\s*)?unknown|don[\u2019']?t\s+copy|do\s+not\s+copy", re.I)


@pytest.mark.parametrize("name", FIXTURES)
def test_committed_artifacts_have_no_hedge_copy(name):
    run_dir = ROOT / "artifacts" / "screenshots" / name
    if not (run_dir / "board.html").exists():
        pytest.skip("artifacts not rendered")
    assert not HEDGE_COPY.search(_visible_text((run_dir / "board.html").read_text()))
    assert not HEDGE_COPY.search((run_dir / "teardown.md").read_text())
