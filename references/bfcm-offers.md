# BFCM offer lexicon

Used by the analyze step to fill `offer_map[]`. `evidence` is always the shortest verbatim
substring that proves the type, from one source named in `evidence_source`: `spoken`
(transcript), `onscreen` (on-screen text) or `copy` (headline, body or CTA; the default).
Gate check A3 looks for it in that source only. The board tags it "said", "on screen" or
"caption".

| `offer_type` | Counts when the copy says | Example evidence |
|---|---|---|
| `pct_off` | N% off, up to N% off, N% discount | `47% off` |
| `dollar_off` | $N off, save $N | `$20 off` |
| `bogo` | buy one get one, 2 for 1 | `BOGO` |
| `bundle` | set, bundle, kit, "the carry system" | `Bundle the carry system` |
| `gift_with_purchase` | free gift, GWP, "with every order" | `free tote with orders` |
| `free_shipping` | free shipping, ships free | `ships free` |
| `early_access` | VIP, early access, waitlist, SMS list, presale | `VIP early access` |
| `price_drop` | new price, lowest price ever, no % shown | `lowest price of the year` |
| `price_claim` | a price comparison with no "off" and no price it fell from: "up to 80% less than you'd expect", "cheaper than the rest", "our full price < their sale price" | `up to 80% less than you’d expect` |
| `guarantee` | money-back guarantee, full refund, risk-free trial | `60-day money-back guarantee` |
| `none` | no offer in the copy (brand or product ad) | the hook itself |

A `price_claim` has no `discount_depth` and never feeds the board's TOP DISCOUNT number or a
ladder bar (gate A9 fails a comparison filed as `pct_off` or `dollar_off`).

`discount_depth`: the value exactly as written (`47%`, `$20`, `3 full sizes`), or the
access word (`VIP`). Never compute or round a depth the ad doesn't print. Ladder bars are
drawn from percents only (they share a scale); other depths show as a label with no bar,
and the big number is the deepest cited percent.

`urgency`: `countdown` (ends tonight, 48 hours, last chance), `date` (a named day or date),
`stock` (while supplies last, low stock), `none`.

## BFCM phase tag (deterministic, `ad_spy_kit/score_winners.py`)

- `bf_teaser`: early access, VIP, waitlist, SMS/launch list, presale.
- `bf_live`: black friday, cyber monday, bfcm, doorbuster, N% off, bundle, gift, ends,
  last chance, holiday sale.
- `evergreen`: neither.

Teaser wins over live when both match, because a VIP ad that mentions a % is still a list
builder.
