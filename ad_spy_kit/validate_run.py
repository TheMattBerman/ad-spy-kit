"""Blocking quality gate for a finished run directory (spec §4.4, §10, §12).

Every rule in evals/output-quality-rubric.md maps to a check here. `replay` and `render`
refuse to call a run final while `errors` is non-empty. Warnings are printed, not fatal.
Corrections captured with `ad-spy-kit correct` (evals/corrections.jsonl) run as extra
blocking checks, so a mistake fixed once stays fixed.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ad_spy_kit.hooks import (
    HOOK_SOURCES,
    HOOK_TAGS,
    available_sources,
    evidence_text,
    source_text,
)
from ad_spy_kit.labels import LABELS
from ad_spy_kit.paths import visible
from ad_spy_kit.template_text import TEMPLATE
from ad_spy_kit.validate import validate_doc

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("competitor", "ads.raw", "winners", "analysis", "counters")

SLICE_SIZE = (1080, 1350)
MIN_SLICES = 3  # summary + two more; a slice with nothing to show is skipped, not drawn blank
PNG_SIZES = {
    "board.png": (2400, 1500),
    "og.png": (1200, 630),
}
# Slice rows between the tag line and the footer lines. A slice whose content fills less
# than SLICE_MIN_FILL of them is blank; one with a gap taller than SLICE_MAX_GAP rows has a
# hole in the layout.
SLICE_BODY_ROWS = (110, 1180)
SLICE_MIN_FILL = 0.12
SLICE_MAX_GAP = 470
NEWSLETTER_WIDTH = 1200

# Rendered text that would leak an internal number or a raw scraped asset.
SCORE_TEXT = re.compile(
    r"gap[_ ]score|opportunity[_ ]score|effectiveness|banger_rank_key|winner[_ ]score"
    r"|\bscore\s*[:=]?\s*\d|\b\d+(?:\.\d+)?\s*/\s*10\b",
    re.I,
)
HOTLINK = re.compile(
    r"""(?:src|href)\s*=\s*["']https?://[^"']+\.(?:png|jpe?g|webp|gif)|"""
    r"""url\(\s*['"]?https?://|fbcdn""",
    re.I,
)
# Hedging copy the board must never print (rule: facts, not maybes).
HEDGES = re.compile(
    r"\b(might|may be|maybe|perhaps|possibly|potentially|arguably|it seems|seems to|"
    r"appears to|could be|likely|probably|we think|i think)\b",
    re.I,
)
# Disclaimer lines Matt banned as hedging; they must never render anywhere (board, slices,
# newsletter, teardown.md) or appear in analysis/counter copy.
BANNED_HEDGE_COPY = re.compile(
    r"spend\s*(?:is\s*)?unknown|unknown\s+spend|don[\u2019']?t\s+copy|do\s+not\s+copy",
    re.I,
)
REQUIRED_FOOTER = ("https://stealads.ai",)
# We see what ran, not what worked: no performance claims in our own words (ad quotes are
# exempt; they are the brand's words, shown verbatim).
CLAIMS = re.compile(
    r"\b(scal(?:e|es|ed|ing)|winning|beats?|beating|converts?|converting|proven|"
    r"outperform\w*|crush(?:es|ing)?|best[- ]performing|top[- ]performing)\b",
    re.I,
)
EM_DASH = "\u2014"
# Verbatim quotes on a board sit in <span class="q">; our own copy is everything else.
QUOTE_SPAN = re.compile(r'<span class="q">.*?</span>', re.S)
NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _norm(text: Any) -> str:
    t = str(text or "").replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", t).strip().lower()


def _copy_text(ad: dict[str, Any]) -> str:
    return " ".join(_norm(ad.get(k)) for k in ("headline", "body", "cta"))


