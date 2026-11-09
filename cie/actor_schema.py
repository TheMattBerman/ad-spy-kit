AGE_BRACKETS = ("teens-early-20s", "mid-20s-30s", "40s", "50-plus")
GENDER_READS = ("male", "female", "mixed-ambiguous")
BODY_TYPES = ("lean-athletic", "average", "heavier-set")
LOOK_POLISH = ("aspirational-polished", "relatable-next-door", "raw-unpolished")
STYLING = ("put-together-aspirational", "athletic-branded", "chill-comfy-casual")
SETTINGS = ("home-gym", "outdoor", "studio-produced", "everyday-life")
ENERGY = ("calm-low-key", "high-energy-hype", "in-between")

REQUIRED_FIELDS = (
    "age_bracket",
    "gender_read",
    "body_type",
    "look_polish",
    "styling",
    "setting",
    "energy",
    "brand_signals",
    "regional_archetype",
)

_FIXED_AXES = {
    "age_bracket": AGE_BRACKETS,
    "gender_read": GENDER_READS,
    "body_type": BODY_TYPES,
    "look_polish": LOOK_POLISH,
    "styling": STYLING,
    "setting": SETTINGS,
    "energy": ENERGY,
}


class ActorSchemaError(Exception):
    pass


def validate_actor_record(record: dict) -> list:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")

    for field, allowed in _FIXED_AXES.items():
        if field in record and record[field] not in allowed:
            errors.append(f"{field} must be one of {allowed}: {record[field]!r}")

    if "brand_signals" in record:
        bs = record["brand_signals"]
        if not isinstance(bs, list) or any(not isinstance(x, str) or not x for x in bs):
            errors.append("brand_signals must be a list of non-empty strings")

    if "regional_archetype" in record:
        ra = record["regional_archetype"]
        if not isinstance(ra, str) or not ra.strip():
            errors.append("regional_archetype must be a non-empty string")

    return errors
