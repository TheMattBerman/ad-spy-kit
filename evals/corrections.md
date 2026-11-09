# Corrections that compound

When Matt (or any user) corrects an output, capture it as a rule the gate enforces on every
future run, so the same mistake cannot ship twice:

```bash
uv run ad-spy-kit correct --rule must_not_contain --pattern '(?i)\bjust \$\d' \
  --reason "no 'just $X' price framing"
```

- Appends one line to `evals/corrections.jsonl` (`id`, `date`, `rule`, `pattern`, `reason`).
- `ad-spy-kit validate` and every `replay`/`render` gate run all of them against the visible
  board text (`K<id>` errors block the run).
- `uv run pytest tests/test_validate_run.py` proves each committed correction holds on every
  fixture.

Rule types: `must_not_contain` (regex must not match) and `must_contain` (regex must match).

Ranking changes are a separate ratchet: `ad-spy-kit golden` fails if winner order, why
lines, dedupe or gap citations drift from `fixtures/<name>/golden.json`. Re-record with
`ad-spy-kit golden --update` only when the change is intended, and say why in the commit.

Kit-review overrides (vendored bigskills) are separate again and only matter once an
official grade exists; see `evals/run_kit_review.py`.
