# Steal Board design system

Reskin by editing `templates/board/war-room-tokens.css` only (the BFCM War Room skin is
the default). Layout lives in `templates/board/war-room.html.j2`.

| Token | Default | Use |
|---|---|---|
| `--bg` / `--panel` / `--line` | #0b0b0d / #0f1014 / #2a2a2e | page, cards, rules |
| `--txt` / `--mut` / `--dim` | #f2f2f2 / #8a8a90 / #5b6072 | text tiers |
| `--accent` | #d4ff3a | the one accent: the opening, the top label, open formats |
| `--danger` | #ff4d4d | dead formats, the exposed gap card |
| `--font-display` / `--font-mono` | Inter / JetBrains Mono | headlines / data |

## Board order (1200×750 at 2×)
Header (brand, how it's sorted, pulled date, ads in pull, kept running, Black Friday) →
two-line headline with the label legend → **left** "Ads they keep running" (6 cards, two columns: the creative in its real frame (9:16, 4:5, 1:1 or
16:9, never cropped; play badge on video) beside rank, band, verbatim hook, facts-only why)
→ **middle** offers, formats (crowded / worn out / open), hooks → **right** the opening,
steal / skip, counter-ad brief (headline, hook, visual, why it's different from theirs, then
"StealAds can turn this brief into a finished ad (early access at stealads.ai)") → footer
(pulled date + stealads.ai link, nothing else). Ads are named by rank (#01), never by ad ID.
No disclaimer lines. Every word on the board is plain: no codes, no em dashes, no claims
about results.

## Rules
- Every bar is proportional to a real value (discount %, format count). No decorative bars.
- Format colours follow the verdict: open = accent, saturated = grey, dead = danger.
- No numeric scores anywhere (gate B1). Bands are words.
- Text must fit its box at 1200×750; the gate measures clipping in Chromium (C5).
- Slices `#slice-01`…`#slice-05` are separate 1080×1350 sections for the X carousel.

Design references (X bookmark study, Sep–Oct 2026) aren't in the repo; `refs/README.md`
says where to drop them for local work.
