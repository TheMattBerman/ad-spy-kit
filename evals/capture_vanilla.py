#!/usr/bin/env python3
"""Record vanilla baseline answers: PROMPT.md + a fixture's ads.raw.json, no kit, one call.

  uv run python evals/capture_vanilla.py [fixture ...]   # needs OPENAI_API_KEY in the env

The reply is saved verbatim to evals/baseline/vanilla/<fixture>.md under the header line
PROMPT.md asks for. Nothing is edited or retried for a better answer. The key is read from the
environment and never printed or written.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.compare_baseline import fixture_names, vanilla_path  # noqa: E402

MODELS = ("gpt-4.1", "gpt-4o")  # first one the key can use wins


def prompt_text() -> str:
    md = (ROOT / "evals" / "baseline" / "PROMPT.md").read_text()
    return " ".join(line.lstrip("> ").strip() for line in md.splitlines() if line.startswith(">"))


def ask(model: str, content: str, key: str) -> str:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}]})
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body.encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def main() -> int:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set; nothing captured.")
        return 1
    names = sys.argv[1:] or fixture_names()
    for name in names:
        raw = (ROOT / "artifacts" / "screenshots" / name / "ads.raw.json").read_text()
        content = f"{prompt_text()}\n\n{raw}"
        for model in MODELS:
            try:
                reply = ask(model, content, key)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (400, 403, 404):
                    raise
        else:
            print(f"{name}: no model in {MODELS} accepted the request; nothing captured.")
            continue
        date = dt.date.today().isoformat()
        header = (
            f"<!-- vanilla capture: {model} (OpenAI API, one call), {date}, no kit installed -->"
        )
        out = vanilla_path(name)
        out.write_text(f"{header}\n{reply.rstrip()}\n")
        words = len(re.findall(r"\w+", reply))
        print(f"{name}: {words} words -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
