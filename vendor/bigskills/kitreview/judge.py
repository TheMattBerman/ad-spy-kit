import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

CRITERIA = [
    ("magic_moment", "Does the kit deliver a concrete, ideally PRICED/quantified payoff on its FIRST run (a real 'whoa' or a removed pain), or is it plumbing that merely 'works'? 5 = named + priced magic moment shown in the README; 1 = no payoff."),
    ("killer_readme", "Does the README SELL the magic, lead with a real artifact ('see the output first'), have an instant copy-paste quick-start, a point of view, and an honest-limits section? 5 = all; 1 = thin/generic."),
    ("opinionated", "Does it encode a real POV / a NAMED framework / the author's defaults, vs a vanilla wrapper anyone could ship? 5 = a defensible named framework; 1 = generic."),
    ("build_process", "Is there CODE-ENFORCED rigor: tests/evals/a blocking quality rubric (not just an LLM following a rubric), spec/plan, semver/CHANGELOG, dev/public split? 5 = a blocking eval rubric + a real test suite; 1 = no tests/evals at all."),
    ("compounding", "Does the kit GET BETTER over time, or ship once and rot? Looks for THREE things: (1) an eval RATCHET — a golden/eval set that grows + a validator that fails the run against it; (2) CORRECTION-CAPTURE — a logged human-override loop that feeds corrections back (a verdicts corpus, corrections.md); (3) a BASELINE-COMPARISON test that proves the skill still beats vanilla (scripts/compare-baseline.sh pattern). 5 = all three wired; 1 = static, none. A strong validator ALONE caps at ~3-4 without a correction-capture loop."),
]
_GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "calibration.md"

def golden_text():
    return _GOLDEN.read_text() if _GOLDEN.is_file() else ""

INSTRUCTIONS = (
    "You are Matt's brutally honest kit reviewer. You grade an AI-agent 'kit' (an installable skill bundle) "
    "against his bar, calibrated to the GOLDEN EXEMPLARS below (his best kits). You do not flatter. "
    "Score EACH criterion 1-5 (5 = as good as the golden exemplars, 1 = bad) and give a one-line reason. "
    "Be strict: a great IDEA with no tests/evals is NOT a high build_process. Return ONLY valid JSON."
)

def build_prompt(profile, golden_text, overrides=None):
    crit = "\n".join(f"- {c}: {desc}" for c, desc in CRITERIA)
    prof = json.dumps({k: (v if not isinstance(v, str) else v[:6000]) for k, v in profile.items()},
                      indent=1, ensure_ascii=False)
    corrections = ""
    if overrides:
        lines = "\n".join(
            f'- {o.get("kit")} / {o.get("criterion")}: model said {o.get("model_score")}, '
            f'Matt says {o.get("matt_score")} — "{o.get("why","")}"'
            for o in overrides)
        corrections = (
            "\n## CORRECTIONS — Matt overruled the model on these. "
            "Match his judgment, not your prior.\n" + lines + "\n")
    return f"""{INSTRUCTIONS}

## GOLDEN EXEMPLARS (this is what 5/5 looks like)
{golden_text[:9000]}
{corrections}
## CRITERIA
{crit}

## KIT TO GRADE
{prof}

Return ONLY: {{"criteria": {{"<id>": {{"score": N, "reason": "<=14 words"}}, ...}}, "weakest": "<id>", "headline": "<one line on the kit>"}}"""

def response_schema():
    props = {c: {"type": "object", "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5},
                 "reason": {"type": "string"}}, "required": ["score"]} for c, _ in CRITERIA}
    return {"type": "object", "properties": {"criteria": {"type": "object", "properties": props,
            "required": list(props.keys())}, "weakest": {"type": "string"}, "headline": {"type": "string"}},
            "required": ["criteria"]}

def _or_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    env_file = Path(os.environ.get("KIT_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OpenRouter key not found. Set OPENROUTER_API_KEY in .env or env.")

def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.S)
    m = re.search(r'\{.*\}', text, re.S)
    return json.loads(m.group(0) if m else text)

def _call_model(key, model, prompt):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.2}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

def profile_id(profile):
    key = {k: v for k, v in profile.items() if k not in ("commit_count",)}
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]

def run_judge(profile, golden_text=None, model="anthropic/claude-opus-4-8", backend="api", _caller=None, overrides=None):
    gt = golden_text if golden_text is not None else globals()["golden_text"]()
    if backend == "cached":
        snap = Path(__file__).resolve().parent.parent / "tests" / "snapshots" / f"{profile_id(profile)}.json"
        if not snap.is_file():
            raise FileNotFoundError(f"no cached judge snapshot for {profile_id(profile)}")
        return json.loads(snap.read_text())
    prompt = build_prompt(profile, gt, overrides)
    caller = _caller or _call_model
    return _parse_json(caller(None if _caller else _or_key(), model, prompt))
