"""Spoken hooks for the free route: ScrapeCreators transcripts for winner videos only.

`ad-spy-kit transcripts <run_dir>` prints a credit quote and stops; `--yes` fetches.
Each call is GET /v1/facebook/adLibrary/ad/transcript with cache_max_age=7d and no long
transcription: 1 credit per video up to 2 minutes, 0 when cached or when there is no
transcript. Results are saved to `<run_dir>/transcripts.json` and written into
ads.raw.json (`transcript`, then `spoken_hook` / `hook_source` via ad_spy_kit/hooks.py).

Opt-in: with AD_SPY_TRANSCRIBE=openrouter and OPENROUTER_API_KEY set, each winner video goes
to OpenRouter instead (ad_spy_kit/transcribe.py), which also returns on-screen text. An ad it
can't do (no video, API error) falls back to ScrapeCreators in the same run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ad_spy_kit.hooks import resolve_hooks
from ad_spy_kit.transcribe import Mode, current_mode, openrouter_key, transcribe_ad

DEFAULT_CACHE_MAX_AGE = "7d"
CREDITS_PER_VIDEO = 1


def transcript_targets(
    ads_raw: dict[str, Any],
    winners: dict[str, Any],
    mode: Mode | None = None,
    media_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Winner videos with no transcript yet, in winner order.

    ScrapeCreators needs the Meta ad id; OpenRouter needs the video (`video_url` from the
    pull, or a cached media/<ad_id>.mp4), so either is enough in that mode.

    An ad whose transcript came back garbled is not re-quoted: a refetch returns the same
    cached text, so it would spend credits for nothing.
    """
    ads = {a["ad_id"]: a for a in ads_raw.get("ads", [])}
    out = []
    for w in winners.get("winners", []):
        ad = ads.get(w["ad_id"])
        if not ad or str(ad.get("format") or "").upper() != "VIDEO":
            continue
        # StealAds' spoken opener counts, even when garbled: the same audio comes back.
        if ad.get("spoken_hook") or ad.get("transcript") or ad.get("spoken_opener"):
            continue
        reachable = ad.get("facebook_ad_id")
        if mode and mode.effective == "openrouter":
            local = media_dir and (media_dir / f"{ad['ad_id']}.mp4").is_file()
            reachable = reachable or ad.get("video_url") or local
        if not reachable:
            continue
        out.append(ad)
    return out


def quote(
    targets: list[dict[str, Any]], *, allow_long: bool = False, mode: Mode | None = None
) -> str:
    n = len(targets)
    if not n:
        return "No video on the board needs a transcript. 0 credits."
    if mode and mode.effective == "openrouter":
        return (
            f"{n} video{'s' if n != 1 else ''} on the board to transcribe: {n} paid OpenRouter "
            f"call{'s' if n != 1 else ''} on {mode.model} (billed by OpenRouter per token; "
            "speech + on-screen text). Go?"
        )
    cost = (
        "10 ScrapeCreators credits per started minute each (long transcription on)"
        if allow_long
        else f"up to {n * CREDITS_PER_VIDEO} ScrapeCreators credit{'s' if n != 1 else ''} "
        f"({CREDITS_PER_VIDEO} per video up to 2 min; cached in the last 7 days or no "
        "transcript = 0)"
    )
    return f"{n} video{'s' if n != 1 else ''} on the board to transcribe: {cost}. Go?"


def apply_transcripts(ads_raw: dict[str, Any], doc: dict[str, Any]) -> int:
    """Write saved transcripts into ads.raw ads (by ad_id). Returns how many landed."""
    by_id = {str(i.get("ad_id")): i for i in doc.get("items", []) if i.get("transcript")}
    landed = 0
    for ad in ads_raw.get("ads", []):
        item = by_id.get(str(ad["ad_id"]))
        if item:
            ad["transcript"] = item["transcript"]
            ad["spoken_hook"] = None  # re-derive from the transcript
            src = item.get("source") or doc.get("source") or "scrapecreators"
            ad["transcript_source"] = f"{src}:{item['model']}" if item.get("model") else src
            # An agent's own read of the screen (onscreen.json) wins over the model's.
            if item.get("onscreen_hook") and not ad.get("onscreen_hook"):
                ad["onscreen_hook"] = item["onscreen_hook"]
                ad["onscreen_text"] = ad.get("onscreen_text") or item.get("onscreen_text")
                ad["onscreen_source"] = ad["transcript_source"]
            elif item.get("onscreen_text") and not ad.get("onscreen_text"):
                ad["onscreen_text"] = item["onscreen_text"]
            landed += 1
        resolve_hooks(ad)
    return landed


