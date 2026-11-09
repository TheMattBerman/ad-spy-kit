# Format taxonomy and verdicts

Format labels come from the Creative Intelligence Engine taxonomy (`cie/taxonomy.py`,
`cie/taxonomy_catalog.py`, ported from Winning Creative Tracker). Use a catalog slug
as `formats[].format`: `faceless-demo`, `native-photo-long-copy`, `carousel`, `yapper`,
`founder-bts`, … (full list: `cie.taxonomy.ALL_FORMATS`). Don't invent one; pick the
nearest entry. Gate A5 fails the run on any slug outside the list.

`formats[]` rolls up winners only: `count` = winners in that format, `days_live_sum` = sum
of their `days_live`. Both are counts the gate can re-derive from `winners.json`.

| `verdict` | Meaning | Board colour |
|---|---|---|
| `sat` | crowded: the competitor already runs this format a lot | grey |
| `dead` | they ran it ≥30 days and stopped, or it never cleared the w2 floor | red |
| `open` | under-used by their winners: a lane for you | lime |

The verdict logic mirrors `cie/gap_engine.py`: paid strength = Σ days live per format,
and a format with an ended run of 30+ days is a dead end. This kit reads paid ads only, so
gaps come from what the winners' offers, hooks and formats leave out.
