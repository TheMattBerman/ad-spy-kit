import json
import os

from .actor_schema import validate_actor_record
from .taxonomy import validate_format_tag, validate_mechanic_tag, validate_message_frame

REQUIRED_RAW = ("organic", "paid", "actor_batch", "narrative")

ORGANIC_RETAINED_STRING_FIELDS = (
    "post_url",
    "creator_handle",
    "thumbnail_url",
    "thumbnail_local_path",
    "hook_text",
    "message_frame",
    "message_frame_reason",
    "message_frame_provider",
    "message_frame_model",
    "mechanics_reason",
    "mechanics_provider",
    "mechanics_model",
)

PAID_RETAINED_STRING_FIELDS = (
    "competitor_name",
    "competitor_handle",
    "ad_id",
    "ad_library_url",
    "creative_url",
    "creative_local_path",
    "headline",
    "primary_text",
    "message_frame",
    "message_frame_reason",
    "message_frame_provider",
    "message_frame_model",
    "mechanics_reason",
    "mechanics_provider",
    "mechanics_model",
)

ACTOR_RETAINED_STRING_FIELDS = (
    "creator_name",
    "creator_handle",
    "profile_url",
    "avatar_url",
    "avatar_local_path",
    "top_thumbnail_url",
    "top_thumbnail_local_path",
    "why_included",
)

COMPETITOR_SOURCES = ("seed", "discovered")

PROVENANCE_STRING_FIELDS = (
    "ring_role",
    "ring_query",
    "source_provider",
    "source_surface_kind",
    "source_surface_id",
    "source_surface_name",
    "scoring_role",
)


def _load(path):
    with open(path) as f:
        return json.load(f)


def _is_non_negative_int(val):
    return isinstance(val, int) and not isinstance(val, bool) and val >= 0


def _is_confidence(val):
    return isinstance(val, (int, float)) and not isinstance(val, bool) and 0 <= val <= 1


def _validate_optional_string_fields(item, prefix, fields):
    errors = []
    for key in fields:
        if key in item and not isinstance(item[key], str):
            errors.append(f"{prefix} {key} must be a string")
    return errors


def _validate_optional_confidence(item, prefix):
    errors = []
    if "format_confidence" in item and not _is_confidence(item["format_confidence"]):
        errors.append(f"{prefix} format_confidence must be a number between 0 and 1")
    if "message_frame_confidence" in item and not _is_confidence(item["message_frame_confidence"]):
        errors.append(f"{prefix} message_frame_confidence must be a number between 0 and 1")
    return errors


def _validate_optional_message_frame(item, prefix):
    frame = item.get("message_frame")
    if frame in (None, ""):
        return []
    if not validate_message_frame(frame):
        return [f"{prefix} unknown message frame: {frame!r}"]
    return []


def _validate_optional_mechanics(item, prefix):
    if "mechanics" not in item:
        return []
    mechanics = item["mechanics"]
    if not isinstance(mechanics, list):
        return [f"{prefix} mechanics must be a list of strings"]
    errors = []
    for tag in mechanics:
        if not isinstance(tag, str):
            errors.append(f"{prefix} mechanics must be a list of strings")
            continue
        if not validate_mechanic_tag(tag):
            errors.append(f"{prefix} unknown mechanic tag: {tag!r}")
    return errors


def _validate_live_provenance(item, prefix, *, required=False, expected_role=None, expected_scoring=None):
    errors = []
    has_any = any(key in item for key in PROVENANCE_STRING_FIELDS + ("source_created",))
    if required and not has_any:
        errors.append(f"{prefix} missing two-ring provenance fields")
        return errors
    if not has_any:
        return errors
    for key in PROVENANCE_STRING_FIELDS:
        if key not in item:
            errors.append(f"{prefix} {key} is required for two-ring provenance")
        elif not isinstance(item[key], str):
            errors.append(f"{prefix} {key} must be a string")
    if "source_created" not in item:
        errors.append(f"{prefix} source_created is required for two-ring provenance")
    elif not isinstance(item["source_created"], bool):
        errors.append(f"{prefix} source_created must be a bool")
    if expected_role is not None and item.get("ring_role") != expected_role:
        errors.append(f"{prefix} ring_role must be {expected_role!r}")
    if expected_scoring is not None and item.get("scoring_role") != expected_scoring:
        errors.append(f"{prefix} scoring_role must be {expected_scoring!r}")
    return errors


def _validate_competitors(root):
    errors = []
    path = os.path.join(root, "raw", "competitors.json")
    if not os.path.exists(path):
        return errors

    try:
        data = _load(path)
    except (ValueError, OSError) as e:
        return [f"raw/competitors.json not valid JSON: {e}"]

    if not isinstance(data, list):
        return ["raw/competitors.json must be a JSON array"]

    for i, item in enumerate(data):
        prefix = f"raw/competitors.json[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix} name must be a non-empty string")

        handles = item.get("handles")
        if not isinstance(handles, list) or any(not isinstance(handle, str) for handle in handles):
            errors.append(f"{prefix} handles must be a list of strings")

        source = item.get("seed_or_discovered")
        if source not in COMPETITOR_SOURCES:
            errors.append(f"{prefix} seed_or_discovered must be one of {COMPETITOR_SOURCES}: {source!r}")

        discovery_reason = item.get("discovery_reason")
        if not isinstance(discovery_reason, str):
            errors.append(f"{prefix} discovery_reason must be a string")

        for key in ("ads_sampled_count", "organic_sampled_count"):
            val = item.get(key)
            if not _is_non_negative_int(val):
                errors.append(f"{prefix} {key} must be a non-negative int")

    return errors


