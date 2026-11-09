# Changelog

## Unreleased

- **StealAds JSON replies (prod recheck, 2026-11-06).**
  - Every StealAds call in the skills passes `response_format: "json"`. The adapter reads the
    JSON rows: CTA, landing URL (and domain), video URL and poster, carousel card pictures
    (saved under `media/cards/`, shown as extra tiles on the ad wall), countries, platforms,
    group id (dedupe), first and last seen, variation count, the `hook` object (spoken opener
    first), `why` and `hook_type_filter`. Null and missing fields are tolerated; static and
    image are one format. `ads.raw.json` records `schema_version` and `reply_format`. The
    Markdown text reader stays as the fallback.
  - `ad-spy-kit advertiser <reply>` reads a saved `search_advertisers` reply: one hit writes
    `competitor.json`, several ask which, and `not_indexed` prints a plain message with the
    ScrapeCreators fallback (exit 2). StealAds' own fetch is named only as something the user
    can run in the StealAds app; the MCP can't pull a missing brand.
  - Tracked mode reads `list_tracked_rival_ads` one rival at a time (`competitor_id`, `limit: 10`,
    about 12 to 14 calls for 10 brands), handles `Count pending`, and writes CTA, landing domain and spoken
    hook flags to `ads.csv`. The board shows the CTA and landing domain, small, under the lead
    ad and on the wall slice.

- **New-user test fixes (Quince, 2026-11-05).**
  - Catalog (DPA) and dynamic (DCO) ads store `{{product.name}}` / `{{product.brand}}`. Any
    text with `{{...}}` is now empty at the adapter: the hook falls back to the real caption
    line, an ad with no real text shows "No written copy. Meta fills in the product." instead
    of a quote, and every such ad is tagged "catalog ad" on its card. Check C9 fails any
    `{{` on the board, slices or `teardown.md`. Old saved runs are cleaned on `winners` and
    `render`.
  - Thin-read note: a capped read of 30 whose longest run is under 120 days, or whose ads are
    under 80% different creatives, prints what `--max-ads 60` costs. `--min-days N` moves the
    date cutoff (ScrapeCreators has only `total_impressions` and `relevancy_monthly_grouped`
    sorts, nothing oldest-first); default stays 30.
  - New offer type `price_claim` for price comparisons ("up to 80% less than you'd expect").
    It never feeds TOP DISCOUNT; check A9 fails a comparison filed as pct_off or dollar_off.
    The offers slide shows the same quote once.
  - README: the CLI pulls and your agent writes; the board appears after the agent step.
    The quote prompt is described as it works (`Go? [y/N]` in a terminal, quote and exit
    otherwise).
  - `onscreen.json` accepts `"no_text": true`; the on-screen step is in the SKILL.md routing
    table and README.
  - A failed gate renames the drawn images to `*.failed.png` and `x-slices.failed/`. The
    counter skill states the hook length limit.
  - Images are saved and embedded at most 1200px (JPEG q85); a Quince board went from 26.6 MB
    of HTML and 80 MB of media to about 2 MB and 3 MB. `--keep-originals` keeps full size.
  - Layout: slice 02 shrinks a long quote to fit instead of cutting it; slice 01 draws whole
    rows of tiles; the counter slice leads with the headline and labels the hook; "3 versions"
    with different lines says "3 versions, different captions" and `teardown.md` lists them.

- **New-user test fixes (Burrow, 2026-11-05).**
  - Young ads no longer hide silently: the board says "N newer ads not shown", up to 2 sale
    ads go on the board anyway, a short board fills up with the newest ads, `winners.json`
    lists `hidden[]`, SKILL.md tells the agent to read them before any "none of them" claim,
    and check A7 fails a "none" claim a hidden ad contradicts.
  - `run` falls back to the newest ads in the same run when nothing has run 30+ days (quoted
    up front), and takes `--max-credits`.
  - No blank slides: a slice with nothing to show is skipped; the gate fails any blank slice
    or big blank block (C8) and text that overflows a slice or the counter-ad panel (C5).
    No "none · caption" offer cards.
  - Near-identical creatives count once (same group or image) and show "N versions".
  - "1 day" not "1 days" (G1 now sees through markup); the labels tile counts the ads on the
    board; slice 05's StealAds line wraps; slices 1, 3 and 4 fill their space; the counter-ad
    panel shows why it's different, not the hook twice; `headline.top` is optional and prints
    on the summary slice; check A8 validates `#NN` rank references; teardown.md no longer
    doubles a parenthetical; small video previews are swapped for a bigger image or drawn at
    their own size; macOS `._*` files are ignored.
  - `install.sh` prints what it replaces, refuses to repoint a link to another checkout
    without `--force`, and says whether Chromium installed. README clone line explains the
    folder name.

