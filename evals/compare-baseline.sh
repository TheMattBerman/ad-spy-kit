#!/usr/bin/env bash
# Baseline comparison (spec §12): kit output vs recorded vanilla answers, same metrics.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec uv run python evals/compare_baseline.py "$@"
