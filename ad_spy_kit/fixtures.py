"""Which bundled fixtures exist: synthetic ones at fixtures/<name>/, recorded live pulls at
fixtures/live/<name>/ (named "live/<name>")."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fixture_names(root: Path = ROOT) -> list[str]:
    base = root / "fixtures"
    names = [p.name for p in base.iterdir() if (p / "competitor.json").is_file()]
    live = base / "live"
    if live.is_dir():
        names += [f"live/{p.name}" for p in live.iterdir() if (p / "competitor.json").is_file()]
    return sorted(names)


def is_live(name: str) -> bool:
    return name.startswith("live/")
