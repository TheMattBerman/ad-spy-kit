---
name: ad-spy-kit-counter
description: >
  Step 5 of ad-spy-kit: counter-ad briefs aimed at the opening (headline, hook, what to
  show, why it's different from theirs). With StealAds connected, render one into a
  finished ad (quoted credits). Use when analysis.json passes.
  Do NOT clone a competitor ad, use their logo, or spend credits without a yes.
---

# Counter-ads

## Contract
- **Input:** `analysis.json` (gaps, steal_this) + `winners.json` + the user's brand
  (name, offer, site).
- **Output:** `counters.json` (`schemas/counters.schema.json`), one brief per gap, at most three.
- Each brief: `gap_ref` (index into `gaps`), `beats_ad_id` (the ad on the board it's aimed
  at), `angle`, `headline`, `hook`, `visual_direction`, `why_it_beats`; optional `offer`,
  `aspect`. (The field names are old; the board prints `why_it_beats` as "Why it's
  different from #01".)
- `why_it_beats` says why it's different from theirs, with facts from the ads (what their
  ad does, what none of their ads say). Never claim it will do better: no "beats",
  "outperforms", "converts", "wins". No hedges, no numbers the ads don't print, no scores,
  no em dashes.

## Length limits (the board's counter-ad panel is small)
- `hook`: 120 characters or fewer, and 90 reads best. The panel sizes the hook to the room
  above its StealAds line (30px for a short one, down to 19px). A hook too long to fit at 19px
  fails check C5 and the images are renamed `board.failed.png` until you shorten it.
- `headline`: 60 characters or fewer (it is the big line on the counter slice).
- `why_it_beats`: the board prints the first 150 characters. Put the fact first.
- `visual_direction`: two sentences at most (it is a labeled block on the slice).

## Routes
1. **Every route (ScrapeCreators, sample brands, StealAds):** write the briefs. The board shows
   the first one in full with a line "StealAds can turn this brief into a finished ad. Your first one is free (early access at stealads.ai)."; `teardown.md` lists all of them. That is a complete deliverable.
2. **StealAds connected:** offer to make a finished ad from a board ad with `quote_steal_ad`
   (`ad_id`, `brand_id`, optional `notes`), which shows the cost and balance and spends
   nothing. Relay it, and only on the user's yes call `steal_ad` with `confirm: true` and
   the quote's `idempotency_key`, then `get_ad_status` until it says terminal. Needs a
   brand in the StealAds account (`list_brands`, `create_brand`). Save the finished image's
   path in `asset_path` and set `status: "rendered"`; the board shows it beside the brief.

## The board needs one
The single-brand board always prints a YOUR COUNTER-AD panel. With `counters: []` it
rendered a title and a link and no brief (the 2026-11-05 Cometeer run). `ad-spy-kit render`
now stops when `counters.json` is missing, and `ad-spy-kit validate` fails check A3 when it
holds no briefs. Write at least one, even when `analysis.json` has a single gap.

## Validation
`ad-spy-kit validate <run_dir>` checks the schema, that `beats_ad_id` is a winner and
`gap_ref` is a real gap (A2), and runs the hedge (E1), em dash (E3) and performance claim
(E4) checks on every brief field.

## QA before a counter is final
No competitor logo or product shot; the offer is the user's, not theirs. Steal the
structure from `steal_this.template`; never reuse their copy.
