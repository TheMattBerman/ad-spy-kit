# BigSkills Eval Rubric

Score each dimension from 1 to 5.

## 1. Trigger Quality
Will the skill be invoked for the right requests?

- **5:** precise description, clear triggers, clear exclusions, tested with should/should-not evals
- **3:** somewhat clear, some ambiguity, no explicit exclusions
- **1:** vague or generic description

## 2. Behavior Shift
Does the skill materially improve output versus baseline?

- **5:** obvious improvement, documented with before/after
- **3:** some improvement, still partial
- **1:** barely different from vanilla output

## 3. Taste Transfer
Does the skill teach judgment, not just process?

- **5:** before/after taste examples in the core, transfers discernment immediately
- **3:** some helpful principles, still procedural, examples only in references
- **1:** mostly step-by-step mechanics

## 4. Anti-Slop Defense
Does the skill stop common failure modes?

- **5:** explicit named anti-patterns with kill-on-sight energy
- **3:** partial guardrails
- **1:** almost no bad-output prevention

## 5. Deliverable Power
Does the skill produce the actual thing the user wants?

- **5:** direct, usable deliverable with scripts backing the workflow
- **3:** helpful but still partly intermediate
- **1:** mostly prep work or analysis for later

## 6. Token Discipline
Is the skill worth its context cost?

- **5:** lean, dense, high signal, depth lives in references
- **3:** some bloat, still usable
- **1:** bloated, repetitive, or badly layered

## 7. Architecture Quality
Is the content split correctly across the skill package?

- **5:** strong use of SKILL, references, scripts, assets, examples; repo-level infra separate from skill folder
- **3:** some misplacement, still workable
- **1:** monolithic or chaotic

## 8. Operational Completeness
Can someone install, verify, and use this skill without asking questions?

- **5:** README, install.sh, doctor.sh, uninstall.sh, VERSION, .env.example, openclaw config, metadata block, evals, dependency checks, graceful degradation documented
- **3:** some operational files, missing verification or dependency story
- **1:** bare SKILL.md with no installation or verification path

## 9. Reusability
Can this skill work repeatedly across real tasks?

- **5:** durable, workspace-aware, leaves artifacts for future runs
- **3:** useful in a narrow but real slice
- **1:** brittle or too vague to reuse well

## Interpretation
- **38–45:** Ship
- **30–37:** Good, tighten before canonizing
- **22–29:** Major revision needed
- **Below 22:** Not a real skill yet

## Audit output format

### Score
- Trigger Quality: X/5
- Behavior Shift: X/5
- Taste Transfer: X/5
- Anti-Slop Defense: X/5
- Deliverable Power: X/5
- Token Discipline: X/5
- Architecture Quality: X/5
- Operational Completeness: X/5
- Reusability: X/5
- **Total: X/45**

### Verdict
One of: Ship / Tighten / Rebuild

### Strengths
3–5 bullets

### Weaknesses
3–5 bullets

### Top fixes
The 3 highest-leverage changes only
