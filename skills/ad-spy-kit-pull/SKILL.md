---
name: ad-spy-kit-pull
description: >
  Step 2 of ad-spy-kit: read a resolved competitor's Meta ads (by default up to 30 live 30+ days) into
  ads.raw.json with images saved locally. StealAds tools first when the session has them
  (search_advertisers, search_ads, find_winning_ads), else ScrapeCreators (quoted first), else tell the user
  both options. Use when competitor.json exists and ads.raw.json
  doesn't. Do NOT use to rank or analyse ads, or for TikTok/Google ads.
---

# Pull

## Contract
- **Input:** `<run_dir>/competitor.json`.
- **Output:** `<run_dir>/ads.raw.json` (`schemas/ads.raw.schema.json`) + `media/<ad_id>.*`.
- **Post:** every ad with media has a local `media/` path and `media_hash`; ads without
  one are listed in `skipped[]` with a reason; `source` says where data came from.

## Path A: StealAds (primary; use it when its tools are in the session)
Reading ads is the no-spend path. Needs the Facebook page id from `competitor.json`
(step 1 writes it from `search_advertisers`; a brand StealAds doesn't hold ends there and
falls back to Path B). **Every StealAds call below passes `response_format: "json"`.**
The default reply is Markdown text; JSON carries the CTA, landing URL, hook object (spoken
and on-screen), group id, start date, platforms and carousel cards.

**Saving replies.** Save each reply exactly as it came back. A large reply is not printed:
Claude Code saves it to a tool-results file and tells you the path. Copy that file
(`cp <path> <run_dir>/<name>`). Never retype or reformat JSON by hand. A small reply you
write out character for character. Tell the user whether every saved file is byte-faithful.

1. `search_ads(query="<brand>", facebook_page_id=<page_id>, format="static", min_run_days=30,
   max_results=24, response_format="json")` → save as `<run_dir>/search_ads.static.json`.
   Then the same with `format="video"` → `<run_dir>/search_ads.video.json`. `min_run_days=30`
   keeps ads that have run 30+ days. Nothing at 30+? Rerun without `min_run_days` and say so.
   A library search is a capped sample: one brand often returns 1 to 5 ads a page, and a
   page can be empty with `has_more` still true.
2. More ads wanted and the response has `has_more` with a `next_cursor`: call again with the
   same arguments plus `cursor=<next_cursor>` and save it as another file, such as
   `search_ads.video.page2.json`. `ingest` unions every `search_ads*.json` and drops repeats
   (same ad id; creatives sharing a `group_id` count once on the board). Stop after about 3
   pages per format; skip this step when the first page already has about 24 ads.
3. `find_winning_ads(query="<brand>", facebook_page_id=<page_id>, min_run_days=30,
   max_results=24, response_format="json")` → save as `<run_dir>/find_winning_ads.json`. Its
   order becomes `bangers_rank`; its label (`strength_label`; "banger" and "winner" both mean
   the top label) passes through. Keep `why`, `group_id`. (The old dev name
   `find_bangers.json` is still read.) Skip it and the board sorts by days live.
