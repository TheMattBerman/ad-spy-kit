#!/usr/bin/env bash
# install.sh: put ad-spy-kit where Claude Code / Codex look for skills, then install deps.
#   ./install.sh                 # claude, symlink (git pull updates the skill)
#   ./install.sh codex --copy    # codex, copied snapshot
#   ./install.sh both --no-deps  # skip uv sync + Chromium
#   ./install.sh --transcribe=openrouter|scrapecreators   # set transcripts, no prompt
#   ./install.sh --force         # replace an existing ad-spy-kit link that points at another folder
# Idempotent: safe to rerun. Says what it replaces; won't repoint a link to another checkout
# without --force. Asks once (on a terminal) about opt-in OpenRouter transcripts.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="claude"; MODE="link"; DEPS=1; TRANSCRIBE=""; PROMPT=1; FORCE=0
for arg in "$@"; do
  case "$arg" in
    claude|codex|both) DEST="$arg" ;;
    --copy) MODE="copy" ;;
    --no-deps) DEPS=0 ;;
    --no-prompt) PROMPT=0 ;;
    --force) FORCE=1 ;;
    --transcribe=openrouter|--transcribe=scrapecreators) TRANSCRIBE="${arg#*=}" ;;
    --transcribe=*) echo "--transcribe takes openrouter or scrapecreators" >&2; exit 1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

targets=()
case "$DEST" in
  claude) targets=("$HOME/.claude/skills") ;;
  codex) targets=("$HOME/.codex/skills") ;;
  both) targets=("$HOME/.claude/skills" "$HOME/.codex/skills") ;;
esac

# What is at $1 now, in one line (a link target, or a plain folder).
describe() {
  if [ -L "$1" ]; then
    local t; t="$(readlink "$1")"
    local origin=""
    [ -d "$t/.git" ] && origin="$(git -C "$t" remote get-url origin 2>/dev/null || true)"
    echo "a link to $t${origin:+ (repo $origin)}"
  elif [ -d "$1" ]; then echo "a copied folder"
  else echo "something that is not a folder"; fi
}

REFUSED=0
install_into() {
  local root="$1" dest="$1/ad-spy-kit"
  mkdir -p "$root"
  # 1.0.0 copied each sub-skill to the top level; the orchestrator now routes to them in place.
  for old in resolve pull winners analyze counter render; do rm -rf "$root/ad-spy-kit-$old"; done
  if [ "$MODE" = "link" ] && [ -L "$dest" ] && [ "$(readlink "$dest")" = "$REPO" ]; then
    echo "  [skip] $dest -> $REPO"; return
  fi
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    local now; now="$(describe "$dest")"
    if [ -L "$dest" ] && [ "$(readlink "$dest")" != "$REPO" ] && [ -e "$dest" ] && [ "$FORCE" = 0 ]; then
      echo "  [stop] $dest is $now, not this folder ($REPO)." >&2
      echo "         Another ad-spy-kit checkout is installed there. Nothing was changed." >&2
      echo "         To switch to this one, rerun with --force. To keep it, leave it alone." >&2
      REFUSED=1; return
    fi
    echo "  [replace] $dest was $now"
  fi
  if [ "$MODE" = "link" ]; then
    rm -rf "$dest"; ln -s "$REPO" "$dest"; echo "  [link] $dest -> $REPO"
  else
    rm -rf "$dest"; mkdir -p "$dest"
    (cd "$REPO" && git ls-files -z 2>/dev/null | xargs -0 -I{} cp --parents {} "$dest" 2>/dev/null) \
      || cp -R "$REPO/." "$dest"
    rm -rf "$dest/.git" "$dest/.venv"; echo "  [copy] $dest"
  fi
}

echo "ad-spy-kit installer"
for t in "${targets[@]}"; do install_into "$t"; done
if [ "$REFUSED" = 1 ]; then exit 1; fi

if [ "$DEPS" = 1 ]; then
  if command -v uv >/dev/null; then
    (cd "$REPO" && uv sync --quiet && uv run --quiet playwright install chromium) \
      || echo "  [warn] dependency install failed; run: uv sync && uv run playwright install chromium"
    # Say plainly whether the browser that draws boards is there, never assume.
    if (cd "$REPO" && uv run --quiet python - <<'PY' >/dev/null 2>&1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
PY
    ); then
      echo "  [deps] Python packages installed. Chromium: installed and launches."
    else
      echo "  [warn] Chromium: NOT installed or won't launch, so boards can't be drawn yet."
      echo "         Fix: cd $REPO && uv sync && uv run playwright install chromium"
    fi
  else
    echo "  [warn] uv not found: https://docs.astral.sh/uv/ then rerun ./install.sh"
    echo "  [warn] Chromium: not checked (needs uv)"
  fi
else
  echo "  [deps] skipped (--no-deps). Chromium: not checked."
fi

# Transcript source. ScrapeCreators is the default; OpenRouter is opt-in and paid.
SETTINGS="${AD_SPY_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/ad-spy-kit/settings.env}"
if [ -z "$TRANSCRIBE" ] && [ "$PROMPT" = 1 ] && [ -t 0 ] && [ ! -f "$SETTINGS" ]; then
  echo
  echo "Transcripts come from ScrapeCreators by default."
  echo "Opt in to OpenRouter (google/gemini-3.8-flash) for speech + on-screen text?"
  echo "It needs OPENROUTER_API_KEY and OpenRouter bills each video. Change it any time:"
  echo "  ./doctor.sh --transcribe on|off"
  read -r -p "Use OpenRouter transcripts? [y/N] " answer || answer=""
  case "$answer" in y|Y|yes|YES) TRANSCRIBE="openrouter" ;; *) TRANSCRIBE="scrapecreators" ;; esac
fi
if [ -n "$TRANSCRIBE" ]; then
  mkdir -p "$(dirname "$SETTINGS")"
  model="$(grep '^AD_SPY_TRANSCRIBE_MODEL=' "$SETTINGS" 2>/dev/null || true)"
  { echo "# ad-spy-kit settings (no keys here; OPENROUTER_API_KEY lives in your env)"
    echo "AD_SPY_TRANSCRIBE=$TRANSCRIBE"
    [ -n "$model" ] && echo "$model"; } > "$SETTINGS"
  echo "  [set]  transcripts: $TRANSCRIBE ($SETTINGS)"
  if [ "$TRANSCRIBE" = openrouter ] && [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "  [note] OPENROUTER_API_KEY is not set; ScrapeCreators is used until it is."
  fi
fi

cat <<MSG

Next:
  bash $REPO/doctor.sh
  uv run --project $REPO ad-spy-kit replay --sample foldbrook   # sample board, no key, free
Then ask your agent: "tear down [competitor]'s Black Friday ads"
MSG
