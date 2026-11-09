"""Hard-stop list: brands that asked not to be torn down (config/excluded_brands.yaml)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ad_spy_kit.errors import ExcludedBrand

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "excluded_brands.yaml"


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text).rstrip("/")
    return re.sub(r"[\s@_\-.']+", "", text)


def load_exclusions(path: Path | None = None) -> set[str]:
    path = path or DEFAULT_PATH
    if not path.exists():
        return set()
    doc = yaml.safe_load(path.read_text()) or {}
    out: set[str] = set()
    for entry in doc.get("brands") or []:
        values = entry.values() if isinstance(entry, dict) else [entry]
        out.update(n for n in (_norm(v) for v in values) if n)
    return out


def check_not_excluded(*identifiers: Any, path: Path | None = None) -> None:
    """Raise ExcludedBrand if any identifier (name, page id, handle, domain) is on the list."""
    blocked = load_exclusions(path)
    for ident in identifiers:
        n = _norm(ident)
        if n and n in blocked:
            raise ExcludedBrand(
                f"'{ident}' is on config/excluded_brands.yaml, so ad-spy-kit won't tear it down.",
                fix=(
                    "Pick another competitor. Remove the entry only if the brand "
                    "withdrew the request."
                ),
                code="excluded_brand",
            )
