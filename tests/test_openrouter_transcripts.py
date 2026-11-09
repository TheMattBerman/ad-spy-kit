"""Opt-in OpenRouter transcripts. Every HTTP call here is a mock; conftest blocks the rest."""

import base64
import json
from pathlib import Path

import httpx
import pytest

from ad_spy_kit import cli, sc_client
from ad_spy_kit.hooks import resolve_hooks
from ad_spy_kit.sl_adapter import map_scrapecreators_ad
from ad_spy_kit.transcribe import (
    DEFAULT_MODEL,
    build_request,
    current_mode,
    parse_reply,
    read_settings,
    save_mode,
    settings_path,
)
from ad_spy_kit.transcripts import fetch_transcripts, quote, transcript_targets

FAKE_KEY = "sk-or-test-NOT-A-REAL-KEY-42"
GARBLED = "As this face because isn't just like a January reset, I absolutely love it."


def _reply(doc: dict, fenced: bool = False) -> dict:
    text = json.dumps(doc)
    return {"choices": [{"message": {"content": f"```json\n{text}\n```" if fenced else text}}]}


class FakeOpenRouter:
    def __init__(self, replies: dict[str, dict | Exception]):
        self.replies, self.bodies = replies, []

    def __call__(self, body: dict, key: str) -> dict:
        assert key == FAKE_KEY
        self.bodies.append(body)
        url = body["messages"][0]["content"][1]["video_url"]["url"]
        got = self.replies[base64.b64decode(url.split(",", 1)[1]).decode()]
        if isinstance(got, Exception):
            raise got
        return got


class FakeSC:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def facebook_ad_transcript(self, ad_id, **_kw):
        self.calls.append(ad_id)
        return {"transcript": self.answers.get(ad_id, ""), "transcript_available": True}


def _on(monkeypatch, key=True):
    monkeypatch.setenv("AD_SPY_TRANSCRIBE", "openrouter")
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return current_mode()


def _run(tmp_path: Path, videos: dict[str, bytes | None]) -> Path:
    run = tmp_path / "run"
    (run / "media").mkdir(parents=True)
    ads = []
    for i, (ad_id, data) in enumerate(videos.items()):
        ads.append(
            resolve_hooks(
                {
                    "ad_id": ad_id,
                    "format": "VIDEO",
                    "facebook_ad_id": f"10{i}",
                    "headline": "",
                    "body": f"Caption {ad_id}. More.",
                    "cta": "",
                }
            )
        )
        if data is not None:
            (run / "media" / f"{ad_id}.mp4").write_bytes(data)
    (run / "ads.raw.json").write_text(json.dumps({"ads": ads}))
    (run / "winners.json").write_text(json.dumps({"winners": [{"ad_id": a} for a in videos]}))
    return run


def _ads(run: Path) -> dict:
    return {a["ad_id"]: a for a in json.loads((run / "ads.raw.json").read_text())["ads"]}


# --- toggle -----------------------------------------------------------------------------


def test_scrapecreators_is_the_default():
    m = current_mode()
    assert (m.requested, m.effective, m.origin, m.model) == (
        "scrapecreators",
        "scrapecreators",
        "default",
        "google/gemini-3.8-flash",
    )


def test_on_without_a_key_falls_back_with_a_clear_message(monkeypatch):
    m = _on(monkeypatch, key=False)
    assert (m.requested, m.effective) == ("openrouter", "scrapecreators")
    assert "OPENROUTER_API_KEY is not set" in m.note and "ScrapeCreators" in m.note


def test_on_with_a_key(monkeypatch):
    m = _on(monkeypatch)
    assert m.effective == "openrouter" and m.key_present and FAKE_KEY not in m.note


def test_unknown_value_is_ignored(monkeypatch):
    monkeypatch.setenv("AD_SPY_TRANSCRIBE", "whisperzzz")
    assert current_mode().effective == "scrapecreators"


