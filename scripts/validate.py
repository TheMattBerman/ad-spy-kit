#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.validate import assert_valid  # noqa: E402

if __name__ == "__main__":
    import json

    name = sys.argv[1]
    path = Path(sys.argv[2])
    doc = json.loads(path.read_text())
    assert_valid(name, doc, root=ROOT)
    print(f"OK {name}")
