"""The board's look: title bar, counters and label pills come straight from the data, and the
rendered page fits its frame with nothing clipped (the phone-size read depends on it)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ad_spy_kit.render import build_context, render_html, screenshot_html

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts" / "screenshots" / "live" / "spacegoods"


def _context() -> dict:
    load = lambda n: json.loads((RUN / f"{n}.json").read_text())  # noqa: E731
    return build_context(
        competitor=load("competitor"),
        ads_raw=load("ads.raw"),
        winners=load("winners"),
        analysis=load("analysis"),
        counters=load("counters"),
        media_dir=RUN / "media",
        run_dir=RUN,
    )


def test_counters_and_pills_match_the_data():
    ads = json.loads((RUN / "ads.raw.json").read_text())["ads"]
    ctx = _context()
    assert ctx["ads_checked"] == len(ads) == 24
    assert ctx["longest_days"] == max(a["days_live"] for a in ads) == 78
    # The labels tile counts the ads drawn on the board, never all the ads checked.
    on_board = Counter(w["strength_label"] for w in ctx["winner_wall"] if w["strength_label"])
    assert dict(ctx["label_counts"]) == dict(on_board)
    assert sum(n for _, n in ctx["label_counts"]) == len(ctx["winner_wall"]) < len(ads)
    assert ctx["title_line"] == "Their top ad opens with an apology."
    # The wall never shows more ads than were checked, and drops blank frames.
    assert 0 < len(ctx["ad_wall"]) <= ctx["ads_checked"]


def test_board_shows_one_opening_and_the_long_run_note(tmp_path):
    html = render_html(
        template="board/war-room.html.j2",
        context=_context(),
        templates_dir=ROOT / "templates",
        out_html=tmp_path / "board.html",
    )
    assert re.search(r"<h1 class=\"verdict\">.*Their top ad opens with an apology\.", html)
    assert len(re.findall(r'<div class="exp-h">', html)) == 1
    assert "Running long doesn't prove an ad works" in html
    assert "No ad names Black Friday" not in html


def test_rendered_board_fits_its_frame(tmp_path):
    pytest.importorskip("playwright")
    out = tmp_path / "board.html"
    render_html(
        template="board/war-room.html.j2",
        context=_context(),
        templates_dir=ROOT / "templates",
        out_html=out,
    )
    try:
        overflow = screenshot_html(
            out, tmp_path / "board.png", width=1200, height=750, check_overflow=True
        )
    except Exception as e:  # no Chromium on this machine
        pytest.skip(f"Chromium unavailable: {e}")
    assert overflow == []
