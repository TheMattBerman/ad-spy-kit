#!/usr/bin/env bash
# bigskills entry point; the harness lives in evals/.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/evals/compare-baseline.sh" "$@"