4. `ad-spy-kit ingest <run_dir>` maps it (`ad_spy_kit/sl_adapter.py`), writes
   `competitor.json` from the rows when it's missing (the page that ran most of them, and
   it prints which) and downloads media now: the cover image, a video's poster, and up to
   four more cards of a carousel (`media/cards/`). It maps `cta`, `landing_url` (and its
   domain), `video_url`, `video_thumbnail_url`, `card_image_urls`, `countries`, `platforms`,
   `group_id`, `start_date` / `end_date`, `first_seen` / `last_seen`, `variation_count`,
   `hook.*`, `why` and `hook_type_filter`, and tolerates any of them being null. Formats are
   one set: static and image both mean IMAGE. `ads.raw.json` records `schema_version` (the
   rows' own, 1 today) and `reply_format` (json, text or mixed). It prints a note when a
   saved page still has an unfetched `next_cursor`. Add `--import-cap-hit` when StealAds
   reported a daily limit; the board then says some ads are missing because of it.
5. No StealAds tools and no ScrapeCreators key: tell the user both options, StealAds first
   (access at https://stealads.ai, then `claude mcp add --transport http stealads
   https://mcp.stealads.ai/mcp` and `/mcp`), then the ScrapeCreators key route (Path B).
6. Brand not in StealAds (`search_advertisers` said `not_indexed`): `ad-spy-kit advertiser`
   already printed the plain message. Go to Path B and show its quote. StealAds' own fetch
   is something the user can run in the StealAds app; the MCP can't pull a missing brand.
7. Any error code → `ad-spy-kit explain <code> "<server message>"` and follow its fallback.

Optional extras, only with the user's yes after a cost preview: `add_competitor` +
`start_tracking` (watch for new ads), `scan_competitor` (check a tracked rival now).

### Tracked competitors ("my competitors"): no competitor.json, no single brand
When the user means the rivals they track, skip steps 1 to 4 and follow "Tracked
competitors" in `SKILL.md`: `list_brands` → pick the brand (ask if several) →
`list_competitors` (save each page; `Count pending` is normal) → `list_tracked_rival_ads` per rival
(`competitor_id`, `limit: 10`, `response_format: "json"`; about 12 to 14 calls fill 10 brands; save each
reply as `tracked_rival_ads.<rival>.json`) →
`ad-spy-kit tracked <run_dir>`. It is free. `competitor.json` is written per rival from the
rows. One rival's tracked ads work too: `list_tracked_rival_ads(brand_id, competitor_id)`
saved as `tracked_rival_ads.json`, then `ad-spy-kit tracked`, which draws a one-brand board
("What <name> keeps running"). For a full teardown of a tracked rival (hooks, opening,
counters) use Path A with that rival's page id, or ingest the tracked rows as in step 2 of
"Single brand from tracked rows" below.

### Single brand from tracked rows
A tracked rival's `list_tracked_rival_ads(brand_id, competitor_id, status="live",
min_run_days=30, limit=50, response_format="json")` page is richer than a library search
(up to 50 rows, caption, hook, why, CTA, landing). Save each page as `search_ads.tracked.json`
(`search_ads.tracked.page2.json`, ...). `ingest` reads them like search rows, so the teardown
flow (winners, on-screen reads, analysis, counters, render) works on them unchanged.

## Path B: ScrapeCreators (`SCRAPECREATORS_API_KEY`; when StealAds isn't in the session)
`ad-spy-kit pull <run_dir> [--max-ads 30] [--newest]` prints a quote ("reads up to the 30
most-shown ads that have been live 30+ days: about 1 ScrapeCreators credit") and spends
nothing. Relay it; on a yes, rerun with `--yes`. The Ad Library can't sort by run length,
so the default asks for live ads (`status=ACTIVE`) that were already running 30 days ago
(`end_date` = 30 days ago; the date filter is overlap-based), most-shown first
(`sort_by=total_impressions`), and drops any ad under 30 days that slips through.
`ad-spy-kit run` does the same for a brand name or page id and, when nothing has run 30+
days, reads the newest ads in the same run (quoted up front; `--max-credits N` caps the
whole run). `--newest` asks for the newest live ads (`sort_by=relevancy_monthly_grouped`). Uses
`page_id`, `trim=false` (the trimmed shape drops the creative snapshot).

**What the sort can do** (ScrapeCreators `company/ads` docs, checked 2026-11-05): `sort_by`
takes only `total_impressions` (most shown, the default here) and `relevancy_monthly_grouped`
(most recent). Nothing sorts oldest-first or by run length. `status` takes ALL, ACTIVE or
INACTIVE; `media_type` takes ALL, IMAGE, VIDEO, MEME, IMAGE_AND_MEME, NONE. The date
filter is the only lever on age, so `--min-days N` moves the `end_date` cutoff (default 30):
`--min-days 120` reads only live ads already running 120 days ago, at the same cost per
page. It is not the default because a brand with few ads that old would return almost
nothing, and the 30-day cutoff is the "solid" floor the labels and the board need.
`ad-spy-kit winners` prints a "Thin read" note (longest run under 120 days, or fewer than
80% of the ads different creatives, with the read capped) with the cost of `--max-ads 60`
and of `--min-days 120`. Relay it; never spend without a yes.

Images are saved at most 1200px on the long edge as JPEG (`--keep-originals` also keeps the
full-size files in `media/originals/`). `bangers_rank`
is null, `variation_count` = `collation_count`, `days_live` = start → end date (or today
when still active), and `strength_label` comes from the shared rule (`ad_spy_kit/labels.py`).

## Spoken hooks (free route, optional, costs credits)
After `ad-spy-kit winners`, run `ad-spy-kit transcripts <run_dir>`. It prints a quote
("3 videos on the board to transcribe: up to 3 ScrapeCreators credits…") and spends nothing.
On a yes, rerun with `--yes`: it calls `/v1/facebook/adLibrary/ad/transcript` for winner
videos only, with `cache_max_age=7d` and no long transcription (`--allow-long` opts in at
10 credits per minute). Results land in `transcripts.json` and ads.raw.json (`transcript`,
`spoken_hook`, `hook_source`). StealAds rows get the Meta ad id from `facebook_ad_id` or
their image filename, so the same command works on StealAds data. StealAds rows already
carry `hook.spoken` (the first ~5 s of speech) and `hook.on_screen`; the kit uses them first
and skips those winners in the transcript quote, so only videos StealAds hasn't heard cost
anything.

Opt-in (`AD_SPY_TRANSCRIBE=openrouter` + `OPENROUTER_API_KEY`; check `ad-spy-kit
transcribe-mode`): the same command quotes N paid OpenRouter calls on
google/gemini-3.8-flash and, on a yes, sends each winner video (saved when the ads are read, as
media/<ad_id>.mp4) for speech + on-screen text. No key, or a video it can't do, falls back
to ScrapeCreators. Never turn it on for the user; it's their bill.

## On-screen hooks (free route, no credits)
`ad-spy-kit onscreen <run_dir>` lists the cached winner images (and video thumbnails with no
transcript) for the session agent to read with its own vision; no OCR service. The agent
records `onscreen_text` and `onscreen_hook` (the headline, else the biggest text) in
`onscreen.json`, then `--apply` writes them into ads.raw.json. Steps:
`skills/ad-spy-kit-analyze`. `ad-spy-kit run` prints the list after the transcript quote.

## Rules
- Download media when the ads are read. fbcdn links expire; the renderer never hotlinks (gate C4).
- Video with no preview image → `skipped: video_no_preview`, counted in the footer.
- A video preview under 300px wide is swapped for the widest other picture the same ad carries
  (no extra request). If nothing bigger exists, the board draws it at its own size on a plain
  card with a play mark, never stretched into a blurry hero.
- macOS `._*` sidecar files on external drives are ignored everywhere the kit lists a folder.
- Never pad a thin read. Fewer than 3 ads clearing the bar later sets `thin_signal` and the
  board says "only N ads cleared the bar".
