"""Opt-in enhanced transcripts: one OpenRouter call per winner video reads speech + screen.

ScrapeCreators transcripts stay the default. Turn this on with any of:
  AD_SPY_TRANSCRIBE=openrouter                 env or ./.env (wins over the saved setting)
  ./doctor.sh --transcribe on                  saves it, then reports status
  ad-spy-kit transcribe-mode openrouter        saves it to the settings file below
  ./install.sh  (answers y at the prompt)      same settings file
and off with AD_SPY_TRANSCRIBE=scrapecreators / `transcribe-mode scrapecreators`.

It needs OPENROUTER_API_KEY. Without it the kit says so and uses ScrapeCreators. The key is
read from the environment (or ./.env) and never printed, saved or logged.

The settings file holds only the mode and model, never a key:
  ${AD_SPY_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/ad-spy-kit/settings.env}

Model: google/gemini-3.8-flash (video + audio in, checked against OpenRouter's public model
list on 2026-10-29). AD_SPY_TRANSCRIBE_MODEL overrides it; an audio-only model such as
openai/gpt-audio-mini gets the soundtrack only (ffmpeg extracts it), so no on-screen text.

The reply goes through the same gate as a ScrapeCreators transcript: resolve_hooks rejects a
garbled opening and falls back to on-screen, then caption, with the usual source tags.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODES = ("scrapecreators", "openrouter")
DEFAULT_MODE = "scrapecreators"
DEFAULT_MODEL = "google/gemini-3.8-flash"
AUDIO_ONLY_MODELS = ("openai/gpt-audio-mini", "openai/gpt-audio")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KEY_ENV = "OPENROUTER_API_KEY"
MAX_VIDEO_BYTES = 20 * 1024 * 1024

PROMPT = (
    "This is a Meta video ad. Reply with JSON only, no prose:\n"
    '{"transcript": "<every spoken word, verbatim, in order; empty string if no speech>",\n'
    ' "onscreen_text": ["<each distinct line of text shown on screen, verbatim>"],\n'
    ' "onscreen_hook": "<the biggest or first headline text on screen, verbatim, or null>"}\n'
    "Copy words exactly as said or shown. Do not summarize, fix grammar or add words."
)
AUDIO_PROMPT = (
    "Transcribe this ad's audio verbatim. Reply with JSON only: "
    '{"transcript": "<every spoken word, in order; empty string if no speech>"}'
)


def settings_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("AD_SPY_CONFIG"):
        return Path(env["AD_SPY_CONFIG"])
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".config")
    return Path(base) / "ad-spy-kit" / "settings.env"


def read_settings(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.strip().startswith("#"):
                out[k.strip()] = v.strip().strip('"')
    return out


def save_mode(mode: str, model: str | None = None, env: dict[str, str] | None = None) -> Path:
    """Persist the toggle (mode + model only; a key is never written)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    path = settings_path(env)
    cur = read_settings(path)
    cur["AD_SPY_TRANSCRIBE"] = mode
    if model:
        cur["AD_SPY_TRANSCRIBE_MODEL"] = model
    cur = {k: v for k, v in cur.items() if k in ("AD_SPY_TRANSCRIBE", "AD_SPY_TRANSCRIBE_MODEL")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# ad-spy-kit settings (no keys here; OPENROUTER_API_KEY lives in your env)\n"
        + "".join(f"{k}={v}\n" for k, v in cur.items())
    )
    return path


def _dotenv() -> dict[str, str]:
    """./.env (the same file doctor.sh sources); values are never printed."""
    return read_settings(Path.cwd() / ".env")


@dataclass(frozen=True)
class Mode:
    requested: str
    effective: str
    model: str
    origin: str  # env | settings | default
    key_present: bool
    note: str

    @property
    def audio_only(self) -> bool:
        return self.model in AUDIO_ONLY_MODELS


def current_mode(env: dict[str, str] | None = None) -> Mode:
    if env is None:
        env = {**{k: v for k, v in _dotenv().items() if v}, **os.environ}
    saved = read_settings(settings_path(env))
    if env.get("AD_SPY_TRANSCRIBE"):
        raw, origin = env["AD_SPY_TRANSCRIBE"], "env"
    elif saved.get("AD_SPY_TRANSCRIBE"):
        raw, origin = saved["AD_SPY_TRANSCRIBE"], "settings"
    else:
        raw, origin = DEFAULT_MODE, "default"
    requested = raw.strip().lower()
    model = (
        env.get("AD_SPY_TRANSCRIBE_MODEL") or saved.get("AD_SPY_TRANSCRIBE_MODEL") or DEFAULT_MODEL
    )
    key = bool(env.get(KEY_ENV))
    if requested not in MODES:
        note = f"AD_SPY_TRANSCRIBE={raw!r} is not one of {', '.join(MODES)}; using ScrapeCreators."
        return Mode(requested, DEFAULT_MODE, model, origin, key, note)
    if requested == "openrouter" and not key:
        note = (
            f"Enhanced transcripts are on ({origin}) but {KEY_ENV} is not set; "
            "using ScrapeCreators transcripts. Set the key or turn it off: "
            "ad-spy-kit transcribe-mode scrapecreators"
        )
        return Mode(requested, DEFAULT_MODE, model, origin, key, note)
    if requested == "openrouter":
        note = f"Enhanced transcripts on ({origin}): OpenRouter {model}."
    else:
        note = (
            f"ScrapeCreators transcripts ({origin}). Opt in: ad-spy-kit transcribe-mode openrouter"
        )
    return Mode(requested, requested, model, origin, key, note)


