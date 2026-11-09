"""Creative cards keep the ad's real shape: frame from pixels, else the format default."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

from ad_spy_kit.aspect import card_frame, css_ratio, image_size, is_video, nearest_frame
from ad_spy_kit.fixtures import fixture_names

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "artifacts" / "screenshots"


@pytest.mark.parametrize(
    ("size", "frame"),
    [
        ((540, 960), "9:16"),
        ((480, 848), "9:16"),  # off by a few pixels still snaps to 9:16
        ((1080, 1920), "9:16"),
        ((600, 750), "4:5"),
        ((1080, 1350), "4:5"),
        ((1080, 1080), "1:1"),
        ((1200, 628), "16:9"),
        ((1920, 1080), "16:9"),
    ],
)
def test_frame_comes_from_the_pixels(size, frame):
    assert nearest_frame(*size) == frame
    assert card_frame(size, video=True) == frame
    assert card_frame(size, video=False) == frame


@pytest.mark.parametrize("size", [None, (0, 0), (0, 500)])
def test_defaults_without_dimensions(size):
    assert card_frame(size, video=True) == "9:16"
    assert card_frame(size, video=False) == "4:5"


def test_video_detection():
    assert is_video("VIDEO")
    assert is_video("IMAGE", "video_preview")
    assert not is_video("IMAGE")
    assert not is_video("CAROUSEL", None)
    assert not is_video(None)


def test_image_size_reads_headers(tmp_path):
    p = tmp_path / "a.jpg"
    Image.new("RGB", (540, 960)).save(p)
    assert image_size(p) == (540, 960)
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    assert image_size(bad) is None
    assert image_size(tmp_path / "missing.jpg") is None
    assert image_size(None) is None


def test_css_ratio():
    assert css_ratio("9:16") == "9 / 16"
    assert css_ratio("4:5") == "4 / 5"


@pytest.mark.parametrize("name", fixture_names())
def test_board_cards_use_real_frames_and_never_crop(name):
    html = (SHOTS / name / "board.html").read_text()
    thumbs = re.findall(r'<div class="thumb f-(\w+)( vid)?" style="aspect-ratio:([\d /]+)">', html)
    assert len(thumbs) >= 6  # wall + winners slice
    for frame, _vid, ratio in thumbs:
        assert css_ratio(frame.replace("x", ":")) == ratio
    assert "background-size:cover" not in html
    css = (ROOT / "templates" / "board" / "war-room-tokens.css").read_text()
    assert re.search(r"\.thumb img \{[^}]*object-fit: contain", css)


def test_live_video_thumbs_are_vertical_with_a_play_badge():
    html = (SHOTS / "live/spacegoods" / "board.html").read_text()
    wall = html.split('<div class="ads">', 1)[1].split('<div class="col col-mid">', 1)[0]
    cards = re.findall(r'<div class="thumb f-(\w+)( vid)?"(.*?)</div>', wall, re.S)
    assert len(cards) == 6
    assert all(frame == "9x16" for frame, _, _ in cards)  # recorded media is 540x960
    for _frame, vid, body in cards:
        assert ('class="play"' in body) == bool(vid)
    assert any(vid for _, vid, _ in cards)
