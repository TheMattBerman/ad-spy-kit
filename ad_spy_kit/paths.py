"""Folder listing helpers. Run folders often live on external drives, where macOS writes an
AppleDouble sidecar (`._name`) next to every file. Those are binary junk, never data, so
every place the kit lists a folder drops them (and other dotfiles) first."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def is_junk(path: Path) -> bool:
    """True for `._*` sidecars and any other hidden file or folder."""
    return path.name.startswith(".")


def visible(paths: Iterable[Path]) -> list[Path]:
    """The paths worth reading: no `._*` sidecars, no hidden entries."""
    return [p for p in paths if not is_junk(p)]
