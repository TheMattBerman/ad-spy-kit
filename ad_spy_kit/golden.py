"""Golden ratchet: the deterministic outputs of each fixture, frozen in fixtures/<name>/golden.json.

A change to winner order, quarantine, dedupe or gap citations shows up as DRIFT in
`ad-spy-kit golden` and fails tests/test_golden.py. Accept an intended change with
`ad-spy-kit golden --update` and commit the diff, so every behavior change is reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.validate_run import Report, check_citations, check_numbers

ROOT = Path(__file__).resolve().parents[1]


def snapshot(name: str) -> dict[str, Any]:
    fx = ROOT / "fixtures" / name
    ads_raw = build_ads_raw_from_fixture(fx)
    winners = score_winners(ads_raw.get("ads", []))
    analysis = json.loads((fx / "analysis.json").read_text())
    ads = {a["ad_id"]: a for a in ads_raw.get("ads", [])}
    rep = Report()
    docs = {"ads.raw": ads_raw, "winners": winners, "analysis": analysis}
    check_citations(docs, rep)
    check_numbers(docs, rep)
    return {
        "rule_version": winners["rule_version"],
        "rank_source": winners["rank_source"],
        "thin_signal": winners["thin_signal"],
        "winner_order": [w["ad_id"] for w in winners["winners"]],
        "winner_why": {w["ad_id"]: w["why"] for w in winners["winners"]},
        "dupes_merged": {
            w["ad_id"]: w["dupes_merged"] for w in winners["winners"] if w["dupes_merged"]
        },
        "quarantined": sorted(q["ad_id"] for q in winners["quarantined"]),
        "gap_order": [g["gap"] for g in analysis.get("gaps", [])],
        "gap_citations": [g.get("evidence_ad_ids", []) for g in analysis.get("gaps", [])],
        "citation_errors": rep.errors,
        # Spoken > on-screen > caption: which source each winner's hook comes from.
        "hook_sources": {
            w["ad_id"]: ads.get(w["ad_id"], {}).get("hook_source", "copy")
            for w in winners["winners"]
        },
        "analysis_hook_sources": {
            h["ad_id"]: h.get("hook_source") or "copy" for h in analysis.get("hooks", [])
        },
    }


def golden_path(name: str) -> Path:
    return ROOT / "fixtures" / name / "golden.json"


def write_golden(name: str) -> Path:
    path = golden_path(name)
    path.write_text(json.dumps(snapshot(name), indent=2, ensure_ascii=False) + "\n")
    return path


def check_golden(name: str) -> list[str]:
    path = golden_path(name)
    if not path.exists():
        return [f"no golden.json for {name}; run `ad-spy-kit golden --update --fixture {name}`"]
    want = json.loads(path.read_text())
    got = snapshot(name)
    return [
        f"{key}: golden={want.get(key)!r} now={got.get(key)!r}"
        for key in sorted(set(want) | set(got))
        if want.get(key) != got.get(key)
    ]
