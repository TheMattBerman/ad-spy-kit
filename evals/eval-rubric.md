# How this kit is evaluated

Three layers, cheapest first. Only the first two run without keys.

| Layer | Command | Blocks? | What it proves |
|---|---|---|---|
| Output gate | `uv run ad-spy-kit validate <run_dir>` (runs inside `render`) | yes, exit 1 | every board rule in `output-quality-rubric.md`, plus captured corrections |
| Ratchet | `uv run ad-spy-kit golden` · `uv run pytest -q` | yes | winners / analysis / counters don't drift per fixture; each gate rule fails when broken; fallbacks and error messages behave |
| Baseline | `bash evals/compare-baseline.sh` (`--write` saves `baseline/kit/` + `results.md`) | yes, exit 1 | kit board vs a vanilla-agent answer on the same ads (citations, verbatim quotes, uncited numbers, hedges). Fails if the kit loses to vanilla. Vanilla captures in `evals/baseline/vanilla/` come from `baseline/PROMPT.md` (`evals/capture_vanilla.py`, one API call each). |
| Shell + CLI | `bats tests/bats` (or `bash scripts/test.sh` for everything) | yes | install / uninstall / doctor in a temp HOME, CLI steps end to end, and the baseline. |
| Kit review | `bash evals/run-kit-review.sh api` (OPENROUTER_API_KEY) or `subagent` | no | bigskills grade (Gold / Strong / …). `cached` runs the compliance scan, then replays a recorded judge snapshot if one exists (none does; exit 3). |

Status on 2026-10-29: gate, ratchet, baseline and bats pass on all 4 fixtures (Foldbrook,
Dewbar, Fizzwell, live Spacegoods). Vanilla captures: gpt-4.1, one call each, 2026-10-29.
Kit 100% verbatim quotes, 0 uncited numbers, 0 hedges; vanilla 12-34% verbatim, 9-13
uncited numbers (`baseline/results.md`). No official kit-review grade yet (`kit-review-score.json` says
ungraded). `self-assessment.md` is a hand score, not a grade.
