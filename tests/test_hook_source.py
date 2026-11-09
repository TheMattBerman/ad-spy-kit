"""Hook source: spoken > on-screen > caption, from either route, checked by gate A3."""

import json
import shutil
from pathlib import Path

import pytest

from ad_spy_kit import cli
from ad_spy_kit.hooks import first_sentence, resolve_hooks
from ad_spy_kit.render import build_context
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.sl_adapter import map_scrapecreators_ad, map_stealads_ad
from ad_spy_kit.transcripts import fetch_transcripts, quote, transcript_targets
from ad_spy_kit.validate_run import Report, check_citations, validate_run

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "fixtures" / "live" / "spacegoods"
TRANSCRIPT = "Okay, two jars in and my skin barrier finally stopped flaking. Now it's one."


def _row(ad_id: str, *, hook: bool = True) -> dict:
    """A real recorded row; hook=False gives the pre-#3163 shape (no `hook` object)."""
    rows = json.loads((LIVE / "search_ads.video.json").read_text())["response"]["ads"]
    row = dict(next(r for r in rows if r["id"] == ad_id))
    if not hook:
        row.pop("hook", None)
    return row


def _ad(**over) -> dict:
    base = {"ad_id": "a1", "headline": "", "body": "Caption line. More copy.", "cta": ""}
    return resolve_hooks({**base, **over})


# --- priority -------------------------------------------------------------------------


def test_first_sentence_is_verbatim():
    assert first_sentence("  I was tired.  Then this.") == "I was tired."
    assert first_sentence("No stop at all") == "No stop at all"
    assert first_sentence("") == ""


@pytest.mark.parametrize(
    ("over", "source", "text"),
    [
        ({}, "copy", "Caption line."),
        ({"onscreen_text": "WANT SHARPER FOCUS?\nsmall print"}, "onscreen", "WANT SHARPER FOCUS?"),
        ({"transcript": "Hi. Rest.", "onscreen_text": "OVERLAY"}, "spoken", "Hi."),
        ({"spoken_hook": "Listen up", "transcript": None}, "spoken", "Listen up"),
    ],
)
def test_priority_is_spoken_then_onscreen_then_caption(over, source, text):
    ad = _ad(**over)
    assert ad["hook_source"] == source
    assert ad[f"{source}_hook"] == text
    assert ad["copy_hook"] == "Caption line."


# --- StealAds adapter -----------------------------------------------------------------


def test_pre_hook_spacegoods_row_has_only_a_caption_hook():
    ad = map_stealads_ad(_row("8873b3b7-6fb2-4e18-b436-442268ff1477", hook=False))
    assert ad["hook_source"] == "copy"
    assert ad["copy_hook"] == "Reread the same email three times."
    assert ad["spoken_hook"] is None and ad["onscreen_hook"] is None
    # The Meta ad id rides in the mirrored image filename.
    assert ad["facebook_ad_id"] == "1513163003271861"


def test_adapter_reads_tracked_get_ad_onscreen_headline():
    row = _row("8873b3b7-6fb2-4e18-b436-442268ff1477", hook=False)
    row["analysis_summary"] = {"visual": {"headline": "Yes, it tastes"}}
    ad = map_stealads_ad(row)
    assert (ad["hook_source"], ad["onscreen_hook"]) == ("onscreen", "Yes, it tastes")


@pytest.mark.parametrize(
    "field",
    [
        {"transcript": TRANSCRIPT},
        {"video_transcript": TRANSCRIPT},
        {"analysis_summary": {"audio": {"transcript": TRANSCRIPT}}},
        {
            "transcript": [
                {"text": "Okay, two jars in and my skin barrier finally stopped"},
                "flaking.",
            ]
        },
    ],
)
def test_adapter_reads_future_transcript_fields(field):
    row = _row("8873b3b7-6fb2-4e18-b436-442268ff1477", hook=False)
    ad = map_stealads_ad({**row, **field})
    assert ad["hook_source"] == "spoken"
    assert ad["spoken_hook"] == "Okay, two jars in and my skin barrier finally stopped flaking."


def test_adapter_reads_a_spoken_hook_alias_and_explicit_fb_id():
    row = {**_row("8873b3b7-6fb2-4e18-b436-442268ff1477"), "verbal_hook": "Stop scrolling."}
    row["facebook_ad_id"] = "999"
    ad = map_stealads_ad(row)
    assert ad["spoken_hook"] == "Stop scrolling." and ad["facebook_ad_id"] == "999"


