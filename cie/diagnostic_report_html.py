"""Offline renderer for the CIE diagnostic report.

The entry point takes a ``report_data`` dict and returns a complete HTML string.
It uses the shared local image probe but no network or external fonts (system
stack only). Validated images are embedded as base64 data URIs so the report is
a single portable file.

report_data contract (all keys optional except ``niche``; a section is omitted
when its data is absent):

    niche: str
    ads_scanned: int
    rivals_count: int
    headline: {"top": str, "bottom": str}         # bottom line glows green
    stats: [ {"label", "value", "sub", "tone"} ]  # tone in {"g","h","b",None}
    competitors: [ {"name","handle","seed_or_discovered",
                    "ads_sampled_count","organic_sampled_count","note"} ]
                 # also accepts a plain list[str] (degrades to name-only)
    winner: {"image_path","format","cost_label","cost_value","subs",
             "saturation","headline","desc","so_what"}
    formats: [ {"format","desc","thumb_path","organic","paid","gap",
                "verdict","verdict_class","sample_label"} ]  # verdict_class in
                # {"open","watch","signal","con","sat","dead"}
    message_frames: [ {"frame","organic","paid","sample","sample_source"} ]
    format_read: str
    swipe_file: [ {"source_type","source_label","format","name","image_path",
                   "url","pulled_text","body_text","metric_label","metric_value",
                   "secondary_label","secondary_value"} ]
    buyer_persona: {"who","appearance","face_paths":[str]}
    cast: {"faces":[{"handle","avatar_path","initials"}],
           "characters":[...],"source":{"source_label"},"casting_paragraph",
           "axes":[{"k","v"}],"face_note"}
    gap: {"format","gap_score"} | None
    gap_insight: str
"""

import base64
import html
import os
import re
from urllib.parse import urlsplit

YOUFORM_CTA_URL = "https://app.youform.com/forms/tpicbmi7"
MATTHEW_X_URL = "https://x.com/themattberman"
EMERALD_URL = "https://emerald.digital"
STEALADS_URL = "https://stealads.ai"

_VERDICT_PILL = {
    "probe": "probe",
    "baseline": "baseline",
    "sustained": "sustained",
    "watch": "watch",
    "signal": "signal",
    "con": "con",
    "sat": "sat",
}

_FORMAT_GLOSSARY = {
    "yapper": "plainspoken talking-head content; one person, direct-to-viewer, opinion or operator lesson first",
    "faceless-demo": "product or workflow demo with little or no visible human character",
    "interview-podcast-street-mic": "interview, podcast, or street-mic creative built around conversation",
    "employee-warehouse": "raw staff, warehouse, packing, or behind-the-counter creative",
    "founder-bts": "behind-the-scenes founder or operator story content",
    "ui-mimic": "creative that looks like an app screen, dashboard, text thread, or native interface",
    "testimonial-screenshot": "customer review, comment, testimonial, or star-rating screenshot",
    "advertorial": "press-style or editorial screenshot creative",
    "notification-ui": "lock-screen, message, DM, alert, or phone-notification mimic",
    "carousel": "multi-frame swipeable post, usually built to teach, compare, or prove a point",
    "insufficient-evidence": "retained receipt where the run did not have enough signal for a scoreable format",
}

_FRAME_GLOSSARY = {
    "us-vs-them": "sets the audience against the old choice, incumbent, or wrong way",
    "old-way-new-way": "contrasts what people used to do with the newer/better path",
    "hidden-cost": "points to a leak, waste, missed revenue, or unseen drag",
    "before-after": "shows a change from prior state to improved state",
    "mistake-to-avoid": "warns the viewer away from a common error",
    "myth-bust": "challenges a belief the market repeats",
    "contrarian-take": "leads with an opinion that cuts against the default view",
    "proof-stack": "leans on numbers, receipts, cases, or visible results",
    "comparison": "compares options, products, methods, or tradeoffs",
    "social-proof": "uses adoption, testimonials, reviews, or crowd signal",
    "authority-education": "teaches from expert or operator authority",
    "self-diagnosis": "helps the viewer audit or score their own situation",
    "failed-attempts": "names what was tried before the better answer",
    "villain-callout": "gives the problem a visible enemy",
    "identity-belonging": "signals who this is for and who gets it",
    "risk-reversal": "reduces fear with trial, guarantee, cancelation, or low-risk language",
    "urgency-scarcity": "uses timing pressure or limited availability",
    "feature-to-benefit": "turns a feature into a viewer/business outcome",
    "how-it-works": "explains the mechanism, workflow, or process",
    "offer-led": "leads with price, discount, bonus, or deal terms",
    "skeptical-expose": "opens like an investigation, expose, or skeptical consumer report",
    "reverse-psychology": "tells the wrong person not to buy or filters the audience",
    "life-hack": "frames the idea as hidden practical knowledge or a shortcut",
    "forbidden-secret": "implies forbidden, restricted, or not-supposed-to-know information",
    "ancestral-tradition": "contrasts old/traditional methods against modern synthetic ones",
    "skeptic-to-believer": "moves from doubt or social resistance to proof",
    "reasons-why": "lists explicit reasons to buy, switch, believe, or care",
    "avatar-callout": "calls out a specific persona or niche identity",
    "cost-transparency": "explains markup, pricing, middlemen, or direct-cost economics",
    "challenge": "uses a test, challenge, ranking, or gamified proof moment",
    "insufficient-evidence": "retained receipt where the run did not have enough signal for a message frame",
}

_MECHANIC_GLOSSARY = {
    "green-screen": "creator talking over source footage, site, chart, or B-roll",
    "split-screen": "screen divided between pitch/source footage and another retention visual",
    "kinetic-captions": "captions or subtitles use movement, highlighting, or visual interruption",
    "loop": "short repeating visual designed to earn rewatch or dwell time",
    "story-poll-mimic": "fake native story poll, quiz, or tap-to-vote element",
    "carousel-reveal": "carousel uses blur, reveal, or payoff across cards",
    "carousel-self-segmentation": "carousel lets viewers choose a persona/use-case path",
    "creator-handle": "paid creative appears through a creator or partner identity",
    "stitch-bait": "opens by reacting to or stitching a viral clip",
}

_FORMAT_LABELS = {
    "yapper": "Talking-head operator clips",
    "faceless-demo": "Faceless demo",
    "pov-fps": "POV / first-person",
    "group-reaction": "Group reaction",
    "tiktok-shop-hustle": "TikTok Shop hustle",
    "interview-podcast-street-mic": "Interview / podcast / street mic",
    "employee-warehouse": "Employee / warehouse native",
    "founder-bts": "Founder behind-the-scenes",
    "gossip-grwm": "Gossip / GRWM story",
    "authority-figure": "Authority figure",
    "narrative-vlog-ditl": "Day-in-the-life story",
    "de-influencing": "De-influencing",
    "realistic-unboxing": "Realistic unboxing",
    "vsl": "VSL",
    "wall-of-text": "Wall of text",
    "desire-metaphor-short": "Desire metaphor short",
    "split-screen-sludge": "Split-screen sludge",
    "micro-loop": "Micro-loop",
    "ai-vo-broll": "AI voiceover / B-roll",
    "ai-song": "AI song",
    "asmr-audio-only": "ASMR / audio-only",
    "voice-note-mimic": "Voice-note mimic",
    "retention-edit-technique": "Retention edit",
    "ai-animation": "AI animation",
    "partnership-native-mimic": "Native partnership mimic",
    "text-only-founders-letter": "Text-only founder letter",
    "native-photo-long-copy": "Native photo + long copy",
    "post-it-note": "Post-it note",
    "ui-mimic": "UI mimic",
    "tweet-reddit-ui": "Tweet / Reddit UI",
    "advertorial": "Advertorial",
    "notification-ui": "Notification UI",
    "infographic-proof": "Infographic proof",
    "grid-static": "Grid static",
    "testimonial-screenshot": "Testimonial screenshot",
    "timeline-proof": "Timeline proof",
    "first-frame-static": "First-frame static",
    "thermal-vision": "Thermal / X-ray visual",
    "diagram-puzzle": "Diagram / puzzle",
    "flat-lay-fit-test": "Flat-lay fit test",
    "spot-the-difference": "Spot the difference",
    "circle-arrow-explainer": "Circle-arrow explainer",
    "quadrant-matrix": "Quadrant / matrix",
    "chart-breakout": "Chart breakout",
    "carousel": "Carousel",
    "insufficient-evidence": "Insufficient evidence",
}

_FRAME_LABELS = {
    "us-vs-them": "Us vs. them",
    "old-way-new-way": "Old way / new way",
    "hidden-cost": "Hidden cost",
    "before-after": "Before / after",
    "mistake-to-avoid": "Mistake to avoid",
    "myth-bust": "Myth bust",
    "contrarian-take": "Contrarian take",
    "proof-stack": "Proof stack",
    "comparison": "Comparison",
    "social-proof": "Social proof",
    "authority-education": "Authority education",
    "self-diagnosis": "Self-diagnosis",
    "failed-attempts": "Failed attempts",
    "villain-callout": "Villain callout",
    "identity-belonging": "Identity / belonging",
    "risk-reversal": "Risk reversal",
    "urgency-scarcity": "Urgency / scarcity",
    "feature-to-benefit": "Feature to benefit",
    "how-it-works": "How it works",
    "offer-led": "Offer-led",
    "skeptical-expose": "Skeptical expose",
    "reverse-psychology": "Reverse psychology",
    "life-hack": "Life hack",
    "forbidden-secret": "Forbidden secret",
    "ancestral-tradition": "Ancestral / tradition",
    "skeptic-to-believer": "Skeptic to believer",
    "reasons-why": "Reasons why",
    "avatar-callout": "Avatar callout",
    "cost-transparency": "Cost transparency",
    "challenge": "Challenge",
    "insufficient-evidence": "Insufficient evidence",
}


def _esc(v) -> str:
    if v is None:
        return ""
    return html.escape(str(v).replace("\u2014", "-").replace("\u2013", "-"))


def _external_url_attr(value) -> str | None:
    if value is None:
        return None
    url = str(value).strip()
    if not url or any(ord(character) < 32 or ord(character) == 127 for character in url):
        return None
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        return None
    return html.escape(url, quote=True)


def _fmt_label(fmt) -> str:
    return _FORMAT_LABELS.get(fmt, str(fmt or ""))


def _frame_label(frame) -> str:
    return _FRAME_LABELS.get(frame, str(frame or ""))


