# Output quality gate

Every rule here is code in `ad_spy_kit/validate_run.py`. It runs at the end of
`ad-spy-kit render` and on its own as `ad-spy-kit validate <run_dir>`. Any error fails the
run (exit 1) and the board isn't final. Warnings print but don't fail. `replay-all` runs
the gate on every fixture; `tests/test_validate_run.py` breaks each rule once on purpose.

## A. Contracts and citations
| Code | Fails when |
|---|---|
| A1 | a run JSON is missing or fails `schemas/*.schema.json` (enums, required fields, lengths) |
| A2 | `citations_ok` isn't true, or a section cites an `ad_id` outside the winners, or a gap cites none |
| A3 | an offer `evidence` or hook `hook_text` isn't verbatim in the cited ad's copy (HTML-unescaped, whitespace-folded) |
| A4 | a number in the headline, stats or gaps is neither printed in the pulled ads' copy nor a count the gate can re-derive (ads scanned, winners, days live, versions) |
| A5 | a `formats[].format` isn't a CIE taxonomy slug (`cie/taxonomy.py`) |
| A7 | a "none of them / no ad" claim in the headline or a gap is contradicted by an ad that is not on the board (young ads included), and the claim neither names it nor limits itself to the board |
| A8 | `#NN` in analysis or counter copy isn't a rank on the board, or "Their #NN ad" isn't the ad the brief answers (`beats_ad_id`) |

## B. Winner policy
| Code | Fails when |
|---|---|
| B1 | a winner carries a hidden score key, or the board shows score text ("score 8", "8/10") |
| B2 | a winner's `why` line hedges |
| B3 | `strength_label` isn't one of the labels in `ad_spy_kit/labels.py` (winner / solid / testing, or none) |
| B4 | winner order doesn't follow `find_winning_ads` order when that's the rank source |

## C. Render
| Code | Fails when |
|---|---|
| C1 | board.html / board.png / og.png / the slices (3 to 5; a slice with nothing to show is skipped) / newsletter.png missing or wrong size |
| C2 | footer lacks `stealads.ai`, or a slice lacks `stealads.ai` |
| C7 | a raw ad ID shows anywhere on the board (ads are named by rank, #01) |
| E2 | board, slices, newsletter or teardown.md prints banned hedge copy (`spend unknown`, `don't copy`) |
| E3 | an em dash in the analysis or counter copy, or on the board outside a verbatim ad quote |
| E4 | a performance claim (scaling, winning, beats, converts, proven, outperforms) in the analysis or counter copy, or on the board outside a verbatim ad quote |
| C4 | board.html loads a remote image (fbcdn links expire; media must be embedded) |
| C5 | text clips its box, a card sits below the fold, the headline is cut off, slice text runs off its edge or into the footer lines, or the counter-ad text runs under its StealAds line (measured in Chromium) |
| C8 | an X slice is essentially empty (under 12% of its body has content) or has a blank block over 470px |
| C6 | *warning:* a winner dropped from the wall for lack of a cached image |

## E. Copy
| Code | Fails when |
|---|---|
| E1 | a hedge (might, maybe, may be, perhaps, likely, probably, seems to, could be…) appears in the headline, gaps, steal/skip or a counter hook |

## K. Captured corrections
| Code | Fails when |
|---|---|
| K`<id>` | a `must_not_contain` rule in `evals/corrections.jsonl` matches the board text or `teardown.md`, or a `must_contain` rule misses the board. Add a line whenever a user corrects a board (`ad-spy-kit correct`); it's enforced from the next run on. |

## Also enforced, outside the gate
- **Determinism:** `ad-spy-kit golden` fails if winners / analysis / counters drift from
  `fixtures/<name>/golden.json`.
- **Adapter shape:** `tests/test_fallbacks.py` maps the old StealAds `list_ads` shape (still accepted) and the
  ScrapeCreators company-ads shape and dedupes on `group_id` before media hash.
- **Speed:** spec §12 asks for a board in under 10s. Fixture replays measure ~5s on the
  build box (render + gate); this isn't a test.
