---
name: ad-spy-kit-render
description: >
  Step 6 of ad-spy-kit: render the Steal Board (board.png/html, 5 X carousel slices,
  newsletter and OG crops) from a run folder, then run the blocking quality gate. Use
  when analysis.json exists, or to re-render after an edit. Do NOT use to change the
  analysis; fix the JSON and re-render instead.
---

# Render + gate

```bash
uv run --project "$KIT" ad-spy-kit render <run_dir>
```

Writes a self-contained `board.html` (media embedded as base64, each image at most 1200px
long edge), then screenshots it with Playwright Chromium, then runs
`ad_spy_kit/validate_run.py`. Exit 0 = final. On a failed check the drawn images are renamed
`board.failed.png`, `newsletter.failed.png`, `og.failed.png` and `x-slices.failed/`, so
nothing looks final; fix the JSON and render again (a pass removes the `.failed` files).

| File | Size |
|---|---|
| `board.png` | 2400×1500 (1200×750 at 2×) |
| `og.png` | 1200×630 |
| `x-slices/01-05.png` | 1080×1350. A slice with nothing to show (no offer with a quote) is skipped, so 3 to 5 slices |
| `newsletter.png` | 1200 wide |
| `teardown.md` | swipe file, one section per winner |
| `validation.json` | gate report |

## The gate (fails the run; codes in `evals/output-quality-rubric.md`)
Schemas · citations to winners · verbatim quotes · no uncited numbers · no hedges · no
score text · bands and order · "N newer ads not shown" claims (A7) · rank refs (A8) ·
no blank slice, no 470px+ blank block in a slice (C8) · no `{{...}}` catalog placeholder on the board, a slice or `teardown.md` (C9) · text that
runs off a slice or under the footer or under the counter-ad's StealAds line (C5) · PNG sizes · footer (`stealads.ai`) · no hedge
lines (`spend unknown`, `don't copy`, gate E2) · no hotlinked media · no clipped text or card below
the fold · every captured correction.

## Layout rules
Tokens in `templates/board/war-room-tokens.css` (`references/design-system.md`). A winner
with no cached image drops off the wall and the next one moves up (`dropped_no_media`).
Bars are proportional to real values (discount depth, format count), never decorative.