def _openrouter_items(
    run_dir: Path, targets: list[dict[str, Any]], mode: Mode, post: Any, download: Any
) -> list[dict[str, Any]]:
    key = openrouter_key()
    kw = {k: v for k, v in (("post", post), ("download", download)) if v is not None}
    return [transcribe_ad(ad, run_dir / "media", mode, key=key, **kw) for ad in targets]


def fetch_transcripts(
    run_dir: Path,
    *,
    client: Any = None,
    cache_max_age: str = DEFAULT_CACHE_MAX_AGE,
    allow_long: bool = False,
    mode: Mode | None = None,
    post: Any = None,
    download: Any = None,
) -> dict[str, Any]:
    """Fetch, save transcripts.json, update ads.raw.json. Only call after a yes on the quote."""
    ads_raw = json.loads((run_dir / "ads.raw.json").read_text())
    winners = json.loads((run_dir / "winners.json").read_text())
    mode = mode or current_mode()
    targets = transcript_targets(ads_raw, winners, mode, run_dir / "media")
    items: list[dict[str, Any]] = []
    if mode.effective == "openrouter":
        items = _openrouter_items(run_dir, targets, mode, post, download)
        failed = {i["ad_id"] for i in items if i.get("error")}
        targets = [a for a in targets if a["ad_id"] in failed and a.get("facebook_ad_id")]
        if targets and client is None:
            from ad_spy_kit.errors import KitError
            from ad_spy_kit.sc_client import _client

            try:
                client = _client()
            except KitError:
                targets = []  # no ScrapeCreators key either: keep the OpenRouter errors
        if targets:
            fell = {a["ad_id"] for a in targets}
            items = [i for i in items if i["ad_id"] not in fell]
    elif client is None:
        from ad_spy_kit.sc_client import _client

        client = _client()
    from cie.scrapecreators_client import ScrapeCreatorsClientError as CieErr

    for ad in targets:
        try:
            got = client.facebook_ad_transcript(
                ad["facebook_ad_id"],
                cache_max_age=cache_max_age,
                allow_long_transcription=allow_long,
            )
        except CieErr as e:
            items.append({"ad_id": ad["ad_id"], "transcript": "", "error": str(e)})
            continue
        items.append(
            {
                "ad_id": ad["ad_id"],
                **({"source": "scrapecreators"} if mode.effective == "openrouter" else {}),
                "facebook_ad_id": ad["facebook_ad_id"],
                "transcript": got.get("transcript") or "",
                "transcript_available": bool(got.get("transcript_available")),
                "cached": bool(got.get("cached")),
                **{
                    k: got[k]
                    for k in ("cached_at", "credits_charged", "duration_seconds")
                    if got.get(k) is not None
                },
            }
        )
    recorded = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    if mode.effective == "openrouter":
        doc: dict[str, Any] = {
            "recorded_at": recorded,
            "source": "openrouter",
            "model": mode.model,
            "endpoint": "/api/v1/chat/completions",
            "items": items,
        }
    else:
        doc = {
            "recorded_at": recorded,
            "source": "scrapecreators",
            "endpoint": "/v1/facebook/adLibrary/ad/transcript",
            "cache_max_age": cache_max_age,
            "allow_long_transcription": allow_long,
            "items": items,
        }
    charged = [i["credits_charged"] for i in items if i.get("credits_charged") is not None]
    if charged:
        doc["credits_charged"] = sum(charged)
    (run_dir / "transcripts.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    apply_transcripts(ads_raw, doc)
    (run_dir / "ads.raw.json").write_text(json.dumps(ads_raw, indent=2, ensure_ascii=False))
    return doc