def _mechanic_label(mechanic) -> str:
    labels = {
        "green-screen": "Green screen",
        "split-screen": "Split screen",
        "kinetic-captions": "Kinetic captions",
        "loop": "Loop",
        "story-poll-mimic": "Story poll mimic",
        "carousel-reveal": "Carousel reveal",
        "carousel-self-segmentation": "Carousel self-segmentation",
        "creator-handle": "Creator handle",
        "stitch-bait": "Stitch bait",
    }
    return labels.get(mechanic, str(mechanic or ""))


def watched_coverage(records):
    return {
        "watched": sum(1 for record in records if record.get("visual_evidence_scope") == "full-motion"),
        "total": len(records),
    }


def _scope_label(scope):
    return {
        "full-motion": "Watched",
        "still-only": "Static image",
        "unwatched": "Unwatched - excluded",
    }.get(scope, "Scope unavailable")


def _img_data_uri(path) -> str | None:
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ("png" if ext == "png" else "jpeg")
    try:
        with open(path, "rb") as f:
            return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return None


def _money(value) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return _esc(value or "unknown")


def _compact_number(value) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _esc(value)

    def suffix(num, label):
        text = f"{num:.1f}".rstrip("0").rstrip(".")
        return f"{text}{label}"

    if value >= 1_000_000:
        return suffix(value / 1_000_000, "M")
    if value >= 1_000:
        return suffix(value / 1_000, "K")
    return str(value)


def _stat_tiles(report_data: dict) -> str:
    stats = report_data.get("stats")
    if not stats:
        return ""
    cells = []
    for s in stats:
        tone = s.get("tone")
        cls = f" {tone}" if tone in ("g", "h", "b") else ""
        sub = str(s.get("sub") or "")
        sub = sub.replace("from the selected source", "from the organic sample")
        cells.append(
            '<div class="stat">'
            f'<div class="l">{_esc(s.get("label"))}</div>'
            f'<div class="n{cls}">{_esc(s.get("value"))}</div>'
            f'<div class="s">{_esc(sub)}</div>'
            "</div>"
        )
    return '<div class="stats">' + "".join(cells) + "</div>"


def _competitors_block(report_data: dict) -> str:
    comps = report_data.get("competitors") or []
    if not comps:
        return ""
    cards = []
    for c in comps:
        if isinstance(c, str):
            c = {"name": c}
        counts = ""
        if "ads_sampled_count" in c or "organic_sampled_count" in c:
            parts = []
            if c.get("ads_sampled_count"):
                parts.append(f'{_esc(c.get("ads_sampled_count"))} paid ads')
            if c.get("organic_sampled_count"):
                parts.append(f'{_esc(c.get("organic_sampled_count"))} organic posts')
            counts = f'<span>{" / ".join(parts)} sampled</span>' if parts else ""
        cards.append(
            '<div class="comp">'
            f'<div class="ch"><b>{_esc(c.get("name"))}</b>'
            f'<span class="hd">{_esc(c.get("handle", ""))}</span></div>'
            f'<div class="cmeta">{counts}</div>'
            f'<div class="cnote">{_esc(c.get("note", ""))}</div>'
            "</div>"
        )
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Who we analyzed</span></div>'
        '<div class="seclede">Paid-ad coverage across the competitors in this sample.</div>'
        '<div class="comps">' + "".join(cards) + "</div>"
    )


def _structured_count(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _resolved_paid_count(brief: dict):
    paid_count = _structured_count(brief.get("paid_count"))
    if paid_count is not None:
        return paid_count
    detail = str(brief.get("challenger_detail", ""))
    if "zero live ads" in detail.lower():
        return 0
    ints = re.findall(r"\d+", detail)
    if len(ints) >= 2:
        return int(ints[1])
    return None


def _resolved_organic_count(brief: dict):
    organic_count = _structured_count(brief.get("organic_count"))
    if organic_count is not None:
        return organic_count
    match = re.search(r"\d+", str(brief.get("challenger_detail", "")))
    return int(match.group()) if match else None


def _resolved_gap_format(report_data: dict, brief: dict) -> str:
    return (
        brief.get("gap_format")
        or (report_data.get("gap") or {}).get("format")
        or (report_data.get("winner") or {}).get("format")
        or ""
    )


def _resolved_baseline_format(report_data: dict, brief: dict) -> str:
    return (
        brief.get("baseline_format")
        or (report_data.get("paid_baseline") or {}).get("format")
        or ""
    )


def _winner_image_data(report_data: dict) -> str | None:
    if not report_data.get("gap"):
        return None
    winner = report_data.get("winner") or {}
    return _img_data_uri(winner.get("image_path"))


def _opening_block(
    report_data: dict,
    h_top: str,
    h_bottom: str,
    lede: str,
    winner_image: str | None,
    has_proof: bool,
    patterns_lead: bool = False,
) -> str:
    # When ranked patterns lead the report, the hero is headline + lede only; the gap winner image
    # and the "test this format" takeaway move out of the hero (the patterns section carries them).
    if patterns_lead:
        return (
            '<section class="opening no-proof"><div class="opening-copy">'
            f'<div class="opening-head"><h1>{h_top}<br><span class="g">{h_bottom}</span></h1>'
            f'<div class="lede">{lede}</div></div></div></section>'
        )
    has_gap = bool(report_data.get("gap"))
    brief = report_data.get("decision_brief") or {}
    winner = report_data.get("winner") or {}
    proof = ""
    if has_proof and winner_image:
        gap_format = _resolved_gap_format(report_data, brief) or winner.get("format")
        format_label = _fmt_label(gap_format) if gap_format else brief.get("challenger_title", "")
        organic_count = _resolved_organic_count(brief)
        paid_count = _resolved_paid_count(brief)
        ads_scanned = _structured_count(report_data.get("ads_scanned"))
        organic_label = (
            f"{organic_count} organic posts"
            if organic_count is not None
            else "- organic posts"
        )
        paid_label = (
            f"{paid_count} of {ads_scanned} paid ads"
            if paid_count is not None and ads_scanned is not None
            else f"{paid_count} paid ads"
            if paid_count is not None
            else "- paid ads"
        )
        proof = (
            '<figure class="opening-proof">'
            f'<img src="{_esc(winner_image)}" alt="Top organic example in {_esc(format_label)}">'
            '<figcaption class="proof-caption">'
            f'<div><span>Format</span><b>{_esc(format_label)}</b></div>'
            f'<div><span>Open-lane proof</span><b>{_esc(organic_label)}<br>{_esc(paid_label)}</b></div>'
            '</figcaption></figure>'
        )

    if has_proof:
        takeaway = (
            '<div class="takeaway">'
            '<span>The 10-second takeaway</span>'
            f'<h2>{_esc(brief.get("challenger_title"))}</h2>'
            f'<p>{_esc(brief.get("test_detail"))}</p>'
            '</div>'
            if brief
            else ""
        )
    elif has_gap:
        takeaway = (
            '<section class="decision-brief no-gap-read">'
            '<div class="decision-kicker">The read <span>Evidence incomplete</span></div>'
            '<div class="decision-lead"><span>Evidence</span>'
            '<h3>No decisive recommendation is shown because the strongest creative receipt is unavailable.</h3>'
            '<p>Restore the missing receipt or rerun the capture before choosing a format to test.</p>'
            '</div></section>'
        )
    else:
        takeaway = _gap_block(report_data)

    opening_class = "opening" if proof else "opening no-proof"
    return (
        f'<section class="{opening_class}">'
        '<div class="opening-copy">'
        f'<div class="opening-head"><h1>{h_top}<br><span class="g">{h_bottom}</span></h1>'
        f'<div class="lede">{lede}</div></div>'
        f'{takeaway}</div>{proof}</section>'
    )


def _signal_band_block(report_data: dict, has_proof: bool) -> str:
    if not has_proof or not report_data.get("decision_brief"):
        return ""
    brief = report_data["decision_brief"]
    organic_count = _resolved_organic_count(brief)
    paid_count = _resolved_paid_count(brief)
    ads_scanned = _structured_count(report_data.get("ads_scanned"))
    baseline_format = _resolved_baseline_format(report_data, brief)
    gap_format = _resolved_gap_format(report_data, brief)
    organic_value = organic_count if organic_count is not None else "-"
    paid_value = (
        f"{paid_count} / {ads_scanned}"
        if paid_count is not None and ads_scanned is not None
        else paid_count
        if paid_count is not None
        else "-"
    )
    return (
        '<section class="signal-band">'
        '<div class="signal-grid">'
        f'<div class="signal-stat"><b>{_esc(organic_value)}</b><span>Organic posts using the challenger</span></div>'
        f'<div class="signal-stat"><b>{_esc(paid_value)}</b><span>Paid ads using the challenger</span></div>'
        '<div class="signal-read">'
        f'<p>The category funds the {_esc(_fmt_label(baseline_format).lower() or "paid default")}. '
        f'<span class="g">The feed rewards the {_esc(_fmt_label(gap_format).lower() or "open lane")}.</span></p>'
        '</div></div>'
        f'<div class="signal-note">{_esc(brief.get("evidence_note"))}</div>'
        '</section>'
    )


def _operational_test_block(report_data: dict, has_proof: bool) -> str:
    if not has_proof or not report_data.get("decision_brief"):
        return ""
    brief = report_data["decision_brief"]
    test_detail = str(brief.get("test_detail") or "")
    constant_detail = test_detail[test_detail.find("Change nothing else."):] if "Change nothing else." in test_detail else test_detail
    baseline_format = _resolved_baseline_format(report_data, brief)
    gap_format = _resolved_gap_format(report_data, brief)
    return (
        '<section class="operational-test">'
        f'<h2>{_esc(brief.get("test_title"))}</h2>'
        '<div class="test-grid">'
        '<div class="test-cell control"><span>Control</span>'
        f'<h3>{_esc(_fmt_label(baseline_format) or brief.get("baseline_title"))}</h3><p>{_esc(brief.get("baseline_detail"))}</p></div>'
        '<div class="test-cell challenger"><span>Challenger</span>'
        f'<h3>{_esc(_fmt_label(gap_format) or brief.get("challenger_title"))}</h3><p>{_esc(brief.get("challenger_detail"))}</p></div>'
        '</div>'
        '<div class="constant-row"><span>Hold constant</span>'
        f'<p>{_esc(constant_detail)}</p></div>'
        '</section>'
    )


def _winner_block(report_data: dict) -> str:
    w = report_data.get("winner")
    if not w:
        return ""
    img = _img_data_uri(w.get("image_path"))
    frame = (
        f'<div class="frame"><span class="fl">TOP ORGANIC EXAMPLE</span>'
        f'<img src="{img}" alt="top performer"></div>'
        if img
        else ""
    )
    ledger = "".join(
        f'<div><div class="k">{_esc(k)}</div><div class="val{(" g" if tone else "")}">{_esc(v)}</div></div>'
        for k, v, tone in (
            ("Format", _fmt_label(w.get("format")), False),
            (w.get("cost_label", "Organic views"), _compact_number(w.get("cost_value")), True),
            ("Paid ads using it", w.get("saturation"), True),
        )
    )
    so_what = (
        f'<div class="socall"><b>So what:</b> {_esc(w.get("so_what"))}</div>'
        if w.get("so_what")
        else ""
    )
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Strongest open lane</span></div>'
        f'<div class="seclede">{_esc(w.get("desc_lede", "The strongest sampled opening came from a format with organic pull and weak paid coverage."))}</div>'
        f'<div class="exhibit{" no-frame" if not frame else ""}">'
        f"{frame}"
        f'<div><h3>{_esc(w.get("headline"))}</h3>'
        f'<div class="desc">{_esc(w.get("desc"))}</div>'
        f'<div class="ledger">{ledger}</div>{so_what}</div>'
        "</div>"
    )


