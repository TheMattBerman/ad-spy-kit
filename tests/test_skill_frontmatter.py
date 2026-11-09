"""Every skill the installer exposes has frontmatter an agent can route on."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = [ROOT / "SKILL.md", *sorted((ROOT / "skills").glob("*/SKILL.md"))]


def _frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    return yaml.safe_load(text.split("---\n", 2)[1])


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_routes(path: Path) -> None:
    fm = _frontmatter(path)
    expected = "ad-spy-kit" if path.parent == ROOT else path.parent.name
    assert fm["name"] == expected
    desc = " ".join(fm["description"].split())
    assert len(desc) <= 1024, "Claude truncates descriptions over 1024 chars"
    assert "Use when" in desc and "Do NOT" in desc


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_paths_exist(path: Path) -> None:
    """Every repo path a skill names in backticks must exist (no dead routing)."""
    import re

    body = path.read_text()
    for rel in re.findall(
        r"`((?:skills|references|schemas|ad_spy_kit|evals|docs|config|"
        r"templates|fixtures)/[^`*<>\s]+)`",
        body,
    ):
        assert (ROOT / rel).exists(), f"{path.relative_to(ROOT)} points at missing {rel}"


def test_only_intended_skills_ship() -> None:
    """`npx skills add --full-depth` finds every SKILL.md; keep that set deliberate."""
    found = sorted(
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("SKILL.md")
        if not any(part in {".venv", "vendor", "node_modules", ".git"} for part in p.parts)
    )
    assert found == sorted(str(p.relative_to(ROOT)) for p in SKILLS)


def test_trigger_anchors_in_description() -> None:
    evals = yaml.safe_load((ROOT / "evals" / "triggers.yaml").read_text())
    desc = " ".join(_frontmatter(ROOT / "SKILL.md")["description"].split()).lower()
    cases = evals["should_trigger"] + evals["should_not_trigger"]
    assert len(evals["should_trigger"]) >= 5 and len(evals["should_not_trigger"]) >= 5
    missing = [c["anchor"] for c in cases if c["anchor"].lower() not in desc]
    assert not missing, f"description lost anchors: {missing}"