- **Tracked competitors.** New `ad-spy-kit tracked <run_dir>` (and `ingest` on a folder of
  `tracked_rival_ads*` files) reads StealAds `list_tracked_rival_ads` JSON, or `search_ads` /
  `find_winning_ads` text called with `tracked_rivals_only`, groups it by rival, saves a
  folder per rival and draws the category board: top 10 brands by ads live 30+ days, 3 ads
  each, plus X slices. Free. Agent flow in `SKILL.md`; row fields in `docs/stealads-mcp.md`.
- **Category boards stop at 10 brands** (keyword search, named lists, `--board-brands`);
  `--brands-file` still reads every brand and the board shows the top 10. Every count on
  the board is for the brands shown. Category runs now also write `x-slices/`.
- **Fix: "1 brands".** A one-brand category run says "1 brand" and "What <name> keeps
  running"; quotes and summaries use singular too; check G1 blocks "1 brands", "1 ads",
  "1 days", "1 versions" on any board. The single-brand wall says "1 ad".
- **Fix: empty YOUR COUNTER-AD panel.** `render` wrote `{"counters": []}` for a missing
  `counters.json`, so the panel showed no brief. `render` now stops with what to write, and
  `validate` fails check A3 on an empty list.
- **Fix: `ingest` writes `competitor.json`** from the saved rows (page id and name of the
  page that ran most of them) when it's missing. Country stays empty unless known.
- **Fix: Markdown replies.** The "More results may be available." trailer no longer lands
  in the last ad's caption.

- **StealAds instructions and ingest match the live prod MCP.** The default agent flow is
  now `search_advertisers` → `search_ads` (static and video, `min_run_days=30`) +
  `find_winning_ads` → save raw JSON → `ad-spy-kit ingest`, which spends nothing.
  Tracking, scans, playbooks and `steal_ad` are optional extras behind a cost preview and
  the user's yes. `ingest` reads `find_winning_ads*.json` (the old `find_bangers*.json`
  still works), unions extra `search_ads*.json` cursor pages, takes the format from the
  file name when the save has no request, and notes a page whose `next_cursor` was never
  fetched. Prod tool schemas are in `docs/stealads-mcp.md`. Old dev credit numbers removed.
- **Ad images are saved on every read.** Each ad's image (or video preview frame) is
  downloaded next to the run as it's read, 8 at a time, 8 MB cap each, from the URLs the
  read already returned (no extra API calls). Dead links are skipped and counted.
  Carousel and catalog ads now find the picture on the card itself. `--no-images` opts out
  (`category`, `run`, `pull`, `ingest`).
- **Category board: one pattern line instead of the Black Friday count.** It names the lead
  2+ brands share and the matching lead none of them use, only when the data shows it.
  The explainer block under the counters is one line plus the label key.

## 1.6.0 (2026-11-04)

- **Labels follow StealAds #3343** (interim until it merges; every threshold is a named
  constant marked "mirrors StealAds #3343"). Winner: still running 120+ days, or 60+ days
  with 3+ versions; stopped after 365+ days with 3+ versions, or 540+ days. Solid: 30+
  days, or 14+ days with 3+ versions. Testing: still running under 30 days. No label: not
  analyzed by StealAds, or an unknown start date (a stopped ad under 30 days also gets
  none). `TOP_LABEL = "winner"` is confirmed. Sample boards are relabeled with the rule.