def _load(run_dir: Path, name: str) -> dict[str, Any] | None:
    path = run_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def allowed_numbers(ads_raw: dict[str, Any], winners: dict[str, Any]) -> set[str]:
    """Numbers a headline/gap/stat may print: ones the ads say, show or write, plus pull counts."""
    ads = ads_raw.get("ads", [])
    wins = winners.get("winners", [])
    nums: set[float] = set()
    for ad in ads:
        said_seen = _norm(f"{evidence_text(ad, 'spoken')} {evidence_text(ad, 'onscreen')}")
        nums.update(float(n) for n in NUMBER.findall(f"{_copy_text(ad)} {said_seen}"))
        nums.update(float(ad.get(k) or 0) for k in ("days_live", "variation_count"))
    days = [w.get("days_live") or 0 for w in wins]
    derived = [
        len(ads),
        ads_raw.get("total_available") or 0,
        len(wins),
        sum(1 for w in wins if w.get("bf_tag") in ("bf_live", "bf_teaser")),
        sum(1 for w in wins if w.get("bf_tag") == "bf_live"),
        sum(1 for a in ads if a.get("is_active")),
        round(sum(days) / len(days)) if days else 0,
        max(days, default=0),
        sum(days),
        len(winners.get("hidden") or []),  # "9 newer ads not shown"
        len(winners.get("quarantined") or []),
        7,
        3,
        2026,  # rule w2 floor (7 days / 3 versions) and the BFCM year
    ]
    from ad_spy_kit.dedupe import distinct_creatives

    derived.append(distinct_creatives(ads))
    nums.update(float(n) for n in derived)
    for fmt_count in (winners.get("format_mix") or {}).values():
        nums.add(float(fmt_count))
    return {f"{n:g}" for n in nums}


