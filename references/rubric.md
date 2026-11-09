# Analysis rubric: hooks and what they pull on, for the ads on the board only

The analyze step reads `winners.json` (top 12 = analysis pool) plus each board ad's copy and
saved creative. It writes `analysis.json` (schema: `schemas/analysis.schema.json`). The
method is Matt's hook teardown (`references/ad-teardown/ad-teardown.md`). Everything you
write here prints on the reader's board: plain words, no em dashes, no claims about results
("scaling", "winning", "proven", "beats"). The field names below are internal and never print.

## Hooks (`hooks[]`)

- `hook_text`: the ad's opening line, copied verbatim from the best source the ad has.
  Priority: **spoken > onscreen > copy**.
  - `spoken`: what the viewer hears first: the ad's `spoken_hook` (the first sentence of
    its `transcript`). Quote any opening span of the transcript. A garbled opening
    (speech-to-text tag, a word repeated, starts mid-sentence, a dropped subject such as
    "because isn't", or source confidence under 0.6) is rejected: `spoken_hook_rejected`
    says why, and the hook falls back to on-screen (the poster frame for a video), then copy.
  - `onscreen`: the headline, else the biggest text, burned into the creative
    (`onscreen_hook`, from StealAds or the agent's own read of the image via
    `onscreen.json`). Video thumbnails count as poster-frame text when there's no transcript.
  - `copy`: the post caption (`copy_hook`: headline, else the first sentence of the body).
- `hook_source`: spoken | onscreen | copy, matching where `hook_text` came from. The board
  tags it "said", "on screen" or "caption". Leaving it out means copy.
- `pattern`: question | contrast | story | shock | curiosity | offer | proof.
- `puppet_string`: the drive it pulls. Exactly one of wealth | health | status-access |
  escape | romance. Fear is not a drive; set `fear_amplifier: true` when urgency or loss
  dials it up.
- `triggers[]`: curiosity | social-proof | scarcity | authority | contrast | identity, each
  with strength subtle | moderate | heavy.

## Gaps (`gaps[]`): the opening

A gap is something **none of their ads do** that the category buys on. Name it in one line
a reader could act on ("None of their ads frame Foldbrook as a holiday gift"). `evidence_ad_ids`
lists the ads that prove the absence (the ones that took the other road). `counter_angle` is
the one-line move. `gap_score` may exist as an internal sort key; it never renders.

An opening that counts who says something ("None of these ads name Black Friday", "2 of
these ads mention the 60-day guarantee, none leads with it") carries `mentions`: the `terms` you searched, the
winners that say one (`ad_ids`), a verbatim `evidence` quote with its `source` (spoken,
onscreen, copy) for every place a term appears, and `leads` (the winners whose opening line
has it) when the lane talks about leading. Search the transcript, the on-screen text and the
copy, never one alone. Gate A6 recounts across all three.

## Steal / skip (`steal_this[]`)

Both lines print on the board next to STEAL and SKIP. Each one is a full plain sentence a
founder gets on first read, with zero context. No brackets, no shorthand, no fragments.

- `template`: the move to borrow, said as an instruction. Good: "Open on an everyday
  slip-up, then blame the cause, not the person." Bad: "Everyday lapses, then: You're not
  getting dumber. Your [X] is depleted."
- `dont_copy`: what's theirs, said as "Skip ... ." plus why. Good: "Skip a 47% off headline.
  Big discounts are what they're known for." Bad: "47% off headline, they own discount".

## Hard rules (the gate enforces each one)

| Rule | Gate code |
|---|---|
| Every offer, hook, gap and steal cites a winner `ad_id` | A2 |
| `evidence` is verbatim in its `evidence_source` (transcript, on-screen text or copy) | A3 |
| `hook_text` is verbatim in its `hook_source` (transcript, on-screen text or copy) | A3 |
| `hook_source` is the best the ad has: no caption hook when a spoken or on-screen one exists | A3 |
| A lane that counts who says something has `mentions`, and its count, ids, quotes and leads match every source | A6 |
| No number in headline, gaps or stats that the ads don't say, show or write, or the pull doesn't count | A4 |
| No hedging (might, maybe, likely, probably, could be, seems, appears to) | E1 |
| No numeric score anywhere visible | B1 |
| `citations_ok: true` only after `ad-spy-kit validate` passes | A2 |

Write like a strategist who checked: short declaratives, the ad id in brackets, no adjectives
the ad didn't earn.