def _format_table(report_data: dict, has_proof: bool) -> str:
    formats = report_data.get("formats") or []
    if not formats:
        return ""
    rows = []
    for fm in formats:
        vc = fm.get("verdict_class", "con")
        verdict = fm.get("verdict")
        if not has_proof and vc == "probe":
            vc = "signal"
            verdict = "NEEDS MORE SIGNAL"
        pill_cls = _VERDICT_PILL.get(vc, "con")
        gap_cls = {"probe": "g", "baseline": "b", "sustained": "b", "watch": "g", "signal": "a", "con": "a", "sat": "h"}.get(vc, "a")
        thumb = _img_data_uri(fm.get("thumb_path"))
        thumb_html = f'<img src="{thumb}" alt="">' if thumb else ""
        term = _FORMAT_GLOSSARY.get(fm.get("format"), "")
        sample_label = str(fm.get("sample_label", "")).replace("rivals", "competitors")
        if sample_label == "sampled organic":
            sample_label = "Sampled organic post"
        rows.append(
            f'<tr class="{"win" if vc == "probe" else ""}">'
            f'<td><div class="fmt"><div class="thumb">{thumb_html}</div>'
            f'<div><b>{_esc(_fmt_label(fm.get("format")))}</b><small>{_esc(fm.get("desc") or term)}</small>'
            f'<span class="lbl">{_esc(sample_label)}</span></div></div></td>'
            f'<td><span class="track"><span class="fill org" style="width:{int(fm.get("organic", 0))}%"></span></span>'
            f'<span class="v">{_esc(fm.get("organic"))}</span></td>'
            f'<td><span class="track"><span class="fill paid" style="width:{int(fm.get("paid", 0))}%"></span></span>'
            f'<span class="v">{_esc(fm.get("paid"))}</span></td>'
            f'<td class="gap {gap_cls}">{_esc(fm.get("gap"))}</td>'
            f'<td><span class="pill {pill_cls}">{_esc(verdict)}</span></td></tr>'
        )
    read = (
        f'<div class="socall" style="margin-top:18px"><b>The read:</b> {_esc(report_data.get("format_read"))}</div>'
        if has_proof and report_data.get("format_read")
        else ""
    )
    lede = (
        "Organic examples show what people watched. Paid examples show what competitors kept running. "
        "The table compares those sampled signals."
        if has_proof
        else "The table summarizes the organic and paid creative evidence in this sample without making a recommendation."
    )
    organic_head = "Organic attention"
    coverage = report_data.get("watched_coverage") or {}
    paid_coverage = coverage.get("paid") or {}
    organic_coverage = coverage.get("organic") or {}
    coverage_line = (
        '<div class="seclede scope-note">Counts exclude unwatched-video and insufficient-evidence creative; '
        'video formats are read only from watched frames, static formats from the still. '
        f'Full-motion watched: {int(paid_coverage.get("watched", 0))} of {int(paid_coverage.get("total", 0))} paid, '
        f'{int(organic_coverage.get("watched", 0))} of {int(organic_coverage.get("total", 0))} organic.</div>'
        if coverage
        else ""
    )
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Creative format evidence</span></div>'
        f'<div class="seclede">{_esc(lede)}</div>'
        + coverage_line
        + f'<table class="tbl"><thead><tr><th>Format</th><th>{_esc(organic_head)} (0-100)</th>'
        "<th>Paid persistence (0-100)</th><th>Opportunity</th><th>What it means</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + read
    )


def _message_frame_block(report_data: dict, has_proof: bool) -> str:
    frames = [
        row for row in (report_data.get("message_frames") or [])
        if row.get("frame") != "insufficient-evidence"
    ][:3]
    mechanics = report_data.get("mechanics") or []
    if not frames and not mechanics:
        return ""
    # A short strategic read per frame. Keeps the section as intelligence (how to
    # hold the test honest) rather than reprinting raw ad copy already shown in the
    # receipts. Bespoke line per common frame, with a direction-based fallback so
    # rare frames still get a useful note instead of a repeated one.
    frame_specific_reads = {
        "feature-to-benefit": "The default paid pitch. A clean control, but crowded.",
        "us-vs-them": "The format, not the contrast, is what earns separation.",
        "how-it-works": "A teaching frame that rides either execution.",
        "life-hack": "Balanced utility. No lane from the message alone.",
        "authority-education": "Authority reads better from a real face than a demo.",
        "self-diagnosis": "Pulls organically. A live challenger angle to test.",
        "proof-stack": "Proof lands harder with a person attached to it.",
        "comparison": "Comparison travels on format as much as on claim.",
        "social-proof": "Social proof wants a face, not a UI.",
        "identity-belonging": "Identity is a casting call, not a copy line.",
    }
    direction_reads = {
        "Paid-heavy": "Heavy in paid. A useful control, but crowded territory.",
        "Organic-heavy": "Organic pull lives here. A live challenger angle to test.",
        "Shared": "The format, not this frame, is what creates the separation.",
    }
    frame_cards = []
    for row in frames:
        frame = row.get("frame", "")
        organic = int(row.get("organic", 0) or 0)
        paid = int(row.get("paid", 0) or 0)
        direction = "Shared"
        if paid >= organic * 2 and paid > organic:
            direction = "Paid-heavy"
        elif organic >= paid * 2 and organic > paid:
            direction = "Organic-heavy"
        read = frame_specific_reads.get(frame) or direction_reads[direction]
        frame_cards.append(
            '<div class="message-row">'
            f'<div class="message-title"><b>{_esc(_frame_label(frame))}</b><span>{_esc(direction)}</span></div>'
            f'<div class="framecounts"><span>{_esc(organic)} organic</span>'
            f'<span>{_esc(paid)} paid</span></div>'
            f'<div class="message-sample"><p>{_esc(read)}</p></div>'
            '</div>'
        )
    mechanic_cards = []
    for row in mechanics[:5]:
        mechanic = row.get("mechanic", "")
        mechanic_cards.append(
            '<span class="mechanic-summary">'
            f'<b>{_esc(_mechanic_label(mechanic))}</b> · '
            f'{_esc(row.get("organic", 0))} organic / {_esc(row.get("paid", 0))} paid'
            '</span>'
        )
    frame_html = (
        f'<div class="message-ledger">{"".join(frame_cards)}</div>'
        if frame_cards
        else ""
    )
    mechanic_html = (
        '<div class="execution-head"><b>Execution patterns observed</b>'
        '<span>Common devices in the sample, not evidence of the market gap.</span></div>'
        f'<div class="mechanics-strip">{"".join(mechanic_cards)}</div>'
        if mechanic_cards
        else ""
    )
    lede = (
        "Use these patterns to keep the format test honest, not as hooks to copy."
        if has_proof
        else "Patterns observed across the sampled creative."
    )
    heading = "Messaging patterns worth controlling" if has_proof else "Messaging patterns observed"
    return (
        '<div class="rule"></div>'
        f'<div class="exh"><span>{_esc(heading)}</span></div>'
        f'<div class="seclede">{_esc(lede)}</div>'
        f'{frame_html}{mechanic_html}'
    )


def _decision_brief_block(report_data: dict) -> str:
    brief = report_data.get("decision_brief") or {}
    if not brief:
        return ""
    return (
        '<section class="decision-brief">'
        '<div class="decision-kicker">The move <span>10-second read</span></div>'
        '<div class="decision-lead">'
        '<span>Challenger</span>'
        f'<h3>{_esc(brief.get("challenger_title"))}</h3>'
        f'<p>{_esc(brief.get("challenger_detail"))}</p>'
        '</div>'
        '<div class="decision-grid">'
        '<div class="decision-item baseline">'
        '<span>Control</span>'
        f'<h3>{_esc(brief.get("baseline_title"))}</h3>'
        f'<p>{_esc(brief.get("baseline_detail"))}</p>'
        '</div>'
        '<div class="decision-item setup">'
        '<span>Test</span>'
        f'<h3>{_esc(brief.get("test_title"))}</h3>'
        f'<p>{_esc(brief.get("test_detail"))}</p>'
        '</div>'
        '</div>'
        f'<div class="decision-note">{_esc(brief.get("evidence_note"))}</div>'
        '</section>'
    )


def _swipe_card(item: dict) -> str:
    image = _img_data_uri(item.get("image_path"))
    source_type = item.get("source_type", "")
    badge_cls = "paid" if source_type == "paid" else "organic"
    media = f'<img src="{image}" alt="">' if image else '<div class="swipe-missing">Preview unavailable</div>'
    url = _external_url_attr(item.get("url"))
    link = (
        f'<a class="swipe-link" href="{url}">Open source</a>'
        if url
        else ""
    )
    body = f'<p class="swipe-body">{_esc(item.get("body_text"))}</p>' if item.get("body_text") else ""
    frame = item.get("message_frame")
    frame_pill = f'<span class="framepill">{_esc(_frame_label(frame))}</span>' if frame else ""
    mechanics = item.get("mechanics") or []
    mechanic_pills = "".join(f'<span class="mechanicpill">{_esc(_mechanic_label(m))}</span>' for m in mechanics[:3])
    scope = (
        f'<span class="scopepill">{_esc(_scope_label(item.get("visual_evidence_scope")))}</span>'
        if "visual_evidence_scope" in item
        else ""
    )
    return (
        '<div class="swipe-card">'
        f'<div class="swipe-media">{media}</div>'
        f'<div class="swipe-badge {badge_cls}">{_esc(item.get("source_label"))}</div>'
        '<div class="swipe-copy">'
        f'<div class="swipe-meta"><span>{_esc(_fmt_label(item.get("format")))}</span><span>{_esc(item.get("name"))}</span></div>'
        f'<div class="swipe-pills">{scope}{frame_pill}{mechanic_pills}</div>'
        f'<h3>{_esc(item.get("pulled_text") or item.get("name") or "Evidence example")}</h3>'
        f'{body}'
        '<div class="swipe-stats">'
        f'<div><b>{_compact_number(item.get("metric_value"))}</b><span>{_esc(item.get("metric_label"))}</span></div>'
        f'<div><b>{_compact_number(item.get("secondary_value"))}</b><span>{_esc(item.get("secondary_label"))}</span></div>'
        '</div>'
        f'{link.replace("Open source", "View original")}'
        '</div></div>'
    )