def check_contracts(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    for name in DOCS:
        doc = docs[name]
        if doc is None:
            rep.errors.append(f"A1 missing {name}.json")
            continue
        rep.errors.extend(f"A1 {name}: {e}" for e in validate_doc(name, doc, root=ROOT))


def check_citations(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    analysis, winners, ads_raw = docs["analysis"], docs["winners"], docs["ads.raw"]
    if not (analysis and winners and ads_raw):
        return
    if analysis.get("citations_ok") is not True:
        rep.errors.append("A2 analysis.citations_ok is not true")
    win_ids = {w["ad_id"] for w in winners.get("winners", [])}
    ads = {a["ad_id"]: a for a in ads_raw.get("ads", [])}

    def cited(section: str, idx: int, ad_id: Any) -> bool:
        if ad_id not in win_ids:
            rep.errors.append(f"A2 {section}[{idx}] cites {ad_id!r}, which is not a winner")
            return False
        return True

    for i, o in enumerate(analysis.get("offer_map", [])):
        if cited("offer_map", i, o.get("ad_id")) and o.get("evidence"):
            check_offer(i, o, ads[o["ad_id"]], rep)
            check_offer_type(i, o, rep)
    for i, h in enumerate(analysis.get("hooks", [])):
        if cited("hooks", i, h.get("ad_id")) and h.get("hook_text"):
            check_hook(i, h, ads[h["ad_id"]], rep)
    for i, g in enumerate(analysis.get("gaps", [])):
        ids = g.get("evidence_ad_ids") or []
        if not ids:
            rep.errors.append(f"A2 gaps[{i}] cites no ad_id")
        for ad_id in ids:
            cited("gaps", i, ad_id)
    for i, s in enumerate(analysis.get("steal_this", [])):
        cited("steal_this", i, s.get("ad_id"))


def check_offer(i: int, o: dict[str, Any], ad: dict[str, Any], rep: Report) -> None:
    """A3: offer evidence is verbatim in the source it claims (said, on screen or caption).

    No `evidence_source` means caption: headline + body + CTA.
    """
    source = o.get("evidence_source") or "copy"
    if source not in HOOK_SOURCES:
        rep.errors.append(
            f"A3 offer_map[{i}].evidence_source {source!r} not in {list(HOOK_SOURCES)}"
        )
        return
    if _norm(o["evidence"]) not in _norm(evidence_text(ad, source)):
        where = {"spoken": "transcript", "onscreen": "on-screen text", "copy": "copy"}[source]
        rep.errors.append(
            f"A3 offer_map[{i}].evidence is not verbatim in {o['ad_id']} {where}: {o['evidence']!r}"
        )


# "up to 80% less than you'd expect" is a price comparison, not a discount: it has no "off"
# and no price it came down from. It is a `price_claim`, never a pct_off or dollar_off.
_COMPARISON = re.compile(
    r"\b(?:less|more|cheaper|lower|higher|under|below|beats?|than)\b|\bstill\s+(?:less|more)\b",
    re.I,
)
_OFF_WORD = re.compile(r"\boff\b|\bsave\b|\bdiscount", re.I)


def check_offer_type(i: int, o: dict[str, Any], rep: Report) -> None:
    """A9: a price comparison ("80% less than you'd expect", "cheaper than the rest") is a
    `price_claim`. Filed as pct_off, dollar_off or price_drop it would put a made-up discount
    on the board (a depth like "50-80%" feeds the TOP DISCOUNT number)."""
    if o.get("offer_type") not in ("pct_off", "dollar_off", "price_drop"):
        return
    quote = str(o.get("evidence") or "")
    if _COMPARISON.search(quote) and not _OFF_WORD.search(quote):
        rep.errors.append(
            f"A9 offer_map[{i}] is {o['offer_type']} but its quote is a price comparison, not "
            f"a discount: {quote!r}. Use offer_type price_claim (no discount_depth)"
        )


def check_hook(i: int, h: dict[str, Any], ad: dict[str, Any], rep: Report) -> None:
    """A3: the hook is verbatim in the source it claims, and that source is the best one.

    Priority is spoken > onscreen > copy (ad_spy_kit/hooks.py). A hook with no
    `hook_source` is a caption hook, checked against headline + body + CTA.
    """
    source = h.get("hook_source") or "copy"
    if source not in HOOK_SOURCES:
        rep.errors.append(f"A3 hooks[{i}].hook_source {source!r} not in {list(HOOK_SOURCES)}")
        return
    if source == "spoken" and ad.get("spoken_hook_rejected"):
        rep.errors.append(
            f"A3 hooks[{i}] quotes the transcript of {h['ad_id']}, but its opening is garbled "
            f"({ad['spoken_hook_rejected']}); use the on-screen or caption hook"
        )
        return
    if _norm(h["hook_text"]).rstrip(".!") not in _norm(source_text(ad, source)):
        where = {"spoken": "transcript", "onscreen": "on-screen text", "copy": "copy"}[source]
        rep.errors.append(
            f"A3 hooks[{i}].hook_text is not verbatim in {h['ad_id']} {where}: {h['hook_text']!r}"
        )
    best = available_sources(ad)[0]
    if HOOK_SOURCES.index(source) > HOOK_SOURCES.index(best):
        rep.errors.append(
            f"A3 hooks[{i}] uses the {HOOK_TAGS[source]} hook but {h['ad_id']} has a "
            f"{HOOK_TAGS[best]} hook: {ad.get(f'{best}_hook')!r}"
        )


def check_formats(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    """A5: format slugs come from the CIE taxonomy, never invented (references/taxonomy.md)."""
    from cie.taxonomy import ALL_FORMATS

    for i, f in enumerate((docs["analysis"] or {}).get("formats", [])):
        if f.get("format") not in ALL_FORMATS:
            rep.errors.append(f"A5 formats[{i}].format {f.get('format')!r} is not a CIE slug")


# A gap that counts winners who say something ("No winner names X", "Only 2 winners mention
# Y") must carry `mentions`, so the count is checked against every source, not one.
_COUNT_START = re.compile(r"^(no|none|only|every|all|\d+|one|two|three|four|five|six)\b")
_MENTION_VERB = re.compile(
    r"\b(names?|mentions?|says?|said|offers?|quotes?|promises?|leads? with|"
    r"puts? .+ in (its|their) (copy|caption|video))\b"
)
_COUNT_WORDS = {"no": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_SOURCES_SEEN = ("spoken", "onscreen", "copy")


def is_mention_claim(gap_text: str) -> bool:
    t = _norm(gap_text)
    return bool(_COUNT_START.search(t) and re.search(r"\b(winners?|ads?)\b", t)) and bool(
        _MENTION_VERB.search(t)
    )


def _claimed_count(gap_text: str) -> int | None:
    t = _norm(gap_text)
    m = re.match(r"^(?:only )?(\d+|no|none|one|two|three|four|five|six)\b", t)
    if not m:
        return None
    word = m.group(1)
    return int(word) if word.isdigit() else _COUNT_WORDS[word]


def check_lanes(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    """A6: a lane that counts who says something is counted across every source.

    `gaps[].mentions` = {terms, ad_ids, evidence[{ad_id, source, quote}], leads?}. The gate
    finds every winner whose transcript, on-screen text or copy contains a term; `ad_ids`
    must be exactly those, `evidence` must quote each (ad, source) hit verbatim, the number
    the lane prints must match, and `leads` (when given) must be exactly the winners whose
    opening line (spoken, on-screen or caption hook) contains a term.
    """
    analysis, winners, ads_raw = docs["analysis"], docs["winners"], docs["ads.raw"]
    if not (analysis and winners and ads_raw):
        return
    ads = {a["ad_id"]: a for a in ads_raw.get("ads", [])}
    win = [ads[w["ad_id"]] for w in winners.get("winners", []) if w["ad_id"] in ads]
    for i, g in enumerate(analysis.get("gaps", [])):
        m = g.get("mentions")
        if m is None:
            if is_mention_claim(g.get("gap", "")):
                rep.errors.append(
                    f"A6 gaps[{i}] counts who says something but has no `mentions`: {g['gap']!r}"
                )
            continue
        terms = [_norm(t) for t in m.get("terms") or [] if _norm(t)]
        if not terms:
            rep.errors.append(f"A6 gaps[{i}].mentions has no terms")
            continue
        hits = {
            (ad["ad_id"], src)
            for ad in win
            for src in _SOURCES_SEEN
            if any(t in _norm(evidence_text(ad, src)) for t in terms)
        }
        found = {ad_id for ad_id, _ in hits}
        claimed = set(m.get("ad_ids") or [])
        if claimed != found:
            rep.errors.append(
                f"A6 gaps[{i}] mentions {sorted(claimed)} but every source says "
                f"{sorted(found)}: {g['gap']!r}"
            )
        quoted = set()
        for j, e in enumerate(m.get("evidence") or []):
            src = e.get("source") or "copy"
            ad = ads.get(e.get("ad_id"))
            quote = _norm(e.get("quote"))
            if src not in HOOK_SOURCES or ad is None or not quote:
                rep.errors.append(f"A6 gaps[{i}].mentions.evidence[{j}] is malformed")
                continue
            if quote not in _norm(evidence_text(ad, src)) or not any(t in quote for t in terms):
                rep.errors.append(
                    f"A6 gaps[{i}].mentions.evidence[{j}] is not a verbatim {HOOK_TAGS[src]} "
                    f"quote with a term: {e.get('quote')!r}"
                )
                continue
            quoted.add((e["ad_id"], src))
        for ad_id, src in sorted(hits - quoted):
            rep.errors.append(f"A6 gaps[{i}] has no evidence for {ad_id} ({HOOK_TAGS[src]})")
        count = _claimed_count(g.get("gap", ""))
        if count is not None and count != len(found):
            rep.errors.append(
                f"A6 gaps[{i}] says {count} but {len(found)} winners mention it: {g['gap']!r}"
            )
        if "leads" in m:
            opens = {
                ad["ad_id"]
                for ad in win
                if any(t in _norm(ad.get(f"{src}_hook")) for t in terms for src in _SOURCES_SEEN)
            }
            if set(m["leads"]) != opens:
                rep.errors.append(
                    f"A6 gaps[{i}].mentions.leads is {sorted(m['leads'])} but the opening "
                    f"lines say {sorted(opens)}"
                )


# A7: "none of them name X" claims against the ads that are NOT on the board. The board holds
# 6 ads; the other ads checked (young ones held back, or ranked lower) can contradict it.
_NONE_CLAIM = re.compile(r"^\W*(none|no\b|not one|zero|nobody|neither)", re.I)
_SCOPED = re.compile(
    r"\b(on|in) (this|the) board\b|\bshown here\b|\bon this page\b|\bthe \d+ ads? (shown|here)\b",
    re.I,
)
# What a claim talks about -> what an ad would say that contradicts it.
_TOPICS: tuple[tuple[re.Pattern[str], re.Pattern[str], str], ...] = (
    (
        re.compile(r"black\s*friday|cyber\s*monday|bfcm", re.I),
        re.compile(r"black\s*friday|cyber\s*monday|bfcm", re.I),
        "Black Friday",
    ),
    (
        re.compile(r"\b(price|prices|pricing|discount|sale|deal|deals|percent|\d+%|% off)\b", re.I),
        re.compile(
            r"\d+\s*%\s*off|%\s*off|\$\s?\d|\bsale\b|discount|\bdeals?\b|\bsave\b|"
            r"\bprice[sd]?\b|\bbogo\b",
            re.I,
        ),
        "a price or sale",
    ),
    (
        re.compile(r"free shipping|ships? free|\bshipping\b", re.I),
        re.compile(r"free\s+(?:shipping|delivery)|ships?\s+free", re.I),
        "free shipping",
    ),
    (
        re.compile(r"guarantee|money[- ]back|refund|returns?\b", re.I),
        re.compile(r"guarantee|money[- ]back|refund|(?:free|easy) returns?", re.I),
        "a guarantee",
    ),
)


def _ad_text(ad: dict[str, Any]) -> str:
    return " ".join(_norm(evidence_text(ad, src)) for src in ("copy", "onscreen", "spoken"))


def check_hidden_ads(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    """A7: a "none of them / no ad" claim in the headline or an opening is checked against
    every ad that is not on the board, newest ones included. One that says the thing makes
    the claim false, so the run fails until the claim names it or limits itself to the board.
    """
    analysis, winners, ads_raw = docs["analysis"], docs["winners"], docs["ads.raw"]
    if not (analysis and winners and ads_raw):
        return
    on_board = {w["ad_id"] for w in winners.get("winners", [])}
    off_board = [a for a in ads_raw.get("ads", []) if a["ad_id"] not in on_board]
    if not off_board:
        return
    claims = [
        ("headline.bottom", analysis["headline"].get("bottom")),
        ("headline.top", analysis["headline"].get("top")),
    ]
    for i, g in enumerate(analysis.get("gaps", [])):
        claims.append((f"gaps[{i}].gap", g.get("gap")))
    for where, text in claims:
        text = str(text or "")
        if not _NONE_CLAIM.search(text) or _SCOPED.search(text):
            continue
        for topic, said, name in _TOPICS:
            if not topic.search(text):
                continue
            hit = next((a for a in off_board if said.search(_ad_text(a))), None)
            if hit is not None:
                shown = (hit.get("headline") or hit.get("body") or "")[:50]
                rep.errors.append(
                    f"A7 {where} says none of their ads cover {name}, but ad {hit['ad_id']} "
                    f"({shown!r}, live {hit.get('days_live') or 0} days) is not on the board "
                    f"and does: {text!r}. Name it ('One newer ad says ...') or limit the "
                    "claim to the board ('None of the 6 ads on this board ...')"
                )
                break


_RANK_REF = re.compile(r"#\s?(\d{1,2})\b")
_THEIR_RANK = re.compile(r"\b(?:their|the)\s+#\s?(\d{1,2})\b", re.I)


def check_rank_refs(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    """A8: "#04" in our own copy names a board rank. It must exist, and "Their #04 ad" in a
    counter-ad brief must be the ad the brief answers (`beats_ad_id`)."""
    analysis, winners, counters = docs["analysis"], docs["winners"], docs["counters"]
    if not winners:
        return
    ranks = {
        w["ad_id"]: int(w["display_rank"])
        for w in winners.get("winners", [])
        if w.get("display_rank") is not None
    }
    valid = sorted(ranks.values())
    fields: list[tuple[str, str, str | None]] = []
    if analysis:
        for i, g in enumerate(analysis.get("gaps", [])):
            fields.append((f"gaps[{i}].counter_angle", str(g.get("counter_angle") or ""), None))
        for i, st in enumerate(analysis.get("steal_this", [])):
            fields.append((f"steal_this[{i}].template", str(st.get("template") or ""), None))
    for i, c in enumerate((counters or {}).get("counters", [])):
        beats = c.get("beats_ad_id")
        for key in ("why_it_beats", "visual_direction", "angle"):
            fields.append((f"counters[{i}].{key}", str(c.get(key) or ""), beats))
    span = f"#{valid[0]:02d} to #{valid[-1]:02d}" if valid else "none"
    for where, text, beats in fields:
        for m in _RANK_REF.finditer(text):
            if int(m.group(1)) not in valid:
                rep.errors.append(
                    f"A8 {where} says #{m.group(1)}, but the board only has {span}: {text!r}"
                )
        their = _THEIR_RANK.search(text)
        if their and beats in ranks and int(their.group(1)) != ranks[beats]:
            rep.errors.append(
                f"A8 {where} says 'Their #{their.group(1)}', but beats_ad_id is "
                f"#{ranks[beats]:02d}: {text!r}"
            )


def check_numbers(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    analysis, winners, ads_raw = docs["analysis"], docs["winners"], docs["ads.raw"]
    if not (analysis and winners and ads_raw):
        return
    ok = allowed_numbers(ads_raw, winners)
    copy = [
        ("headline.top", analysis["headline"].get("top")),
        ("headline.bottom", analysis["headline"].get("bottom")),
    ]
    copy += [(f"gaps[{i}].gap", g.get("gap")) for i, g in enumerate(analysis.get("gaps", []))]
    copy += [(f"stats[{i}].value", s.get("value")) for i, s in enumerate(analysis.get("stats", []))]
    for where, text in copy:
        for n in NUMBER.findall(str(text or "")):
            if f"{float(n):g}" not in ok:
                rep.errors.append(f"A4 uncited number {n} in {where}: {text!r}")


def check_winners(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    winners = docs["winners"]
    if not winners:
        return
    ranks = []
    for w in winners.get("winners", []):
        for key in ("effectiveness_score", "banger_rank_key", "score", "winner_score"):
            if key in w:
                rep.errors.append(f"B1 winners.{w['ad_id']} carries hidden score {key}")
        label = w.get("strength_label")
        if label is not None and label not in LABELS:
            rep.errors.append(f"B3 {w['ad_id']} strength_label {label!r} not in {list(LABELS)}")
        if w.get("why") and HEDGES.search(w["why"]):
            rep.errors.append(f"B2 {w['ad_id']} why line hedges: {w['why']!r}")
        if w.get("bangers_rank") is not None:
            ranks.append(w["bangers_rank"])
    if winners.get("rank_source") == "find_bangers" and ranks != sorted(ranks):
        rep.errors.append(f"B4 winner order {ranks} does not follow find_bangers order")


def check_copy(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    analysis, counters = docs["analysis"], docs["counters"]
    fields: list[tuple[str, Any]] = []
    if analysis:
        fields += [
            ("headline.top", analysis["headline"].get("top")),
            ("headline.bottom", analysis["headline"].get("bottom")),
        ]
        for i, g in enumerate(analysis.get("gaps", [])):
            fields += [
                (f"gaps[{i}].gap", g.get("gap")),
                (f"gaps[{i}].counter_angle", g.get("counter_angle")),
            ]
        for i, s in enumerate(analysis.get("steal_this", [])):
            fields += [
                (f"steal_this[{i}].template", s.get("template")),
                (f"steal_this[{i}].dont_copy", s.get("dont_copy")),
            ]
    if counters:
        for i, c in enumerate(counters.get("counters", [])):
            fields += [
                (f"counters[{i}].{k}", c.get(k))
                for k in ("headline", "hook", "visual_direction", "why_it_beats")
            ]
    for where, text in fields:
        m = HEDGES.search(str(text or "")) or BANNED_HEDGE_COPY.search(str(text or ""))
        if m:
            rep.errors.append(f"E1 hedging '{m.group()}' in {where}: {text!r}")
        if EM_DASH in str(text or ""):
            rep.errors.append(f"E3 em dash in {where} (use a period, comma or colon): {text!r}")
        claim = CLAIMS.search(str(text or ""))
        if claim:
            rep.errors.append(
                f"E4 performance claim '{claim.group()}' in {where} (we see what ran, not "
                f"what worked): {text!r}"
            )


def _visible(html: str) -> str:
    text = re.sub(r"<(style|script).*?</\1>", " ", html, flags=re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", text))


def board_html_errors(html: str, ad_ids: list[str] | None = None) -> list[str]:
    """Checks every board shares (single brand and category): no score text, no hotlinked
    images, the stealads.ai footer, no banned hedge lines, no raw ad IDs, and in our own copy
    (outside verbatim quotes) no em dashes and no performance claims."""
    errors: list[str] = []
    text = re.sub(r"data:image/[^'\")]+", "", html)
    visible = _visible(text)
    for m in SCORE_TEXT.finditer(visible):
        errors.append(f"B1 score text on board: {m.group()!r}")
    if HOTLINK.search(text):
        errors.append("C4 board.html hotlinks a remote image (must embed bytes)")
    for needle in REQUIRED_FOOTER:
        if needle not in text:
            errors.append(f"C2 footer missing {needle!r}")
    for m in BANNED_HEDGE_COPY.finditer(visible):
        errors.append(f"E2 banned hedge copy on board: {m.group()!r}")
    if TEMPLATE.search(visible):
        at = TEMPLATE.search(visible).start()  # type: ignore[union-attr]
        errors.append(
            "C9 catalog placeholder text on the board: "
            f"{visible[max(0, at - 30) : at + 30].strip()!r} (Meta's {{{{product.name}}}} "
            "template; it is empty text, never a quote)"
        )
    own = _visible(QUOTE_SPAN.sub(" ", text))
    if EM_DASH in own:
        at = own.index(EM_DASH)
        errors.append(f"E3 em dash in board copy: {own[max(0, at - 30) : at + 30].strip()!r}")
    for m in CLAIMS.finditer(own):
        errors.append(f"E4 performance claim on board: {m.group()!r}")
    for m in re.finditer(r"(?<![\w.])1\s+(?:brands|ads|days|versions)\b", visible):
        errors.append(f"G1 plural after one on board: {m.group()!r}")
    for ad_id in ad_ids or []:
        ad_id = str(ad_id or "")
        # Short ids (ad-1) must match whole; long ids are caught by any 6-char prefix.
        token = ad_id if len(ad_id) < 12 else ad_id[:6]
        tail = r"(?![\w-])" if len(ad_id) < 12 else ""
        if token and re.search(rf"(?<![\w-]){re.escape(token)}{tail}", visible):
            errors.append(f"C7 ad id {token!r} shows on the board")
            break
    return errors


def check_render(run_dir: Path, rep: Report) -> None:
    html_path = run_dir / "board.html"
    if not html_path.exists():
        rep.errors.append("C1 missing board.html")
        return
    text = html_lib.unescape(re.sub(r"data:image/[^'\")]+", "", html_path.read_text()))
    rep.errors.extend(board_html_errors(html_path.read_text()))
    md_path = run_dir / "teardown.md"
    if md_path.exists():
        for m in BANNED_HEDGE_COPY.finditer(md_path.read_text()):
            rep.errors.append(f"E2 banned hedge copy in teardown.md: {m.group()!r}")
        if TEMPLATE.search(md_path.read_text()):
            rep.errors.append("C9 catalog placeholder text ({{...}}) in teardown.md")
    slices = re.findall(r'<section id="slice-0\d".*?</section>', text, re.S)
    if len(slices) < MIN_SLICES:
        rep.errors.append(f"C1 expected at least {MIN_SLICES} slice sections, found {len(slices)}")
    for i, sl in enumerate(slices, start=1):
        if "https://stealads.ai" not in sl:
            rep.errors.append(f"C2 slice {i:02d} missing stealads.ai")
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return
    for rel, size in PNG_SIZES.items():
        p = run_dir / rel
        if not p.exists():
            rep.errors.append(f"C1 missing {rel}")
        elif Image.open(p).size != size:
            rep.errors.append(f"C1 {rel} is {Image.open(p).size}, expected {size}")
    for i in range(1, len(slices) + 1):
        rel = f"x-slices/{i:02d}.png"
        p = run_dir / rel
        if not p.exists():
            rep.errors.append(f"C1 missing {rel}")
            continue
        if Image.open(p).size != SLICE_SIZE:
            rep.errors.append(f"C1 {rel} is {Image.open(p).size}, expected {SLICE_SIZE}")
            continue
        fill, gap = slice_fill(p)
        if fill < SLICE_MIN_FILL:
            rep.errors.append(
                f"C8 {rel} is essentially empty ({fill:.0%} of its body has content). "
                "Leave the section out of the run's analysis or give it content."
            )
        elif gap > SLICE_MAX_GAP:
            rep.errors.append(
                f"C8 {rel} has a {gap}px blank block (limit {SLICE_MAX_GAP}); rebalance it."
            )
    stale = (
        [
            p.name
            for p in visible((run_dir / "x-slices").glob("[0-9]*.png"))
            if int(p.stem) > len(slices)
        ]
        if (run_dir / "x-slices").is_dir()
        else []
    )
    for name in stale:
        rep.errors.append(f"C1 stale x-slices/{name}: this board has {len(slices)} slices")
    news = run_dir / "newsletter.png"
    if not news.exists():
        rep.errors.append("C1 missing newsletter.png")
    elif Image.open(news).size[0] != NEWSLETTER_WIDTH:
        rep.errors.append(f"C1 newsletter.png must be {NEWSLETTER_WIDTH}px wide")
    manifest = _load(run_dir, "render")
    if manifest:
        for item in manifest.get("text_overflow") or []:
            rep.errors.append(f"C5 layout: {item}")
        for ad_id in manifest.get("dropped_no_media") or []:
            rep.warnings.append(f"C6 winner {ad_id} dropped from wall (no cached image)")


def slice_fill(path: Path) -> tuple[float, int]:
    """(share of body rows that hold any ink, tallest blank run in rows) for one slice PNG.

    Ink is any pixel that differs from the slice's background. Only the body between the
    tag line and the footer lines counts, so the tag and footer never make a blank slice
    look full.
    """
    from PIL import Image, ImageChops

    with Image.open(path) as im:
        rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((4, 4)))
    ink = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > 24 else 0)
    lo, hi = SLICE_BODY_ROWS
    rows = [ink.crop((0, y, ink.width, y + 1)).getbbox() is not None for y in range(lo, hi)]
    fill = sum(rows) / len(rows)
    gap = run = 0
    for has_ink in rows:
        run = 0 if has_ink else run + 1
        gap = max(gap, run)
    return fill, gap


def load_corrections(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or ROOT / "evals" / "corrections.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_corrections(run_dir: Path, rep: Report, corrections: list[dict[str, Any]]) -> None:
    html_path = run_dir / "board.html"
    html = html_path.read_text() if html_path.exists() else ""
    visible = html_lib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"data:image/[^'\")]+", "", html)))
    md_path = run_dir / "teardown.md"
    swipe = md_path.read_text() if md_path.exists() else ""
    for c in corrections:
        pattern = re.compile(c["pattern"], re.I)
        hit = bool(pattern.search(visible))
        if c["rule"] == "must_not_contain" and (hit or pattern.search(swipe)):
            rep.errors.append(f"K{c['id']} correction violated ({c['reason']}): /{c['pattern']}/")
        if c["rule"] == "must_contain" and not hit:
            rep.errors.append(f"K{c['id']} correction violated ({c['reason']}): /{c['pattern']}/")


COUNTERS_FIX = (
    "Write counters.json with 1 to 3 counter-ad briefs, one per gap in analysis.json "
    "(each needs gap_ref, beats_ad_id, angle, headline, hook, visual_direction and "
    "why_it_beats; see skills/ad-spy-kit-counter/SKILL.md), then render again."
)


def check_counters(docs: dict[str, dict[str, Any] | None], rep: Report) -> None:
    counters, winners, analysis = docs["counters"], docs["winners"], docs["analysis"]
    if not (counters and winners):
        return
    if not counters.get("counters"):
        # The board always prints a YOUR COUNTER-AD panel; with no brief it renders empty.
        rep.errors.append(
            "A3 counters.json has no briefs, so the board's YOUR COUNTER-AD panel would be "
            "empty. " + COUNTERS_FIX
        )
        return
    win_ids = {w["ad_id"] for w in winners.get("winners", [])}
    n_gaps = len((analysis or {}).get("gaps", []))
    for i, c in enumerate(counters.get("counters", [])):
        if c.get("beats_ad_id") and c["beats_ad_id"] not in win_ids:
            rep.errors.append(f"A2 counters[{i}] beats {c['beats_ad_id']!r}, which is not a winner")
        if n_gaps and not 0 <= int(c.get("gap_ref", -1)) < n_gaps:
            rep.errors.append(f"A2 counters[{i}].gap_ref {c.get('gap_ref')} is not a gap index")


def check_no_ad_ids(run_dir: Path, rep: Report) -> None:
    """C7: the board names ads by winner rank (#01); raw ad ids are clutter."""
    html_path, ads_path = run_dir / "board.html", run_dir / "ads.raw.json"
    if not (html_path.exists() and ads_path.exists()):
        return
    ids = [a.get("ad_id") for a in json.loads(ads_path.read_text()).get("ads", [])]
    errs = board_html_errors(html_path.read_text(), ids)
    rep.errors.extend(e for e in errs if e.startswith("C7"))


def validate_run(
    run_dir: Path, *, rendered: bool = True, corrections: list[dict[str, Any]] | None = None
) -> Report:
    run_dir = Path(run_dir)
    docs = {name: _load(run_dir, name) for name in DOCS}
    rep = Report()
    check_contracts(docs, rep)
    check_citations(docs, rep)
    check_numbers(docs, rep)
    check_formats(docs, rep)
    check_lanes(docs, rep)
    check_hidden_ads(docs, rep)
    check_rank_refs(docs, rep)
    check_winners(docs, rep)
    check_copy(docs, rep)
    check_counters(docs, rep)
    if rendered:
        check_render(run_dir, rep)
        check_no_ad_ids(run_dir, rep)
        check_corrections(run_dir, rep, load_corrections() if corrections is None else corrections)
    return rep
