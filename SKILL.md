---
name: ad-spy-kit
description: >
  Tear down a competitor's Meta ads into one board: the ads they keep running (sorted by
  how long each has run, labeled winner / solid / testing), every hook and offer quoted
  word for word, the opening none of them use, and counter-ad briefs. Also runs a whole
  category: several brands on one sorted board, or the competitors a StealAds user already
  tracks. Use when the user says "tear down <brand>'s ads", "what is <brand> running for
  Black Friday / BFCM", "spy on a competitor's ads", "spy on my category", "sort my
  competitors' ads", "show me what my competitors keep running", "competitor ad teardown",
  "steal board", or wants counter-ads against a named brand. Do NOT use for: analysing the user's
  own ad account or spend/ROAS (no spend data exists here), organic social or SEO research,
  a single ad screenshot with no brand (use an ad-teardown skill), or writing ads from
  scratch with no competitor.
license: MIT
metadata:
  version: 1.6.0
  author: Matt Berman (@TheMattBerman)
---

# ad-spy-kit

One competitor in, one board out (or several brands in, one category board out). The board
is the deliverable; everything else is plumbing for it. `KIT` below means the directory this
file lives in (plugin installs: `${CLAUDE_PLUGIN_ROOT}`). Every command is
`uv run --project "$KIT" ad-spy-kit …`.

## Step 0: first run (do this before anything else)

1. Run `bash "$KIT/doctor.sh"`. If it reports missing Python deps or no Chromium (always
   the case on a fresh `npx skills add` install), run:
   `uv sync --project "$KIT" && uv run --project "$KIT" playwright install chromium`
2. No data source yet? Show a sample board: `ad-spy-kit replay --sample foldbrook` (a
   made-up brand, offline, about 5 seconds, free). Say it's a made-up sample brand.

If any command prints "Chromium isn't installed", run the fix line it prints, then retry.

## How the board decides

1. **On the board.** Ads that ran 7+ days or have 3+ versions, still running. Deterministic
   (`ad_spy_kit/score_winners.py`), no model. Near-identical creatives (same StealAds group
   or same image) count once and show "N versions" (with ", different captions" when the
   merged ads carry different copy; `teardown.md` lists the lines). Ads under 7 days with under 3 versions
   are held back (`winners.json` `quarantined[]`), with two exceptions so the board never
   silently misleads: up to 2 sale or early-access ads still go on, labeled testing, and a
   board under 6 ads fills up with the newest live ads. Whatever is still held back is counted
   on the board ("N newer ads not shown") and listed in `winners.json` `hidden[]` and
   `teardown.md`.
