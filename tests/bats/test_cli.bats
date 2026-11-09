#!/usr/bin/env bats
load helpers

setup() {
  setup_home
  cd "$REPO"
  RUN="$BATS_TEST_TMPDIR/sg"
  cp -r "$REPO/artifacts/screenshots/live/spacegoods" "$RUN"
}

@test "cli --help lists every step" {
  run uv run ad-spy-kit --help
  [ "$status" -eq 0 ]
  for cmd in replay replay-all validate transcripts onscreen golden; do
    [[ "$output" == *"$cmd"* ]]
  done
}

@test "replay renders an offline board that passes the gate" {
  run uv run ad-spy-kit replay --fixture foldbrook --output "$BATS_TEST_TMPDIR/foldbrook"
  [ "$status" -eq 0 ]
  [ -s "$BATS_TEST_TMPDIR/foldbrook/board.png" ]
  grep -q '"ok": true' "$BATS_TEST_TMPDIR/foldbrook/validation.json"
}

@test "validate passes the shipped Spacegoods run" {
  run uv run ad-spy-kit validate "$RUN"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"ok": true'* ]]
}

@test "validate blocks a hedged headline" {
  uv run python - "$RUN" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "analysis.json"
a = json.loads(p.read_text())
a["headline"]["top"] = "This might be their best ad"
p.write_text(json.dumps(a))
PY
  run uv run ad-spy-kit validate "$RUN"
  [ "$status" -ne 0 ]
  [[ "$output" == *'"ok": false'* ]]
}

@test "transcripts spends nothing when every winner video has one" {
  run env -u SCRAPECREATORS_API_KEY uv run ad-spy-kit transcripts "$RUN"
  [ "$status" -eq 0 ]
  [[ "$output" == *"0 credits"* ]]
}

@test "onscreen has nothing left to read on Spacegoods" {
  run uv run ad-spy-kit onscreen "$RUN"
  [ "$status" -eq 0 ]
  [[ "$output" == *"No image on the board needs an on-screen read"* ]]
}

@test "golden ratchet holds for every fixture" {
  run uv run ad-spy-kit golden
  [ "$status" -eq 0 ]
}

@test "baseline: the kit beats every recorded vanilla answer" {
  run bash "$REPO/evals/compare-baseline.sh"
  [ "$status" -eq 0 ]
  [[ "$output" != *"no capture recorded"* ]]
  [[ "$output" != *"FAIL"* ]]
}
