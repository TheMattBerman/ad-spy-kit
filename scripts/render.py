#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ad_spy_kit.pipeline import replay_fixture  # noqa: E402

if __name__ == "__main__":
    run = replay_fixture(sys.argv[1], output_dir=Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(run)
