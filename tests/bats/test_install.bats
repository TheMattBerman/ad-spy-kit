#!/usr/bin/env bats
load helpers

setup() { setup_home; }

@test "install links the repo into ~/.claude/skills" {
  run "$REPO/install.sh" --no-deps
  [ "$status" -eq 0 ]
  [[ "$output" == *"[link]"* ]]
  [ "$(readlink "$HOME/.claude/skills/ad-spy-kit")" = "$REPO" ]
  [ ! -e "$HOME/.codex/skills/ad-spy-kit" ]
}

@test "install is idempotent: a rerun skips the existing link" {
  "$REPO/install.sh" --no-deps
  run "$REPO/install.sh" --no-deps
  [ "$status" -eq 0 ]
  [[ "$output" == *"[skip]"* ]]
}

@test "codex --copy installs a snapshot without .git or .venv" {
  run "$REPO/install.sh" codex --copy --no-deps
  [ "$status" -eq 0 ]
  dest="$HOME/.codex/skills/ad-spy-kit"
  [ -d "$dest" ] && [ ! -L "$dest" ]
  [ -f "$dest/SKILL.md" ] && [ -f "$dest/VERSION" ]
  [ ! -e "$dest/.git" ] && [ ! -e "$dest/.venv" ]
}

@test "both installs into claude and codex" {
  run "$REPO/install.sh" both --no-deps
  [ "$status" -eq 0 ]
  [ -L "$HOME/.claude/skills/ad-spy-kit" ] && [ -L "$HOME/.codex/skills/ad-spy-kit" ]
}

@test "install removes 1.0.0's loose sub-skills" {
  mkdir -p "$HOME/.claude/skills/ad-spy-kit-pull" "$HOME/.claude/skills/other-skill"
  "$REPO/install.sh" --no-deps
  [ ! -e "$HOME/.claude/skills/ad-spy-kit-pull" ]
  [ -d "$HOME/.claude/skills/other-skill" ]
}

@test "install rejects an unknown option" {
  run "$REPO/install.sh" --bogus
  [ "$status" -eq 1 ]
  [[ "$output" == *"Unknown option: --bogus"* ]]
}

@test "install --help prints usage and changes nothing" {
  run "$REPO/install.sh" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"./install.sh"* ]]
  [ ! -e "$HOME/.claude" ]
}

@test "install says what it replaces and refuses to repoint another checkout without --force" {
  other="$BATS_TEST_TMPDIR/other-checkout"
  mkdir -p "$other" "$HOME/.claude/skills"
  ln -s "$other" "$HOME/.claude/skills/ad-spy-kit"
  run "$REPO/install.sh" --no-deps
  [ "$status" -eq 1 ]
  [[ "$output" == *"[stop]"* ]]
  [[ "$output" == *"$other"* ]]
  [[ "$output" == *"--force"* ]]
  # Nothing changed.
  [ "$(readlink "$HOME/.claude/skills/ad-spy-kit")" = "$other" ]
  run "$REPO/install.sh" --no-deps --force
  [ "$status" -eq 0 ]
  [[ "$output" == *"[replace]"*"$other"* ]]
  [ "$(readlink "$HOME/.claude/skills/ad-spy-kit")" = "$REPO" ]
}

@test "install replaces a dangling link and says so" {
  mkdir -p "$HOME/.claude/skills"
  ln -s "$BATS_TEST_TMPDIR/gone" "$HOME/.claude/skills/ad-spy-kit"
  run "$REPO/install.sh" --no-deps
  [ "$status" -eq 0 ]
  [[ "$output" == *"[replace]"* ]]
  [ "$(readlink "$HOME/.claude/skills/ad-spy-kit")" = "$REPO" ]
}

@test "install says whether Chromium was checked" {
  run "$REPO/install.sh" --no-deps
  [ "$status" -eq 0 ]
  [[ "$output" == *"Chromium: not checked"* ]]
}
