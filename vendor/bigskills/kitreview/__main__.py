import argparse, json, os, sys
from pathlib import Path
from .compliance import check_compliance
from .profile import build_profile
from .judge import run_judge, golden_text, build_prompt, response_schema, profile_id
from .overrides import append_override, load_overrides
from .scorecard import build_scorecard

def _render(sc):
    L = [f"Kit Scorecard: {sc.kit}   GRADE: {sc.grade} ({sc.quality_avg}/5)",
         f"  compliance  {sc.compliance_verdict}"]
    # Collapse findings by rule — show each unique rule once with a count
    from collections import defaultdict
    _by_rule: dict = defaultdict(list)
    for f in sc.findings:
        _by_rule[f['rule']].append(f)
    for rule, group in _by_rule.items():
        rep = group[0]
        count_tag = f"  (x{len(group)})" if len(group) > 1 else ""
        L.append(f"      {rep['severity'].upper():5} [{rep['rule']}] {rep['message']}{count_tag}")
    L.append("  quality")
    for q in sc.quality:
        L.append(f"      {q['id']:14} {q['score']}/5  — {q.get('reason','')}")
    if sc.optimization_plan:
        L.append("  optimization plan:")
        for s in sc.optimization_plan:
            tag = s.get("criterion", "")
            L.append(f"      {s['rank']}. [{tag}] {s.get('fix','')}")
    return "\n".join(L)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit-review")
    ap.add_argument("kit")
    ap.add_argument("--judge", default="api", choices=["api", "cached", "subagent"])
    ap.add_argument("--judge-model", default="anthropic/claude-opus-4-8")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--override", action="store_true")
    ap.add_argument("--criterion")
    ap.add_argument("--score", type=int)
    ap.add_argument("--why", default="")
    a = ap.parse_args(argv)

    corpus = Path(os.environ.get("KIT_VERDICTS_DIR", Path(__file__).resolve().parent.parent / "verdicts"))

    if a.override:
        if not (a.criterion and a.score):
            print("--override needs --criterion and --score", file=sys.stderr)
            return 1
        try:
            pid = profile_id(build_profile(a.kit))
        except Exception:
            pid = None
        rec = append_override(corpus, profile_id=pid, kit=Path(a.kit).resolve().name,
                              criterion=a.criterion, model_score=None,
                              matt_score=a.score, why=a.why)
        print(f"recorded override: {rec['kit']}/{rec['criterion']} -> {rec['matt_score']}")
        return 0

    findings = check_compliance(a.kit)
    profile = build_profile(a.kit)
    overrides = load_overrides(corpus)
    if a.judge == "subagent":
        # the kit-review SKILL drives this path: emit prompt, get JSON back, then re-run with --judge cached-from-file
        print(json.dumps({"prompt": build_prompt(profile, golden_text(), overrides),
                          "schema": response_schema(), "profile_id": profile_id(profile)}, indent=2))
        return 0
    try:
        judge_result = run_judge(profile, backend=a.judge, model=a.judge_model, overrides=overrides)
    except FileNotFoundError:
        pid = profile_id(profile)
        print(f"no cached snapshot for {pid}; run with --judge api or record one", file=sys.stderr)
        return 1
    sc = build_scorecard(a.kit, findings, judge_result)
    print(json.dumps(sc.to_dict(), indent=2) if a.json else _render(sc))
    return 0 if sc.grade in ("Gold", "Strong") else 2

if __name__ == "__main__":
    sys.exit(main())