def openrouter_key() -> str:
    return os.environ.get(KEY_ENV) or _dotenv().get(KEY_ENV, "")


# --- one ad ---------------------------------------------------------------------------


def _download(url: str) -> bytes | None:
    import httpx

    try:
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    return r.content


def video_bytes(
    ad: dict[str, Any], media_dir: Path, download: Callable = _download
) -> bytes | None:
    """The winner's video: a cached media/<ad_id>.mp4, else the pull's video_url (expires)."""
    local = media_dir / f"{ad['ad_id']}.mp4"
    if local.is_file():
        return local.read_bytes()
    url = ad.get("video_url")
    if not url:
        return None
    data = download(url)
    if data:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
    return data


def extract_audio(video: bytes) -> bytes | None:
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.mp4", Path(d) / "out.mp3"
        src.write_bytes(video)
        done = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-vn",
                "-ac",
                "1",
                "-b:a",
                "64k",
                str(dst),
            ],
            capture_output=True,
        )
        return dst.read_bytes() if done.returncode == 0 and dst.is_file() else None


def build_request(model: str, video: bytes | None = None, audio: bytes | None = None) -> dict:
    if audio is not None:
        part = {
            "type": "input_audio",
            "input_audio": {"data": base64.b64encode(audio).decode(), "format": "mp3"},
        }
        prompt = AUDIO_PROMPT
    else:
        data = base64.b64encode(video or b"").decode()
        part = {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}}
        prompt = PROMPT
    return {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, part]}],
    }


def _post(body: dict, key: str) -> dict:
    import httpx

    r = httpx.post(
        ENDPOINT,
        json=body,
        headers={"Authorization": f"Bearer {key}", "X-Title": "ad-spy-kit"},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def parse_reply(resp: dict) -> dict[str, Any]:
    """Model reply → {transcript, onscreen_text, onscreen_hook}. Raises ValueError if unusable."""
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("OpenRouter reply had no message") from e
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    text = _FENCE.sub("", str(text).strip())
    try:
        doc = json.loads(text[text.index("{") : text.rindex("}") + 1])
    except ValueError as e:
        raise ValueError("OpenRouter reply was not JSON") from e
    lines = doc.get("onscreen_text") or []
    if isinstance(lines, str):
        lines = [lines]
    hook = doc.get("onscreen_hook")
    return {
        "transcript": str(doc.get("transcript") or "").strip(),
        "onscreen_text": "\n".join(str(x).strip() for x in lines if str(x).strip()) or None,
        "onscreen_hook": str(hook).strip() if hook else None,
    }


def transcribe_ad(
    ad: dict[str, Any],
    media_dir: Path,
    mode: Mode,
    *,
    key: str,
    post: Callable[[dict, str], dict] = _post,
    download: Callable = _download,
) -> dict[str, Any]:
    """One paid call. Returns a transcripts.json item; `error` set when it fell through."""
    item: dict[str, Any] = {"ad_id": ad["ad_id"], "source": "openrouter", "model": mode.model}
    video = video_bytes(ad, media_dir, download)
    if not video:
        return {**item, "transcript": "", "error": "no video file or video_url to send"}
    if len(video) > MAX_VIDEO_BYTES:
        return {**item, "transcript": "", "error": f"video over {MAX_VIDEO_BYTES >> 20} MB"}
    if mode.audio_only:
        audio = extract_audio(video)
        if audio is None:
            return {**item, "transcript": "", "error": "ffmpeg missing or failed; no audio"}
        body = build_request(mode.model, audio=audio)
    else:
        body = build_request(mode.model, video=video)
    try:
        got = parse_reply(post(body, key))
    except Exception as e:  # noqa: BLE001 - any API/parse failure falls back per ad
        msg = re.sub(re.escape(key), "***", str(e)) if key else str(e)
        return {**item, "transcript": "", "error": f"{type(e).__name__}: {msg}"[:300]}
    return {**item, **{k: v for k, v in got.items() if v is not None or k == "transcript"}}
