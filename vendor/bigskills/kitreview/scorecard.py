from .models import CriterionScore, KitScorecard
from .judge import CRITERIA

# golden exemplar to copy, per criterion, for the optimization plan
ANCHOR = {
    "magic_moment": "price the payoff in the README like brand-shoot ($Xk manual vs $Y kit), and lead with 'see the output first'",
    "killer_readme": "rewrite the README like frontrun: worked example up top, a quick-start, and an honest-limits section",
    "opinionated": "name your framework like Google Ads' 'Intent Map' and state your defaults explicitly",
    "build_process": "add a blocking eval rubric like frontrun (evals/output-quality-rubric.md, machine-checkable categories) and a real test suite like slideshow-kit",
    "compounding": "wire a feedback loop: a growing eval/golden set that gates the run, a correction-capture log (a verdicts corpus like bigskills), and a baseline-comparison test that proves you still beat vanilla",
}

def _band(avg, build_process, compliance_clean):
    if avg >= 4.5 and build_process >= 4 and compliance_clean:
        return "Gold"
    if avg >= 3.5 and build_process >= 3:
        return "Strong"
    if avg >= 2.5:
        return "Concept"
    return "Thin"

def build_scorecard(kit, findings, judge_result):
    scores = (judge_result or {}).get("criteria", {})
    quality = [CriterionScore(c, int(scores.get(c, {}).get("score", 0)),
                              scores.get(c, {}).get("reason", "")) for c, _ in CRITERIA]
    vals = [q.score for q in quality if q.score]
    avg = round(sum(vals) / len(vals), 2) if vals else 0.0
    build = next((q.score for q in quality if q.id == "build_process"), 0)
    errors = [f for f in findings if f.severity == "error"]
    compliance = "FLAG" if [f for f in findings if f.severity == "error"] else "PASS"
    grade = _band(avg, build, not errors)
    if errors and grade == "Gold":
        grade = "Strong"   # a hard compliance error can't be Gold

    # optimization plan: low criteria first, then floor fixes
    plan = []
    for q in sorted(quality, key=lambda x: x.score):
        if 0 < q.score < 4:
            plan.append({"criterion": q.id, "current": q.score,
                         "fix": ANCHOR.get(q.id, ""), "exemplar": ANCHOR.get(q.id, "")})
    _seen_rules: set = set()
    for f in findings:
        if f.rule not in _seen_rules:
            _seen_rules.add(f.rule)
            plan.append({"criterion": "compliance", "rule": f.rule, "fix": f.fix})
    for i, step in enumerate(plan, 1):
        step["rank"] = i

    return KitScorecard(kit=kit, compliance_verdict=compliance,
                        findings=[f.to_dict() for f in findings],
                        quality=[q.to_dict() for q in quality],
                        grade=grade, quality_avg=avg, optimization_plan=plan)
