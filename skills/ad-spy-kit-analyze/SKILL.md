---
name: ad-spy-kit-analyze
description: >
  Step 4 of ad-spy-kit: you (the agent) read the board's ads (copy and creatives) and write
  analysis.json: offers, hooks, which formats are crowded or open, the opening none of them
  use, steal/skip. Use when winners.json exists. Do NOT use on ads that aren't on the board,
  and do NOT estimate spend, reach or results.
---

# Analyse

Runs on your own model in the session; no API key. StealAds `get_competitor_analysis`
(a tracked competitor) and `create_playbook` are optional extras. `create_playbook` can
spend credits: show its cost preview first.

## Contract
- **Input:** `winners.json` (pool = top 12), each board ad's copy in `ads.raw.json`, and its
  image in `media/` (look at it).
- **Output:** `analysis.json`, schema `schemas/analysis.schema.json`.
- **Post:** check every quote and ad number against `ads.raw.json` yourself, then set
  `citations_ok: true` and run `ad-spy-kit validate <run_dir>`. It must pass A1-A8 and E1
  (A2 fails while `citations_ok` is not true).

## Read the ads that are NOT on the board first
The board holds 6 ads, but a headline or an opening speaks for the brand. Before you write
either, read every ad in `ads.raw.json`, and `winners.json` `hidden[]` (young ads held back,
with headline and sale tag). The `bf_tag` of a hidden ad is `bf_live` when its copy says
Black Friday, a % off, a bundle or a gift. Rules:
- A "None of them name Black Friday or a price" is false if any ad says it, shown or not.
  Check A7 fails it. Name the ad ("One newer ad says up to 70% off.") or limit the claim:
  "None of the 6 ads on this board name a price."
