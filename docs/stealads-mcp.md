# StealAds MCP: maintainer notes

The StealAds MCP is the primary way to run the kit (Matt's decision, 2026-11-05). It is
live in prod at `https://mcp.stealads.ai/mcp` (OAuth via `auth.stealads.ai`). StealAds is
early access: readers get access from Matt through `https://stealads.ai` (placeholder
until Matt supplies it). README and the skills lead with it; the ScrapeCreators key flow
is the complete alternate path for readers without access.

**Status 2026-11-05: prod tool list and schemas verified, prod search E2E still pending.**
The dev server (`https://mcp-dev.stealads.ai/mcp`, 55 tools) was tested end to end with
read-only calls on 2026-10-28. On 2026-11-05 this repo connected to prod, read every tool
schema below, and called only `whoami`, `get_usage` and `get_capabilities` (all fine, scopes
read / write / spend). No search ran on prod yet, so prod row shapes are unchecked and it is
not confirmed whether search costs credits. The tool names differ from dev, see the table.

## Launch status record (§11.3)
1. [ ] Prod E2E and a paid-account check pending. Prod connects (`whoami`, `get_usage`,
   `get_capabilities` answered 2026-11-05) but no search has run yet.
2. [ ] A free and a paid account both connect the OAuth connector (not yet checked)
3. [ ] E2E on prod: search_advertisers → search_ads (page filter, format=static and video,
   min_run_days 30) + find_winning_ads → save raw JSON → `ingest` → winners → render.
   Pending, waiting on the owner's OK to run searches. **Dev, 2026-10-28:**
   search_advertisers → search_ads (page filter, plus format=video / format=static) →
   find_bangers → `ingest` → winners → render → gate passed. Write and paid tools were not
   called.
4. [x] Record a live pull into `fixtures/`: `fixtures/live/spacegoods` (dev corpus; it's the
   `search_ads` pages plus `find_bangers`, the dev name of prod `find_winning_ads`). `tests/test_live_stealads.py`
   maps the real rows.
5. [x] Durable media URLs load logged-out: `generated.stealads.ai/originals/…` images
   downloaded with no auth during `ingest` (dev).
6. [x] README "From brief to ad" section, doctor line, and the counter panel line
   "StealAds can turn this brief into a finished ad (early access at stealads.ai)" (1.6.0).
7. [x] Public copy now leads with the MCP (2026-11-05): README "Get started", skills,
   doctor.sh and the missing-key message show the URL and `https://stealads.ai`.

## Connection
Endpoint `https://mcp.stealads.ai/mcp`, OAuth via `auth.stealads.ai`, signup at
`https://app.stealads.ai/signup`. Claude Code: `claude mcp add --transport http stealads
https://mcp.stealads.ai/mcp`, then `/mcp` to connect. Sign in at
`https://app.stealads.ai` first: a signed-out Google sign-in can land on the app home
instead of the consent screen (StealAds #3561). If that happens, press connect again.

## Prod tools (verified schemas, 2026-11-05)
Read from the live tool list at `https://mcp.stealads.ai/mcp` (no search or write was called).
Dev names that are gone on prod:

| Dev | Prod |
|---|---|
| `find_bangers` | `find_winning_ads` (same idea), or `search_ads` with `search_intent: "bangers"` |
| `list_ads` | none. Closest is `list_tracked_rival_ads` (free, tracked rivals only) |
| `search_competitors` | `search_advertisers` (finds the Facebook page id) |
| `collect_competitor_ads` | `add_competitor`, `start_tracking`, `scan_competitor` (these can spend) |
| `analyze_competitor` | `get_competitor_analysis` (read scope) and `create_playbook` (can spend) |
| `generate_ads` | `quote_steal_ad` then `steal_ad`, or `create_campaign` (spend, preview first) |

Same on both: `search_ads`, `search_advertisers`, `get_ad`, `create_brand`.

### Cost, from the tool descriptions
- **Read tools, no credits stated:** `search_advertisers`, `search_ads`, `find_winning_ads`,
  `get_ad`, `list_competitors`, `get_competitor_analysis`, `get_usage`, `whoami`,
  `get_capabilities`. `get_capabilities` marks all of them read-only. Whether library
  search counts against a daily allowance is not stated (open question).
- **`list_tracked_rival_ads`:** "Reading ads does not use credits." It shares a daily
  workspace reading allowance. Confirmed on prod: every reply says `cost_credits: 0`, and
  `get_usage` was identical before and after (4813 used).
- **`quote_steal_ad`:** read-only cost preview. It does not create an ad or reserve credits.
- **Spend credits after a cost preview:** `add_competitor` (only with `track: true`),
  `start_tracking`, `resume_tracking`, `scan_competitor`, `create_playbook`, `steal_ad`,
  `create_campaign`, `revise_copy`. First call with no `confirm` returns the cost and an
  `idempotency_key` (valid 15 minutes). A spend needs `confirm: true`, that
  `idempotency_key`, and `max_credits` copied from the preview. The kit never confirms
  without the user's yes. No credit numbers are recorded here: read them from the preview.

### Find the brand
- `search_advertisers`: `query` (string, 3-100 chars, required), `max_results` (1-25),
  `cursor` (`next_cursor` of the previous page for the same query). Returns Facebook page ids.
  Exact names rank first; similar names and website matches are suggestions. If several
  match, ask the user.

### Pull its ads
- `search_ads` (up to 24 rows a page): `query` (required, advertiser name or product
  keywords, max 200), `facebook_page_id` (max 64), `format` (`static` | `video`; omit for
  both), `min_run_days` (integer 0-36500), `max_results` (1-24), `cursor` (`next_cursor`
  from the previous page, same query and filters; an empty page can still have more),
  `search_intent` (`exact` | `bangers`), `search_angles` (1-3 strings), `audience`, `buyer`
  (`business_owners` | `consumers` | `professionals` | `any`), `industry_slug`, `angle`,
  `hook_type` (these three take exact values from `_references.filters` in a result),
  `has_spoken_hook` (boolean), `brand_id`, `competitor_id`, `tracked_rivals_only` (needs
  `brand_id`), `presentation` (`gallery` | `none`, legacy hint).
- `find_winning_ads` (ranked sample, up to 24): `query` (required), `facebook_page_id`,
  `format` (`static` | `video`), `min_run_days` (0-36500), `max_results` (1-24),
  `search_angles` (1-3), `audience`, `buyer` (same enum), `industry_slug`, `angle`,
  `hook_type`, `has_spoken_hook`, `brand_id`, `competitor_id`, `tracked_rivals_only`.
  No `cursor` and no `search_intent`.
- Both describe `strength_label` the same way: unanalyzed ads have no label; analyzed ads
  are winners when still running 120+ days (60 with 3+ versions), or when stopped or
  delivery unknown after 540+ days (365 with 3+ versions); solid after 30+ run days (14 with
  3+ versions); testing otherwise. Cautions are separate and never change the label. This
  matches `ad_spy_kit/labels.py`. When StealAds sends no label (unanalyzed) but does send a
  real `start_date`, the kit applies this same rule itself and marks the ad
  `label_source: "run_length"`. With no start date the ad stays unlabeled.
- `get_ad`: `ad_id` (required), `analysis_detail` (`none` | `typed` | `summary` | `full`,
  for your own ads). Includes `hook`; `hook.spoken` is the verbal opener, `hook.on_screen`
  the opening overlay text. Full transcripts are omitted.
- `list_tracked_rival_ads` (free, tracked rivals only): `brand_id` (required),
  `competitor_id`, `format` (`image` | `video`, not static), `status` (`live` | `stopped` |
  `all`), `min_run_days`, `limit` (default 20, max 50), `cursor`, `compact` (default true).
  Kit support: `ad-spy-kit tracked` (see "Tracked rows" below).

### Optional extras (cost preview first, the user says yes)
- `list_competitors`: `brand_id`. `get_competitor_analysis`: `competitor_id` (common hooks,
  angles, funnel stages, longest-running ads; for a tracked competitor).
- `add_competitor`: `brand_id`, `name` (required); `page_url`, `facebook_page_id`,
  `country_code` (2 letters), `track` (boolean), `confirm`, `idempotency_key`, `max_credits`.
  A matching name or page returns the existing competitor.
- `scan_competitor`, `start_tracking`, `resume_tracking`: `competitor_id` (required),
  `confirm`, `idempotency_key`, `max_credits`. A scan needs active tracking.
- `quote_steal_ad`: `brand_id`, `ad_id` (required), `notes`. `steal_ad`: same plus
  `confirm`, `idempotency_key`. Then `get_ad_status` with `_references.job_id` until
  `terminal` is true.
- `create_campaign`: `brand_id`, `prompt` (required), `count` (1-10), `size` (`1:1` | `4:5` |
  `9:16` | `16:9`), `source_ad_ids` (2-5 UUIDs), `confirm`, `idempotency_key`, `max_credits`,
  plus a `truth` object of brand approvals the preview asks for.
- `create_brand`: `name`, `industry`, `primaryColor` (`#rrggbb`), `toneOfVoice`,
  `targetAudience` (required); `websiteUrl`. No crawl, no credits. `list_brands` lists them.

### Saved file names `ingest` reads
| Saved from | File name |
|---|---|
| `search_ads` (both formats) | `search_ads.json` |
| `search_ads` with `format: "video"` / `"static"` | `search_ads.video.json` / `search_ads.static.json` (the file name sets IMAGE / VIDEO when the save has no request) |
| next page by `cursor` | any other `search_ads*.json`, e.g. `search_ads.video.page2.json` |
| `find_winning_ads` | `find_winning_ads.json` (rank order; old name `find_bangers.json` still works, and both can sit in one run folder) |
| old dev `list_ads` | `stealads_list_ads.json` (still accepted; prod has no such tool) |

Save the tool's JSON as it came back. A `{request, response}` wrapper (as in
`fixtures/live`) is optional. `ingest` unions the pages on the StealAds ad id and prints a
note when a saved page still says `has_more` with a cursor nobody fetched. The winners file
still calls the rank source `find_bangers` internally (`rank_source`); that is the
StealAds rank order, whichever tool produced it.

### Gaps and open questions (2026-11-05)
- **Prod rows are unseen.** The schemas describe inputs only, so the field list in "What
  real dev rows look like" below is not confirmed on prod. Named in the prod instructions
  and descriptions: `strength_label`, `strength`, `still_running`, `steal_caution`,
  `hook.spoken`, `hook.on_screen`, `_references` and `_references.filters`. All of those the
  adapter already reads. First prod pull should confirm `id`, `facebook_page_id`,
  `page_name`, `image_url`, `body_text`, `run_duration_days`, `variation_count`, `group_id`.
- **Text-only results.** The prod instructions mention "text-only results" with ad links
  and Markdown image previews. If a host only returns text, the agent cannot save raw JSON
  and `ingest` has nothing to read. Check on the first prod pull.
- **Is search free?** Not stated. Do not tell users it is until a pull and `get_usage`
  before / after show the same balance.
- **`search_intent: "bangers"`.** Not described. Unknown whether it ranks by strength. The
  kit ranks from `find_winning_ads` instead; a `search_ads` bangers call has no rank file.
- **`list_tracked_rival_ads` is unusable on a big workspace.** Prod 2026-11-05: the brand
  "BFCM 2026 Research" (428 active tracked rivals, 54,977 tracked ads) answers every call,
  with or without `competitor_id`, `status`, `min_run_days` or a small `limit`, with "This
  tracked set exceeds the tool's read limit. Use a smaller brand workspace." So does
  "OutboundIntel Category Research". Brands with 0 tracked rivals return an empty page.
  The tool cannot be used to page through a large workspace. Fallback in `SKILL.md`.
- **Error codes.** The ones in `ad_spy_kit/errors.py` are from dev; prod codes are unconfirmed.

## Prod recheck 2026-11-06 (read-only; supersedes the 2026-11-05 gaps below where they differ)
Every read call took `response_format: "json"`. Credits were identical before and after the
reads (`get_usage`; every tracked reply says `cost_credits: 0`). Replies were saved byte for
byte next to the run data (`stealads-prod-recheck/`); `tests/data/stealads_json/` holds
trimmed copies.

- **JSON rows exist on prod** (`schema_version: 1` on every row and on every advertiser).
  Search and tracked rows share one field set: `id`, `facebook_page_id`, `page_name`,
  `format` (`static` | `video`), `image_url`, `video_url`, `video_thumbnail_url`,
  `card_image_urls`, `platforms`, `countries`, `group_id`, `body_text`, `original_headline`,
  `first_seen`, `last_seen`, `start_date`, `end_date`, `still_running`, `run_duration_days`,
  `variation_count`, `cta`, `landing_url`, `ad_library_url`, `hook` (`spoken`, `on_screen`,
  `opening_visual`, `written`, `type`, `source`), `hook_type`, `hook_type_filter`, `strength`,
  `strength_label`, `why`, `steal_caution`, `for`, `filters`. Search rows add `source` (and
  `your_rival` with `brand_id`); tracked rows add `ad_id`, `competitor_id`, `rival_name`,
  `days_live`, `status`, `format_filter`, `ad_url`, `body_text_truncated`.
- **Tracked paging works on the 428-rival BFCM brand.** The "exceeds the read limit" error
  is gone. Unfiltered pages (`order: "recent"`) mix up to three rivals and return 36 rows at
  `limit: 50`; `competitor_id` pages (`order: "rival"`) return one rival, up to 50 rows.
  `totals.tracked_rivals` is null until the roster walk finishes (1 with `competitor_id`).
  `list_competitors` pages 50 rivals with `next_cursor` / `has_more`; rivals whose count is
  not ready say `count_status: "pending"`, `ads_tracked: null`, `ads_tracked_label: "Count
  pending"`; a count past the cap says `218+` with `ads_tracked_capped: true`.
- **`compact` (default true)** cuts `body_text` to 280 characters ending in an ellipsis and
  sets `body_text_truncated`. `compact: false` returns the full caption and no `primary_text`.
- **`search_advertisers`** resolves name, domain, page id and Ad Library link for a brand
  StealAds holds (`advertisers: [{name, facebook_page_id}]`, `source: "ad_library"`). Brands
  it doesn't hold (Space Goods by name, domain, page id and link) return `status:
  "not_indexed"`, `can_pull: false`, `suggestions` (fuzzy names, not the brand) and a message
  that a one-time fetch is offered in the StealAds app. MCP pulling "is not available yet".
  `ad-spy-kit advertiser` turns that into the plain message and the ScrapeCreators fallback.
- **Still missing:** a matching-ad count (#3424; `returned_count` only, `totals` is rivals),
  any `download_url` or raw export link, and any carousel row (`card_image_urls` was null on
  234 rows; `countries` null on all). The same Meta ad can carry different `hook` data in a
  library row and a tracked row (one analyzed, one not, or two different `hook.type`
  values), so tracked boards show what each row says.

## Tracked rows (`list_tracked_rival_ads`, prod, 2026-11-05)
Read-only, `cost_credits: 0`. No daily allowance figure appears in any reply (the tool
description only says reads share one). The reply is JSON (not Markdown), from the "Ridge"
brand workspace (1 tracked rival, Bellroy; 20 rows a page at `limit: 20`):

`{brand_id, ads: [...], returned_count, next_cursor, has_more, totals: {tracked_rivals},
page_status_counts: {live, stopped, unknown}, order: "rival_id_then_owner_then_updated_desc",
description, cost_credits}`. One rival per page.

| Row field | Example | Kit field |
|---|---|---|
| `ad_id` | StealAds UUID | `ad_id` |
| `competitor_id` | StealAds UUID of the rival | grouping key, `competitor.json` |
| `rival_name` | "Bellroy" | `page_name` |
| `banger_band` | `banger` / `solid` / `testing` / null | `strength_label` (StealAds' own, null = no label) |
| `days_live` | 230 | `days_live`, `run_duration_days` |
| `still_running`, `status` | true, "live" | `is_active` |
| `first_seen`, `last_seen` | ISO times StealAds saw the ad | `first_seen_at`, `last_seen_at` |
| `variation_count` | 2 | `variation_count` |
| `format` | `image` or `video` | `format` IMAGE / VIDEO |
| `headline` | "Your iPhone, your choice", often "" | `headline` |
| `image_url` | `generated.stealads.ai/originals/<competitor_id>/<fb_ad_id>-<sha>.jpg` | media (downloaded) |
| `ad_url` | StealAds ad-library link | not used |

Missing from tracked rows: `facebook_page_id` (comes from `list_competitors`, fields `id`,
`name`, `facebook_page_id`, `page_url`, `country_code`, `is_active`, `ads_tracked`), body text
(`compact: false` adds "clipped primary text", field name unchecked; the kit reads
`primary_text`, `body_text`, `body`, `text` or `caption` if present), start date (`first_seen` is when
StealAds first saw the ad, not when it started), `hook`, `why`, `group_id`, `ad_library_url`,
CTA, landing URL, `steal_caution`. Some rows come back with `banger_band: null`. Because the
bodies are missing, hooks on the tracked board are the headline only (often empty), so a
card with no headline shows only its picture and run length.

Saved file names `ad-spy-kit tracked` reads: `tracked_rival_ads*.json|.md|.txt` (JSON
`list_tracked_rival_ads` pages, or Markdown/JSON `search_ads` / `find_winning_ads` replies
called with `tracked_rivals_only: true` and `competitor_id`), plus an optional
`list_competitors.json`. Recorded replies for tests: `tests/data/tracked/`.

`search_ads` / `find_winning_ads` with `brand_id` + `tracked_rivals_only` (the fallback)
return the same Markdown as library search with "(your rival)" after the name. Samples are
thin on prod: a `competitor_id` call with `max_results: 10` returned 1 to 5 rows, Skims (185
tracked ads) and Vuori (511) none at `min_run_days: 30`, and keyword calls across all 428
rivals returned 1 to 7 rows.

## Fields the adapter tolerates being absent
`strength_label` or `banger_band` (winner / banger | solid | testing; both top names map to
the kit's top label, unknown values show no label, see `ad_spy_kit/labels.py`), `why` (facts-only rank line), `group_id`
(Meta variation group), `run_duration_days`, `hook` (pre-#3163 rows fall back to the
tolerant names in `TRANSCRIPT_KEYS` / `SPOKEN_HOOK_KEYS` / `ONSCREEN_KEYS`). Mapping: `ad_spy_kit/sl_adapter.py`.

## What real dev rows look like (search_ads / find_bangers, 2026-10-28; prod unchecked)
- Present: `id` (StealAds UUID; the kit's `ad_id`), `facebook_page_id`, `page_name`,
  `image_url`, `body_text`, `original_headline` (often null), `ad_format` (a label such as
  "ugc video" or "text dominant", not IMAGE/VIDEO), `hook_type`, `angle`, `banger_band`,
  `why`, `group_id` (sometimes null), `run_duration_days`, `variation_count`,
  `still_running`, `strength`, `steal_caution`, `for`, `_references`, and since PR #3163
  `hook` (below).
- Absent: `start_date`, `is_active`, `ad_library_url`, `cta`, `landing_url`. The adapter
  maps `still_running` → `is_active`, defaults the rest to "", and never builds an Ad
  Library link from the image filename.
- The `page` filter is a ranking hint; ingest drops rows from other page ids
  (`other_advertiser`). Creator partnership ads keep the brand's page id under the
  creator's `page_name`.
- IMAGE/VIDEO comes from the `format` argument of the saved search (`search_ads.video.json`,
  `search_ads.static.json`), else from `ad_format`. A video row's `image_url` is its preview
  frame.
- `steal_caution` passes through to the swipe file as "Caution: …" when a winner has one.
- Ridge (page 176366735873065) returned no ads on the dev corpus; Bellroy returned one.

## Hook fields (StealAds MCP PR #3163, live on dev 2026-10-29)
Every `search_ads`, `find_bangers` and `get_ad` row now carries a `hook` object (checked with
read-only calls on Spacegoods: 24 search rows, 15 video, 9 static, 24 find_bangers, one
get_ad; the recordings in `fixtures/live/spacegoods` were re-recorded with it):

| `hook.` | What | Kit field | Spacegoods #01 |
|---|---|---|---|
| `spoken` | Verbal opener, ~first 5 s of speech (≤1,000 chars). Null when the video is silent or not extracted yet; never inferred from overlays | `spoken_opener` → `spoken_hook` = its first sentence | "Apology to everyone who bought Rainbow Dust from our videos." |
| `on_screen` | Up to 3 opening overlay lines (≤240 chars each); `[]` on images | `onscreen_text` (joined), `onscreen_hook` = line 1 | "Sorry we messed up..." |
| `written` | Video: `on_screen[0]`. Image: text read off the creative, else the caption headline | image only: `onscreen_hook` when it differs from `original_headline` | — |
| `opening_visual` | StealAds' description of the first frame | `opening_visual` (for the agent; never quoted as a hook) | "A man holding a product pouch…" |
| `type` | Hook type label | `hook_type` when the row has none | storytelling |
| `source` | `video` or `image` | format, after the search `format` filter | video |

`search_ads` / `find_bangers` also take `has_spoken_hook` (true / false / omitted). The kit
doesn't pass it: a winner without a spoken opener still counts.

How the kit uses it (`apply_stealads_hook` in `ad_spy_kit/sl_adapter.py`):
- StealAds goes first. A spoken hook is picked from, in order: an explicit source field, the
  first sentence of `hook.spoken`, the first sentence of a transcript. The first that passes
  the garbled check wins; `spoken_hook_source` records which (`stealads`, `scrapecreators`,
  `openrouter:<model>`). Spacegoods #02's opener starts mid-sentence ("so spacegoods isn't
  just like…"), so it's rejected and the ad falls back to on-screen, then caption.
- `onscreen_source` is `stealads`, `agent-vision` (onscreen.json) or `openrouter:<model>`.
  An agent read never replaces a StealAds on-screen hook; its lines only widen the offer
  evidence. On-screen reads still fill ads StealAds left empty.
- `ad-spy-kit transcripts` skips any winner with a StealAds opener (even a garbled one), so
  no ScrapeCreators credit or OpenRouter call is quoted for it. A transcript fetched anyway
  is still kept as offer evidence.

Still missing from StealAds rows (2026-10-29):
- `transcript`: full transcripts are deliberately omitted (PR #3163). Offers quoted as
  "said" beyond the first ~5 s still need a ScrapeCreators or OpenRouter transcript.
- `facebook_ad_id`: still not on search / get_ad rows. The adapter reads it from the
  mirrored image filename (`originals/<page>/<fb_ad_id>-<sha>.jpg`).
- A transcript confidence: none sent. The garbled check reads the text alone.
- `video_url`: not on public rows, so OpenRouter mode on the StealAds route needs the
  ScrapeCreators pull (or a cached mp4) for the video.
- Coverage: in StealAds' own sample of the 2,000 newest dev ads, 31.7% of videos had a usable
  spoken hook. Spacegoods' 15 videos: 11 spoken, 12 with overlay lines, 1 with neither.

## Plans (dev-era spec, not checked on prod)
Credit numbers below are from the old spec and the dev server. On prod, read the cost
preview instead; do not quote these to users.
- **Free:** 0 monthly credits, 1 brand, no tracked competitors, one onboarding generation
  (one stolen ad → one counter). Library search and fresh pulls are free, capped at about
  100 searches and 200 imports a day.
- **Paid:** the skill shows the tool's own cost preview before any spend (`quote_steal_ad`,
  or the first call of `add_competitor`, `start_tracking`, `scan_competitor`,
  `create_campaign`) and runs only on the user's yes. `get_usage` shows the balance.
- Error codes and fallbacks: `ad_spy_kit/errors.py` (`ad-spy-kit explain <code>`).

## Labels and `run_duration_days` (open question, 2026-11-05)
On the StealAds path the label is StealAds' own (`strength_label` / `banger_band`),
passed through with `label_source: "stealads"` and never recomputed here. `apply_winning_signals`
(`ad_spy_kit/stealads_mcp.py`) copies `run_duration_days` into `days_live`. That value drives
the "Live N days" text, sort order and the 7-day board gate, not the label. BFCM data work
found `run_duration_days` unreliable (placeholder start dates sit exactly 30 days before
`first_seen`). A wrong value can show a long run next to a winner label, or drop or keep an
ad at the 7-day gate, but it cannot flip a label on this side. A bad upstream label passes
through. See the PR description for the proposed fix; no label logic was changed.

## Prod E2E, 2026-11-05 (read-only calls, owner approved)
- `get_usage` before and after `search_advertisers`, 6 `search_ads` and 2 `find_winning_ads`
  calls: credits unchanged. Library search spent no credits on an agency plan.
- **Prod search returns Markdown text, not JSON.** `search_ads` and `find_winning_ads` give a
  numbered list: page name, caption line, "N days running · Still running", `Label:`,
  `Strength:`, `Hook:`, `Image:`, `Preview:`, `Ad:` (Ad Library link), `StealAds:` (app link,
  its last segment is the ad id), then "More results may be available." and
  `Next page cursor (for tool calls): <cursor>`. `get_ad` and `get_usage` return JSON.
  `ad_spy_kit/stealads_text.py` parses the text; `ingest` reads text or JSON saves.
- Text rows have no `variation_count`, `group_id`, `hook.spoken`, `hook.on_screen`,
  `start_date` or `why`; the page id comes from the image URL and the ad id from the StealAds
  link. A text caption line may be the headline (Cometeer) or the caption (Integralmedica),
  so it is stored as `body_text` and shown as "caption".
- Prod corpus is thin: Spacegoods is not indexed (`search_advertisers` returns `[]`; the dev
  page id 104163495557745 returns "No ads found"). Cometeer (page 266773617290091) returned 1
  static ad and 0 video. `max_results=6` returned 2 rows with a cursor.
- `search_advertisers` with an unknown name returns fuzzy, unrelated names.
