"""Counters ship as briefs; the board names ads by rank; the footer is data + stealads.ai."""

from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
from pathlib import Path

import pytest

from ad_spy_kit.fixtures import fixture_names

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = fixture_names()
SHOTS = ROOT / "artifacts" / "screenshots"


def _board(name: str) -> str:
    return (SHOTS / name / "board.html").read_text()


def _text(fragment: str) -> str:
    fragment = re.sub(r"<style.*?</style>", " ", fragment, flags=re.S)
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def test_no_image_model_route_left_in_repo():
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.split()
    skip = ("cie/", "vendor/", "tests/test_brief_route.py")
    pattern = re.compile(r"replicate|gpt[- ]image|kling|--motion", re.I)
    hits = []
    for rel in files:
        if rel.startswith(skip):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            body = path.read_text()
        except UnicodeDecodeError:
            continue
        hits += [f"{rel}: {m.group(0)}" for m in pattern.finditer(body)]
    assert not hits, hits[:10]
    assert not (ROOT / "ad_spy_kit" / "replicate_client.py").exists()


@pytest.mark.parametrize("name", FIXTURES)
def test_footer_is_data_and_link_only(name):
    board = _board(name)
    footer = re.search(r'<footer class="foot">(.*?)</footer>', board, re.S).group(1)
    assert re.fullmatch(r"data: [^·]+ · stealads\.ai", _text(footer)), _text(footer)
    assert 'href="https://stealads.ai"' in footer
    handles = re.findall(r'<div class="slice-handle">(.*?)</div>', board, re.S)
    assert len(handles) == 5
    for h in handles:
        assert _text(h) == _text(footer)
        assert 'href="https://stealads.ai"' in h


@pytest.mark.parametrize("name", FIXTURES)
def test_no_ad_ids_on_the_board(name):
    text = _text(re.sub(r"data:[^'\")\s]+", "", _board(name)))
    ads = json.loads((SHOTS / name / "ads.raw.json").read_text())["ads"]
    for ad in ads:
        ad_id = str(ad["ad_id"])
        if len(ad_id) < 12:
            assert not re.search(rf"(?<![\w-]){re.escape(ad_id)}(?![\w-])", text), ad_id
        else:
            assert ad_id[:6] not in text, ad_id


@pytest.mark.parametrize("name", FIXTURES)
def test_counter_panel_is_hook_why_and_stealads_cta(name):
    board = _board(name)
    panel = re.search(
        r'<div class="card counter">(.*?)<a class="cad-cta"[^>]*>(.*?)</a>', board, re.S
    )
    assert panel, "counter panel missing"
    counter = json.loads((SHOTS / name / "counters.json").read_text())["counters"][0]
    body = _text(panel.group(1))
    # Board: the hook, then why it's different from theirs. The headline is not repeated as a
    # badge (it duplicated the hook). The full brief is in teardown.md.
    assert _text(html_lib.escape(counter["hook"])) in body
    assert _text(html_lib.escape(counter["why_it_beats"][:50])) in body
    assert "different from #" in board
    assert f'<em class="lab">{html_lib.escape(counter["headline"])}</em>' not in panel.group(1)
    assert _text(html_lib.escape(counter["visual_direction"])) not in body
    assert "First ad free, early access" in panel.group(2)
    assert 'class="cad-cta" href="https://stealads.ai"' in board


@pytest.mark.parametrize("name", FIXTURES)
def test_teardown_lists_every_brief(name):
    md = (SHOTS / name / "teardown.md").read_text()
    for c in json.loads((SHOTS / name / "counters.json").read_text())["counters"]:
        assert f"### {c['headline']}" in md
        assert c["visual_direction"] in md and c["why_it_beats"] in md
    assert (
        "StealAds can turn this brief into a finished ad. Your first one is free "
        "(early access at stealads.ai)."
    ) in md
    assert md.rstrip().splitlines()[-1].startswith("data: ")
