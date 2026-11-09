"""Stable, stdlib-only cache primitives for classification responses."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable


class ClassificationCacheError(ValueError):
    """Raised for invalid cache keys or unreadable cache entries."""


_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


def classification_cache_key(
    *,
    prompt: str,
    taxonomy: Any,
    provider: str,
    model: str,
    text: str,
    evidence_hashes: Iterable[str] = (),
) -> str:
    """Hash every input that can change a provider classification response."""
    payload = {
        "version": 1,
        "prompt": str(prompt),
        "taxonomy": taxonomy,
        "provider": str(provider),
        "model": str(model),
        "text": str(text),
        "evidence_hashes": sorted(str(value) for value in evidence_hashes),
    }
    return _sha256_json(payload)


class ClassificationCache:
    """A small JSON-file cache keyed by :func:`classification_cache_key`."""

    def __init__(self, cache_dir: str | os.PathLike[str]):
        self.cache_dir = Path(cache_dir)

    def get(self, key: str) -> Any | None:
        path = self._entry_path(key)
        if not path.is_file():
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                entry = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise ClassificationCacheError(f"could not read cache entry: {path}") from error
        if not isinstance(entry, dict) or entry.get("key") != key or "value" not in entry:
            raise ClassificationCacheError(f"invalid cache entry: {path}")
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        path = self._entry_path(key)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {"key": key, "value": value}
        try:
            payload = _canonical_json(entry)
        except (TypeError, ValueError) as error:
            raise ClassificationCacheError("cache value must be JSON serializable") from error
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.cache_dir, delete=False) as handle:
            handle.write(payload)
            temporary_path = Path(handle.name)
        temporary_path.replace(path)

    def _entry_path(self, key: str) -> Path:
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise ClassificationCacheError("cache key must be a SHA-256 hex digest")
        return self.cache_dir / f"{key}.json"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
