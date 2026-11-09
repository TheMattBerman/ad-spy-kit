# BigSkills Anti-Patterns

## 1. Documentation Voice
Reads like product docs, a wiki article, or an onboarding manual.

**Symptoms:** neutral tone, obvious statements, too much explanation of basics, no point of view.
**Fix:** Rewrite in expert voice. Add stronger defaults, sharper judgment, specific anti-patterns.

## 2. Comprehensive Blob Syndrome
Tries to cover every angle, audience, exception, and framework.

**Symptoms:** giant SKILL.md, too many sections that "might be useful," everything feels equally important.
**Fix:** Narrow the job. Cut optionality. Move depth into references. Delete whatever does not improve output.

## 3. Weak Triggering
Description is broad, fuzzy, or packed with generic language. No exclusions.

**Symptoms:** triggers on everything, triggers on nothing, unclear user phrases, no "do NOT use for" clause.
**Fix:** Name the job, the output, the trigger phrases, and the explicit exclusions more concretely.

## 4. Framework Bloat
Piles on models, matrices, stages, and named systems that create overhead without leverage.

**Symptoms:** too many numbered frameworks, lots of internal process, weak deliverables.
**Fix:** Keep only frameworks that materially improve output. Delete decorative systems.

## 5. Intermediate Deliverable Addiction
Produces research docs, memos, strategy artifacts, or prep work instead of the real thing.

**Symptoms:** outputs become "notes for later use," user still has to do another step manually.
**Fix:** Push toward finished outputs by default. Let research serve the deliverable, not replace it.

## 6. Fake Examples
Teaches with toy examples that do not resemble real work.

**Symptoms:** generic placeholder brands, unrealistic scenarios, examples that prove nothing.
**Fix:** Use real before/after examples or realistic approximations with clear stakes.

## 7. No Baseline Comparison
Assumed useful without testing what vanilla output looks like.

**Symptoms:** no before/after, no evaluation criteria, lots of confidence, no proof.
**Fix:** Run the task without the skill, then with the skill, and compare materially.

## 8. No Compression Pass
Skill only grows. Never gets trimmed.

**Symptoms:** repeated principles, verbose examples, references duplicated in the core.
**Fix:** Cut 20–30%. Merge overlaps. Push depth outward.

## 9. Architecture Dumping
Everything lives in SKILL.md regardless of whether it belongs there.

**Symptoms:** giant monolithic file, schemas in the core, reference docs pasted inline.
**Fix:** Use the right layer: core vs references vs scripts vs assets.

## 10. No Self-Improvement Loop
Written once and never learns from usage.

**Symptoms:** same weak output months later, recurring failure modes not captured.
**Fix:** Version the skill. Audit it. Tighten it after real tasks. Maintain gotchas.

## 11. No Operational Infrastructure
SKILL.md exists but there is no way to install, verify, or understand dependencies.

**Symptoms:** no README, no install script, no doctor, no dependency documentation, no evals, no VERSION.
**Fix:** Add the full operational layer. A skill without install + doctor + evals is a draft, not a product.

## 12. Dead Config Files
Config files that nothing reads programmatically. Documentation pretending to be config.

**Symptoms:** config.json or config.example.json exists but no script imports or reads it. Defaults are hardcoded in scripts.
**Fix:** Either make scripts read the config, or delete the config and document defaults where they live.

## 13. No Graceful Degradation
Skill is all-or-nothing. If one dependency is missing, nothing works.

**Symptoms:** no documentation of what works without optional dependencies, no --copy-only or fallback mode.
**Fix:** Document what works at each dependency level. Design the skill so partial functionality is useful.
