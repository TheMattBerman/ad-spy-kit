# Golden Calibration Corpus

What 5/5 looks like, per criterion, extracted from Matt's four golden kits.
Each snippet is a direct quote from the named source file. Use these as few-shot anchors when scoring.

---

## magic_moment

**Source: `brand-shoot-kit/README.md` — Cost Comparison table**

```
| The Old Way | The Agent Way |
|-------------|--------------|
| Studio day rental: $2,000 | OpenAI image API: ~$0.10 per shot |
| Photographer: $2,500 | Brand Shoot Kit: free |
| Stylist + props: $1,200 | OpenClaw: free |
| Model + makeup: $1,500 | QA + reroll: built in |
| Retoucher (12 shots): $1,800 | Human review: 10 minutes |
| Reshoot if a shot fails: another $2,000+ | Reroll loop: included |
| Time to deliver: 2-4 weeks | Time to deliver: 30 minutes |
| **One shoot: ~$11,000** | **One full 12-shot packet: ~$1.50** |
```

Why this is 5/5: the payoff is named, priced, and side-by-side with the status quo. The operator knows exactly what they are replacing and what it costs.

---

**Source: `brand-shoot-kit/README.md` — "see the output first" block**

```
> 👀 **See the output first:** every run produces `<packet>/index.html` — a premium gallery with images, QA scores, exports, reference, and provenance. Open it in a browser to see what a finished shoot looks like.
```

Why this is 5/5: the README leads with a real output artifact before any explanation. The reader sees the product before they read the pitch.

---

## killer_readme

**Source: `frontrun/README.md` — honest limits section**

```
## honest limits

- It reads dozens to low-hundreds of sources per brand, not a hundred-thousand-row scrape. Depth of signal over volume.
- A full URL-in run needs four API keys and about 5 minutes. Missing keys skip sources rather than fake them.
- Live voice quality depends on what the source APIs return for a given category. Thin pools produce fewer angles, and the run says so.
- It mines and surfaces. The operator still decides what is real, on-brand, and worth shipping.
- It produces decision-ready briefs, not published copy.
```

Why this is 5/5: explicit, specific, non-defensive. Names real constraints (key count, corpus size, operator role). Does not overpromise.

---

**Source: `frontrun/README.md` — worked-example scorecard (6-dimension)**

```
**Worked example.** Watch the 3-mention phrase beat the 47-mention phrase:

| Phrase | Mentions | S | R | E | C | P | D | raw | x mult | ranked |
|---|---|---|---|---|---|---|---|---|---|---|
| "pricing" cluster | 47 | 1 | 5 | 2 | 2 | 1 | 1 | 12 | 0.27 | **3.2** |
| "i churned the day they removed CSV export" | 3 | 5 | 3 | 4 | 5 | 4 | 5 | 26 | 1.0 | **26.0** |
```

Why this is 5/5: shows a concrete output artifact (the math) inside the README. The reader sees the system working before they install anything.

---

## opinionated

**Source: `Google Ads Kit/README.md` — Intent Map framing**

```
Most Google Ads problems are not bid problems.
They are **intent-mixing problems**.

Your account is buying different kinds of searches — buyers, comparison shoppers, researchers, job seekers, freebie hunters — and mixing them together. When that happens, bids optimize against noise, RSAs get generic, good traffic subsidizes bad traffic, and every budget decision is distorted.

Google Ads Copilot is an AI agent that reads search behavior, builds a durable Intent Map, finds waste, isolates signal, and turns what the account is learning into structure, copy, and scale decisions.
```

Why this is 5/5: the kit names a specific enemy ("intent-mixing problems"), coins its own term ("Intent Map"), and states a defensible thesis that no generic Google Ads tool would say.

---

**Source: `frontrun/README.md` — diffusion-gap framework**

```
## the core idea: the diffusion gap

The language that wins a category shows up in customer voice before it shows up in the ads.

Creators mint a phrase. Some of it diffuses into reviews and search. Most of it has not yet. **That not-yet-diffused language is the leading edge of the category.**

creators mint language  ->  diffuses to reviews + search  ->  shows up in ads (late)
                       ^
              the gap is the edge
```

