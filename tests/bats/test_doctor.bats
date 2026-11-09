#!/usr/bin/env bats
load helpers

setup() { setup_home; }

@test "doctor passes on a ready machine, keyless" {
  run env -u SCRAPECREATORS_API_KEY "$REPO/doctor.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ad-spy-kit doctor ($(cat "$REPO/VERSION"))"* ]]
  [[ "$output" == *"fail=0"* ]]
  [[ "$output" == *"SCRAPECREATORS_API_KEY not set"* ]]
}

@test "doctor reports a set key without printing it" {
  run env SCRAPECREATORS_API_KEY=bats-fake-key-7Qx9 "$REPO/doctor.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"SCRAPECREATORS_API_KEY set"* ]]
  [[ "$output" != *"bats-fake-key-7Qx9"* ]]
}

@test "doctor fails when uv is missing" {
  run env PATH="/usr/bin:/bin" HOME="$HOME" bash -c 'command -v uv >/dev/null && exit 99; "$0"' "$REPO/doctor.sh"
  [ "$status" -ne 99 ] || skip "uv lives in /usr/bin on this machine"
  [ "$status" -ne 0 ]
  [[ "$output" == *"FAIL  uv missing"* ]]
}
