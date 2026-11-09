import re


DEFAULT_RELEVANCE_THRESHOLD = 0.25
# Paid ads are gated on niche/intent presence in their own copy (see score_record), so any ad
# that clears the gate is on-niche; a lower bar just admits legit-but-thin competitor copy
# ("Never miss a meeting") without re-admitting the off-niche brands the gate already zeroed.
PAID_RELEVANCE_THRESHOLD = 0.1

BUYER_INTENT_TERMS = {
    "owner",
    "owners",
    "operator",
    "operators",
    "business",
    "businesses",
    "software",
    "management",
    "manage",
    "billing",
    "scheduling",
    "members",
    "member",
    "retention",
    "staff",
    "pricing",
    "profitability",
    "admin",
    "dashboard",
    "crm",
    "pos",
}


def _collapse(text):
    # Fold separators so "note taker", "note-taker", "notetaker", "tl;dv" all unify.
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _stem(term):
    return term[:-1] if len(term) > 4 and term.endswith("s") else term


def _hit(term, worded, collapsed):
    # Short tokens (e.g. "ai") match only on word boundaries to avoid matching inside
    # unrelated words; longer tokens match a separator-folded, singular/plural-tolerant form.
    if len(term) <= 2:
        return re.search(rf"\b{re.escape(term)}\b", worded) is not None
    stem = _stem(term)
    return term in collapsed or stem in collapsed


def score_record(record, niche, competitors=None, paid=False):
    terms = _query_terms(niche, [])
    competitor_terms = _query_terms("", competitors or [])
    # Whole-brand forms catch punctuated/multiword names ("tl;dv" -> "tldv", "Granola AI" -> "granolaai").
    competitor_brands = [b for b in (_collapse(c) for c in (competitors or [])) if len(b) >= 3]
    # Paid ads are pulled BY competitor name, so score them on their own creative copy only:
    # a competitor-name match is guaranteed here and collides with off-niche brands that share a
    # name (e.g. "Grain" vs the watch brand "Original Grain"). Organic keeps the full text.
    worded = _content_text(record) if paid else _record_text(record)
    collapsed = _collapse(worded)
    if not terms:
        return 0.5, "No niche terms configured; retained by default."
    matched = sorted({term for term in terms if _hit(term, worded, collapsed)})
    # A collapsed whole-brand hit ("tldv", "granolaai") is a specific, strong signal.
    # A bare competitor word ("granola", "fathom") is weak — it collides with common words
    # (granola the food), so it must not clear the bar on its own. Short tokens ("ai") are ignored.
    comp_brands = sorted({brand for brand in competitor_brands if brand in collapsed})
    comp_tokens = sorted({term for term in competitor_terms if len(term) >= 3 and _hit(term, worded, collapsed)})
    matched_competitors = sorted(set(comp_brands) | set(comp_tokens))
    matched_intent = sorted({term for term in BUYER_INTENT_TERMS if _hit(term, worded, collapsed)})
    # Gate for paid: an ad pulled BY competitor name must show the actual NICHE in its own copy.
    # Off-niche brands pulled under a colliding competitor name (a watch under "Grain", a fashion
    # label under "Hugo", a charity under "Fellow") carry the competitor name but no niche terms, so
    # they drop here; real competitor ads keep their niche language (meeting / notes / ai) and
    # survive. Buyer-intent terms are deliberately NOT accepted here: they are generic business
    # words that leak off-niche ads (a charity's "members", a fidget toy's "pos") through the gate.
    if paid and not matched:
        return 0.0, "Paid ad shows no niche-term signal in its own creative copy."
    head = max(terms, key=len) if terms else ""
    score = 0.0
    score += min(0.4, 0.1 * len([m for m in matched if m not in matched_competitors]))
    if head and head in matched:
        score += 0.2  # the niche category head-noun (e.g. "notetakers") is a strong on-niche signal
    score += min(0.5, 0.25 * len(comp_brands))
    score += min(0.3, 0.15 * len([t for t in comp_tokens if t not in comp_brands]))
    score += min(0.35, 0.18 * len(matched_intent))
    score = min(1.0, score)
    if matched or matched_competitors or matched_intent:
        reason_parts = []
        if matched:
            reason_parts.append("niche: " + ", ".join(matched[:8]))
        if matched_competitors:
            reason_parts.append("competitor: " + ", ".join(matched_competitors[:8]))
        if matched_intent:
            reason_parts.append("buyer-intent: " + ", ".join(matched_intent[:8]))
        return score, "; ".join(reason_parts)
    if _has_source_metric(record):
        return 0.12, "No direct niche term match; retained only if threshold allows due to source metrics."
    return 0.0, "No niche, competitor, or metric signal matched."


def apply_relevance(records, niche, competitors=None, threshold=None, paid=False):
    if threshold is None:
        threshold = PAID_RELEVANCE_THRESHOLD if paid else DEFAULT_RELEVANCE_THRESHOLD
    kept = []
    drops = []
    for index, record in enumerate(records):
        score, reason = score_record(record, niche, competitors, paid=paid)
        enriched = dict(record)
        enriched["relevance_score"] = round(score, 3)
        enriched["relevance_reason"] = reason
        if score >= threshold:
            kept.append(enriched)
        else:
            enriched["drop_reason"] = f"relevance_score {score:.3f} below {threshold:.2f}: {reason}"
            drops.append({"index": index, **enriched})
    return kept, drops


def _query_terms(niche, competitors):
    raw = [niche] + list(competitors)
    words = []
    for item in raw:
        words.extend(re.findall(r"[a-z0-9]+", str(item).lower()))
    stop = {"the", "and", "for", "with", "your", "you", "from", "this", "that"}
    return [w for w in dict.fromkeys(words) if len(w) >= 2 and w not in stop]


def _record_text(record):
    fields = (
        "hook_text",
        "primary_text",
        "headline",
        "caption",
        "description",
        "title",
        "competitor_name",
        "competitor_handle",
        "creator_handle",
        "post_url",
        "ad_library_url",
        "format",
    )
    return " ".join(str(record.get(field) or "") for field in fields).lower()


def _content_text(record):
    # Only the creative's own copy, never the metadata we stamped on it (competitor_name, handles,
    # urls, format). Used to score paid ads so an off-niche brand pulled under a colliding
    # competitor name cannot pass on the stamped name alone.
    fields = ("hook_text", "primary_text", "headline", "caption", "description", "title")
    return " ".join(str(record.get(field) or "") for field in fields).lower()


def _has_source_metric(record):
    return bool(record.get("views") or record.get("days_active") or record.get("post_url") or record.get("ad_id"))