def _load_run_meta(root):
    path = os.path.join(root, "raw", "run_meta.json")
    if not os.path.exists(path):
        return {}
    try:
        data = _load(path)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _validate_creative_record(item, prefix, *, provenance_required=False, expected_role=None, expected_scoring=None):
    errors = []
    fmt = item.get("format")
    if not validate_format_tag(fmt):
        errors.append(f"{prefix} unknown format tag: {fmt!r}")
    for key in ("views", "follower_count"):
        val = item.get(key)
        if not _is_non_negative_int(val):
            errors.append(f"{prefix} {key} must be a non-negative int")
    errors.extend(_validate_optional_string_fields(item, prefix, ORGANIC_RETAINED_STRING_FIELDS))
    errors.extend(_validate_optional_confidence(item, prefix))
    errors.extend(_validate_optional_message_frame(item, prefix))
    errors.extend(_validate_optional_mechanics(item, prefix))
    errors.extend(
        _validate_live_provenance(
            item,
            prefix,
            required=provenance_required,
            expected_role=expected_role,
            expected_scoring=expected_scoring,
        )
    )
    return errors


def _validate_buyer_context(root):
    errors = []
    path = os.path.join(root, "raw", "buyer_context.json")
    if not os.path.exists(path):
        return errors
    try:
        data = _load(path)
    except (ValueError, OSError) as e:
        return [f"raw/buyer_context.json not valid JSON: {e}"]
    if not isinstance(data, list):
        return ["raw/buyer_context.json must be a JSON array"]
    for i, item in enumerate(data):
        prefix = f"raw/buyer_context.json[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(
            _validate_creative_record(
                item,
                prefix,
                provenance_required=True,
                expected_role="buyer",
                expected_scoring="context_only",
            )
        )
    return errors


def validate_diagnostic_capture(root: str) -> list:
    errors = []
    run_meta = _load_run_meta(root)
    is_two_ring = run_meta.get("virlo_model") == "two_ring"
    for name in REQUIRED_RAW:
        path = os.path.join(root, "raw", f"{name}.json")
        if not os.path.exists(path):
            errors.append(f"missing raw pull: raw/{name}.json")
            continue
        try:
            data = _load(path)
        except (ValueError, OSError) as e:
            errors.append(f"raw/{name}.json not valid JSON: {e}")
            continue

        if name == "narrative":
            if not isinstance(data, dict):
                errors.append("raw/narrative.json must be a JSON object")
                continue
            for key in ("casting_paragraph", "gap_insight"):
                val = data.get(key)
                if not isinstance(val, str) or not val.strip():
                    errors.append(f"raw/narrative.json {key} must be a non-empty string")
            continue

        items = data
        if not isinstance(items, list):
            errors.append(f"raw/{name}.json must be a JSON array")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"raw/{name}.json[{i}] must be an object")
                continue
            if name in ("organic", "paid"):
                fmt = item.get("format")
                if not validate_format_tag(fmt):
                    errors.append(f"raw/{name}.json[{i}] unknown format tag: {fmt!r}")
            if name == "organic":
                prefix = f"raw/organic.json[{i}]"
                errors.extend(
                    _validate_creative_record(
                        item,
                        prefix,
                        provenance_required=is_two_ring,
                        expected_role="interest" if is_two_ring else None,
                        expected_scoring="gap_input" if is_two_ring else None,
                    )
                )
            if name == "paid":
                days = item.get("days_active")
                if not _is_non_negative_int(days):
                    errors.append(f"raw/paid.json[{i}] days_active must be a non-negative int")
                if not isinstance(item.get("still_active"), bool):
                    errors.append(f"raw/paid.json[{i}] still_active must be a bool")
                prefix = f"raw/paid.json[{i}]"
                errors.extend(_validate_optional_string_fields(item, prefix, PAID_RETAINED_STRING_FIELDS))
                errors.extend(_validate_optional_confidence(item, prefix))
                errors.extend(_validate_optional_message_frame(item, prefix))
                errors.extend(_validate_optional_mechanics(item, prefix))
            if name == "actor_batch":
                prefix = f"raw/actor_batch.json[{i}]"
                # A subscription run may deliberately retain an actor receipt
                # awaiting local-agent vision. It must not invent a demographic
                # profile merely to satisfy this validator.
                if item.get("actor_read_status") != "needs-agent":
                    for e in validate_actor_record(item):
                        errors.append(f"raw/actor_batch.json[{i}] {e}")
                else:
                    paths = item.get("actor_read_evidence_paths")
                    if not isinstance(paths, list) or not paths:
                        errors.append(f"{prefix} needs-agent actor read requires visual evidence paths")
                errors.extend(_validate_optional_string_fields(item, prefix, ACTOR_RETAINED_STRING_FIELDS))
                errors.extend(
                    _validate_live_provenance(
                        item,
                        prefix,
                        required=is_two_ring,
                        expected_role="interest" if is_two_ring else None,
                        expected_scoring="context_only" if is_two_ring else None,
                    )
                )
                if "follower_count" in item and not _is_non_negative_int(item["follower_count"]):
                    errors.append(f"{prefix} follower_count must be a non-negative int")

    errors.extend(_validate_competitors(root))
    errors.extend(_validate_buyer_context(root))
    return errors
