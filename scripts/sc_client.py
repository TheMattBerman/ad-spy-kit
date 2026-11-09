#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.sc_client import pull_via_scrapecreators  # noqa: E402

if __name__ == "__main__":
    import json

    print(json.dumps(pull_via_scrapecreators(sys.argv[1]), indent=2))
