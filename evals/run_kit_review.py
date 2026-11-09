#!/usr/bin/env python3
"""Run the vendored bigskills kit-review grader against what this repo actually ships.

The grader sees a clean export of git-tracked files (no .venv, no local caches), so the
compliance scan matches a fresh clone. Judge backends:

  cached    replay a recorded judge snapshot for this exact kit profile (offline)
  api       live judge via OpenRouter (needs OPENROUTER_API_KEY)
  subagent  print the judge prompt + schema so a local agent can grade it

This script never writes a snapshot. A missing snapshot means "no official grade".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "bigskills"
KIT_NAME = "ad-spy-kit"
EXIT_UNGRADED = 3


def export_tracked(dest_parent: Path) -> Path:
    dest = dest_parent / KIT_NAME
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode()
    for rel in filter(None, listing.split("\0")):
        src = ROOT / rel
        if not src.is_file():
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    return dest


def main() -> int:
    judge = sys.argv[1] if len(sys.argv) > 1 else "cached"
    if judge == "api" and not os.environ.get("OPENROUTER_API_KEY"):
        print("kit-review api judge needs OPENROUTER_API_KEY (not set). No grade.", file=sys.stderr)
        return EXIT_UNGRADED
    env = os.environ.copy()
    env["PYTHONPATH"] = str(VENDOR) + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    env.setdefault("KIT_VERDICTS_DIR", str(VENDOR / "verdicts"))
    sys.path.insert(0, str(VENDOR))
    from kitreview.compliance import check_compliance
    from kitreview.judge import profile_id
    from kitreview.profile import build_profile

    with tempfile.TemporaryDirectory() as tmp:
        kit = export_tracked(Path(tmp))
        findings = [f.to_dict() for f in check_compliance(str(kit))]
        pid = profile_id(build_profile(str(kit)))
        verdict = "FLAG" if any(f["severity"] == "error" for f in findings) else "PASS"
        print(
            json.dumps({"compliance": verdict, "findings": findings, "profile_id": pid}, indent=2)
        )
        cmd = [sys.executable, "-m", "kitreview", str(kit), "--judge", judge, "--json"]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if judge == "subagent":
        print(proc.stdout)
        return 0
    out = proc.stdout.strip()
    if not out:
        print(
            f"No official grade: {proc.stderr.strip() or 'judge produced no output'}\n"
            "Grade with `bash evals/run-kit-review.sh api` (OPENROUTER_API_KEY) or "
            "`bash evals/run-kit-review.sh subagent`. Never hand-write a snapshot.",
            file=sys.stderr,
        )
        return EXIT_UNGRADED
    data = json.loads(out)
    (ROOT / "evals" / "kit-review-latest.json").write_text(json.dumps(data, indent=2) + "\n")
    grade = data.get("grade", "?")
    summary = {
        "grade": grade,
        "quality_avg": data.get("quality_avg"),
        "compliance": data.get("compliance_verdict"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if grade in ("Gold", "Strong") else 2


if __name__ == "__main__":
    raise SystemExit(main())
