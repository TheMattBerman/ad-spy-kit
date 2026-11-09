#!/usr/bin/env bash
# uninstall.sh [claude|codex|both]: remove ad-spy-kit (and 1.0.0's loose sub-skills).
set -euo pipefail
case "${1:-claude}" in
  claude) roots=("$HOME/.claude/skills") ;;
  codex) roots=("$HOME/.codex/skills") ;;
  both) roots=("$HOME/.claude/skills" "$HOME/.codex/skills") ;;
  *) echo "Usage: ./uninstall.sh [claude|codex|both]"; exit 1 ;;
esac
for root in "${roots[@]}"; do
  for name in ad-spy-kit ad-spy-kit-resolve ad-spy-kit-pull ad-spy-kit-winners \
    ad-spy-kit-analyze ad-spy-kit-counter ad-spy-kit-render; do
    rm -rf "${root:?}/$name"
  done
  echo "Removed ad-spy-kit from $root"
done
