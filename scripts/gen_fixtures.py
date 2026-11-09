#!/usr/bin/env python3
"""Generate the SYNTHETIC demo fixtures (invented ads in StealAds MCP PR #3136 shapes).

These are not recorded from a live list_ads call. Spec §11.3 gate check 4 still needs a
real recording; until then every fixture board says "synthetic fixture" in its header.

Foldbrook is the spec's worked example. Dewbar (skincare) and Fizzwell (prebiotic soda) are
fictional brands, so no invented ad is pinned on a real company. Each fixture exercises a
different offer shape: discount ladder, sets + gift-with-purchase, packs + subscription.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def thumb(path: Path, label: str, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (600, 750), color=color)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 580, 730], outline=(212, 255, 58), width=4)
    d.text((40, 40), label, fill=(255, 255, 255))
    img.save(path)


def mcp_why(days: int, versions: int, *, still_running: bool = True) -> str | None:
    if days < 7 and versions < 2 and not still_running:
        return None
    parts: list[str] = []
    if days == 0:
        parts.append("Live less than a day")
    else:
        parts.append(f"Live {days} {'day' if days == 1 else 'days'}")
    if versions >= 2:
        parts.append(f"{versions} versions")
    if still_running:
        parts.append("still running")
    return " · ".join(parts) if parts else None


Row = tuple[
    str, str, str, int, int, str, str | None
]  # id, copy, format, days, versions, band, group


def build(slug: str, spec: dict) -> None:
    fx = ROOT / "fixtures" / slug
    golden = fx / "golden.json"
    kept = golden.read_text() if golden.exists() else None  # the ratchet outlives regen
    if fx.exists():
        shutil.rmtree(fx)
    fx.mkdir(parents=True, exist_ok=True)
    if kept:
        golden.write_text(kept)
    competitor = {
        "query": spec["query"],
        "competitor_id": f"cmp_{slug}_fixture",
        "brand_id": "brand_fixture",
        "page_id": spec["page_id"],
        "page_name": spec["page_name"],
        "ig_username": spec["ig"],
        "followers": spec["followers"],
        "country": "US",
        "confidence": "exact",
        "alternates": [],
        "tracked": False,
        "source": "fixture",
    }
    rows: list[Row] = spec["rows"]
    mcp_ads = []
    for mcp_id, body, fmt, days, var, band, group in rows:
        still = days >= 7 or var >= 3
        why = mcp_why(days, var, still_running=still)
        if band == "testing" and days < 7:
            why = None
        mcp_ads.append(
            {
                "id": mcp_id,
                "ad_library_url": f"https://www.facebook.com/ads/library/?id={mcp_id}",
                "start_date": "2026-09-01",
                "headline": body.split(".")[0],
                "body_text": body,
                "original_cta": "Shop Now",
                "link_url": spec["link_url"],
                "format": fmt,
                "is_active": True,
                "still_running": still,
                "run_duration_days": days,
                "variation_count": var,
                "banger_band": band,
                "why": why,
                "group_id": group,
                "media": [{"url": f"fixture://{mcp_id}.png", "durable": True, "kind": "image"}],
            }
        )
        thumb(fx / "media" / f"{mcp_id}.png", f"{spec['page_name']} {mcp_id}", spec["color"](days))

    (fx / "competitor.json").write_text(json.dumps(competitor, indent=2))
    live = {
        "competitor_id": competitor["competitor_id"],
        "pulled_at": "2026-10-28T18:00:00Z",
        "ads": mcp_ads,
    }
    (fx / "stealads_list_ads.json").write_text(json.dumps(live, indent=2))
    find_bangers = {"ads": [{"id": row[0]} for row in rows[:6]]}
    (fx / "find_bangers.json").write_text(json.dumps(find_bangers, indent=2))
    analysis = {"competitor": spec["page_name"], **spec["analysis"], "citations_ok": True}
    (fx / "analysis.json").write_text(json.dumps(analysis, indent=2))
    counters = {"counters": [{"gap_ref": 0, **spec["counter"], "aspect": "4:5", "status": "brief"}]}
    (fx / "counters.json").write_text(json.dumps(counters, indent=2))


def offer(ad_id, offer_type, depth, urgency, evidence, early=False):
    return {
        "ad_id": ad_id,
        "offer_type": offer_type,
        "discount_depth": depth,
        "urgency": urgency,
        "early_access": early,
        "evidence": evidence,
    }


def hook(ad_id, text, pattern, string, trigger, strength):
    return {
        "ad_id": ad_id,
        "hook_text": text,
        "pattern": pattern,
        "puppet_string": string,
        "fear_amplifier": False,
        "triggers": [{"name": trigger, "strength": strength}],
    }


def stats(avg: str, last_label: str, last_value: str, last_sub: str) -> list[dict]:
    return [
        {"label": "Ads live", "value": "8", "sub": "pulled 10/28", "tone": "g"},
        {"label": "Winners", "value": "6", "sub": "w2 floor", "tone": "g"},
        {"label": "Avg days", "value": avg, "sub": "winners only", "tone": "n"},
        {"label": last_label, "value": last_value, "sub": last_sub, "tone": "g"},
    ]


FOLDBROOK = {
    "query": "foldbrook wallet",
    "page_id": "123456789",
    "page_name": "Foldbrook",
    "ig": "foldbrook",
    "followers": 890000,
    "link_url": "https://foldbrook.example/collections/wallets",
    "color": lambda d: (30 + d, 40, 90),
    "rows": [
        (
            "ad-1",
            "Black Friday: up to 47% off wallets & rings.",
            "VIDEO",
            41,
            12,
            "banger",
            "meta-foldbrook-001",
        ),
        ("ad-2", "The last wallet you'll buy.", "IMAGE", 38, 9, "banger", "meta-foldbrook-002"),
        ("ad-3", "VIP early access starts now.", "IMAGE", 22, 6, "solid", "meta-foldbrook-003"),
        ("ad-4", "47% off, 48 hours only.", "CAROUSEL", 19, 5, "solid", "meta-foldbrook-004"),
        ("ad-5", "Why we rarely discount.", "VIDEO", 15, 4, "testing", "meta-foldbrook-005"),
        ("ad-6", "Bundle the carry system.", "IMAGE", 11, 3, "testing", "meta-foldbrook-006"),
        ("ad-7", "New colors drop Friday.", "IMAGE", 5, 1, "testing", None),
        ("ad-8", "Free shipping over $75.", "IMAGE", 4, 2, "testing", None),
    ],
    "analysis": {
        "headline": {
            "top": "Foldbrook is scaling 4 BFCM creatives.",
            "bottom": "None of them sell the gift.",
        },
        "stats": stats("24", "Max off", "47%", "ad-1 body"),
        "offer_map": [
            offer("ad-1", "pct_off", "47%", "countdown", "47% off"),
            offer("ad-3", "early_access", "VIP", "date", "VIP early access", early=True),
        ],
        "hooks": [
            hook(
                "ad-1",
                "Black Friday: up to 47% off wallets & rings.",
                "contrast",
                "wealth",
                "scarcity",
                "heavy",
            ),
            hook(
                "ad-2",
                "The last wallet you'll buy.",
                "contrast",
                "status-access",
                "contrast",
                "moderate",
            ),
        ],
        "formats": [
            {"format": "faceless-demo", "count": 2, "days_live_sum": 56, "verdict": "sat"},
            {
                "format": "native-photo-long-copy",
                "count": 3,
                "days_live_sum": 71,
                "verdict": "dead",
            },
            {"format": "carousel", "count": 1, "days_live_sum": 19, "verdict": "open"},
        ],
        "gaps": [
            {
                "gap": "No winner frames Foldbrook as a holiday gift",
                "evidence_ad_ids": ["ad-1", "ad-2"],
                "gap_score": 8,
                "counter_angle": "Gift durability — still daily carry in January",
            }
        ],
        "steal_this": [
            {
                "ad_id": "ad-2",
                "template": "Last [category] you'll buy — lifetime frame",
                "dont_copy": "47% off headline — they own discount",
            }
        ],
    },
    "counter": {
        "beats_ad_id": "ad-1",
        "angle": "Gift lane",
        "headline": "The gift that's still in their pocket in January",
        "hook": "Stop buying wallets that feel like stocking stuffers.",
        "offer": "Gift-ready sets with engraving",
        "visual_direction": "Matte black wallet on walnut, warm holiday light, ribbon, no % badge",
        "why_it_beats": (
            "Foldbrook's top winner leads with the discount. "
            "No winner sells the gift, so this takes the lane they left open."
        ),
    },
}

DEWBAR = {
    "query": "dewbar skincare",
    "page_id": "223344556",
    "page_name": "Dewbar",
    "ig": "dewbar",
    "followers": 412000,
    "link_url": "https://dewbar.example/collections/sets",
    "color": lambda d: (90, 40 + d, 70),
    "rows": [
        (
            "ad-1",
            "Black Friday Glow Set: 3 full sizes for $58 ($84 value).",
            "VIDEO",
            34,
            11,
            "banger",
            "meta-dew-001",
        ),
        (
            "ad-2",
            "Free gift with every order over $40, through Cyber Monday.",
            "IMAGE",
            27,
            8,
            "banger",
            "meta-dew-002",
        ),
        (
            "ad-3",
            "Join the VIP list: first pick of the holiday sets.",
            "IMAGE",
            21,
            5,
            "solid",
            "meta-dew-003",
        ),
        (
            "ad-4",
            "My skin barrier finally stopped flaking. Two jars in.",
            "VIDEO",
            18,
            4,
            "solid",
            "meta-dew-004",
        ),
        (
            "ad-5",
            "Dermatologist-tested. Fragrance-free. Still $24.",
            "IMAGE",
            12,
            3,
            "testing",
            "meta-dew-005",
        ),
        ("ad-6", "Bundle any 3 minis, save 20%.", "CAROUSEL", 9, 3, "testing", "meta-dew-006"),
        ("ad-7", "New: overnight lip mask.", "IMAGE", 3, 1, "testing", None),
        ("ad-8", "Shop the holiday sale now.", "IMAGE", 2, 1, "testing", None),
    ],
    "analysis": {
        "headline": {
            "top": "Dewbar is scaling 4 BFCM ads, every one a set or a gift.",
            "bottom": "None of them show skin that changed.",
        },
        "stats": stats("20", "Hero set", "$58", "ad-1 body"),
        "offer_map": [
            offer("ad-1", "bundle", "3 full sizes", "none", "3 full sizes for $58 ($84 value)"),
            offer(
                "ad-2",
                "gift_with_purchase",
                "over $40",
                "date",
                "Free gift with every order over $40, through Cyber Monday",
            ),
            offer("ad-6", "bundle", "20%", "none", "Bundle any 3 minis, save 20%"),
            offer("ad-3", "early_access", "VIP", "none", "Join the VIP list", early=True),
        ],
        "hooks": [
            hook(
                "ad-1",
                "Black Friday Glow Set: 3 full sizes for $58 ($84 value).",
                "offer",
                "wealth",
                "contrast",
                "moderate",
            ),
            hook(
                "ad-4",
                "My skin barrier finally stopped flaking.",
                "story",
                "health",
                "identity",
                "heavy",
            ),
            hook(
                "ad-5",
                "Dermatologist-tested. Fragrance-free.",
                "proof",
                "health",
                "authority",
                "heavy",
            ),
        ],
        "formats": [
            {"format": "faceless-demo", "count": 1, "days_live_sum": 34, "verdict": "sat"},
            {"format": "native-photo-long-copy", "count": 3, "days_live_sum": 60, "verdict": "sat"},
            {"format": "yapper", "count": 1, "days_live_sum": 18, "verdict": "open"},
            {"format": "carousel", "count": 1, "days_live_sum": 9, "verdict": "open"},
        ],
        "gaps": [
            {
                "gap": "No winner shows a visible before and after",
                "evidence_ad_ids": ["ad-4", "ad-5"],
                "gap_score": 7,
                "counter_angle": "Same face, first day and sixth week, no filter",
            }
        ],
        "steal_this": [
            {
                "ad_id": "ad-2",
                "template": "Free gift over $[threshold], through [date]",
                "dont_copy": "Glow Set naming — that's their franchise",
            }
        ],
    },
    "counter": {
        "beats_ad_id": "ad-4",
        "angle": "Visible proof",
        "headline": "Six weeks. Same face. No filter.",
        "hook": "Same face. Six weeks apart. No filter.",
        "offer": "Starter set with a six-week guarantee",
        "visual_direction": "Split frame, same person, natural light, no makeup, no % badge",
        "why_it_beats": (
            "Every Dewbar winner sells a set or a gift. "
            "None shows skin that changed, so proof beats packaging."
        ),
    },
}

FIZZWELL = {
    "query": "fizzwell soda",
    "page_id": "334455667",
    "page_name": "Fizzwell",
    "ig": "drinkfizzwell",
    "followers": 268000,
    "link_url": "https://fizzwell.example/shop",
    "color": lambda d: (40, 70, 60 + d),
    "rows": [
        (
            "ad-1",
            "Black Friday: 30% off every 12-pack, today only.",
            "VIDEO",
            29,
            9,
            "banger",
            "meta-fz-001",
        ),
        (
            "ad-2",
            "Subscribe and save 15% forever. Cancel anytime.",
            "IMAGE",
            33,
            7,
            "banger",
            "meta-fz-002",
        ),
        (
            "ad-3",
            "Gift a variety pack: 12 flavors, one box.",
            "CAROUSEL",
            20,
            6,
            "solid",
            "meta-fz-003",
        ),
        (
            "ad-4",
            "Tastes like the soda you grew up on. 2g sugar.",
            "VIDEO",
            17,
            4,
            "solid",
            "meta-fz-004",
        ),
        (
            "ad-5",
            "Doorbuster: free shipping on any 2 packs.",
            "IMAGE",
            13,
            3,
            "testing",
            "meta-fz-005",
        ),
        (
            "ad-6",
            "Early access: the Cyber Monday flavor drop.",
            "IMAGE",
            8,
            3,
            "testing",
            "meta-fz-006",
        ),
        ("ad-7", "Meet Cherry Cola.", "IMAGE", 4, 1, "testing", None),
        ("ad-8", "Ends tonight: 30% off.", "IMAGE", 2, 1, "testing", None),
    ],
    "analysis": {
        "headline": {
            "top": "Fizzwell is scaling 4 BFCM ads on discounts and packs.",
            "bottom": "None of them sell it as the party drink.",
        },
        "stats": stats("20", "Max off", "30%", "ad-1 body"),
        "offer_map": [
            offer("ad-1", "pct_off", "30%", "countdown", "30% off every 12-pack, today only"),
            offer("ad-2", "pct_off", "15%", "none", "Subscribe and save 15% forever"),
            offer("ad-3", "bundle", "12 flavors", "none", "Gift a variety pack"),
            offer("ad-5", "free_shipping", "free shipping", "none", "free shipping on any 2 packs"),
        ],
        "hooks": [
            hook(
                "ad-1",
                "Black Friday: 30% off every 12-pack, today only.",
                "offer",
                "wealth",
                "scarcity",
                "heavy",
            ),
            hook(
                "ad-4",
                "Tastes like the soda you grew up on.",
                "story",
                "escape",
                "identity",
                "moderate",
            ),
            hook(
                "ad-2", "Subscribe and save 15% forever.", "offer", "wealth", "contrast", "subtle"
            ),
        ],
        "formats": [
            {"format": "faceless-demo", "count": 1, "days_live_sum": 29, "verdict": "sat"},
            {"format": "native-photo-long-copy", "count": 3, "days_live_sum": 54, "verdict": "sat"},
            {"format": "carousel", "count": 1, "days_live_sum": 20, "verdict": "open"},
            {"format": "yapper", "count": 1, "days_live_sum": 17, "verdict": "open"},
        ],
        "gaps": [
            {
                "gap": "No winner puts Fizzwell at a holiday table or party",
                "evidence_ad_ids": ["ad-1", "ad-3"],
                "gap_score": 7,
                "counter_angle": "The drink for everyone skipping alcohol this season",
            }
        ],
        "steal_this": [
            {
                "ad_id": "ad-2",
                "template": "Subscribe and save [x]% forever — cancel anytime",
                "dont_copy": "30% off 12-packs — that's their Black Friday",
            }
        ],
    },
    "counter": {
        "beats_ad_id": "ad-1",
        "angle": "Party lane",
        "headline": "The party drink for everyone not drinking",
        "hook": "Not drinking this year? Bring the good soda.",
        "offer": "Holiday host pack",
        "visual_direction": "Cans on a crowded holiday table, hands reaching in, no % badge",
        "why_it_beats": (
            "Fizzwell's winners sell discounts and packs. "
            "None puts the can at the party, where the holiday buying happens."
        ),
    },
}


def main() -> None:
    for slug in ("glossier", "olipop"):  # 1.0.0 clones of Foldbrook under real brand names
        shutil.rmtree(ROOT / "fixtures" / slug, ignore_errors=True)
    build("foldbrook", FOLDBROOK)
    build("dewbar", DEWBAR)
    build("fizzwell", FIZZWELL)
    print("fixtures ok")


if __name__ == "__main__":
    main()
