#!/usr/bin/env bash
# doctor.sh: is this machine ready to render a Steal Board? Exit 0 = yes (keyless mode).
#   ./doctor.sh                      # check everything, incl. which transcript source is on
#   ./doctor.sh --transcribe on|off  # opt in/out of OpenRouter transcripts, then check
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
toggle=""
while [ $# -gt 0 ]; do
  case "$1" in
    --transcribe) toggle="${2:-}"; shift 2 || shift ;;
    --transcribe=*) toggle="${1#*=}"; shift ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
  esac
done
case "$toggle" in
  ""|on|off|openrouter|scrapecreators) ;;
  *) echo "--transcribe takes on|off|openrouter|scrapecreators" >&2; exit 1 ;;
esac
pass=0; fail=0
ok(){ printf "  ok    %s\n" "$1"; pass=$((pass+1)); }
bad(){ printf "  FAIL  %s\n" "$1"; fail=$((fail+1)); }
note(){ printf "  note  %s\n" "$1"; }

[ -f .env ] && set -a && . ./.env && set +a

echo "ad-spy-kit doctor ($(cat VERSION))"
echo "core:"
command -v uv >/dev/null && ok "uv $(uv --version 2>/dev/null | awk '{print $2}')" \
  || bad "uv missing: https://docs.astral.sh/uv/"
if uv run --quiet python -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  ok "python 3.11+ (uv env)"
else
  bad "python 3.11+ not available to uv: uv python install 3.12"
fi
if uv run --quiet python -c 'import ad_spy_kit, jinja2, jsonschema, PIL' 2>/dev/null; then
  ok "python deps"
else
  bad "python deps missing: uv sync"
fi
if uv run --quiet python - <<'PY' 2>/dev/null
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
PY
then ok "Playwright Chromium launches"; else bad "Chromium isn't installed (it draws the board). Fix: uv sync --project \"$REPO\" && uv run --project \"$REPO\" playwright install chromium"; fi
for f in SKILL.md schemas/analysis.schema.json templates/board/war-room.html.j2 fixtures/foldbrook/golden.json; do
  [ -f "$f" ] && ok "$f" || bad "missing $f (broken checkout?)"
done

echo "data sources (StealAds first, then ScrapeCreators):"
note "StealAds MCP (primary): this script can't see agent connectors. If it's connected in your agent, the skill uses it first. Not connected? Get access at https://stealads.ai, then: claude mcp add --transport http stealads https://mcp.stealads.ai/mcp (sign in at https://app.stealads.ai first, then /mcp to connect)"
if [ -n "${SCRAPECREATORS_API_KEY:-}" ]; then ok "SCRAPECREATORS_API_KEY set: alternate path ready, live ads come from ScrapeCreators when StealAds isn't connected"
else note "SCRAPECREATORS_API_KEY not set: alternate path off. Without StealAds, get a key at https://scrapecreators.com and put it in .env"; fi
note "sample brands always work, free: uv run ad-spy-kit replay --sample foldbrook"

echo "transcripts:"
if [ -n "$toggle" ]; then
  uv run --quiet ad-spy-kit transcribe-mode "$toggle" >/dev/null 2>&1 \
    && note "saved: transcripts $toggle" || bad "could not save the transcript setting"
fi
# Prints mode, model, key set/not set and one note line; never the key itself.
if status="$(uv run --quiet ad-spy-kit transcribe-mode 2>/dev/null)"; then
  while IFS= read -r line; do note "$line"; done <<<"$status"
else
  note "transcript mode unknown (python deps missing?)"
fi

echo "counter-ads:"
note "every route writes counter-ads as briefs you can hand to a designer"

echo
echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