def test_scrapecreators_row_keeps_its_ad_id_and_transcript():
    raw = {
        "ad_archive_id": "1513163003271861",
        "transcript": TRANSCRIPT,
        "snapshot": {"body": {"text": "Caption."}, "display_format": "VIDEO"},
    }
    ad = map_scrapecreators_ad(raw)
    assert ad["facebook_ad_id"] == "1513163003271861"
    assert ad["hook_source"] == "spoken"


# --- free-route transcripts (mocked; no real ScrapeCreators calls) ---------------------


class FakeClient:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def facebook_ad_transcript(self, ad_id, *, cache_max_age, allow_long_transcription):
        self.calls.append((ad_id, cache_max_age, allow_long_transcription))
        return {"transcript": self.answers.get(ad_id, ""), "transcript_available": True}


def _run(tmp_path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    ads = [
        {"ad_id": "v1", "format": "VIDEO", "facebook_ad_id": "111", "body": "Cap one."},
        {"ad_id": "v2", "format": "VIDEO", "facebook_ad_id": "222", "body": "Cap two."},
        {"ad_id": "i1", "format": "IMAGE", "facebook_ad_id": "333", "body": "Static."},
        {"ad_id": "v9", "format": "VIDEO", "facebook_ad_id": "999", "body": "Loser."},
    ]
    for a in ads:
        a.update(headline="", cta="")
        resolve_hooks(a)
    (run / "ads.raw.json").write_text(json.dumps({"ads": ads}))
    winners = {"winners": [{"ad_id": i} for i in ("v1", "i1", "v2")]}
    (run / "winners.json").write_text(json.dumps(winners))
    return run


def test_only_winner_videos_are_quoted(tmp_path):
    run = _run(tmp_path)
    ads_raw = json.loads((run / "ads.raw.json").read_text())
    winners = json.loads((run / "winners.json").read_text())
    targets = transcript_targets(ads_raw, winners)
    assert [a["ad_id"] for a in targets] == ["v1", "v2"]
    assert quote(targets).startswith("2 videos on the board to transcribe: up to 2 ScrapeCreators")
    assert quote([]) == "No video on the board needs a transcript. 0 credits."


def test_fetch_uses_7d_cache_and_no_long_transcription(tmp_path):
    run = _run(tmp_path)
    client = FakeClient({"111": "I quit coffee. Here's why."})
    doc = fetch_transcripts(run, client=client)
    assert client.calls == [("111", "7d", False), ("222", "7d", False)]
    assert json.loads((run / "transcripts.json").read_text())["items"] == doc["items"]
    ads = {a["ad_id"]: a for a in json.loads((run / "ads.raw.json").read_text())["ads"]}
    assert (ads["v1"]["hook_source"], ads["v1"]["spoken_hook"]) == ("spoken", "I quit coffee.")
    assert ads["v2"]["hook_source"] == "copy"  # empty transcript → caption stays


def test_cli_without_yes_spends_nothing(tmp_path, monkeypatch, capsys):
    run = _run(tmp_path)

    def boom():
        raise AssertionError("no client may be built without --yes")

    monkeypatch.setattr("ad_spy_kit.sc_client._client", boom)
    assert cli.main(["transcripts", str(run)]) == 0
    out = capsys.readouterr().out
    assert "up to 2 ScrapeCreators credits" in out and "--yes" in out
    assert not (run / "transcripts.json").exists()


def test_cie_client_calls_the_ad_transcript_endpoint(monkeypatch):
    from cie.scrapecreators_client import ScrapeCreatorsClient

    seen = {}

    def fake_request(self, path, params=None):
        seen.update(path=path, params=params)
        return {
            "success": True,
            "cached": True,
            "data": {"transcript": " Hi. ", "transcript_available": True},
        }

    monkeypatch.setattr(ScrapeCreatorsClient, "request", fake_request)
    got = ScrapeCreatorsClient(api_key="test").facebook_ad_transcript("123")
    assert seen == {
        "path": "/v1/facebook/adLibrary/ad/transcript",
        "params": {"id": "123", "cache_max_age": "7d"},
    }
    assert got["transcript"] == "Hi." and got["cached"] is True
    assert got["credits_charged"] is None


def test_dewbar_fixture_transcripts_land_on_the_ad():
    ads = {a["ad_id"]: a for a in build_ads_raw_from_fixture(ROOT / "fixtures" / "dewbar")["ads"]}
    assert ads["ad-4"]["hook_source"] == "spoken"
    assert ads["ad-4"]["spoken_hook"].startswith("Okay, two jars in")
    assert ads["ad-1"]["hook_source"] == "copy"  # transcript_available: false


# --- gate A3 --------------------------------------------------------------------------


def _docs(ad: dict, hook: dict) -> dict:
    return {
        "ads.raw": {"ads": [ad]},
        "winners": {"winners": [{"ad_id": ad["ad_id"]}]},
        "analysis": {"citations_ok": True, "hooks": [{"ad_id": ad["ad_id"], **hook}]},
    }


def _a3(ad: dict, hook: dict) -> list[str]:
    rep = Report()
    check_citations(_docs(ad, hook), rep)
    return [e for e in rep.errors if e.startswith("A3")]


def test_a3_accepts_a_verbatim_spoken_hook():
    ad = _ad(transcript=TRANSCRIPT)
    assert _a3(ad, {"hook_text": "Okay, two jars in", "hook_source": "spoken"}) == []


def test_a3_rejects_a_spoken_hook_not_in_the_transcript():
    ad = _ad(transcript=TRANSCRIPT)
    errors = _a3(ad, {"hook_text": "My barrier healed overnight.", "hook_source": "spoken"})
    assert errors and "transcript" in errors[0]


def test_a3_rejects_a_caption_hook_when_a_spoken_one_exists():
    ad = _ad(transcript=TRANSCRIPT)
    errors = _a3(ad, {"hook_text": "Caption line.", "hook_source": "copy"})
    assert any("uses the caption hook" in e and "said hook" in e for e in errors)


def test_a3_rejects_an_onscreen_claim_with_no_onscreen_text():
    errors = _a3(_ad(), {"hook_text": "Caption line.", "hook_source": "onscreen"})
    assert errors and "on-screen text" in errors[0]


def test_a3_missing_source_means_caption():
    assert _a3(_ad(), {"hook_text": "Caption line."}) == []
    assert _a3(_ad(), {"hook_text": "Never said this."})


# --- board ----------------------------------------------------------------------------


def _ctx(name: str) -> dict:
    fx = ROOT / "fixtures" / name
    ads_raw = build_ads_raw_from_fixture(fx)
    return build_context(
        competitor=json.loads((fx / "competitor.json").read_text()),
        ads_raw=ads_raw,
        winners=score_winners(ads_raw["ads"]),
        analysis=json.loads((fx / "analysis.json").read_text()),
        counters={"counters": []},
        media_dir=fx / "media",
    )


def test_wall_and_hook_rows_carry_source_tags():
    ctx = _ctx("foldbrook")
    tags = {w["display_rank"]: w["hook_tag"] for w in ctx["winner_wall"]}
    assert tags[1] == "said" and tags[2] == "on screen" and tags[3] == "caption"
    assert [h["hook_tag"] for h in ctx["hooks"]] == ["said", "on screen"]


def test_spacegoods_videos_use_the_recorded_spoken_hooks():
    ctx = _ctx("live/spacegoods")
    tags = {w["format"]: set() for w in ctx["winner_wall"]}
    for w in ctx["winner_wall"]:
        tags[w["format"]].add(w["hook_tag"])
    assert tags == {"VIDEO": {"said", "on screen"}, "IMAGE": {"on screen"}}
    # #02's transcript opening is garbled, so its poster frame's headline is the hook.
    two = next(w for w in ctx["winner_wall"] if w["display_rank"] == 2)
    assert two["hook_tag"] == "on screen"
    assert two["hook_text"].startswith("@spacegoods is my cheat code for productivity!")
    top = ctx["winner_wall"][0]
    assert top["hook_text"] == "Apology to everyone who bought Rainbow Dust from our videos."
    doc = json.loads((LIVE / "transcripts.json").read_text())
    assert doc["cache_max_age"] == "7d" and doc["allow_long_transcription"] is False
    assert "api_key" not in json.dumps(doc).lower()


def test_credits_charged_are_summed_into_transcripts_json(tmp_path):
    run = _run(tmp_path)

    class Charging(FakeClient):
        def facebook_ad_transcript(self, ad_id, **kw):
            got = super().facebook_ad_transcript(ad_id, **kw)
            return {**got, "credits_charged": 0 if ad_id == "222" else 1}

    doc = fetch_transcripts(run, client=Charging({"111": "Hi."}))
    assert doc["credits_charged"] == 1


def test_rendered_ridge_board_prints_the_tags(tmp_path):
    run = ROOT / "artifacts" / "screenshots" / "foldbrook"
    if not (run / "board.html").exists():
        pytest.skip("run `ad-spy-kit replay-all` first")
    # The board tags the #1 hook; every hook's tag is in the swipe file.
    assert 'src-spoken">said<' in (run / "board.html").read_text()
    md = (run / "teardown.md").read_text()
    for tag in ("(said)", "(on screen)", "(caption)"):
        assert tag in md
    dst = tmp_path / "foldbrook"
    shutil.copytree(run, dst)
    assert validate_run(dst, corrections=[]).ok
