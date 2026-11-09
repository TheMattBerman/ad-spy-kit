#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.sl_adapter import map_list_ads_response  # noqa: E402

if __name__ == "__main__":
    import json

    payload = json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(map_list_ads_response(payload), indent=2))