- **StealAds is early access.** Every mention says "early access at stealads.ai"; setup
  docs mark the StealAds tools as "if you have StealAds early access". The brief-to-ad
  handoff uses one line: "StealAds can turn this brief into a finished ad. Your first one
  is free (early access at stealads.ai)."
- **One label rule everywhere** (`ad_spy_kit/labels.py`). The single-brand board, the
  category board and the saved Ad Library import all call `strength_label()`. StealAds
  labels pass through (`strength_label` or `banger_band`; "banger" and "winner" both mean
  the top label; unknown values show no label instead of crashing). ScrapeCreators rows get
  labels too, from run length and versions, mirroring StealAds PR #3343: testing = live
  under 14 days; solid = 30+ days or 3+ versions (a stopped run counts half); top label =
  live 30+ days and 3+ versions (interim, pending confirmation), or stopped after a year
  with 3+ versions, or 18 months; else no label. `TOP_LABEL` is "winner" pending
  confirmation.
- **`ad-spy-kit category`**: several brands on one sorted board, from a keyword or a list.
  Quotes credits first, newest 30 ads per brand, images embedded, same board checks.
  `--from` redraws a saved run for free.
- **Quote before every spend.** `run`, `resolve`, `pull` and `category` print the
  ScrapeCreators cost and spend nothing without `--yes` (or "y" at the prompt).
- **Reads what they keep running.** The Ad Library has no "longest running" sort, so `run`,
  `pull` and `category` ask for live ads that were already running 30 days ago (its date
  filter is overlap-based: `status=ACTIVE`, `end_date` = 30 days ago), most-shown first
  (`sort_by=total_impressions`), up to 30 per brand, and drop any ad under 30 days that
  slips through. `--newest` reads the newest live ads instead, and the board says so.
  Quotes use the observed page sizes: about 30 ads on the first page, 10 per page after.
- **Boards in plain words, round 2.** "Checked" instead of "pulled"; no data-vendor chip
  (a small "data: Meta Ad Library" footer line instead); plain format names ("person
  talking to camera"); no "always-on" tag; Steal/Skip lines are full sentences; one label
  legend with the actual bars; the category board's title never promises "keep running"
  when its ads are new. Made-up samples use the shared label rule, so labels match the
  legend; StealAds boards say "Labels from StealAds".
- **First run never breaks.** Missing Chromium prints a plain message and the one-line fix;
  `replay` renders into a scratch folder and never deletes the shipped sample board.
- **Errors tell the truth.** A rejected key or empty balance says so instead of "no
  Facebook page found". A page ID or Ad Library page link resolves with no search.
- **Made-up sample brand.** The Ridge sample (a real company with invented ads) is now
  Foldbrook. Sample creatives are drawn as text ad cards. The README leads with the real
  recorded Spacegoods board.
- **Readable copy.** Board, teardown.md, CLI output, errors, README and skills use plain
  words, no em dashes, no performance claims. New gate checks: E3 (em dash) and E4
  (performance claim) in our own copy; verbatim ad quotes are exempt.
- `replay --sample <name>` (`--fixture` still works). Stopped ScrapeCreators ads read
  "Ran N days". The format swap keeps every missing format. macOS Playwright path in the
  bats helpers.

## 1.5.4 (2026-10-29)

- **StealAds hooks first.** StealAds MCP PR #3163 (live on dev) adds a `hook` object to
  `search_ads`, `find_bangers` and `get_ad` rows: `spoken` (verbal opener, ~first 5 s),
  `on_screen` (≤3 overlay lines), `written`, `opening_visual`, `type`, `source`. The adapter
  maps them ahead of everything else: the spoken hook is the first sentence of `hook.spoken`
  after the garbled check, then a transcript; on-screen comes from `hook.on_screen` (or an
  image's `written` text when it isn't the caption headline). New source tags
  `spoken_hook_source` and `onscreen_source` (`stealads`, `scrapecreators`, `agent-vision`,
  `openrouter:<model>`). An agent's screen read never replaces a StealAds on-screen hook.
- `ad-spy-kit transcripts` no longer quotes winners StealAds has already heard.
- Still missing from StealAds: full `transcript`, `facebook_ad_id` (still read from the image
  filename), transcript confidence, `video_url` (docs/stealads-mcp.md).
- `live/spacegoods` re-recorded read-only with the `hook` object (no other field changed).
  #03's hook is now StealAds' "Want sharper focus?"; #01, #04 and #05 are unchanged; #02's
  opener starts mid-sentence, so it stays on screen.

## 1.5.3 (2026-10-29)

- **Opt-in OpenRouter transcripts.** ScrapeCreators stays the default. With
  `AD_SPY_TRANSCRIBE=openrouter` and `OPENROUTER_API_KEY`, `ad-spy-kit transcripts` quotes
  N paid calls on `google/gemini-3.8-flash` (video + audio in, confirmed on OpenRouter's
  public model list) and, on `--yes`, sends each winner video once for verbatim speech and
  on-screen text. `AD_SPY_TRANSCRIBE_MODEL` swaps the model; an audio-only model
  (`openai/gpt-audio-mini`) gets the soundtrack via ffmpeg.
- Toggle: env or `.env`, `ad-spy-kit transcribe-mode on|off|status`, `./doctor.sh
  --transcribe on|off` (doctor always reports mode, model and key set / not set, never the
  key), or the one-time `./install.sh` prompt (`--transcribe=` / `--no-prompt` skip it). The
  saved setting holds mode and model only.
- On without a key: a clear message, then ScrapeCreators. A video OpenRouter can't do (no
  file, API error, bad JSON) falls back to ScrapeCreators in the same run; errors are saved
  with the key redacted. The garbled-opening check and SAID / ON SCREEN / CAPTION tags apply
  unchanged; an agent's own screen read wins over the model's. `transcript_source` records
  where each transcript came from.
