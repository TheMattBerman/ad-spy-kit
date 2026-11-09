from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def load_schema(name: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parents[1]
    path = root / "schemas" / f"{name}.schema.json"
    return json.loads(path.read_text())


def validate_doc(name: str, doc: dict[str, Any], *, root: Path | None = None) -> list[str]:
    schema = load_schema(name, root=root)
    validator = Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in err.path)}: {err.message}" for err in validator.iter_errors(doc)
    ]


def assert_valid(name: str, doc: dict[str, Any], *, root: Path | None = None) -> None:
    errors = validate_doc(name, doc, root=root)
    if errors:
        raise ValueError(f"{name} schema invalid:\n" + "\n".join(errors))