def _swipe_text_card(item: dict) -> str:
    url = _external_url_attr(item.get("url"))
    link = f'<a class="swipe-link" href="{url}">Open source</a>' if url else ""
    scope = (
        f'<div class="swipe-pills"><span class="scopepill">{_esc(_scope_label(item.get("visual_evidence_scope")))}</span></div>'
        if "visual_evidence_scope" in item
        else ""
    )
    return (
        '<div class="swipe-text-card">'
        f'<div class="swipe-meta"><span>{_esc(_fmt_label(item.get("format")))}</span><span>{_esc(item.get("name"))}</span></div>'
        f'{scope}'
        f'<h3>{_esc(item.get("pulled_text") or item.get("name") or "Evidence example")}</h3>'
        f'<div class="swipe-stats"><div><b>{_compact_number(item.get("metric_value"))}</b><span>{_esc(item.get("metric_label"))}</span></div>'
        f'<div><b>{_compact_number(item.get("secondary_value"))}</b><span>{_esc(item.get("secondary_label"))}</span></div></div>'
        f'{link.replace("Open source", "View original")}</div>'
    )


def _has_local_image(item: dict) -> bool:
    return bool(_img_data_uri(item.get("image_path")))


def _swipe_band(title: str, lede: str, items: list[dict], cls: str = "") -> str:
    if not items:
        return ""
    image_items = [item for item in items if _has_local_image(item)]
    if image_items:
        cards = "".join(_swipe_card(item) for item in image_items)
        content = f'<div class="swipe-grid">{cards}</div>'
    else:
        cards = "".join(_swipe_text_card(item) for item in items)
        content = f'<div class="swipe-text-grid">{cards}</div>'
    return (
        f'<div class="swipe-band {cls}">'
        f'<div class="band-head"><h3>{_esc(title)}</h3><p>{_esc(lede)}</p></div>'
        f'{content}'
        '</div>'
    )


def _swipe_file_block(report_data: dict, has_proof: bool) -> str:
    items = report_data.get("swipe_file") or []
    if not items:
        return ""

    paid = [item for item in items if item.get("source_type") == "paid"]
    organic = [item for item in items if item.get("source_type") != "paid"]
    media_note = (
        '<div class="fixture-note">Preview unavailable. Source text and a link to the original are still included.</div>'
        if not any(_has_local_image(item) for item in items)
        else ""
    )
    if has_proof:
        top_lede = "Representative ads and organic posts behind the recommendation."
        paid_title = "Paid control"
        paid_lede = "Long-running competitor ads establish the format to beat."
        organic_title = "Organic challenger"
        organic_lede = "High-attention organic posts establish the format worth testing."
    else:
        top_lede = "Representative paid ads and organic posts retained as evidence from this sample."
        paid_title = "Paid evidence"
        paid_lede = "Paid ads retained as evidence from this sample."
        organic_title = "Organic evidence"
        organic_lede = "Organic posts retained as evidence from this sample."

    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Evidence gallery</span></div>'
        f'<div class="seclede">{_esc(top_lede)}</div>'
        + media_note
        + _swipe_band(
            paid_title,
            paid_lede,
            paid,
            "paid-band",
        )
        + _swipe_band(
            organic_title,
            organic_lede,
            organic,
            "organic-band",
        )
    )


def _face(path, initials="", handle=None) -> str:
    uri = _img_data_uri(path)
    if not uri:
        return ""
    inner = f'<img src="{uri}">'
    handle_html = f'<span>{_esc(handle)}</span>' if handle is not None else ""
    return f'<div class="face"><div class="ph">{inner}</div>{handle_html}</div>'


def _confidence_label(value) -> str:
    if value in ("", None):
        return ""
    try:
        pct = round(float(value) * 100)
        if 0 <= pct <= 100:
            return f"{pct}% confidence"
    except (TypeError, ValueError):
        pass
    return f"confidence {value}"


def _character_card(character: dict) -> str:
    image = _img_data_uri(character.get("thumbnail_path") or character.get("avatar_path"))
    avatar = _img_data_uri(character.get("avatar_path"))
    avatar_html = f'<span class="character-avatar"><img src="{avatar}" alt=""></span>' if avatar else ""
    media = f'<div class="character-media"><img src="{image}" alt="">{avatar_html}</div>' if image else ""
    handle = character.get("handle") or character.get("name") or "Retained creator"
    line_one = " / ".join([v for v in (character.get("setting"), character.get("energy")) if v])
    line_two = " / ".join([v for v in (character.get("age"), character.get("build")) if v])
    tags = "".join(
        f'<span>{_esc(tag)}</span>'
        for tag in (character.get("styling"), character.get("polish"))
        if tag
    )
    confidence = _confidence_label(character.get("confidence"))
    meta = ""
    return (
        f'<div class="character-card{" no-media" if not image else ""}">'
        f'{media}'
        '<div class="character-copy">'
        f'<h3>{_esc(handle)}</h3>'
        + (f'<p>{_esc(line_one)}</p>' if line_one else "")
        + (f'<p>{_esc(line_two)}</p>' if line_two else "")
        + (f'<div class="character-tags">{tags}</div>' if tags else "")
        + (f'<div class="character-meta">{_esc(meta)}</div>' if meta else "")
        + '</div></div>'
    )


def _buyer_and_cast_block(report_data: dict) -> str:
    buyer = report_data.get("buyer_persona")
    cast = report_data.get("cast")
    if not buyer and not cast:
        return ""
    is_two_ring = report_data.get("virlo_model") == "two_ring"
    heading = (
        "Audience and creator patterns"
        if is_two_ring
        else "Audience and creator patterns"
    )
    parts = [
        '<div class="rule"></div>',
        f'<div class="exh"><span>{_esc(heading)}</span></div>',
    ]
    if buyer:
        buyer_lede = (
            "Audience clues observed in the sampled creative."
            if is_two_ring
            else "Audience clues observed in the sampled creative."
        )
        buyer_faces = "".join(_face(p) for p in (buyer.get("face_paths") or []))
        parts.append(
            f'<div class="seclede">{_esc(buyer_lede)}</div>'
            '<div class="cast audience-card" style="margin-bottom:14px">'
            + (f'<div class="faces">{buyer_faces}</div>' if buyer_faces else "")
            + f'<h3>{_esc(buyer.get("who"))}</h3>'
            + f'<p>{_esc(buyer.get("appearance"))}</p></div>'
        )
    if cast:
        characters = "".join(_character_card(c) for c in (cast.get("characters") or []))
        source = cast.get("source") if isinstance(cast.get("source"), dict) else {}
        source_label = source.get("source_label")
        if is_two_ring:
            source_note = ""
            cast_lede = "The faces, settings, and delivery styles that repeated across the sampled organic posts."
            cast_title = "Observed creator pattern"
        else:
            source_note = ""
            cast_lede = "The faces, settings, and delivery styles that repeated across the sampled organic posts."
            cast_title = "Observed creator pattern"
        faces = "".join(
            _face(f.get("avatar_path"), f.get("initials", ""), f.get("handle", ""))
            for f in (cast.get("faces") or [])
        )
        axes = "".join(
            f'<div><span class="k">{_esc(a.get("k"))}</span><span class="vv">{_esc(a.get("v"))}</span></div>'
            for a in (cast.get("axes") or [])
        )
        note = (
            f'<div class="facenote">{_esc(cast.get("face_note"))}</div>'
            if cast.get("face_note")
            else ""
        )
        casting_paragraph = str(cast.get("casting_paragraph") or "")
        if casting_paragraph.startswith("Cast a "):
            casting_paragraph = "The repeated pattern points to a " + casting_paragraph[7:]
        parts.append(
            f'<div class="seclede">{_esc(cast_lede)}{source_note}</div>'
            '<div class="cast">'
            f'<h3>{_esc(cast_title)}</h3>'
            + (f'<div class="character-grid">{characters}</div>' if characters else "")
            + (f'<div class="faces fallback-faces">{faces}</div>' if faces and not characters else "")
            + note
            + '<div class="castrow" style="margin-top:16px">'
            + f'<div><p>{_esc(casting_paragraph)}</p></div>'
            + (f'<div class="axes">{axes}</div>' if axes else "")
            + "</div></div>"
        )
    return "".join(parts)


def _gap_block(report_data: dict) -> str:
    gap = report_data.get("gap")
    insight = report_data.get("gap_insight", "")
    if gap is None:
        return (
            '<section class="decision-brief no-gap-read">'
            '<div class="decision-kicker">The read <span>Evidence incomplete</span></div>'
            '<div class="decision-lead"><span>Decision</span><h3>No decisive gap in this sample.</h3>'
            '<p>The available evidence does not support a clean test yet. Broaden the competitor set, '
            'add more organic examples, or compare an adjacent niche.</p></div></section>'
        )
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>The gap</span></div>'
        f'<div class="socall"><b>{_esc(_fmt_label(gap.get("format")))} is the lane to take.</b> '
        f'{_esc(insight)} <span class="muted">Paid evidence: {_esc(gap.get("paid_evidence"))}.</span></div>'
    )


def _evidence_block(report_data: dict) -> str:
    evidence = report_data.get("evidence") or {}
    rows = evidence.get("rows") or []
    if not rows:
        return ""
    evidence_cells = "".join(
        '<div class="eitem">'
        f'<div class="k">{_esc(row.get("label"))}</div>'
        f'<div class="val">{_esc(row.get("value"))}</div>'
        '</div>'
        for row in rows
    )
    rings = evidence.get("rings") or {}
    rings_html = ""
    if rings:
        ring_cards = []
        for role in ("buyer", "interest"):
            ring = rings.get(role)
            if not isinstance(ring, dict):
                continue
            label = "Buyer context examples" if role == "buyer" else "Organic interest examples"
            ring_cards.append(
                '<div class="eitem">'
                f'<div class="k">{_esc(label)}</div>'
                f'<div class="val">{_esc(ring.get("count", 0))}</div>'
                '</div>'
            )
        if ring_cards:
            rings_html = '<div class="egrid ringgrid">' + "".join(ring_cards) + '</div>'
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Evidence base</span></div>'
        '<div class="seclede">Sample counts and named coverage retained as evidence. Visible creative remains the proof.</div>'
        f'<div class="egrid">{evidence_cells}</div>{rings_html}'
    )