- Pull saves winner-floor videos as `media/<ad_id>.mp4` only when opted in; the video URL is
  never stored.
- Tests: pytest blocks all network (conftest) and mocks every OpenRouter / ScrapeCreators
  call; new bats file covers the doctor, install and CLI toggles. No paid call was made.

## 1.5.2 (2026-10-29)

- **Garbled transcripts fall back.** A spoken hook is rejected when its opening is a bad
  transcription: a speech-to-text tag ([Music], ♪), a repeated word, a lowercase mid-sentence
  start, a dropped subject ("because isn't"), or a source confidence under 0.6
  (`transcript_confidence` / `asr_confidence` / `confidence`). `spoken_hook_rejected` records
  why; the hook falls back to on-screen (the poster frame for a video), then caption. Gate A3
  fails a spoken hook on a rejected ad. `transcripts` no longer re-quotes an ad that already
  has a transcript.
- `live/spacegoods` #02: its transcript opening drops words, so its hook is now the poster
  frame headline, tagged ON SCREEN: "@spacegoods is my cheat code for productivity! Get 20%
  off their starter kit with my exclusive code: EMILYN". Its offer evidence moved to the
  same on-screen line.
- **Baseline to bigskills standard.** Vanilla captures for all 4 fixtures
  (`evals/baseline/vanilla/`, gpt-4.1, one call each via `evals/capture_vanilla.py`), kit
  outputs saved in `evals/baseline/kit/`, the table in `evals/baseline/results.md`.
  `compare-baseline` now scores quotes against every source, covers live fixtures, and fails
  if the kit loses to vanilla. `scripts/compare-baseline.sh` points at it.
- **bats suite.** `tests/bats/` covers install.sh, uninstall.sh and doctor.sh in a temp
  HOME (link, copy, both, idempotent rerun, legacy cleanup, bad options, key never printed)
  plus the CLI end to end. `scripts/test.sh` runs pytest, ruff and bats.
- **Board polish.** Card-title markers, a soft header gradient, an accent rule on the
  verdict and hook rows, STEAL / SKIP as small tags, and a single-line footer:
  "pulled DATE · stealads.ai".
- VERSION, pyproject, SKILL.md metadata and plugin.json are back in step with the changelog.

## 1.5.1 (2026-10-29)