- Count hidden ads in `headline.top` when they matter ("6 ads on this board, 10 newer ones
  not shown.").
- `analysis.headline.top` is optional. It prints under the headline on the X summary slice
  and in `teardown.md`, never on the 1200×750 board. Leave it out when `bottom` says it all.
- `#04` in any of your copy is a board rank. Check A8 fails a rank the board doesn't have,
  and a counter brief whose "Their #04 ad" isn't its `beats_ad_id`.
- An `offer_map` row with no `evidence` quote is left out. Don't add `none` rows.

## Read before writing
- `references/rubric.md`: field-by-field rules, hook patterns and trigger enums.
- `references/bfcm-offers.md`: offer types, depth, urgency.
- `references/taxonomy.md`: format slugs and sat / dead / open.
- `references/ad-teardown/ad-teardown.md`: the full hook teardown method, if stuck.

## Hooks: take the one the viewer meets first
Each ad in `ads.raw.json` carries `spoken_hook`, `onscreen_hook`, `copy_hook` and
`hook_source` (the best one present). Write `hook_text` from that source and set
`hook_source` to match: **spoken** (first sentence of `transcript`) > **onscreen** (text in
the creative) > **copy** (post caption). A3 checks the quote against that source and fails a
caption hook when the ad has a spoken or on-screen one. Only fields in `ads.raw.json`
count: never transcribe audio yourself, and record what you read off an image through
`onscreen.json` first (below), never straight into `analysis.json`.

## Garbled transcripts
When `spoken_hook_rejected` is set, the transcript opening is a bad transcription. Don't
quote it or tidy it up: `ad-spy-kit onscreen` lists that video's thumbnail as a poster frame;
read it and use its headline, else the caption. A3 fails a spoken hook on a rejected ad.
Offers may still quote a clean later sentence of the transcript.

## On-screen hooks: read the board's images yourself (free route, no OCR service)
Run `ad-spy-kit onscreen <run_dir>`. It lists every board image (role `creative`) and
every board video with no spoken hook (role `poster-frame`, its thumbnail). Open each file
with your own vision and record, verbatim, in `<run_dir>/onscreen.json`:
```json
{"source": "agent-vision", "items": [{"ad_id": "…", "role": "creative",
  "read_from": "media/<ad_id>.jpg",
  "onscreen_text": "every overlay line, top to bottom, one per line",
  "onscreen_hook": "the headline; with no headline, the biggest text"}]}
```
Copy spelling, typos and emoji exactly as printed. Leave out product-pack labels and
logos. An image with no words on it (a product shot, a catalog photo) is
`{"ad_id": "…", "onscreen_hook": null, "no_text": true}`: it counts as read, the ad keeps
its caption hook, and the list stops showing it. Then `ad-spy-kit onscreen <run_dir> --apply` writes it into ads.raw.json and the
hook becomes `hook_source: "onscreen"` (tag "on screen"). A3 checks your hook against the
stored `onscreen_hook`. When StealAds rows already carry on-screen fields, the list is empty.

## Catalog and dynamic ads (`catalog: true`)
Catalog (DPA) and dynamic (DCO) ads store `{{product.name}}` for the headline and sometimes
`{{product.brand}}` for the caption. The kit empties any text with `{{...}}` when it reads the
ads, so `headline` is "" and the hook is the first real caption line. An ad with no real
text at all has no hook: don't write one for it, and don't put it in `hooks`. The board tags
these "catalog ad". A `{{` anywhere on the board, a slice or `teardown.md` fails check C9.

## Offers: from what the ad says, shows or writes
Each `offer_map` row quotes `evidence` verbatim from one source and names it in
`evidence_source`: `spoken` (the transcript), `onscreen` (`onscreen_text`) or `copy`
(headline, body, CTA; the default). The board tags each rung "said", "on screen" or
"caption". One row per offer per ad: a video saying "58% off plus five free gifts" gets a
`pct_off` row and a `gift_with_purchase` row. A3 fails a quote that isn't in its source.

**A price comparison is not a discount.** "Up to 80% less than you'd expect", "Our full price
is lower than their sale price" and "cheaper than the rest" have no "off" and no price they
came down from. Use `offer_type: "price_claim"` and leave `discount_depth` out. Only
`pct_off` and `dollar_off` rows (a real "30% off", "$20 off") feed the board's TOP DISCOUNT
number. Check A9 fails a comparison filed as pct_off or dollar_off. The same quote from
several ads is shown once on the offers slide, naming the other ads ("#02, #05").

## The opening: count across every source
Before writing "None of their ads…", "Only N of these ads…" or "none leads with…", search each ad's
`transcript`, `onscreen_text` and copy for the terms, and add `mentions` (rubric:
`references/rubric.md`, Gaps) with a verbatim quote and source for every hit. A6 recounts
across all three sources and fails an opening counted from one.

## Steal / skip (full sentences, see `references/rubric.md`)
Each line is one plain sentence a founder gets on first read. Steal: "Open on an everyday
slip-up, then blame the cause, not the person." Skip: "Skip their "You've tried
everything." caption. It's theirs." Never brackets or fragments like "Your [X] is depleted".

## Headline (it prints on the reader's board, so write it for a busy founder)
Two lines. Top: what they're doing, a count the data proves ("Foldbrook has 4 Black Friday
ads still running."). Bottom: the opening, 60 characters or fewer ("None of them sell the
gift."). Plain words only:
- No hedges ("might", "likely", "seems").
- No performance claims. We see what ran, not what worked: never "scaling", "winning",
  "proven", "converts", "beats". Say "still running", "they keep running it", "they've
  made 9 versions".
- No em dashes. Use a period, comma or colon.
- No method words ("lane", "corpus", "floor", "puppet strings", "pull"). Say "the
  opening", "their ads", "we checked 24 ads".
The gate blocks em dashes (E3) and performance claims (E4) in every field you write.

## The five ways this step fails (the gate catches all five)
1. A quote that is a paraphrase, or tagged with the wrong source → A3. Copy-paste from the
   source text.
2. A number the ads don't print ("$93k spend", "3x ROAS") → A4.
3. Citing an ad that isn't on the board → A2.
4. "might / likely / seems" → E1. If you aren't sure, leave it out. An em dash → E3.
   "Scaling", "winning", "proven", "beats" → E4.
5. An opening counted from the caption alone ("Only 1 ad puts the refund in its copy" when
   two videos say it) → A6.
