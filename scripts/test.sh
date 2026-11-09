#!/usr/bin/env bash
# scripts/test.sh: the full suite. pytest, ruff, then the bats shell/CLI tests.
#   bats: https://github.com/bats-core/bats-core (e.g. git clone ... && ./install.sh ~/.local)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
if command -v bats >/dev/null; then
  bats tests/bats
else
  echo "bats not found: install bats-core to run tests/bats (pytest + ruff passed)" >&2
  exit 1
fi
