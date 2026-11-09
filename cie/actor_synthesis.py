from collections import Counter

_FIXED_AXES = (
    "age_bracket",
    "gender_read",
    "body_type",
    "look_polish",
    "styling",
    "setting",
    "energy",
)


class ActorSynthesisError(Exception):
    pass


def synthesize_actor_profile(records: list) -> dict:
    if not records:
        raise ActorSynthesisError("cannot synthesize an actor profile from an empty batch")

    profile = {}
    for field in _FIXED_AXES:
        counts = Counter(r[field] for r in records)
        profile[field] = {"tally": dict(counts.most_common()), "mode": counts.most_common(1)[0][0]}

    brand_counts = Counter()
    for r in records:
        brand_counts.update(r.get("brand_signals", []))
    profile["brand_signals"] = dict(brand_counts.most_common())

    archetype_counts = Counter(r["regional_archetype"] for r in records)
    profile["regional_archetype"] = dict(archetype_counts.most_common())

    return profile
