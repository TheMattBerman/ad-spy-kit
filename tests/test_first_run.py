"""First run: no Chromium gives a plain message with the fix, and the shipped board survives."""

import pytest
from playwright.sync_api import Error as PlaywrightError

from ad_spy_kit import render
from ad_spy_kit.cli import main
from ad_spy_kit.errors import KitError
from ad_spy_kit.pipeline import replay_fixture


class _NoChromium:
    class chromium:  # noqa: N801
        @staticmethod
        def launch():
            raise PlaywrightError("BrowserType.launch: Executable doesn't exist at /x/chrome")


def test_missing_chromium_is_a_plain_kit_error():
    with pytest.raises(KitError) as e:
        render.launch_chromium(_NoChromium())
    msg = e.value.render()
    assert "(Chromium) isn't installed" in msg
    assert "playwright install chromium" in msg and "uv sync --project" in msg
    assert "Traceback" not in msg


def test_failed_replay_keeps_the_existing_board(tmp_path, monkeypatch, capsys):
    out = tmp_path / "sample"
    out.mkdir()
    (out / "board.png").write_bytes(b"shipped board")
    real = render.launch_chromium
    monkeypatch.setattr(render, "launch_chromium", lambda p: real(_NoChromium()))
    code = main(["replay", "--sample", "foldbrook", "--output", str(out)])
    assert code == 2
    assert "playwright install chromium" in capsys.readouterr().err
    assert (out / "board.png").read_bytes() == b"shipped board"
    assert [p.name for p in tmp_path.iterdir()] == ["sample"]  # no scratch folder left


def test_unknown_sample_says_which_exist():
    with pytest.raises(KitError) as e:
        replay_fixture("nope")
    assert "dewbar" in e.value.render()