- **Gate A6: lanes are counted across every source.** A lane that counts who says something
  ("No winner names…", "Only N winners…", "none leads with…") must carry `gaps[].mentions`
  (terms, winner ids, a verbatim quote + source per hit, optional `leads`). The gate recounts
  across transcript, on-screen text and copy, and checks the printed number and the leads.
  The teardown lists each quote with its source tag.
- `live/spacegoods`: the third lane is now "2 winners mention the 60-day guarantee; none
  leads with it" (#01 said, #03 said, #03 caption). Counter 2's line matches it.

## 1.5.0 (2026-10-29)

- **Image hooks come from the image.** The hook on an image ad is its headline, else its
  biggest on-screen text. On the free path the session agent reads each winner image (and a
  video thumbnail as poster-frame text when there's no transcript) with its own vision:
  `ad-spy-kit onscreen <run_dir>` lists the files, the agent writes `onscreen.json`,
  `--apply` puts `onscreen_text` / `onscreen_hook` into ads.raw.json. No OCR service.
  Gate A3 checks an on-screen hook against the stored `onscreen_hook`. The StealAds adapter
  reads more on-screen field names.
- **Offers count what the ad says and shows.** `offer_map[].evidence_source` is `spoken`,
  `onscreen` or `copy`; A3 checks the quote in that source only. Ladder rungs and slice 03
  tag each offer "said", "on screen" or "caption". New offer type `guarantee`. A4 accepts
  numbers the ads say or show.
- `live/spacegoods`: #06's hook is now on screen, read from its cached image; the offer
  ladder is rebuilt from the transcripts (58% deepest, cited by #01).

## 1.4.0 (2026-10-29)

- **Hooks come from what the viewer meets first.** Every ad carries `spoken_hook`,
  `onscreen_hook`, `copy_hook` and `hook_source` (`ad_spy_kit/hooks.py`); priority is
  spoken > on-screen > caption. The wall cards and hook rows tag each hook "said",
  "on screen" or "caption".
- **Free route transcripts:** `ad-spy-kit transcripts <run_dir>` quotes, then (`--yes`)
  calls ScrapeCreators `/v1/facebook/adLibrary/ad/transcript` for winner videos only,
  `cache_max_age=7d`, no long transcription. The spoken hook is the first sentence.
  `ad-spy-kit run` prints the quote after winners.
- **StealAds adapter** reads transcript / spoken-hook / on-screen fields when present
  (tolerant names, nested `analysis_summary.visual.headline`) and the Meta ad id from the
  image filename. `docs/stealads-mcp.md` lists the fields we've asked StealAds to expose.
- **Gate A3** checks each hook verbatim against its claimed source and fails a caption hook
  when a spoken or on-screen one exists. The golden ratchet records each winner's source.
- Fixtures: Ridge shows StealAds-style spoken and on-screen fields, Dewbar a mocked
  ScrapeCreators `transcripts.json` (both synthetic).
- **`live/spacegoods` has real transcripts** (`fixtures/live/spacegoods/transcripts.json`,
  2026-10-29: 5 winner videos, 3 credits, 2 served from cache). All five video hooks are now
  spoken; the static winner keeps its caption. The spoken scripts differ from the captions,
  so the board says "No ad names Black Friday." and "Most ads share one caption".

## 1.3.1 (2026-10-28)

- **Creatives keep their real shape.** Each card's frame comes from the image's pixels,
  snapped to 9:16, 4:5, 1:1 or 16:9 (`ad_spy_kit/aspect.py`); with no readable image, video
  defaults to 9:16 and statics to 4:5. Images sit in the frame with `object-fit: contain`, so
  nothing is cropped. Video thumbs get a small play badge.
- **Winner wall re-flowed:** tall thumbnail beside its caption, two columns of three.
- **Winners slice** is now a 3×2 grid of tall creative cards, not a text list.
- **Newsletter** is the whole board at 1200×750 (1x); the old 640px crop cut the wall and
  stranded the footer.

## 1.3.0 (2026-10-28)

- **Counters are briefs on every route:** headline, hook, visual direction and why it beats
  the original (`beats_ad_id`). The counter panel ends with "Render this in StealAds" →
  stealads.ai. The bring-your-own image route is gone: no `counters` command, no image
  env vars, no image client.
- **Board, newsletter and slices name ads by winner rank (#01), never by ad ID.** The footer
  and slice handles are just the pulled date and the stealads.ai link. Gate C7 fails a
  board that shows an ad ID. `teardown.md` still cites full IDs.
- **Board layout:** the trigger matrix is gone (each hook already shows its lead trigger),
  which leaves room for the full counter brief above the fold.
- **X slices fixed:** each slice now shoots its own section; before, all five were the same
  crop of the board. The counters slice shows both briefs and the StealAds button.
- Gate A2 checks that each counter beats a winner and points at a real gap; E1 covers every
  brief field.

## 1.2.0 (2026-10-28)

- **StealAds dev MCP verified end to end** (prod still gated). Real read-only
  `search_ads` + `find_bangers` responses for Spacegoods are recorded at
  `fixtures/live/spacegoods` with their cached creatives and replay offline.
- **Adapter fixes for real rows:** `ingest` reads `search_ads*.json` (the dev server has no
  `list_ads`), maps `still_running` → `is_active`, infers IMAGE/VIDEO from the saved search
  filter or `ad_format`, tolerates null headlines and missing CTA / landing / Ad Library
  fields, drops other advertisers, keeps `strength` and `steal_caution`, and treats
  `generated.stealads.ai` media as durable.
- **Board:** wall cards fall back to the ad's verbatim first line when there's no headline,
  the footer says "StealAds ad IDs" when there are no Ad Library links, the source pill
  reads "STEALADS DEV MCP", a no-discount pull shows "None" instead of "0%", and the board
  shows the top two gaps, one steal and one counter (teardown.md keeps them all).
- **No hedge lines:** "spend unknown" and "Steal the structure, don't copy the ad" are gone
  from the board, slices, newsletter, teardown.md and README; the Steal / Don't module is
  now Steal / Skip. Gate E2 (and correction K002, flipped from must-contain to
  must-not-contain) blocks those phrases anywhere they render; E1 blocks them in copy.

## 1.1.0 (2026-10-28)

Audit against the bigskills kit-review rubric. Highlights:

- **Install:** `npx skills add`, Claude plugin (`.claude-plugin/`), or `./install.sh`. The
  installer links the whole kit instead of copying loose SKILL.md files, and removes 1.0.0's
  loose sub-skills. `doctor.sh` launches Chromium and reports each data source honestly.
- **Skills:** orchestrator rewritten around the Steal Board method, with routing, data-source
  order, spend gate, errors table, before/after taste and "done means". Six sub-skills got
  trigger descriptions and Input / Output / Validation contracts that name real commands.
  `references/*/SKILL.md` were renamed so `--full-depth` installs only the seven real skills.
- **Fallbacks:** ScrapeCreators pull with cached media, StealAds `ingest` + `explain`.
  Every missing key prints the variable to set and what still works.
- **Gate:** `validate_run.py` blocks on schemas, citations, verbatim quotes, uncited numbers,
  hedges, score text, bands and order, CIE format slugs (A5), PNG sizes, footer, hotlinks,
  layout and captured corrections. The golden ratchet and baseline harness are real.
- **Fixtures:** the Glossier / OLIPOP fixtures were Ridge copies with the name swapped.
  They're replaced by two distinct fictional brands (Dewbar, Fizzwell). Every fixture board
  says "synthetic fixture".
- **Board:** offer bars use percents only, and the big number is the deepest cited percent.
  The trigger matrix is labelled, modules are capped so a busy run fits, and `teardown.md` is a
  full cited swipe file.
- **Honesty:** the hand-written Gold snapshot is gone (ungraded until a judge runs). The README
  follows the §11.3 launch gate (no MCP connect copy) and drops unsourced prices and times.

## 1.0.0 (2026-10-28)

- Initial ship: orchestrator + six sub-skills, StealAds MCP-first pull, w2 winners, War Room render.
- Fixture replay CI, real CIE ScrapeCreators client, bigskills kit-review gate.
- StealAds PR #3136 fields: `banger_band`, facts-only `why`, Meta `group_id`, `run_duration_days`.