def test_saved_setting_turns_it_on_and_env_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    save_mode("openrouter", "openai/gpt-audio-mini")
    m = current_mode()
    assert (m.effective, m.origin, m.model, m.audio_only) == (
        "openrouter",
        "settings",
        "openai/gpt-audio-mini",
        True,
    )
    monkeypatch.setenv("AD_SPY_TRANSCRIBE", "scrapecreators")
    assert current_mode().effective == "scrapecreators"


def test_settings_file_never_holds_a_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    path = save_mode("openrouter")
    assert FAKE_KEY not in path.read_text()
    assert set(read_settings(path)) == {"AD_SPY_TRANSCRIBE"}


def test_cli_toggle_on_off_and_status_never_print_the_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    assert cli.main(["transcribe-mode", "on"]) == 0
    assert read_settings(settings_path())["AD_SPY_TRANSCRIBE"] == "openrouter"
    out = capsys.readouterr().out
    assert "transcripts: openrouter" in out and "OPENROUTER_API_KEY: set" in out
    assert FAKE_KEY not in out
    assert cli.main(["transcribe-mode", "off"]) == 0
    assert "transcripts: scrapecreators" in capsys.readouterr().out


# --- request / reply --------------------------------------------------------------------


def test_video_request_is_one_base64_data_url():
    body = build_request(DEFAULT_MODEL, video=b"MP4")
    part = body["messages"][0]["content"][1]
    assert body["model"] == "google/gemini-3.8-flash" and body["temperature"] == 0
    assert part["video_url"]["url"] == "data:video/mp4;base64," + base64.b64encode(b"MP4").decode()


def test_audio_request_uses_input_audio():
    part = build_request("openai/gpt-audio-mini", audio=b"MP3")["messages"][0]["content"][1]
    assert part["type"] == "input_audio" and part["input_audio"]["format"] == "mp3"


def test_parse_reply_handles_fences_and_lists():
    got = parse_reply(
        _reply(
            {
                "transcript": " Hi there. ",
                "onscreen_text": ["BIG", "small"],
                "onscreen_hook": "BIG",
            },
            True,
        )
    )
    assert got == {"transcript": "Hi there.", "onscreen_text": "BIG\nsmall", "onscreen_hook": "BIG"}
    with pytest.raises(ValueError):
        parse_reply({"choices": [{"message": {"content": "Sorry, I can't."}}]})


# --- the run ----------------------------------------------------------------------------


