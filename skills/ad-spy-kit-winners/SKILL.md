---
name: ad-spy-kit-winners
description: >
  Step 3 of ad-spy-kit: pick and sort the ads they keep running, from ads.raw.json to
  winners.json, with the shared labels. No model. Use when ads.raw.json exists. Do NOT use
  to judge creative quality or to score ads; this step only orders what kept running.
---

# Sort and label (winners.json)

## Contract
- **Input:** `<run_dir>/ads.raw.json`. **Output:** `<run_dir>/winners.json`.
- Run: `ad-spy-kit winners <run_dir>`. Same input → same output, frozen per sample brand by
  `fixtures/<name>/golden.json` (`ad-spy-kit golden` fails on drift).

## Rule
- **Eligible:** active AND (`days_live` ≥ 7 OR `variation_count` ≥ 3). The rest go to
  `quarantined[]` with the reason.
- **Order:** `find_winning_ads` rank first (old name `find_bangers`); unranked eligible ads after, by days live then
  versions. winners.json records which order applied; the board says "labels and order
  from StealAds" or "sorted by how long each ad has run".
- **Dedupe:** StealAds `group_id` or the same image hash (either joins two ads into one
  creative); with neither, headline + body + landing URL. The kept ad lists `dupes_merged`,
  and the board says "N versions" and counts creatives, not copies.
- **Held back, never hidden:** quarantined ads stay in `quarantined[]` (with headline, body,
  `bf_tag`). Up to 2 sale or early-access ones (`bf_live`, `bf_teaser`) still go on the board as
  testing (`added_while_new: true`), taking a free spot or the place of an ad that is also
  under 7 days old, never an ad that has run a week. A board under 6 ads fills up with the
  newest live ads. The rest is `hidden[]`: distinct creatives not on the board and not a
  copy of one. The board prints "N newer ads not shown".
- **Tag:** `bf_live` | `bf_teaser` | `evergreen` (`references/bfcm-offers.md`).
- **Board:** top 6. **Analysis pool:** top 12. Fewer than 3 → `thin_signal: true`.

## Labels (one rule, `ad_spy_kit/labels.py`)
- StealAds rows: the label StealAds sent, passed through ("banger" and "winner" both mean
  the top label). No label from StealAds means unanalyzed: no label.
- Every other row (mirrors StealAds #3343): winner = still running 120+ days, or 60+ days
  with 3+ versions, or stopped after 365+ days with 3+ versions, or 540+ days; solid = 30+
  days, or 14+ days with 3+ versions; testing = still running under 30 days; no label =
  unknown start date, or stopped before 30 days.

## Never
Show or write a numeric winner / effectiveness score. The board gets rank, `strength_label`
(winner | solid | testing) and a facts-only `why` ("Live 41 days · 12 versions · still
running"). Gate B1 fails the run on any score key or "score N" text.

Known deviation: the spec tie-breaks on `effectiveness_score`, but the adapter drops that
field (it's hidden), so ties fall back to days live then versions.
