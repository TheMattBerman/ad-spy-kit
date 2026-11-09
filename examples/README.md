# Examples

Four finished boards, rebuilt by `uv run ad-spy-kit replay-all` into
`artifacts/screenshots/<name>/`.

- **Spacegoods** is a real recorded run on a public brand (recorded Oct 28, 2026). It's a
  sample, not a verdict on them.
- **Foldbrook, Dewbar and Fizzwell are made-up brands** with made-up ads. Every one of their
  boards says "made-up sample brand" in the header.

| Board | Shows | Open |
|---|---|---|
| Spacegoods (real recording) | video ads with spoken hooks, discounts said out loud, a guarantee none of them lead with | [board](../artifacts/screenshots/live/spacegoods/board.png) · [text version](../artifacts/screenshots/live/spacegoods/teardown.md) |
| Foldbrook (made-up wallets) | a deep discount and VIP early access; nobody sells the gift | [board](../artifacts/screenshots/foldbrook/board.png) · [text version](../artifacts/screenshots/foldbrook/teardown.md) · [slices](../artifacts/screenshots/foldbrook/x-slices/) |
| Dewbar (made-up skincare) | sets and a free gift instead of a flat discount; nobody shows skin that changed | [board](../artifacts/screenshots/dewbar/board.png) · [text version](../artifacts/screenshots/dewbar/teardown.md) |
| Fizzwell (made-up soda) | 12-pack discount, subscribe and save, free shipping; nobody puts it at the party | [board](../artifacts/screenshots/fizzwell/board.png) · [text version](../artifacts/screenshots/fizzwell/teardown.md) |

Each folder also has the JSON the board was built from (`winners.json`, `analysis.json`,
`counters.json`) and `validation.json`, the check report.

## What a plain answer says vs what the board says (Foldbrook)

| A plain chatbot answer | The board |
|---|---|
| "Foldbrook is running a mix of discount-focused ads." | "Foldbrook has 4 Black Friday ads still running." Each one is on the board with how long it has run. |
| "Their top ad likely drives strong ROAS." | "Live 41 days · 12 versions · still running", which is what the data shows. |
| "Consider testing a gifting angle." | "None of them sell the gift." Then the brief: "Stop buying wallets that feel like stocking stuffers." |

## Your own run

```bash
export SCRAPECREATORS_API_KEY=...        # or put it in .env
uv run ad-spy-kit run "Brand Name" --out runs/brand          # prints the cost, spends nothing
uv run ad-spy-kit run "Brand Name" --out runs/brand --yes    # go
# your agent writes runs/brand/analysis.json (skills/ad-spy-kit-analyze), then:
uv run ad-spy-kit render runs/brand
```