def _glossary_block(report_data: dict) -> str:
    formats = report_data.get("formats") or []
    used = [f.get("format") for f in formats if f.get("format") in _FORMAT_GLOSSARY]
    seen = []
    for fmt in used:
        if fmt not in seen:
            seen.append(fmt)
    frame_rows = report_data.get("message_frames") or []
    used_frames = [f.get("frame") for f in frame_rows if f.get("frame") in _FRAME_GLOSSARY]
    seen_frames = []
    for frame in used_frames:
        if frame not in seen_frames:
            seen_frames.append(frame)
    mechanic_rows = report_data.get("mechanics") or []
    used_mechanics = [m.get("mechanic") for m in mechanic_rows if m.get("mechanic") in _MECHANIC_GLOSSARY]
    seen_mechanics = []
    for mechanic in used_mechanics:
        if mechanic not in seen_mechanics:
            seen_mechanics.append(mechanic)
    if not seen and not seen_frames and not seen_mechanics:
        return ""
    items = "".join(f'<div><b>{_esc(fmt)}</b><span>{_esc(_FORMAT_GLOSSARY[fmt])}</span></div>' for fmt in seen)
    items += "".join(
        f'<div><b>{_esc(frame)}</b><span>{_esc(_FRAME_GLOSSARY[frame])}</span></div>'
        for frame in seen_frames
    )
    items += "".join(
        f'<div><b>{_esc(mechanic)}</b><span>{_esc(_MECHANIC_GLOSSARY[mechanic])}</span></div>'
        for mechanic in seen_mechanics
    )
    return (
        '<div class="rule"></div>'
        '<div class="exh"><span>Taxonomy glossary</span></div>'
        f'<div class="gloss">{items}</div>'
    )


def _cta_block(report_data: dict, has_proof: bool) -> str:
    if report_data.get("gap") and has_proof:
        return (
            f'<a class="cta" href="{YOUFORM_CTA_URL}"><span><span class="h">Turn this into ads.</span>'
            '<span class="s">Send this report to Matthew at Emerald. StealAds builds both versions so your team runs the test instead of debating it.</span>'
            f'<span class="powered">Powered by <b>StealAds.ai</b></span></span>'
            '<span class="btn">BUILD THE TEST →</span></a>'
        )
    return (
        f'<a class="cta" href="{YOUFORM_CTA_URL}"><span><span class="h">No gap found yet. Send us the run for a deeper pull.</span>'
        '<span class="s">We can pull more competitors, widen the sample, or move into an adjacent market.</span>'
        f'<span class="powered">Powered by <b>StealAds.ai</b></span></span>'
        '<span class="btn">DEEPEN THE READ →</span></a>'
    )


def _hook_chips(pattern: dict) -> str:
    hooks = pattern.get("top_hooks") or []
    if not hooks:
        return ""
    chips = "".join(f'<span class="hookchip">{_esc(_hook_label(h))}</span>' for h in hooks)
    return f'<div class="pat-hooks"><span class="l">Hooks running inside</span><div>{chips}</div></div>'


def _hook_label(hook) -> str:
    return str(hook or "").replace("-", " ")


def _pattern_creatives(pattern: dict) -> str:
    cards = []
    for creative in pattern.get("resolved_creatives") or []:
        uri = _img_data_uri(creative.get("image_path"))
        if not uri:
            continue
        who = _esc(creative.get("who"))
        caption = _esc((creative.get("hook_text") or "")[:90])
        href = _external_url_attr(creative.get("url"))
        media = f'<div class="pc-img"><img src="{uri}" alt=""></div>'
        body = (
            f'<span class="pc-who">{who}</span>'
            + (f'<span class="pc-hook">{caption}</span>' if caption else "")
        )
        inner = f'{media}<div class="pc-body">{body}</div>'
        cards.append(
            f'<a class="pc" href="{href}" target="_blank" rel="noopener">{inner}</a>'
            if href
            else f'<div class="pc">{inner}</div>'
        )
    if not cards:
        return ""
    return f'<div class="pat-creatives">{"".join(cards)}</div>'


def _pattern_card(pattern: dict, tier: str) -> str:
    angle = _frame_label(pattern.get("angle"))
    fmt = _fmt_label(pattern.get("format"))
    competitors = _structured_count(pattern.get("distinct_competitors"))
    creators = _structured_count(pattern.get("distinct_creators"))
    paid_count = _structured_count(pattern.get("paid_count"))
    organic_count = _structured_count(pattern.get("organic_count"))
    if tier == "proven":
        badge = "Proven"
        why = f"{competitors} competitors are independently sustaining this in paid. Revealed budget, not one advertiser's bet."
    elif tier == "emerging":
        adj = " It sits next to a proven paid angle." if pattern.get("adjacent_to_proven") else ""
        badge = "Emerging"
        why = f"{creators} creators are posting this organically with save and share momentum.{adj} Not saturated in paid yet."
    else:
        badge = "Hypothesis"
        why = "A single signal so far. Cheap to test before it is proven."
    tiles = "".join(
        f'<div class="pt"><span>{label}</span><b>{value}</b></div>'
        for label, value in (
            ("Competitors", competitors),
            ("Paid ads", paid_count),
            ("Creators", creators),
            ("Organic posts", organic_count),
        )
    )
    return (
        f'<article class="pat {tier}">'
        f'<div class="pat-head"><span class="pat-badge">{badge}</span>'
        f'<h3>{angle} <span class="x">x</span> {fmt}</h3></div>'
        f'<p class="pat-why">{_esc(why)}</p>'
        f'{_hook_chips(pattern)}'
        f'<div class="pat-tiles">{tiles}</div>'
        f'{_pattern_creatives(pattern)}'
        '</article>'
    )


def _pattern_tier(report_data_patterns: dict, tier: str, title: str, lede: str) -> str:
    items = report_data_patterns.get(tier) or []
    if not items:
        return ""
    cards = "".join(_pattern_card(p, tier) for p in items)
    return (
        f'<div class="pat-tier {tier}">'
        f'<div class="pat-tier-head"><h3>{_esc(title)}</h3><p>{_esc(lede)}</p></div>'
        f'{cards}</div>'
    )


def _patterns_block(report_data: dict) -> str:
    patterns = report_data.get("patterns")
    if not patterns:
        return ""
    proven = patterns.get("proven") or []
    emerging = patterns.get("emerging") or []
    hypothesis = patterns.get("hypothesis") or []
    if not (proven or emerging or hypothesis):
        counts = patterns.get("counts") or {}
        excluded = _structured_count(counts.get("excluded_leg"))
        return (
            '<section class="patterns"><div class="exh"><span>Winning patterns</span></div>'
            '<p class="seclede">Not enough repeated signal to name a winning pattern yet. '
            f'{excluded} creatives lacked a scoreable angle or format. Add competitors, widen the pull, or rerun.</p>'
            '</section>'
        )
    proven_tier = _pattern_tier(
        patterns, "proven", "Proven",
        "Angle and format that two or more competitors keep funding. The market already validated these.",
    )
    emerging_tier = _pattern_tier(
        patterns, "emerging", "Emerging",
        "Gaining organic momentum across multiple creators, not yet saturated in paid. The early window.",
    )
    hypothesis_tier = _pattern_tier(
        patterns, "hypothesis", "Hypothesis",
        "One signal so far. Not proven, but cheap to test.",
    )
    return (
        '<section class="patterns">'
        '<div class="exh"><span>The winning patterns</span><span class="r">Proven / Emerging / Hypothesis</span></div>'
        '<p class="seclede">Each pattern is an angle paired with a format. Proven means multiple competitors keep paying '
        'for it. Emerging means creators are pushing it organically before paid catches up. Hooks are shown per pattern.</p>'
        f'{proven_tier}{emerging_tier}{hypothesis_tier}'
        '</section>'
    )


def render_report_html(report_data: dict) -> str:
    niche = _esc(report_data["niche"])
    has_gap = bool(report_data.get("gap"))
    winner_image = _winner_image_data(report_data)
    has_proof = bool(has_gap and winner_image)
    if has_gap and not has_proof:
        headline = {
            "top": "Creative receipt unavailable.",
            "bottom": "No recommendation shown.",
        }
    else:
        headline = report_data.get("headline") or (
            {
                "top": "One format keeps getting funded.",
                "bottom": "One keeps getting watched.",
            }
            if has_proof
            else {
                "top": "No gap found yet.",
                "bottom": "Pull more signal.",
            }
        )
    h_top = _esc(headline["top"])
    h_bottom = _esc(headline["bottom"])
    if has_gap and not has_proof:
        default_lede = (
            "The sampled evidence remains available below, but the strongest creative receipt could not be opened."
        )
        lede = _esc(default_lede)
    elif has_proof:
        default_lede = "One paid baseline. One organic challenger. The evidence below shows the cleanest test."
        lede = _esc(report_data.get("lede", default_lede))
    else:
        default_lede = (
            "This run did not find a clean creative gap yet. Add competitors, widen the pull, "
            "or try an adjacent niche and rerun."
        )
        lede = _esc(report_data.get("lede", default_lede))
    # When the pivot found ranked patterns, they lead the report. Override the gap-driven hero so
    # the headline is the top proven (or emerging) pattern, and suppress the gap takeaway/winner
    # image below so the format-gap read stops competing with the patterns.
    patterns = report_data.get("patterns") or {}
    lead_proven = (patterns.get("proven") or [])
    lead_emerging = (patterns.get("emerging") or [])
    lead_pattern = (lead_proven or lead_emerging or [None])[0]
    patterns_lead = bool(lead_pattern)
    if patterns_lead:
        angle = _frame_label(lead_pattern.get("angle"))
        fmt = _fmt_label(lead_pattern.get("format"))
        if lead_proven:
            n = _structured_count(lead_pattern.get("distinct_competitors"))
            h_top = _esc("The market already told you what works.")
            h_bottom = _esc(f"{angle} x {fmt}.")
            lede = _esc(
                f"{n} competitors independently keep funding this play. Below is every winning pattern, "
                "ranked from proven to emerging, with the hooks running inside each."
            )
        else:
            n = _structured_count(lead_pattern.get("distinct_creators"))
            h_top = _esc("Nobody is paying for this yet.")
            h_bottom = _esc(f"{angle} x {fmt}.")
            lede = _esc(
                f"{n} creators are pushing this organically before paid catches up. Below is every pattern, "
                "ranked from proven to emerging, with the hooks running inside each."
            )
    ads = _esc(report_data.get("ads_scanned", ""))
    rivals = _esc(report_data.get("rivals_count", ""))
    organic = _esc(report_data.get("organic_count", ""))
    if patterns_lead:
        status = "patterns ready"
    else:
        status = "decision ready" if has_proof else "evidence incomplete" if has_gap else "no gap found yet"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Winning Creative Tracker - {niche}</title>
