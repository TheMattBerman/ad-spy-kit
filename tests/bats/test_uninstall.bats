#!/usr/bin/env bats
load helpers

setup() { setup_home; }

@test "uninstall removes the skill and legacy sub-skills, keeps others" {
  "$REPO/install.sh" --no-deps
  mkdir -p "$HOME/.claude/skills/ad-spy-kit-render" "$HOME/.claude/skills/other-skill"
  run "$REPO/uninstall.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$HOME/.claude/skills/ad-spy-kit" ]
  [ ! -e "$HOME/.claude/skills/ad-spy-kit-render" ]
  [ -d "$HOME/.claude/skills/other-skill" ]
  [ -f "$REPO/SKILL.md" ]  # a symlinked install never deletes the checkout
}

@test "uninstall both clears claude and codex" {
  "$REPO/install.sh" both --no-deps
  run "$REPO/uninstall.sh" both
  [ "$status" -eq 0 ]
  [ ! -e "$HOME/.claude/skills/ad-spy-kit" ] && [ ! -e "$HOME/.codex/skills/ad-spy-kit" ]
}

@test "uninstall with nothing installed still succeeds" {
  run "$REPO/uninstall.sh" codex
  [ "$status" -eq 0 ]
  [[ "$output" == *"Removed ad-spy-kit from $HOME/.codex/skills"* ]]
}

@test "uninstall rejects an unknown target" {
  run "$REPO/uninstall.sh" everywhere
  [ "$status" -eq 1 ]
  [[ "$output" == *"Usage"* ]]
}
