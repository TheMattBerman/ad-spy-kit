#!/usr/bin/env bats
# Opt-in OpenRouter transcripts: toggles and messages only. Nothing here calls any API.
load helpers

setup() {
  setup_home
  unset AD_SPY_TRANSCRIBE AD_SPY_TRANSCRIBE_MODEL OPENROUTER_API_KEY AD_SPY_CONFIG XDG_CONFIG_HOME
  SETTINGS="$HOME/.config/ad-spy-kit/settings.env"
  cd "$REPO"
}

_run_dir() {
  RUN="$BATS_TEST_TMPDIR/run"; mkdir -p "$RUN"
  echo '{"ads":[{"ad_id":"v1","format":"VIDEO","facebook_ad_id":"1","headline":"","body":"Cap.","cta":""}]}' > "$RUN/ads.raw.json"
  echo '{"winners":[{"ad_id":"v1"}]}' > "$RUN/winners.json"
}

@test "doctor reports ScrapeCreators as the default transcript source" {
  run "$REPO/doctor.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"transcripts: scrapecreators (asked: scrapecreators, from default)"* ]]
  [[ "$output" == *"OPENROUTER_API_KEY: not set"* ]]
}

@test "doctor --transcribe on saves it; with no key it says ScrapeCreators is used" {
  run "$REPO/doctor.sh" --transcribe on
  [ "$status" -eq 0 ]
  grep -qx "AD_SPY_TRANSCRIBE=openrouter" "$SETTINGS"
  [[ "$output" == *"OPENROUTER_API_KEY is not set; using ScrapeCreators"* ]]
}

@test "doctor shows openrouter on with a key and never prints it" {
  run env OPENROUTER_API_KEY=sk-or-bats-fake-9Zq AD_SPY_TRANSCRIBE=openrouter "$REPO/doctor.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"transcripts: openrouter"* ]]
  [[ "$output" == *"google/gemini-3.8-flash"* ]]
  [[ "$output" == *"OPENROUTER_API_KEY: set"* ]]
  [[ "$output" != *"sk-or-bats-fake-9Zq"* ]]
}

@test "doctor --transcribe off turns it back off" {
  "$REPO/doctor.sh" --transcribe on >/dev/null
  run "$REPO/doctor.sh" --transcribe off
  [ "$status" -eq 0 ]
  grep -qx "AD_SPY_TRANSCRIBE=scrapecreators" "$SETTINGS"
}

@test "doctor rejects a bad --transcribe value" {
  run "$REPO/doctor.sh" --transcribe maybe
  [ "$status" -eq 1 ]
}

@test "install --transcribe=openrouter saves the opt-in without a prompt or a key" {
  run env OPENROUTER_API_KEY=sk-or-bats-fake-9Zq "$REPO/install.sh" --no-deps --transcribe=openrouter
  [ "$status" -eq 0 ]
  grep -qx "AD_SPY_TRANSCRIBE=openrouter" "$SETTINGS"
  ! grep -q "sk-or-bats-fake-9Zq" "$SETTINGS"
  [[ "$output" != *"sk-or-bats-fake-9Zq"* ]]
}

@test "install without a terminal never prompts and leaves the default" {
  run "$REPO/install.sh" --no-deps </dev/null
  [ "$status" -eq 0 ]
  [[ "$output" != *"Use OpenRouter transcripts?"* ]]
  [ ! -f "$SETTINGS" ]
}

@test "install rejects a bad --transcribe value" {
  run "$REPO/install.sh" --no-deps --transcribe=gpt
  [ "$status" -eq 1 ]
}

@test "transcripts: opted in without a key quotes ScrapeCreators and says why" {
  _run_dir
  run env AD_SPY_TRANSCRIBE=openrouter uv run ad-spy-kit transcripts "$RUN"
  [ "$status" -eq 0 ]
  [[ "$output" == *"OPENROUTER_API_KEY is not set"* ]]
  [[ "$output" == *"ScrapeCreators credit"* ]]
  [[ "$output" == *"Nothing spent"* ]]
}

@test "transcripts: opted in with a key quotes paid OpenRouter calls and spends nothing" {
  _run_dir
  run env AD_SPY_TRANSCRIBE=openrouter OPENROUTER_API_KEY=sk-or-bats-fake-9Zq \
    uv run ad-spy-kit transcripts "$RUN"
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 paid OpenRouter call on google/gemini-3.8-flash"* ]]
  [[ "$output" == *"Nothing spent"* ]]
  [[ "$output" != *"sk-or-bats-fake-9Zq"* ]]
  [ ! -f "$RUN/transcripts.json" ]
}