<style>
  :root {{
    --bg:#080809; --panel:#101113; --card:#141518; --line:rgba(255,255,255,.10);
    --fg:hsl(0 0% 95%); --mut:hsl(0 0% 64%); --dim:hsl(0 0% 42%);
    --green:oklch(0.82 0.19 156); --greend:oklch(0.64 0.16 156);
    /* Single-accent system: green = organic/challenger/winner. --blue is the one
       muted paid/control tone. --amber and --hot are neutralized so nothing
       competes with the green. */
    --hot:hsl(0 0% 46%); --blue:#8f9db1; --amber:hsl(0 0% 60%);
    --radius:0px; --pill:999px;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:ui-monospace,SFMono-Regular,"JetBrains Mono",Menlo,Consolas,monospace;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  html,body {{ max-width:100%; overflow-x:hidden; }}
  body {{ background:var(--bg); color:var(--fg); font-family:var(--sans); line-height:1.5;
    -webkit-font-smoothing:antialiased; padding:0 22px 90px; }}
  .wrap {{ max-width:1120px; margin:0 auto; }}
  .dossier {{ display:flex; flex-wrap:wrap; gap:6px 24px; padding:24px 0 28px;
    font-family:var(--mono); font-size:12px; letter-spacing:.12em; color:var(--dim); text-transform:uppercase; }}
  .dossier b {{ color:var(--mut); font-weight:600; }} .dossier .live {{ color:var(--green); }}
  .muted {{ color:var(--mut); }}
  h1 {{ max-width:1080px; font-size:70px; line-height:.98; letter-spacing:-.045em; font-weight:900; text-wrap:balance; }}
  h1 .g {{ color:var(--green); }}
  .lede {{ color:var(--mut); font-size:17px; max-width:720px; margin-top:18px; }}
  .opening {{ display:grid; grid-template-columns:minmax(0,1.65fr) minmax(300px,.75fr); gap:48px; align-items:start; }}
  .opening.no-proof {{ grid-template-columns:1fr; }}
  .opening-copy,.opening-head {{ min-width:0; }}
  .opening .lede {{ max-width:650px; }}
  .opening-proof {{ min-width:0; margin:0; border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; background:var(--panel); }}
  .opening-proof img {{ display:block; width:100%; aspect-ratio:4/5; object-fit:contain; background:#050607; }}
  .proof-caption {{ display:grid; grid-template-columns:minmax(0,.75fr) minmax(0,1.25fr); border-top:1px solid var(--line); }}
  .proof-caption > div {{ min-width:0; padding:11px 13px 13px; }}
  .proof-caption > div + div {{ border-left:1px solid var(--line); }}
  .proof-caption span,.takeaway > span,.test-cell > span,.constant-row > span {{ display:block; font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .proof-caption b {{ display:block; margin-top:4px; font-size:12px; line-height:1.35; overflow-wrap:anywhere; }}
  .takeaway {{ max-width:650px; margin-top:28px; border-top:1px solid rgba(47,255,137,.42); padding-top:17px; }}
  .takeaway h2 {{ color:var(--green); font-size:28px; line-height:1.08; letter-spacing:-.025em; margin-top:8px; }}
  .takeaway p {{ color:var(--mut); font-size:13px; max-width:600px; margin-top:9px; }}
  .signal-band {{ margin-top:38px; border-block:1px solid var(--line); }}
  .signal-grid {{ display:grid; grid-template-columns:1fr 1fr 1.5fr; }}
  .signal-stat,.signal-read {{ min-width:0; padding:26px 24px; }}
  .signal-stat + .signal-stat,.signal-read {{ border-left:1px solid var(--line); }}
  .signal-stat b {{ display:block; color:var(--green); font-size:50px; line-height:.92; letter-spacing:-.04em; }}
  .signal-stat:nth-child(2) b {{ color:var(--blue); }}
  .signal-stat span {{ display:block; color:var(--dim); font-size:12px; line-height:1.35; margin-top:12px; max-width:210px; }}
  .signal-read {{ display:flex; flex-direction:column; justify-content:center; }}
  .signal-read p {{ font-size:26px; font-weight:800; line-height:1.12; letter-spacing:-.02em; }}
  .signal-read .g {{ color:var(--green); }}
  .signal-note {{ border-top:1px solid var(--line); color:var(--dim); font-size:12px; padding:10px 20px 12px; }}
  .operational-test {{ margin-top:36px; }}
  .operational-test > h2 {{ color:var(--fg); font-size:34px; font-weight:900; letter-spacing:-.03em; line-height:1.05; margin-bottom:16px; }}
  .test-grid {{ display:grid; grid-template-columns:1fr 1fr; border-block:1px solid var(--line); }}
  .test-cell {{ min-width:0; padding:18px 20px 20px; }}
  .test-cell + .test-cell {{ border-left:1px solid var(--line); }}
  .test-cell h3 {{ font-size:19px; line-height:1.15; margin:8px 0 7px; }}
  .test-cell p {{ color:var(--mut); font-size:13px; }}
  .test-cell.control h3 {{ color:var(--blue); }}
  .test-cell.challenger h3 {{ color:var(--green); }}
  .constant-row {{ display:grid; grid-template-columns:140px 1fr; gap:20px; align-items:start; border-bottom:1px solid var(--line); padding:13px 20px 15px; }}
  .constant-row p {{ color:var(--mut); font-size:13px; }}
  .rule {{ height:1px; background:var(--line); margin:46px 0 32px; }}
  .exh {{ font-family:var(--mono); font-size:11px; letter-spacing:.18em; text-transform:uppercase;
    color:var(--dim); display:flex; justify-content:space-between; margin-bottom:6px; }}
  .exh .r {{ color:var(--dim); }}
  .seclede {{ color:var(--mut); font-size:14px; margin:0 0 18px; max-width:680px; }}
  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:0; margin-top:30px; border-block:1px solid var(--line); }}
  .stat {{ min-width:0; padding:17px 18px 18px; }}
  .stat + .stat {{ border-left:1px solid var(--line); }}
  .stat .l {{ font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .stat .n {{ font-size:26px; line-height:1.05; font-weight:900; letter-spacing:-.02em; margin-top:7px; overflow-wrap:anywhere; }}
  .stat .n.g {{ color:var(--green); }} .stat .n.h {{ color:var(--hot); }} .stat .n.b {{ color:var(--blue); }}
  .stat .s {{ color:var(--mut); font-size:12px; margin-top:6px; }}
  .comps {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }}
  .comp {{ border-top:1px solid var(--line); padding:14px 2px; }}
  .comp .ch {{ display:flex; align-items:baseline; gap:8px; }} .comp .ch b {{ font-size:15px; }}
  .comp .hd {{ font-family:var(--mono); font-size:12px; color:var(--dim); }}
  .comp .cmeta {{ display:flex; gap:10px; align-items:center; margin:7px 0; font-family:var(--mono); font-size:11px; color:var(--mut); }}
  .src {{ padding:2px 7px; border-radius:5px; font-weight:700; }}
  .src.s {{ background:oklch(0.80 0.19 158 / .16); color:var(--green); }}
  .src.d {{ background:rgba(76,141,255,.15); color:var(--blue); }}
  .comp .cnote {{ font-size:13px; color:var(--mut); }}
  .exhibit {{ display:grid; grid-template-columns:minmax(250px,340px) 1fr; gap:34px; align-items:start;
    background:linear-gradient(135deg,rgba(47,255,137,.045),transparent 52%),var(--panel); border-block:1px solid var(--line); padding:28px 0; position:relative; overflow:hidden; }}
  .exhibit.no-frame {{ grid-template-columns:1fr; }}
  .exhibit::before {{ content:""; position:absolute; inset:0;
    background:radial-gradient(420px 240px at 18% 30%,oklch(0.80 0.19 158 / .12),transparent); pointer-events:none; }}
  .frame {{ position:relative; border:1px solid rgba(255,255,255,.12); border-radius:var(--radius); overflow:hidden; }}
  .frame img {{ width:100%; display:block; }}
  .frame.noimg-lg {{ font-family:var(--mono); font-size:11px; color:var(--dim); text-align:center; padding:60px 10px; }}
  .frame .fl {{ display:block; position:static; font-family:var(--mono); font-size:10px; letter-spacing:.1em;
    background:var(--panel); color:var(--green); padding:8px 10px; border-bottom:1px solid var(--line); }}
  .exhibit h3 {{ font-size:26px; font-weight:800; line-height:1.12; }}
  .exhibit .desc {{ color:var(--mut); font-size:14px; margin:10px 0 18px; }}
  .ledger {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--line);
    border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }}
  .ledger div {{ background:var(--panel); padding:12px 14px; }}
  .ledger .k {{ font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .ledger .val {{ font-size:16px; font-weight:700; margin-top:3px; }} .ledger .val.g {{ color:var(--green); }}
  .socall {{ margin-top:16px; border-left:3px solid var(--green); padding:8px 0 8px 14px; font-size:14px; }}
  .socall b {{ color:var(--green); }}
  .tbl {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .tbl thead th {{ font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    color:var(--dim); text-align:left; padding:0 14px 12px; font-weight:600; }}
  .tbl tbody tr {{ border-top:1px solid var(--line); }} .tbl tbody tr.win {{ background:oklch(0.80 0.19 158 / .06); }}
  .tbl td {{ padding:14px; vertical-align:middle; }}
  .fmt {{ display:flex; gap:14px; align-items:center; min-width:280px; }}
  .thumb {{ width:54px; height:54px; border-radius:var(--radius); overflow:hidden; flex:none; border:1px solid var(--line); background:#050607; }}
  .thumb img {{ width:100%; height:100%; object-fit:cover; }}
  .noimg {{ font-family:var(--mono); font-size:8px; color:var(--dim); text-align:center; line-height:1.2; padding-top:9px; }}
  .fmt b {{ font-weight:700; }} .fmt small {{ display:block; color:var(--dim); font-size:12px; }}
  .fmt .lbl {{ font-family:var(--mono); font-size:10px; color:var(--mut); }}
  .track {{ display:inline-block; width:90px; height:3px; background:transparent; overflow:hidden;
    vertical-align:middle; margin-right:8px; }}
  .fill {{ display:block; height:100%; }} .fill.org {{ background:var(--green); }} .fill.paid {{ background:var(--blue); }}
  .v {{ font-family:var(--mono); font-size:12px; color:var(--mut); }}
  .gap {{ font-family:var(--mono); font-weight:700; }}
  .gap.g {{ color:var(--green); }} .gap.b {{ color:var(--blue); }} .gap.h {{ color:var(--hot); }} .gap.a {{ color:var(--amber); }} .gap.d {{ color:var(--dim); }}
  .pill {{ font-family:var(--mono); font-size:11px; font-weight:700; padding:4px 9px; border-radius:var(--pill); white-space:nowrap; }}
  .pill.probe {{ background:oklch(0.80 0.19 158 / .16); color:var(--green); }}
  .pill.baseline,.pill.sustained {{ background:rgba(76,141,255,.14); color:var(--blue); }}
  .pill.watch {{ background:oklch(0.80 0.19 158 / .10); color:var(--green); }}
  .pill.signal {{ background:rgba(245,166,35,.14); color:var(--amber); }}
  .pill.sat {{ background:rgba(244,63,94,.14); color:var(--hot); }}
  .pill.con {{ background:rgba(245,166,35,.14); color:var(--amber); }}
  .decision-brief {{ margin-top:30px; border-top:1px solid rgba(47,255,137,.42); border-bottom:1px solid var(--line);
    background:linear-gradient(110deg,rgba(47,255,137,.08),rgba(47,255,137,.015) 54%,transparent); }}
  .decision-kicker {{ display:flex; justify-content:space-between; gap:16px; padding:13px 20px; border-bottom:1px solid var(--line);
    font-family:var(--mono); font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--green); }}
  .decision-kicker span {{ color:var(--dim); }}
  .decision-lead {{ display:grid; grid-template-columns:120px minmax(220px,.7fr) 1fr; gap:22px; align-items:start; padding:24px 20px; }}
  .decision-lead > span,.decision-item > span {{ display:block; font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .decision-lead h3 {{ color:var(--green); font-size:30px; line-height:1.02; letter-spacing:-.025em; }}
  .decision-lead p {{ color:var(--mut); font-size:14px; max-width:560px; }}
  .decision-grid {{ display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--line); }}
  .decision-item {{ min-width:0; padding:18px 20px 20px; }}
  .decision-item + .decision-item {{ border-left:1px solid var(--line); }}
  .decision-item > span {{ margin-bottom:10px; }}
  .decision-item h3 {{ font-size:19px; line-height:1.12; font-weight:900; margin-bottom:7px; }}
  .decision-item p {{ color:var(--mut); font-size:13px; }}
  .decision-item.baseline h3 {{ color:var(--blue); }}
  .decision-item.setup h3 {{ color:var(--amber); }}
  .decision-note {{ color:var(--dim); font-size:12px; padding:11px 20px 13px; border-top:1px solid var(--line); }}
  .message-ledger {{ border-block:1px solid var(--line); }}
  .message-row {{ display:grid; grid-template-columns:200px 190px minmax(0,1fr); gap:18px; align-items:start; padding:15px 0; }}
  .message-row + .message-row {{ border-top:1px solid var(--line); }}
  .message-title {{ display:flex; flex-direction:column; gap:4px; }}
  .message-title b {{ font-size:15px; }}
  .message-title span {{ font-family:var(--mono); font-size:10px; color:var(--amber); text-transform:uppercase; }}
  .message-sample p {{ color:var(--mut); font-size:12px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
  .execution-head {{ display:flex; align-items:baseline; justify-content:space-between; gap:20px; margin-top:22px; }}
  .execution-head span {{ color:var(--dim); font-size:12px; }}
  .mechanics-strip {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
  .mechanic-summary {{ border:1px solid var(--line); padding:8px 10px; font-family:var(--mono); font-size:10px; color:var(--mut); }}
  .mechanic-summary b {{ color:var(--blue); }}
  .framecounts {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 8px; }}
  .framecounts span,.framepill,.mechanicpill {{ font-family:var(--mono); font-size:10px; border:1px solid rgba(47,255,137,.16);
    border-radius:var(--pill); color:var(--green); background:rgba(47,255,137,.07); padding:4px 7px; text-transform:uppercase; letter-spacing:.04em; }}
  .mechanicpill {{ color:var(--blue); background:rgba(76,141,255,.10); border-color:rgba(76,141,255,.20); }}
  .swipe-band {{ margin-top:18px; }}
  .swipe-band + .swipe-band {{ margin-top:24px; }}
  .band-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:18px; margin-bottom:12px; }}
  .band-head.mini {{ margin-top:18px; }}
  .band-head h3 {{ font-size:22px; font-weight:900; }}
  .band-head p {{ max-width:440px; color:var(--mut); font-size:13px; text-align:right; }}
  .paid-band .band-head h3 {{ color:var(--blue); }}
  .organic-band .band-head h3 {{ color:var(--green); }}
  .swipe-grid,.swipe-text-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
  .fixture-note {{ color:var(--dim); font-size:12px; margin:0 0 10px; }}
  .swipe-text-card {{ border:1px solid var(--line); background:var(--panel); padding:13px; min-width:0; }}
  .swipe-text-card h3 {{ font-size:14px; line-height:1.25; margin:10px 0 12px; overflow-wrap:anywhere; }}
  .swipe-card {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; min-width:0; }}
  .swipe-media {{ position:relative; aspect-ratio:4/5; background:#050607; border-bottom:1px solid var(--line); overflow:hidden; }}
  .swipe-media img {{ width:100%; height:100%; object-fit:contain; display:block; background:#050607; }}
  .swipe-missing {{ height:100%; display:flex; align-items:center; justify-content:center; text-align:center;
    font-family:var(--mono); font-size:11px; line-height:1.6; color:var(--dim); }}
  .swipe-badge {{ position:static; font-family:var(--mono); font-size:10px; letter-spacing:.09em;
    text-transform:uppercase; padding:7px 12px; border-bottom:1px solid var(--line); background:var(--panel); font-weight:800; }}
  .swipe-badge.organic {{ color:var(--green); }}
  .swipe-badge.paid {{ color:var(--blue); }}
  .swipe-copy {{ padding:14px; }}
  .swipe-meta {{ display:flex; justify-content:space-between; gap:10px; font-family:var(--mono); font-size:10px;
    text-transform:uppercase; letter-spacing:.08em; color:var(--dim); margin-bottom:8px; }}
  .swipe-pills {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }}
  .framepill,.mechanicpill {{ display:inline-block; }}
  .scopepill {{ display:inline-block; font-family:var(--mono); font-size:10px; border:1px solid var(--line);
    border-radius:var(--pill); color:var(--mut); background:transparent; padding:4px 7px; text-transform:uppercase; letter-spacing:.04em; }}
  .scope-note {{ color:var(--dim); }}
  .swipe-copy h3 {{ font-size:15px; line-height:1.25; font-weight:800; margin-bottom:8px; }}
  .swipe-body {{ color:var(--mut); font-size:12px; margin-bottom:12px; }}
  .swipe-stats {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--line); border:1px solid var(--line);
    border-radius:var(--radius); overflow:hidden; margin-top:12px; }}
  .swipe-stats div {{ background:var(--panel); padding:9px 10px; }}
  .swipe-stats b {{ display:block; font-family:var(--mono); color:var(--fg); font-size:13px; }}
  .swipe-stats span {{ display:block; font-family:var(--mono); color:var(--dim); font-size:9px; text-transform:uppercase; margin-top:2px; }}
  .swipe-link {{ display:inline-block; margin-top:12px; color:var(--green); font-family:var(--mono); font-size:11px;
    text-transform:uppercase; letter-spacing:.08em; text-decoration:none; }}
  .cast {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:22px; }}
  .audience-card {{ background:linear-gradient(180deg,rgba(47,255,137,.07),var(--panel)); }}
  .faces {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:12px; }}
  .fallback-faces {{ margin-top:12px; }}
  .face {{ text-align:center; }}
  .face .ph {{ width:60px; height:60px; border-radius:50%; overflow:hidden; background:linear-gradient(135deg,#233,#122);
    border:1px solid var(--line); display:flex; align-items:center; justify-content:center;
    font-family:var(--mono); font-size:15px; color:var(--mut); font-weight:700; }}
  .face .ph img {{ width:100%; height:100%; object-fit:cover; }}
  .face span {{ display:block; font-family:var(--mono); font-size:10px; color:var(--dim); margin-top:5px; }}
  .character-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:14px; }}
  .character-card {{ background:#0c0e11; border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; min-width:0; }}
  .character-media {{ position:relative; aspect-ratio:4/5; background:#050607; border-bottom:1px solid var(--line); overflow:hidden; }}
  .character-media > img {{ width:100%; max-width:100%; height:100%; object-fit:contain; display:block; background:#050607; }}
  .character-avatar {{ position:absolute; left:10px; bottom:10px; width:46px; height:46px; border-radius:50%; overflow:hidden;
    border:2px solid #0c0e11; background:#111; box-shadow:0 0 0 1px var(--line); }}
  .character-avatar img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .character-copy {{ padding:13px; }}
  .character-card.no-media .character-copy {{ padding:16px 13px; }}
  .character-copy h3 {{ font-size:15px; font-weight:900; margin-bottom:8px; overflow-wrap:anywhere; }}
  .character-copy p {{ color:var(--mut); font-size:12px; margin:0 0 6px; }}
  .character-tags {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }}
  .character-tags span {{ font-family:var(--mono); font-size:10px; color:var(--green); background:rgba(47,255,137,.08);
    border:1px solid rgba(47,255,137,.18); border-radius:999px; padding:4px 7px; }}
  .character-meta {{ margin-top:10px; font-family:var(--mono); font-size:10px; color:var(--dim); text-transform:uppercase; letter-spacing:.04em; }}
  .castrow {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  .cast h3 {{ font-size:22px; font-weight:800; margin-bottom:6px; }} .cast p {{ color:var(--mut); font-size:14px; }}
  .axes {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--line);
    border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }}
  .axes div {{ background:var(--panel); padding:9px 12px; font-size:13px; display:flex; justify-content:space-between; }}
  .axes .k {{ font-family:var(--mono); font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:var(--dim); }}
  .axes .vv {{ font-weight:600; }}
  .facenote {{ font-family:var(--mono); font-size:11px; color:var(--amber); margin-top:2px; }}
  .egrid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
  .ringgrid {{ margin-top:12px; grid-template-columns:repeat(2,1fr); }}
  .eitem {{ border-top:1px solid var(--line); padding:14px 2px; }}
  .eitem .k,.ledger .k {{ font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .eitem .val {{ font-size:28px; font-weight:900; margin-top:5px; }}
  .eitem .srcfile {{ font-family:var(--mono); font-size:11px; color:var(--mut); margin-top:6px; }}
  .costs {{ margin-top:14px; display:grid; gap:8px; }}
  .costs div,.skips,.total {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:11px 13px; color:var(--mut); font-size:13px; }}
  .costs b {{ color:var(--fg); margin-right:8px; }}
  .costs span {{ font-family:var(--mono); font-size:11px; }}
  .total {{ color:var(--green); font-family:var(--mono); }}
  .gloss {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
  .gloss div {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:13px 14px; }}
  .gloss b {{ display:block; font-family:var(--mono); font-size:12px; color:var(--green); margin-bottom:4px; }}
  .gloss span {{ color:var(--mut); font-size:13px; }}
  .cta {{ margin-top:34px; display:flex; justify-content:space-between; align-items:center; gap:16px;
    background:linear-gradient(90deg,var(--green),var(--greend)); color:#04140c; border-radius:var(--radius); padding:22px 26px; text-decoration:none; transition:transform .16s ease; }}
  .cta .h {{ display:block; font-weight:900; font-size:22px; }} .cta .s {{ display:block; font-size:13px; opacity:.85; margin-top:4px; }}
  .cta .powered {{ display:block; font-family:var(--mono); font-size:11px; letter-spacing:.04em; margin-top:8px; opacity:.75; text-transform:uppercase; }}
  .cta .btn {{ background:#04140c; color:var(--green); font-weight:800; padding:13px 20px;
    border-radius:var(--radius); font-size:14px; font-family:var(--mono); white-space:nowrap; }}
  .cta:active {{ transform:translateY(1px); }}
  .cta:focus-visible {{ outline:2px solid var(--fg); outline-offset:4px; }}
  .brandline {{ margin-top:16px; font-family:var(--mono); font-size:11px; color:var(--dim); text-align:center; text-transform:uppercase; letter-spacing:.08em; }}
  .brandline a {{ color:var(--mut); text-decoration:none; }}
  .brandline a:hover {{ color:var(--green); }}
  @media(max-width:1100px) {{
    .opening {{ grid-template-columns:1fr; }}
    .opening-proof {{ display:grid; grid-template-columns:minmax(240px,.8fr) minmax(0,1fr); }}
    .opening-proof img {{ height:340px; aspect-ratio:auto; }}
    .proof-caption {{ border-top:0; border-left:1px solid var(--line); }}
  }}
  @media(max-width:820px) {{ h1 {{ font-size:48px; }} .stats,.comps,.castrow,.egrid,.gloss,.swipe-grid,.swipe-text-grid,.character-grid {{ grid-template-columns:1fr 1fr; }}
    .decision-lead {{ grid-template-columns:100px 1fr; }} .decision-lead p {{ grid-column:2; }}
    .message-row {{ grid-template-columns:160px 150px 1fr; }}
    .band-head {{ display:block; }} .band-head p {{ text-align:left; margin-top:6px; }}
    .exhibit {{ grid-template-columns:1fr; }} }}
  @media(max-width:560px) {{ body {{ padding-inline:18px; }} .dossier {{ gap:5px 14px; font-size:10px; padding-bottom:24px; }}
    h1 {{ font-size:42px; line-height:.98; }} .lede {{ font-size:15px; }}
    .opening {{ gap:28px; }}
    .opening-proof {{ display:block; }}
    .opening-proof img {{ width:100%; height:auto; aspect-ratio:4/5; }}
    .proof-caption {{ grid-template-columns:1fr 1fr; border-top:1px solid var(--line); border-left:0; }}
    .signal-grid,.test-grid {{ grid-template-columns:1fr; }}
    .signal-stat,.signal-read,.test-cell {{ padding-inline:14px; }}
    .signal-stat + .signal-stat,.signal-read,.test-cell + .test-cell {{ border-left:0; border-top:1px solid var(--line); }}
    .test-cell.challenger {{ order:-1; }}
    .constant-row {{ grid-template-columns:1fr; gap:7px; padding-inline:14px; }}
    .stats,.comps,.castrow,.egrid,.gloss,.swipe-grid,.swipe-text-grid,.character-grid,.decision-grid {{ grid-template-columns:1fr; }}
    .stats {{ gap:0; }} .stat {{ padding-inline:0; }} .stat + .stat {{ border-left:0; border-top:1px solid var(--line); }}
    .decision-brief {{ margin-top:24px; }} .decision-kicker {{ padding-inline:14px; }}
    .decision-lead {{ display:block; padding:18px 14px; }} .decision-lead h3 {{ font-size:27px; margin:7px 0 9px; }}
    .decision-grid {{ grid-template-columns:1fr; }}
    .decision-item.setup {{ order:-1; }}
    .decision-item + .decision-item {{ border-left:0; border-top:0; }}
    .decision-item.baseline {{ border-top:1px solid var(--line); }}
    .decision-note {{ padding-inline:14px; }}
    .message-row {{ grid-template-columns:1fr; gap:7px; }} .framecounts {{ margin:0; }}
    .execution-head {{ display:block; }} .execution-head span {{ display:block; margin-top:4px; }}
    .cta {{ display:block; padding:20px; }} .cta .btn {{ display:inline-block; margin-top:14px; }}
    .tbl,.tbl tbody,.tbl tr,.tbl td {{ display:block; width:100%; }}
    .tbl thead {{ display:none; }}
    .tbl tbody tr {{ border:1px solid var(--line); border-radius:10px; margin:10px 0; padding:12px; }}
    .tbl td {{ padding:6px 0; }}
    .tbl td:not(:first-child) {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
    .tbl td:nth-child(2)::before {{ content:"Organic attention"; font-family:var(--mono); font-size:10px; color:var(--dim); text-transform:uppercase; }}
    .tbl td:nth-child(3)::before {{ content:"Paid persistence"; font-family:var(--mono); font-size:10px; color:var(--dim); text-transform:uppercase; }}
    .tbl td:nth-child(4)::before {{ content:"Opportunity"; font-family:var(--mono); font-size:10px; color:var(--dim); text-transform:uppercase; }}
    .tbl td:nth-child(5)::before {{ content:"What it means"; font-family:var(--mono); font-size:10px; color:var(--dim); text-transform:uppercase; }}
    .fmt {{ min-width:0; }}
    .cta {{ flex-direction:column; align-items:stretch; }}
    .cta .btn {{ text-align:center; }}
  }}
  /* ---- Winning patterns (Proven / Emerging / Hypothesis) ---- */
  .patterns {{ margin-top:44px; }}
  .pat-tier {{ margin-top:26px; }}
  .pat-tier-head {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; border-bottom:1px solid var(--line); padding-bottom:9px; margin-bottom:18px; }}
  .pat-tier-head h3 {{ font-size:22px; font-weight:900; letter-spacing:-.02em; }}
  .pat-tier-head p {{ color:var(--dim); font-size:12.5px; max-width:560px; }}
  .pat-tier.proven .pat-tier-head h3 {{ color:var(--blue); }}
  .pat-tier.emerging .pat-tier-head h3 {{ color:var(--green); }}
  .pat-tier.hypothesis .pat-tier-head h3 {{ color:var(--mut); }}
  .pat {{ border:1px solid var(--line); background:var(--panel); padding:20px 22px 22px; margin-bottom:14px; }}
  .pat.proven {{ border-left:3px solid var(--blue); }}
  .pat.emerging {{ border-left:3px solid var(--green); }}
  .pat.hypothesis {{ border-left:3px solid var(--dim); }}
  .pat-head {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
  .pat-badge {{ font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase;
    color:var(--dim); border:1px solid var(--line); padding:3px 8px; }}
  .pat.proven .pat-badge {{ color:var(--blue); border-color:rgba(143,157,177,.4); }}
  .pat.emerging .pat-badge {{ color:var(--green); border-color:rgba(47,255,137,.35); }}
  .pat-head h3 {{ font-size:26px; font-weight:900; letter-spacing:-.025em; line-height:1.05; }}
  .pat-head h3 .x {{ color:var(--dim); font-weight:600; padding:0 4px; }}
  .pat-why {{ color:var(--mut); font-size:14px; margin-top:11px; max-width:720px; }}
  .pat-hooks {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:14px; }}
  .pat-hooks .l {{ font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); }}
  .pat-hooks > div {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .hookchip {{ font-family:var(--mono); font-size:11px; color:var(--fg); background:var(--card);
    border:1px solid var(--line); padding:3px 9px; text-transform:capitalize; }}
  .pat-tiles {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); margin-top:16px; }}
  .pt {{ min-width:0; padding:11px 13px 12px; }}
  .pt + .pt {{ border-left:1px solid var(--line); }}
  .pt span {{ display:block; font-family:var(--mono); font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:var(--dim); }}
  .pt b {{ display:block; font-size:24px; font-weight:900; letter-spacing:-.02em; margin-top:5px; }}
  .pat-creatives {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:16px; }}
  .pc {{ min-width:0; border:1px solid var(--line); background:var(--card); text-decoration:none; color:inherit; display:block; }}
  a.pc:hover {{ border-color:var(--green); }}
  .pc-img {{ aspect-ratio:4/5; overflow:hidden; background:#050607; }}
  .pc-img img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .pc-body {{ padding:8px 9px 9px; }}
  .pc-who {{ display:block; font-family:var(--mono); font-size:11px; color:var(--mut); overflow-wrap:anywhere; }}
  .pc-hook {{ display:block; color:var(--dim); font-size:11px; line-height:1.3; margin-top:4px; }}
  @media (max-width:720px) {{
    .pat-tiles {{ grid-template-columns:repeat(2,1fr); }}
    .pat-tiles .pt:nth-child(3) {{ border-left:none; border-top:1px solid var(--line); }}
    .pat-tiles .pt:nth-child(4) {{ border-top:1px solid var(--line); }}
    .pat-creatives {{ grid-template-columns:repeat(2,1fr); }}
    .pat-head h3 {{ font-size:22px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="dossier"><span><b>Winning Creative Tracker</b></span><span>Niche: <b>{niche}</b></span>
    <span>Sample: <b>{ads} paid ads / {rivals} competitors / {organic} organic posts</b></span><span>Status: <span class="live">{status}</span></span></div>
  {_opening_block(report_data, h_top, h_bottom, lede, winner_image, has_proof, patterns_lead)}
  {_patterns_block(report_data)}
  {_signal_band_block(report_data, has_proof)}
  {_operational_test_block(report_data, has_proof)}
  {_stat_tiles(report_data) if not has_gap else ""}
  {_format_table(report_data, has_proof)}
  {_swipe_file_block(report_data, has_proof)}
  {_buyer_and_cast_block(report_data)}
  {_message_frame_block(report_data, has_proof)}
  {_competitors_block(report_data)}
  {_evidence_block(report_data)}
  {_cta_block(report_data, has_proof)}
  <div class="brandline">Built by <a href="{MATTHEW_X_URL}">Matthew Berman</a> and <a href="{EMERALD_URL}">Emerald Digital</a> / Powered by <a href="{STEALADS_URL}">StealAds</a></div>
</div>
</body>
</html>
"""
