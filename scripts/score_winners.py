#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.score_winners import score_winners  # noqa: E402

if __name__ == "__main__":
    import json

    raw = json.loads(Path(sys.argv[1]).read_text())
    ads = raw["ads"] if isinstance(raw, dict) else raw
    out = score_winners(ads)
    print(json.dumps(out, indent=2))