def test_quote_names_paid_openrouter_calls(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one", "v2": b"two"})
    ads = json.loads((run / "ads.raw.json").read_text())
    targets = transcript_targets(ads, json.loads((run / "winners.json").read_text()), mode)
    assert quote(targets, mode=mode).startswith(
        "2 videos on the board to transcribe: 2 paid OpenRouter calls on google/gemini-3.8-flash"
    )


def test_openrouter_fills_speech_and_screen_and_tags_the_source(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one"})
    fake = FakeOpenRouter(
        {
            "one": _reply(
                {
                    "transcript": "I quit coffee. Here's why.",
                    "onscreen_text": ["QUIT COFFEE"],
                    "onscreen_hook": "QUIT COFFEE",
                }
            )
        }
    )
    doc = fetch_transcripts(run, mode=mode, post=fake, client=FakeSC({}))
    assert doc["source"] == "openrouter" and doc["model"] == DEFAULT_MODEL
    ad = _ads(run)["v1"]
    assert (ad["hook_source"], ad["spoken_hook"]) == ("spoken", "I quit coffee.")
    assert ad["transcript_source"] == "openrouter:google/gemini-3.8-flash"
    assert ad["onscreen_hook"] == "QUIT COFFEE"
    saved = (run / "transcripts.json").read_text()
    assert FAKE_KEY not in saved and FAKE_KEY not in json.dumps(fake.bodies)


def test_garbled_openrouter_transcript_falls_back_to_its_screen_text(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one"})
    fake = FakeOpenRouter({"one": _reply({"transcript": GARBLED, "onscreen_hook": "Get 20% off"})})
    fetch_transcripts(run, mode=mode, post=fake, client=FakeSC({}))
    ad = _ads(run)["v1"]
    assert ad["spoken_hook_rejected"] and ad["hook_source"] == "onscreen"
    assert ad["onscreen_hook"] == "Get 20% off"


def test_garbled_with_no_screen_text_falls_back_to_caption(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one"})
    fake = FakeOpenRouter({"one": _reply({"transcript": GARBLED})})
    fetch_transcripts(run, mode=mode, post=fake, client=FakeSC({}))
    assert _ads(run)["v1"]["hook_source"] == "copy"


def test_an_agent_screen_read_wins_over_the_model(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one"})
    raw = json.loads((run / "ads.raw.json").read_text())
    raw["ads"][0]["onscreen_hook"] = "Agent read"
    (run / "ads.raw.json").write_text(json.dumps(raw))
    fake = FakeOpenRouter({"one": _reply({"transcript": "", "onscreen_hook": "Model read"})})
    fetch_transcripts(run, mode=mode, post=fake, client=FakeSC({}))
    assert _ads(run)["v1"]["onscreen_hook"] == "Agent read"


def test_failed_or_missing_videos_fall_back_to_scrapecreators(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    run = _run(tmp_path, {"v1": b"one", "v2": None})  # v2 has no video file
    fake = FakeOpenRouter({"one": RuntimeError(f"502 from upstream, key {FAKE_KEY}")})
    sc = FakeSC({"100": "Spoken one.", "101": "Spoken two."})
    doc = fetch_transcripts(run, mode=mode, post=fake, client=sc)
    assert sc.calls == ["100", "101"]
    assert {i["source"] for i in doc["items"]} == {"scrapecreators"}
    ads = _ads(run)
    assert ads["v1"]["transcript_source"] == "scrapecreators"
    assert ads["v2"]["spoken_hook"] == "Spoken two."


def test_failure_with_no_scrapecreators_key_keeps_a_redacted_error(monkeypatch, tmp_path):
    mode = _on(monkeypatch)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no ./.env to load a key from
    run = _run(tmp_path, {"v1": b"one"})
    fake = FakeOpenRouter({"one": RuntimeError(f"401 bad key {FAKE_KEY}")})
    doc = fetch_transcripts(run, mode=mode, post=fake)
    (item,) = doc["items"]
    assert "401" in item["error"] and FAKE_KEY not in item["error"]
    assert _ads(run)["v1"]["hook_source"] == "copy"


def test_scrapecreators_mode_never_calls_openrouter(tmp_path):
    run = _run(tmp_path, {"v1": b"one"})

    def boom(*_a):
        raise AssertionError("OpenRouter called in ScrapeCreators mode")

    fetch_transcripts(run, post=boom, client=FakeSC({"100": "Hello there."}))
    assert _ads(run)["v1"]["transcript_source"] == "scrapecreators"


def test_the_real_http_path_is_blocked_in_tests():
    with pytest.raises(httpx.TransportError, match="blocked"):
        httpx.post("https://openrouter.ai/api/v1/chat/completions")


# --- pull: video files only when opted in, never the URL ---------------------------------


def _sc_rows():
    snap = {
        "display_format": "VIDEO",
        "videos": [
            {
                "video_preview_image_url": "https://x.example-fbcdn.net/p.jpg",
                "video_sd_url": "https://x.example-fbcdn.net/v.mp4",
            }
        ],
    }
    return [
        {"ad_archive_id": "old", "start_date": "2026-01-01", "snapshot": snap},
        {"ad_archive_id": "new", "start_date": "2099-01-01", "snapshot": snap},
    ]


def _fake_img(url, stem):
    p = stem.with_suffix(".jpg")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"img")
    return p, "h"


@pytest.mark.parametrize("on", [True, False])
def test_pull_saves_winner_floor_videos_only_when_opted_in(tmp_path, on):
    ads = [map_scrapecreators_ad(r) for r in _sc_rows()]
    assert all(a.get("video_url") for a in ads)
    got = []
    sc_client.cache_media(
        ads,
        tmp_path,
        downloader=_fake_img,
        fetch_videos=on,
        video_downloader=lambda url, dest: got.append(dest.name),
    )
    assert got == (["old.mp4"] if on else [])
    assert "fbcdn" not in json.dumps(ads)