2. **Order and labels.** StealAds order when the data came from StealAds; else
   sorted by how long each ad has run, with labels from the shared rule
   (`ad_spy_kit/labels.py`, mirrors StealAds #3343): winner = live 120+ days, or 60+ days
   with 3+ versions; solid = 30+ days, or 14+ days with 3+ versions; testing = live under
   30 days; no label = start date unknown, or stopped before 30 days.
   **Never a numeric score.**
3. **Quote.** Every offer, hook and gap points at a real ad, quoted word for word. A hook
   comes from what the viewer hears first, then on-screen text, then the caption, and the
   board says which ("said", "on screen", "caption").
4. **The opening.** What none of their ads say that the category buys on.
5. **Counter.** Steal the structure, never the ad. Up to three briefs aimed at the opening.

## Routing: run the steps in order, skip a step whose output already validates

| # | Step | Read | Writes |
|---|---|---|---|
| 0 | First run | this file, Step 0 | browser installed; sample board |
| 1 | Find the brand's page | `skills/ad-spy-kit-resolve/SKILL.md` | `competitor.json` |
| 2 | Pull their ads | `skills/ad-spy-kit-pull/SKILL.md` | `ads.raw.json`, `media/` |
| 3 | Sort and label | `skills/ad-spy-kit-winners/SKILL.md` | `winners.json` |
| 3b | Read the board's images (you, the agent): `ad-spy-kit onscreen <run_dir>` lists them, you look at each and record its text (or `"no_text": true`), then `--apply` | `skills/ad-spy-kit-analyze/SKILL.md` (On-screen hooks) | `onscreen.json` → `ads.raw.json` |
| 4 | Analyse (you, the agent). **Read the ads that are not on the board first** (below) | `skills/ad-spy-kit-analyze/SKILL.md` | `analysis.json` |
| 5 | Counter-ads (1 to 3 briefs; the board's counter-ad panel needs one) | `skills/ad-spy-kit-counter/SKILL.md` | `counters.json` |
| 6 | Render and check | `skills/ad-spy-kit-render/SKILL.md` | `board.png`, slices, `validation.json` |
| C | Category run (several brands) | below | `board.png`, `x-slices/`, `summary.md`, `category.json` |
| T | Tracked competitors ("my competitors") | below | `board.png`, `x-slices/`, `summary.md`, `category.json` |

Run folder: `runs/<slug>/` (or `--out`). Steps 1-3 in one go with ScrapeCreators:
`ad-spy-kit run "<brand>" --yes` (after the user says yes to the quote). The user can give
a brand name, a page ID, or an Ad Library page link (`view_all_page_id=`). A sample brand
name (`foldbrook`, `dewbar`, `fizzwell`) replays offline and says it's made up.

The CLI only pulls and sorts. **You write the analysis** (steps 3b to 5); the board exists
only after `ad-spy-kit render`. Tell the user that plainly, and run the steps yourself.

`ad-spy-kit winners` (and `run`) can print a "Thin read" note: the longest run is under 120
days, or fewer than 80% of the ads are different creatives (catalog and duplicates). Relay it
word for word with its cost. On their yes, `ad-spy-kit pull <run_dir> --max-ads 60 --yes`, or
`--min-days 120` to read only ads already running 120+ days (same cost as the first read).
Never describe a thin read as the brand's whole picture.

`run` reads ads live 30+ days. When the brand has none (a young account, a new campaign), it
reads their newest ads in the same run, with the page it already found, and the quote says
up front what both reads can cost. `--max-credits N` is a hard cap on the whole run: it
refuses to start when the first read could pass it, and skips the second read (printing the
exact `--newest` command to rerun) when that wouldn't fit. Never make the user pay for a
second page lookup.

### Before you write a headline or a "none of them" claim

The board holds 6 ads. `ads.raw.json` holds every ad checked, and `winners.json` lists
`hidden[]` (young ads not shown) with their headlines. Read all of them, not just the six,
before writing the headline, a gap, or any "none of them / no ads / nobody" sentence. If a
hidden ad says the thing (a sale, Black Friday, a price, free shipping, a guarantee), either
name it ("One newer ad says up to 70% off.") or limit the claim to the board ("None of the 6
ads on this board name a price."). `validate` fails check A7 when a "none" claim is
contradicted by an ad that is not on the board. Check A8 fails a "#04" that isn't a rank on
the board, and a "Their #04 ad" that isn't the ad the brief answers.

### Category run

Trigger: "spy on my category", "sort my competitors' ads", "tear down every brand running
Black Friday <category> ads". Run `ad-spy-kit category "<keyword>"` or
`ad-spy-kit category "Brand A, Brand B"`. It prints a quote and spends nothing. Relay the
quote, and on a yes rerun with `--yes`. It reads each brand's ads live 30+ days (up to 30; `--newest` for the newest), labels them
with the shared rule, and writes `board.png` (images embedded), `x-slices/` and `summary.md`.
A category board shows at most 10 brands, 3 ads each (StealAds caps its own category pulls
at 10 brands x 10 ads), so a keyword run reads up to 10 and naming more than 10 is refused.
Show the board, then the label counts. `--from <folder>` redraws a saved run for free.
For a long brand list use `--brands-file <csv>` (name, page_id, country), always with
`--max-credits`: it reads every brand, and the board shows the top 10. A rerun with the
same `--out` resumes for free.

### Tracked competitors ("show me what my competitors keep running")

Trigger: the user means the rivals they already track in StealAds, not a keyword. Free: the
reads spend no credits (they share a daily reading allowance, so keep them modest).
1. `list_brands`. One brand: use it. Several: ask which (never assume the first is the main
   one). Remember its `id` (the `brand_id`).
2. `list_competitors(brand_id, limit=50)` with `response_format` unset (it has none; it is
   JSON). Save each page byte for byte as `<run_dir>/list_competitors.json`, then
   `list_competitors.page2.json` (follow `next_cursor` while `has_more`; a 400-rival
   workspace is 9 pages, 2 or 3 is enough here). It adds each rival's Facebook page id and
   country. A rival with `count_status: "pending"` (`ads_tracked_label: "Count pending"`,
   `ads_tracked: null`) has no ad count yet: that is not an error and not zero. A count
   labelled `218+` is capped (`ads_tracked_capped: true`).
3. Read the ads with `response_format: "json"`, one rival at a time (free, and the allowance
   stays small):
   `list_tracked_rival_ads(brand_id, competitor_id=<id from list_competitors>, status="live",
   min_run_days=30, limit=10, response_format="json")`. Take the rivals the user names first,
   then the biggest by `ads_tracked` (skip `Count pending` ones unless named; a rival that
   returns `NOT_FOUND` is skipped). Save each reply as `<run_dir>/tracked_rival_ads.<rival>.json`.
   A rival can return an empty page with `has_more: true` ("Nothing matched yet in the first 5
   rival pages"): that rival has no ads live 30+ days in the pages searched; do not chase it.
   About 12 to 14 calls fill a 10-brand board (10 ads each is plenty). An unfiltered call
   (no `competitor_id`, `limit: 50`) returns up to 3 rivals newest first, but its `next_cursor`
   keeps going through the same rival (prod 2026-11-06: page 2 was 50 more rows of one
   brand), so use it for one first page at most. A large reply is not printed: Claude Code saves
   it to a tool-results file and prints the path; copy that file (`cp`), never retype it.
   `compact` stays at its default (captions cut to 280 characters, `body_text_truncated`
   says so); pass `compact: false` only for a rival whose full copy you need. Say how many
   pages you read.
4. Error "exceeds the tool's read limit" (older builds, 428-rival BFCM workspace; gone on prod 2026-11-06): fall back to up to 12 rivals the user names, or the biggest by `ads_tracked`: for
   each, `list_tracked_rival_ads(brand_id, competitor_id, ...)` as in step 3. Last resort:
   `search_ads(query="<rival name>", brand_id, competitor_id, tracked_rivals_only=true,
   min_run_days=30, max_results=24)`, saved as `tracked_rival_ads.<rival>.md`.
5. `ad-spy-kit tracked <run_dir> --title "<brand name>"`. It writes one folder per rival
   under `brands/` (competitor.json from the rows, ads.raw.json with `schema_version`,
   images), then the category board: the top 10 rivals by number of ads live 30+ days, 3
   ads each, StealAds' own labels. `ads.csv` carries each ad's CTA, landing domain and
   whether it has a spoken hook. Nothing to analyse: no `analysis.json` is needed. Show
   `board.png`, then the label counts and the brand with the most long-running ads.
   `ad-spy-kit ingest <run_dir>` does the same when the folder holds only
   `tracked_rival_ads*` files.
6. Say it plainly: these are ads from the rivals read, not the whole set. Never give a total
   for the workspace.

## Data source: pick the first that works, say which one you used

1. **StealAds tools in this session** (`search_advertisers`, `search_ads`,
   `find_winning_ads`): this is the primary path, and it spends nothing. Every call passes
   `response_format: "json"` (the default is Markdown text, which carries less). The flow:
   1. `search_advertisers(query="<what the user typed>", response_format="json")`. It takes a
      brand name, a domain (`quince.com`), a Facebook page id or an Ad Library page link. Save
      the reply as `<run_dir>/search_advertisers.json`, then
      `ad-spy-kit advertiser <run_dir>/search_advertisers.json --query "<what they typed>"`.
      One hit: it writes `competitor.json`. Several: it lists them, ask the user. **Not in
      StealAds** (`status: "not_indexed"`, `can_pull: false`): it prints the plain message
      and exits 2. Relay that message as is, then take the ScrapeCreators path (below,
      `ad-spy-kit run "<brand>"` prints its quote and spends nothing until the user says yes).
      StealAds' own fetch for a missing brand runs in the StealAds app; pulling through the
      MCP isn't live. Say that as an option, never as something you can do. Never reuse a page
      id from a fixture, and never take a fuzzy suggestion as the brand.
   2. `search_ads(query="<brand>", facebook_page_id=<id>, brand_id=<id if the workspace has one>,
      format="static", min_run_days=30, max_results=24, response_format="json")` and the same
      with `format="video"`. Save each reply as `search_ads.static.json` and
      `search_ads.video.json`. A reply is a raw JSON object: when it is large, Claude Code
      saves it to a tool-results file and prints its path. Copy that file (`cp`), never retype
      JSON, and say whether every saved file is byte-faithful. An empty `ads` list is saved
      the same way. A page with `next_cursor` and `has_more`: call again with `cursor` and
      save it as `search_ads.video.page2.json` (or `.static.`). A library search is a capped
      sample (often 1 to 5 ads a page for one brand, with empty pages that still have
      `has_more`), so when the brand is one of the user's tracked rivals, use
      `list_tracked_rival_ads(brand_id, competitor_id, status="live", min_run_days=30,
      limit=50, response_format="json")` saved as `tracked_rival_ads.json` instead: it returns
      far more rows for that brand.
   3. `find_winning_ads(query="<brand>", facebook_page_id=<id>, min_run_days=30,
      max_results=24, response_format="json")` → save as `find_winning_ads.json`. Its order is
      the board order.
   4. `ad-spy-kit ingest <run_dir>` (it writes `competitor.json` from the saved rows when
      you haven't, and says which page it picked). It reads the JSON rows (CTA, landing
      domain, spoken and on-screen hooks, carousel cards, group ids, platforms, first and last
      seen) and records the rows' `schema_version` and `reply_format` in `ads.raw.json`. A
      Markdown text reply saved by an older run still reads. Then the routing table from
      step 3 on.
   Tracking, scans, playbooks and making ads are optional extras that show a cost preview
   first and need the user's yes (spend gate below). See `docs/stealads-mcp.md`.
2. **No StealAds tools, `SCRAPECREATORS_API_KEY` set:** `ad-spy-kit run "<brand>"` (quote
   first, below). Same boards and labels.
3. **Neither:** show a sample brand, then tell the user both options, StealAds first:
   - StealAds (primary, early access): get access at https://stealads.ai, then
     `claude mcp add --transport http stealads https://mcp.stealads.ai/mcp` and `/mcp` to
     connect, signed in at https://app.stealads.ai first (other agents: add `https://mcp.stealads.ai/mcp` as a remote HTTP MCP server).
   - ScrapeCreators key: get one at https://scrapecreators.com, put
     `SCRAPECREATORS_API_KEY=...` in a `.env` in the folder they run from. Works today.
   Never fake data.

## Spend gate: quote first, every path

Nothing that costs credits runs without the user's yes. Every spending command prints its
own quote and spends nothing until rerun with `--yes`:

- `ad-spy-kit run "<brand>"`: "This finds the Facebook page for <brand> and reads up to
  its 30 most-shown ads that have been live 30+ days: about 2 ScrapeCreators credits. If
  none of their ads has run 30+ days, it then reads their newest 30 live ads in the same
  run: 1 ScrapeCreators credit more, 2 to 3 ScrapeCreators credits in all." Relay it word for
  word, ask "Go?", and only then rerun with `--yes`. Add `--max-credits N` when the user
  names a ceiling.
- `ad-spy-kit resolve` / `ad-spy-kit pull`: same, 1 credit to find a page, 1 per page of ads.
- `ad-spy-kit category …`: quotes the search plus reading each brand.
- `ad-spy-kit transcripts <run_dir>`: 1 credit per video, 0 when cached in the last 7 days.
  If the user opted in to OpenRouter, the quote names the paid calls instead.
- StealAds: the search flow above (`search_advertisers`, `search_ads`, `find_winning_ads`)
  is the no-spend path. `add_competitor` with tracking, `start_tracking`, `scan_competitor`,
  `create_playbook`, `steal_ad` and `create_campaign` can spend credits and show a cost
  preview on the first call. Relay the preview, check `get_usage`, and confirm (with the
  preview's `idempotency_key` and `max_credits`) only on the user's yes. Never put a credit
  number in your own words that the preview didn't show.

Without StealAds ad making, counter-ads ship as written briefs. That's a complete deliverable.

## Errors: relay the message, it already says what to do

All messages live in `ad_spy_kit/errors.py`. The CLI exits 2 for these, 1 for a failed check.

| Situation | What the user sees |
|---|---|
| No ScrapeCreators key | the StealAds route (access link, MCP URL), or where to get a key and where the `.env` goes, plus the free sample brands |
| Key rejected or out of credits | says exactly that, nothing spent |
| Browser missing | "Chromium isn't installed" plus the one-line fix |
| StealAds error code | `ad-spy-kit explain <code>` gives the meaning and next step |
| More than one page matches | top 3 pages with IDs; ask which, rerun with the page ID |
| Brand on `config/excluded_brands.yaml` | hard stop, nothing read |
| Checks fail | `validation.json` lists each problem; fix the JSON, render again. The images are renamed `board.failed.png`, `x-slices.failed/`; none is final until the gate passes |
| `counters.json` has no briefs | check A3: the board's counter-ad panel would be empty. Write 1 to 3 briefs (step 5), render again |
| Tracked set over the read limit | `tracked_over_limit`: use the per-rival fallback in "Tracked competitors" step 4 |

## Words on the board (the reader sees all of it)

Write like a busy founder talking to a friend. We see what ran, not what worked.

| Never | Say |
|---|---|
| "Foldbrook is scaling 4 BFCM creatives." | "Foldbrook has 4 Black Friday ads still running." |
| "Strong hook, scores 8/10." | "#01 · winner · Live 41 days · 12 versions" |
| "They spend heavily on video." | Nothing about spend. Show run length and versions. |
| "Their winning ad", "proven", "converts", "why it beats" | "the ad they keep running", "they've made 9 versions", "why it's different from theirs" |
| "every live ad" | "30 of their ads that have run 30+ days" |
| "Foldbrook might be leaning into discounts." | Leave it out. No hedges. |

No em dashes in anything you write. Use a period, comma or colon. Quotes from the ads stay
exactly as printed. The checks block hedges, made-up numbers, paraphrased quotes, spend
guesses, scores, em dashes and performance claims in your own words.

## Done means

`ad-spy-kit render <run_dir>` exits 0 (it runs the checks) and you show the user `board.png`
first (look at it, and at every slice: the checks catch clipped text, blank slices and
big blank blocks, but read them anyway), then the opening in one line, then the counter briefs. When the user corrects the
board, capture it: `ad-spy-kit correct --rule must_not_contain --pattern '<regex>' --reason
'<their words>'`, so it never ships again.
