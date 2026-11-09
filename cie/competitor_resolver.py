"""Pure competitor company-page resolution."""

import re


# Categories that indicate a real software/tech/product company.
# Bare "digital"/"web" are deliberately excluded: they match "Digital creator" (a person) and
# "...website" content-site categories, which are not software companies.
_ON_NICHE = re.compile(
    r"software|technolog|\bapp\b|app page|internet company|product/service|computer|saas|information technology|business service|science, technology|electronics|web (design|develop)",
    re.I,
)
# Categories that are clearly the wrong kind of brand for a software niche. Person/creator page
# types are included so an exact IG-handle match to a HUMAN (a public figure named "Jamie") can
# never resolve as if it were the software company.
_OFF_NICHE = re.compile(
    r"jewelry|watch|apparel|clothing|shoe|food|beverage|restaurant|grocer|movie|film|music|band|singer|religio|church|nonprofit|charity|school|education|college|photograph|health|beauty|medical|book|magazine|entertainment|chef|cook|fashion|retail|furniture|automotive|\bcar\b|travel|hotel|real estate|sports|athlete|artist|digital creator|content creator|public figure|personal blog|blogger|influencer",
    re.I,
)


def _collapse(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# Trailing tokens that decorate a brand's page/handle without changing its identity
# ("otterai" == "otter", "meetilyapp" == "meetily"). Deliberately NOT "io"/"co": those fuse into
# real brand names ("Loomio" != "Loom", "Draftco" != "Draft") and would create wrong-brand matches.
_SUFFIXES = ("ai", "app", "hq", "inc", "official", "premium", "insta", "ig")


def _brand_core(text) -> str:
    core = _collapse(text)
    changed = True
    while changed and len(core) > 3:
        changed = False
        for suffix in _SUFFIXES:
            if core.endswith(suffix) and len(core) - len(suffix) >= 3:
                core = core[: -len(suffix)]
                changed = True
    return core


def _handle_match(query, ig_username) -> bool:
    # Exact brand-core equality only. "otter.ai" == "Otter.ai", but "grainesdepelerins" != "Grain"
    # and "krispcall" != "Krisp" (a prefix is not enough — it is how collisions sneak in).
    handle = _collapse(ig_username)
    if len(handle) < 3:
        return False
    return _brand_core(query) == _brand_core(ig_username)


def _name_match(query, name) -> bool:
    # The query brand-core must equal the whole page name's brand-core (so a multi-word brand like
    # "Zen Planner" matches "Zen Planner"), OR appear as a whole word in the name (so "Grain"
    # matches "Grain" / "Grain Platform" but NOT "Graines de Pelerins", and "Fellow" matches
    # "Fellow App" but NOT "Fellowship Church"). A substring of a larger word is never a match.
    core = _brand_core(query)
    if not core:
        return False
    if _brand_core(name) == core:
        return True
    words = re.split(r"[^a-z0-9]+", str(name or "").lower())
    return any(_brand_core(word) == core for word in words if word)


def score_candidate(query, candidate) -> float:
    category = str(candidate.get("category") or "")
    if candidate.get("page_is_deleted") or _OFF_NICHE.search(category):
        return -1.0  # off-niche category is a hard reject; no signal overrides a wrong-kind brand
    handle_match = _handle_match(query, candidate.get("ig_username"))
    on_niche = bool(_ON_NICHE.search(category))
    name_match = _name_match(query, candidate.get("name"))
    # Require a POSITIVE identity signal: an exact IG-handle brand match, or an on-niche category
    # paired with a whole-word name match. Merely "not off-niche" is not enough (that lets a
    # Public Figure / E-commerce / Producer page win on likes alone).
    if not (handle_match or (on_niche and name_match)):
        return -1.0
    score = 0.0
    if handle_match:
        score += 5
    if on_niche:
        score += 2
    if name_match:
        score += 2
    if candidate.get("verification") == "BLUE_VERIFIED":
        score += 1
    score += min(1.0, float(candidate.get("likes") or 0) / 1_000_000)
    return score


def resolve_company_page(query, candidates) -> dict | None:
    scored = [(score_candidate(query, candidate), candidate) for candidate in candidates]
    qualified = [(score, candidate) for score, candidate in scored if score >= 2.0]
    if not qualified:
        return None
    score, candidate = max(qualified, key=lambda item: item[0])
    return {
        "page_id": candidate.get("page_id"),
        "name": candidate.get("name"),
        "category": candidate.get("category"),
        "ig_username": candidate.get("ig_username"),
        "likes": candidate.get("likes"),
        "score": score,
    }
