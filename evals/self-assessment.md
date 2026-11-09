# Self-assessment: SELF-ASSESSED, NOT THE OFFICIAL kit-review GRADE

The bigskills `kit-review` judge has not graded this kit. No `OPENROUTER_API_KEY` was
available, and no snapshot was recorded or written by hand. This file is a hand score
against the vendored rubric (`vendor/bigskills/kitreview`, `docs/bigskills/eval-rubric.md`).
It was written by the agent that built the kit, so it's biased toward the kit. To get the
official grade, run `bash evals/run-kit-review.sh api` or `bash evals/run-kit-review.sh subagent`.

- Date: 2026-10-28
- Commit scored: 64f1816 (this file lands in the next commit) (branch `cursor/ad-spy-kit-full-build-37b1`)
- Machine checks at that commit:
  - `bash evals/run-kit-review.sh cached`: compliance **PASS**, 0 findings, exit 3 (ungraded)
  - `uv run pytest -q`: 81 passed
  - `ruff check .` and `ruff format --check .`: clean
  - `ad-spy-kit replay-all`: 3/3 gate ok
  - `ad-spy-kit golden`: 3/3 OK
  - `doctor.sh`: 8 pass, 0 fail

## kit-review criteria (1-5, calibrated to the golden exemplars)

| Criterion | Self-score | Evidence | What keeps it from 5 |
|---|---|---|---|
| magic_moment | 4 | The README opens with a one-line priced promise, a "see the output first" block and the board image. The old-way vs Steal Board table prices the kit side: $0 and ~5s on fixtures, 1 ScrapeCreators credit per request live. | The status quo isn't priced, because there's no sourced figure. Every artifact comes from a synthetic fixture, and no live run is recorded. |
| killer_readme | 4 | Artifact first, three copy-paste install paths, a keyless demo, a five-step method, a CLI table, an honest-limits section that says "no spend" and "fixtures synthetic", and an evals section. | There's no worked example on real data like frontrun's scorecard. The npx and plugin installs need one extra `uv sync` step. |
| opinionated | 4 | The named Steal Board method: survived-spend floor (7+ days or 3+ versions), banger / solid / testing bands with facts only and no scores, verbatim-only citation, "the lane is what no winner says", and "steal the structure, never the ad". | It's less of a coined, diagrammed market theory than frontrun's diffusion gap. |
| build_process | 4 | Blocking code gate `ad-spy-kit validate`:<br>- A1-A5: schema, citations, numbers, formats<br>- B1-B4: verbatim quotes<br>- C1-C6: layout and footer<br>- E1: hedges<br>- K: corrections<br>Also JSON schemas, pytest + bats dual suite (`scripts/test.sh`): bats covers install.sh, uninstall.sh, doctor.sh and the CLI in a temp HOME. Spec, semver VERSION and CHANGELOG in step (1.5.2). | CI is disabled on the repo by request, so the suite runs by hand. |
| compounding | 4 | Eval ratchet: `fixtures/*/golden.json` and `ad-spy-kit golden`. Correction capture: `ad-spy-kit correct` writes to `evals/corrections.jsonl`, and the K gate fails any later board or swipe file that breaks a correction (3 rules live). Baseline: `evals/compare-baseline.sh` scores the kit against recorded vanilla captures for all 4 fixtures and fails if the kit loses. | Vanilla captures come from one model (gpt-4.1) only. |

Average: 4.0, with build_process at 4. By the scorecard thresholds (Gold needs avg ≥ 4.5 and
build_process ≥ 4; Strong needs avg ≥ 3.5 and build_process ≥ 3), that is **Strong, not
Gold**. The compliance scan passes, so no cap applies.

## bigskills 9-dimension skill rubric

| Dimension | Self-score | Evidence / gap |
|---|---|---|
| Trigger Quality | 4 | All 7 SKILL.md descriptions carry "Use when" and "Do NOT". `evals/triggers.yaml` has 6 should-trigger and 5 should-not-trigger cases, and `tests/test_skill_frontmatter.py` checks them. But that test only checks anchor words in the descriptions; no real agent run has observed the triggers. |
| Behavior Shift | 4 | `examples/README.md` has the Foldbrook before/after taste table, and compare-baseline scores kit vs recorded vanilla on all 4 fixtures: kit 100% verbatim, 0 uncited numbers; vanilla 12-34% verbatim, 9-13 uncited numbers. |
| Taste Transfer | 4 | The before/after table sits in the orchestrator, and the steal/skip rules and open-lane rule are in the core. The deeper calls (offer depth, hook taxonomy) live in `references/`. |
| Anti-Slop Defense | 5 | Named, code-enforced kills:<br>- paraphrased quotes<br>- uncited numbers<br>- hedges (E1)<br>- invalid format slugs (A5)<br>- numeric scores (K001)<br>- hedge lines like "spend unknown" / "don't copy" (E2)<br>- fold overflow (C5)<br>The gate fails the run. |
| Deliverable Power | 4 | One run makes the board PNG and HTML, 5 X slices, a newsletter image, an OG image, a cited `teardown.md`, counter briefs (headline, hook, visual direction, why it beats the original) with a one-click StealAds render. The live ScrapeCreators path is unit-tested with mocks but not run against the real services. |
| Token Discipline | 4 | Orchestrator 97 lines; six sub-skills of 32-37 lines; depth is in `references/`. Some routing text repeats between the orchestrator and the sub-skills. |
| Architecture Quality | 4 | The SKILL.md, `skills/`, `references/`, CLI, `schemas/`, `templates/`, `fixtures/`, `evals/` and `examples/` split is clean, and the bigskills authoring docs live in `docs/bigskills/`. Ported upstream code (`cie/`, `vendor/`) sits at the repo root next to the kit. |
| Operational Completeness | 4 | README, install.sh (claude / codex / both, idempotent), uninstall.sh, doctor.sh (launches Chromium), VERSION, .env.example, Claude plugin and marketplace metadata, SKILL.md metadata block, evals, and missing-key messages with `ad-spy-kit explain`. There's no openclaw config. |
| Reusability | 4 | Each run directory is self-contained and replayable, the run.json hash is stable, corrections carry forward, and the kit works on fixtures with no keys. It's US- and Meta-only, and the StealAds path waits on the gate. |
| **Total** | **37/45** | Band "Good, tighten before canonizing" (30-37). |

## What would move it up

1. Record one live prod StealAds `search_ads` / `find_winning_ads` pull (once the spec §11.3 gate opens)
   or one ScrapeCreators pull as a non-synthetic fixture, and render it. That lifts
   magic_moment, killer_readme and Deliverable Power.
2. Done 1.5.2: vanilla captures recorded; add a second model's captures.
3. Get the official grade: `bash evals/run-kit-review.sh api` with `OPENROUTER_API_KEY`, then
   commit the snapshot it writes.
4. Done 1.5.2: bats tests for install.sh, uninstall.sh and doctor.sh. Still to do:
   observe the trigger evals in a real agent session.