Why this is 5/5: a named, diagrammed framework that carries the author's distinct market theory. No other tool would frame it this way.

---

**Source: `slideshow-kit/README.md` — named carousel archetypes**

```
| Format | Use When |
|---|---|
| `narrative` | Story-driven lessons, case studies, and founder POV |
| `numbered_diagnostic` | "The 4 tells", "5 reasons your X is broken", diagnostic posts |
| `receipt_context` | Quote, screenshot, or claim followed by interpretation |
| `process_reveal` | "How I did X in N minutes" or workflow breakdowns |
| `anatomy_breakdown` | Teardowns, examples, and what-to-notice posts |
| `before_after` | Transformation, contrast, and old-way/new-way posts |
| `counter_narrative` | Contrarian takes on category orthodoxy |
```

Why this is 5/5: the kit names seven distinct carousel archetypes with specific slot rules. This is encoded author judgment, not a generic "write a carousel" prompt.

---

## build_process

**Source: `frontrun/evals/output-quality-rubric.md` — blocking categories**

```
a run is `pass` only if every BLOCKING assertion passes. `pass_with_warnings` allows WARN-level misses. any BLOCKING miss is `fail`.

## A. structural presence (BLOCKING)
- **A1** all numbered artifacts exist: `00-intake.md`, `00b-scope-contract.md`, `01-source-index.md`, `raw/`, `02-evidence-cards.json`, ...
- **A2** `raw/` contains at least one source file.
- **A3** `02-evidence-cards.json` parses as a JSON array of objects.

## B. evidence card integrity (BLOCKING)
- **B1** every card validates against `voice-evidence-card.schema.json`
- **B3** `verbatim` is separated from `interpretation`: they are distinct fields. assert `verbatim != interpretation` on every card
- **B5** `do_not_claim` is non-empty on every card. the anti-overclaim field is mandatory.

## F. anti-generic / no-laundering (BLOCKING)
- **F1 no banned phrase in live copy.** no brief's own outward copy contains a banned phrase: `actionable insights`, `single source of truth`, `seamless`, `robust`, `synergy`, `elevate`, `unlock`, `leverage` (as a verb)...
- **F4 no survey math from comments.** no artifact states a percentage-of-customers claim derived from a comment pool.
```

Why this is 5/5: pass/fail is determined by code (`validate_run.py`), not LLM judgment. Seven blocking sections with machine-checkable assertions. A run that violates any of them fails automatically.

---

**Source: `slideshow-kit/tests/` — dual pytest + bats test suite**

```
tests/
  test_concept_corpus.py
  test_concept_meta.py
  test_design_md_parser.py
  test_format_lint.py
  test_format_registry.py
  test_hook_patterns.py
  test_prompt_builder.py
  test_save_filter.py
  test_draft_script.bats
  test_generate_concepts.bats
  test_install.bats
  test_lint_script.bats
  test_doctor.bats
```

Why this is 5/5: a real dual test suite (Python pytest for library contracts + bats for CLI/integration). Quality is not self-reported. It is measured by a test runner that can fail a CI run.

---

## compounding (5/5 exemplar: bigskills itself)

bigskills wires all three parts of the loop, so it is the anchor for a 5/5 compounding score.

1. **Eval ratchet.** `tests/snapshots/` holds a golden set of judge outputs, and the pytest suite gates grading behavior against them. The calibration tests in `tests/test_calibration.py` assert that fixture kits grade to their expected bands, so a regression that moves a kit out of its band fails the run.

2. **Correction-capture.** `kit-review --override <kit> --criterion <id> --score <N> --why "..."` appends a logged human override to the `verdicts/*.jsonl` corpus. The judge few-shot-injects the most recent corrections into its prompt as a CORRECTIONS section, and `tests/test_calibration_lock.py` asserts no snapshot can contradict a recorded correction. Once Matt corrects the model, the judge cannot drift back.

3. **Baseline-comparison.** `scripts/compare-baseline.sh` runs the target task with and without the skill and compares distinctiveness vs vanilla output, the truest magic-moment test.

Why this is 5/5: a growing golden set that fails the run, a logged correction loop that the judge learns from, and a baseline test. A strong validator alone, with no correction-capture loop, caps at 3 to 4.
