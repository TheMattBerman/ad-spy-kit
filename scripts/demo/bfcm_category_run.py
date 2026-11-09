"""Demo wrapper around `ad-spy-kit category` that also measures the real spend.

    uv run python scripts/demo/bfcm_category_run.py --query "black friday skincare" \
        --out /workspace/bfcm-run/skincare [--yes]

Same path a reader runs (ad_spy_kit/category.py): it quotes the credits and spends nothing
without --yes, reads each brand's newest 30 ads, labels them with the shared rule and embeds
every image in the board. This wrapper adds the account balance before and after
(`/v1/credit-balance`) so the spend in the write-up is measured, not estimated. The key is
read from the environment and never printed or written.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import urllib.request
from pathlib import Path

from ad_spy_kit import category

API = "https://api.scrapecreators.com"


def balance() -> int:
    req = urllib.request.Request(
        API + "/v1/credit-balance", headers={"x-api-key": os.environ["SCRAPECREATORS_API_KEY"]}
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return int(json.loads(resp.read())["creditCount"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="black friday skincare")
    ap.add_argument("--title", default=None)
    ap.add_argument("--brands", type=int, default=category.DEFAULT_MAX_BRANDS)
    ap.add_argument("--max-ads", type=int, default=category.DEFAULT_MAX_ADS)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--yes", action="store_true", help="spend the quoted credits")
    args = ap.parse_args()
    before = balance() if args.yes else None
    code = category.run(
        args.query,
        out=args.out,
        yes=args.yes,
        title=args.title,
        max_ads=args.max_ads,
        max_brands=args.brands,
        rerun=shlex.join(["python", __file__, "--query", args.query, "--out", str(args.out)])
        + " --yes",
    )
    if before is not None:
        spent = before - balance()
        print(f"Measured spend: {spent} ScrapeCreators credits")
        doc = json.loads((args.out / "category.json").read_text())
        doc["summary"]["credits_measured"] = spent
        (args.out / "category.json").write_text(json.dumps(doc, indent=2) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
