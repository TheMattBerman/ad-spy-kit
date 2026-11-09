---
name: ad-spy-kit-resolve
description: >
  Step 1 of ad-spy-kit: turn a brand name, Instagram handle, Ad Library URL or page ID into
  one confirmed Meta page (competitor.json). Use when the ad-spy-kit orchestrator routes
  here or the user asks "which Facebook page is <brand>". Do NOT use for pulling ads
  (ad-spy-kit-pull) or for brands on config/excluded_brands.yaml.
---

# Resolve

## Contract
- **Input:** brand name, `@handle`, Ad Library URL, or numeric page ID; optional country (US).
- **Output:** `<run_dir>/competitor.json` (`schemas/competitor.schema.json`) with
  `page_id`, `page_name`, `confidence` = exact | likely | ambiguous, `alternates[]`.
- **Pre:** brand not excluded. **Post:** `confidence` is exact or likely, or you stopped.

## Steps
1. **Exclusions first.** `ad_spy_kit/exclusions.py` hard-stops on any name, handle or
   domain in `config/excluded_brands.yaml` (matching ignores case, spaces, punctuation, @,
   www). The CLI runs it before and after the lookup.
2. **StealAds tools present in the session (primary path):** `search_advertisers(query="<brand>", response_format="json")`
   returns Facebook page ids (it takes a name, a domain, a page id or an Ad Library link). Save
   the reply as `<run_dir>/search_advertisers.json` and run `ad-spy-kit advertiser` on it: one hit
   writes `competitor.json`, several list the pages to ask about, and `not_indexed` prints a
   plain "StealAds doesn't have this brand" message (exit 2) and sends you to step 3. Fuzzy
   suggestions are never the brand. No brand in the StealAds account and
   no tracking are needed to read ads, and nothing is spent. Tracking (`add_competitor`
   with `track: true`, `start_tracking`) is an optional extra: it shows a cost preview
   first, so relay it and wait for the user's yes.
3. **Else, with a ScrapeCreators key:** `ad-spy-kit resolve "<brand>" [--country US] [--out runs/x]`.
   A brand name costs 1 credit, so it prints a quote first; rerun with `--yes` on the
   user's go. A numeric page ID or an Ad Library page link (`view_all_page_id=`) resolves
   straight to that page with no search and no credit.
4. **Neither:** tell the user both options, StealAds first (access at
   https://stealads.ai, then `claude mcp add --transport http stealads
   https://mcp.stealads.ai/mcp` and `/mcp`), then a ScrapeCreators key. Never guess a page.
5. Pick: exact name / IG handle match first, then most likes; deleted pages dropped.
   **Ambiguous** = runner-up has more than half the top page's likes.

## Stop conditions
- `ambiguous`: show the top 3 (`page_id · page_name`) and ask. Rerun with the page ID.
- No match: say so and ask for the brand's Ad Library page link. Never guess a page.
- A link to one ad (`/ads/library/?id=`) names an ad, not a page: the CLI says how to get
  the page link instead.
- Exit 2 from the CLI prints the fix line (missing key, excluded brand). Relay it verbatim.
