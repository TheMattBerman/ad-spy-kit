#!/usr/bin/env python3
"""Baseline comparison (spec §12): kit output vs a vanilla "tear down X's ads" answer.

Both sides are scored on the same countable things, against the same ads.raw.json:
  cited_ids       distinct Ad Library ids the answer points at
  quotes          quoted strings; verbatim = found in that brand's ads (copy, said, on screen)
  uncited_numbers numbers not in the ads or the pull's own counts
  hedges          might/maybe/likely/... in the copy
  visual          ships a board PNG

Vanilla answers live in evals/baseline/vanilla/<fixture>.md (live/x -> live-x.md), recorded
from evals/baseline/PROMPT.md with no kit installed (evals/capture_vanilla.py does one API
call per fixture). No vanilla file -> the row says so; nothing is invented.

  --write   save the kit side to evals/baseline/kit/<fixture>.md and the table to
            evals/baseline/results.md

Exit 1 if the kit breaks pass criteria 1-2 (0 uncited numbers, 100% verbatim quotes, 0
hedges) or scores worse than a recorded vanilla answer on any of those.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.hooks import evidence_text  # noqa: E402
from ad_spy_kit.validate_run import HEDGES, NUMBER, _norm, allowed_numbers  # noqa: E402

QUOTE = re.compile(r"[\"\u201c]([^\"\u201d]{6,200})[\"\u201d]")
BASE = ROOT / "evals" / "baseline"
COLS = ("cited_ids", "quotes", "verbatim_quotes", "uncited_numbers", "hedges")


def fixture_names() -> list[str]:
    fx = ROOT / "fixtures"
    return sorted(str(p.parent.relative_to(fx)) for p in fx.rglob("golden.json"))


def slug(name: str) -> str:
    return name.replace("/", "-")


def vanilla_path(name: str) -> Path:
    return BASE / "vanilla" / f"{slug(name)}.md"


def _corpus(ads: list[dict]) -> str:
    return " ".join(_norm(evidence_text(a, s)) for a in ads for s in ("copy", "spoken", "onscreen"))


def score_text(text: str, ads_raw: dict, winners: dict) -> dict:
    ads = ads_raw.get("ads", [])
    corpus = _corpus(ads)
    ids = {a["ad_id"] for a in ads}
    cited = {i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text)}
    quotes = QUOTE.findall(text)
    verbatim = [q for q in quotes if _norm(q).rstrip(".!…") in corpus]
    ok_nums = allowed_numbers(ads_raw, winners)
    # Ad IDs are citations, not claims: drop them before counting numbers.
    no_ids = text
    for i in sorted(ids, key=len, reverse=True):
        no_ids = re.sub(rf"(?<![\w-]){re.escape(i)}(?![\w-])", " ", no_ids)
    numbers = NUMBER.findall(no_ids)
    uncited = [n for n in numbers if f"{float(n):g}" not in ok_nums]
    return {
        "cited_ids": len(cited),
        "quotes": len(quotes),
        "verbatim_quotes": len(verbatim),
        "uncited_numbers": len(uncited),
        "hedges": len(HEDGES.findall(text)),
    }


def kit_text(run_dir: Path) -> str:
    a = json.loads((run_dir / "analysis.json").read_text())
    parts = [a["headline"]["top"], a["headline"]["bottom"]]
    parts += [f'{h["ad_id"]} "{h["hook_text"]}"' for h in a.get("hooks", [])]
    parts += [
        f'{o["ad_id"]} "{o["evidence"]}"' for o in a.get("offer_map", []) if o.get("evidence")
    ]
    parts += [f"{g['gap']} ({', '.join(g.get('evidence_ad_ids', []))})" for g in a.get("gaps", [])]
    parts += [s.get("stat", "") or f"{s['label']} {s['value']}" for s in a.get("stats", [])]
    return "\n".join(parts)


def _rate(m: dict) -> float:
    return m["verbatim_quotes"] / m["quotes"] if m["quotes"] else 1.0


def verdict(kit: dict, vanilla: dict | None) -> list[str]:
    """Why the kit side fails (empty = pass)."""
    out = []
    if kit["uncited_numbers"] or kit["verbatim_quotes"] != kit["quotes"] or kit["hedges"]:
        out.append("kit breaks pass criteria 1-2")
    if vanilla:
        if _rate(kit) < _rate(vanilla):
            out.append("vanilla quotes more verbatim")
        for c in ("uncited_numbers", "hedges"):
            if kit[c] > vanilla[c]:
                out.append(f"kit has more {c}")
    return out


def main(argv: list[str]) -> int:
    write = "--write" in argv
    names = [a for a in argv if a != "--write"] or fixture_names()
    failed = False
    lines = [f"{'fixture':16} {'side':8} " + " ".join(f"{c:>15}" for c in COLS) + "  visual"]
    for name in names:
        run = ROOT / "artifacts" / "screenshots" / name
        ads_raw = json.loads((run / "ads.raw.json").read_text())
        winners = json.loads((run / "winners.json").read_text())
        text = kit_text(run)
        if write:
            (BASE / "kit").mkdir(exist_ok=True)
            (BASE / "kit" / f"{slug(name)}.md").write_text(
                f"<!-- kit output: analysis.json of artifacts/screenshots/{name} -->\n{text}\n"
            )
        kit = score_text(text, ads_raw, winners)
        rows = [("kit", kit, (run / "board.png").exists())]
        vpath = vanilla_path(name)
        vanilla = score_text(vpath.read_text(), ads_raw, winners) if vpath.exists() else None
        if vanilla:
            rows.append(("vanilla", vanilla, False))
        for side, m, visual in rows:
            lines.append(
                f"{name:16} {side:8} " + " ".join(f"{m[c]:>15}" for c in COLS) + f"  {visual}"
            )
        if not vanilla:
            lines.append(f"{name:16} vanilla  no capture recorded (see evals/baseline/PROMPT.md)")
        for why in verdict(kit, vanilla):
            failed = True
            lines.append(f"  FAIL {name}: {why}")
    print("\n".join(lines))
    if write:
        (BASE / "results.md").write_text(
            "# Baseline results\n\nGenerated by `bash evals/compare-baseline.sh --write`.\n\n```\n"
            + "\n".join(lines)
            + "\n```\n"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
