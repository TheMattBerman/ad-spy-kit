import base64
import json
import os
import urllib.request

from .actor_schema import AGE_BRACKETS, BODY_TYPES, ENERGY, GENDER_READS, LOOK_POLISH, SETTINGS, STYLING
from .subscription_agent import SubscriptionAgentError, run_subscription_visual_agent
from .virlo_client import USER_AGENT, _load_dotenv_if_needed


class ActorVisionError(Exception):
    pass


def can_headless_vision(dcfg):
    llm = getattr(dcfg, "llm", None)
    if not llm or llm.tier not in ("openrouter", "api_key") or not llm.model or not llm.api_key_env:
        return False
    return llm.tier == "openrouter" or llm.model.startswith("openai/")


def vision_read_actor(seed, dcfg=None):
    """Read an actor only from supplied local visual evidence.

    Subscription runs deliberately return a routeable incomplete record: actor
    traits must be supplied by an agent with visual access, never guessed from
    handles, captions, or URLs.
    """
    evidence = _local_image_evidence(seed)
    llm = getattr(dcfg, "llm", None)
    if not llm:
        return _needs_agent_read(evidence, provider="subscription", model="")
    if llm.tier == "subscription":
        if not evidence:
            return _needs_agent_read(evidence, provider="subscription", model="", reason="insufficient-visual-evidence: no readable local image paths")
        try:
            return _subscription_actor_read(seed, evidence)
        except (SubscriptionAgentError, ActorVisionError) as error:
            return _needs_agent_read(evidence, provider="subscription", model="codex", reason=f"needs-agent: local Codex vision request did not complete ({error})")
    if not can_headless_vision(dcfg):
        return _needs_agent_read(
            evidence,
            provider=str(getattr(llm, "tier", "unconfigured")),
            model=str(getattr(llm, "model", "")),
            reason="insufficient-visual-evidence: no configured supported vision model",
        )
    if not evidence:
        return _needs_agent_read(
            evidence,
            provider=llm.tier,
            model=llm.model,
            reason="insufficient-visual-evidence: no readable local image paths",
        )
    try:
        return _vision_actor_read(seed, llm, evidence)
    except ActorVisionError as error:
        return _needs_agent_read(
            evidence,
            provider=llm.tier,
            model=llm.model,
            reason=f"needs-agent: vision request did not complete ({error})",
        )


def _needs_agent_read(evidence, provider, model, reason="needs-agent: subscription visual read requires an agent job"):
    return {
        **_unknown_actor_fields(),
        "actor_read_provider": provider,
        "actor_read_model": model,
        "actor_read_confidence": 0.0,
        "actor_read_status": "needs-agent",
        "actor_read_evidence_paths": [item["path"] for item in evidence],
        "actor_read_provenance": _provenance(evidence, "needs-agent"),
        "actor_read_note": reason,
    }


def _unknown_actor_fields():
    return {
        "age_bracket": None,
        "gender_read": None,
        "body_type": None,
        "look_polish": None,
        "styling": None,
        "setting": None,
        "energy": None,
        "brand_signals": [],
        "regional_archetype": None,
    }


def _local_image_evidence(seed):
    paths = (
        ("avatar", seed.get("avatar_abs_path") or seed.get("avatar_local_path")),
        (
            "top-thumbnail",
            seed.get("top_thumbnail_abs_path") or seed.get("top_thumbnail_local_path"),
        ),
    )
    return [{"role": role, "path": str(path)} for role, path in paths if path and os.path.isfile(path)]


def _vision_actor_read(seed, llm, evidence):
    _load_dotenv_if_needed(llm.api_key_env)
    api_key = os.environ.get(llm.api_key_env)
    if not api_key:
        raise ActorVisionError(f"{llm.api_key_env} is not set")
    url, model = _vision_endpoint(llm)
    payload = _vision_payload(seed, model, evidence)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        parsed = _parse_json_object(body["choices"][0]["message"]["content"])
    except Exception as error:
        raise ActorVisionError(str(error)) from error
    normalized = _normalize_actor_read(parsed, seed)
    normalized.update(
        {
            "actor_read_provider": llm.tier,
            "actor_read_model": llm.model,
            "actor_read_confidence": _confidence(parsed.get("actor_read_confidence")),
            "actor_read_status": "complete",
            "actor_read_evidence_paths": [item["path"] for item in evidence],
            "actor_read_provenance": _provenance(evidence, "vision-read"),
            "actor_read_note": str(parsed.get("actor_read_note") or "Vision-read from supplied local images."),
        }
    )
    return normalized


def _subscription_actor_read(seed, evidence):
    content = run_subscription_visual_agent(
        prompt=_actor_prompt(seed, evidence),
        image_paths=[item["path"] for item in evidence],
        schema=_actor_schema(),
        cwd=seed.get("agent_cwd") or os.getcwd(),
    )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise ActorVisionError("Codex actor read was not strict JSON") from error
    normalized = _normalize_actor_read(parsed, seed)
    normalized.update(
        {
            "actor_read_provider": "subscription",
            "actor_read_model": "codex",
            "actor_read_confidence": _confidence(parsed.get("actor_read_confidence")),
            "actor_read_status": "complete",
            "actor_read_evidence_paths": [item["path"] for item in evidence],
            "actor_read_provenance": _provenance(evidence, "vision-read"),
            "actor_read_note": str(parsed.get("actor_read_note") or "Vision-read from supplied local images."),
        }
    )
    return normalized


def _vision_endpoint(llm):
    if llm.tier == "openrouter":
        return "https://openrouter.ai/api/v1/chat/completions", llm.model
    if llm.model.startswith("openai/"):
        return "https://api.openai.com/v1/chat/completions", llm.model.split("/", 1)[1]
    raise ActorVisionError("api_key tier requires an openai/<vision-model> identifier")


def _vision_payload(seed, model, evidence):
    content = [{"type": "text", "text": _actor_prompt(seed, evidence)}]
    content.extend({"type": "image_url", "image_url": {"url": _image_data_uri(item["path"])}} for item in evidence)
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "actor_visual_read", "strict": True, "schema": _actor_schema()},
        },
    }


def _actor_prompt(seed, evidence):
    prompt = {
        "allowed": {
            "age_bracket": AGE_BRACKETS,
            "gender_read": GENDER_READS,
            "body_type": BODY_TYPES,
            "look_polish": LOOK_POLISH,
            "styling": STYLING,
            "setting": SETTINGS,
            "energy": ENERGY,
        },
        "instruction": (
            "First decide whether a person is visibly present. If not, set person_visible=false; do not invent a person. "
            "If a person is visible, infer every fixed field only from the supplied images and return only the required JSON. "
            "Choose exactly one allowed value for every fixed field. Use mixed-ambiguous when unsure. "
            "Do not identify the person or infer an exact region. Describe visible brand_signals only."
        ),
        "creator": seed.get("creator_name", ""),
        "image_roles": [item["role"] for item in evidence],
    }
    return json.dumps(prompt, ensure_ascii=True)


def _actor_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "person_visible", "age_bracket", "gender_read", "body_type", "look_polish", "styling", "setting", "energy",
            "brand_signals", "regional_archetype", "actor_read_confidence", "actor_read_note",
        ],
        "properties": {
            "person_visible": {"type": "boolean"},
            "age_bracket": {"type": "string", "enum": list(AGE_BRACKETS)},
            "gender_read": {"type": "string", "enum": list(GENDER_READS)},
            "body_type": {"type": "string", "enum": list(BODY_TYPES)},
            "look_polish": {"type": "string", "enum": list(LOOK_POLISH)},
            "styling": {"type": "string", "enum": list(STYLING)},
            "setting": {"type": "string", "enum": list(SETTINGS)},
            "energy": {"type": "string", "enum": list(ENERGY)},
            "brand_signals": {"type": "array", "items": {"type": "string"}},
            "regional_archetype": {"type": "string"},
            "actor_read_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "actor_read_note": {"type": "string"},
        },
    }


def _normalize_actor_read(parsed, seed):
    if parsed.get("person_visible") is not True:
        raise ActorVisionError("no recognizable person was visible in the supplied images")
    return {
        "person_visible": True,
        "age_bracket": _required_allowed(parsed.get("age_bracket"), AGE_BRACKETS, "age_bracket"),
        "gender_read": _required_allowed(parsed.get("gender_read"), GENDER_READS, "gender_read"),
        "body_type": _required_allowed(parsed.get("body_type"), BODY_TYPES, "body_type"),
        "look_polish": _required_allowed(parsed.get("look_polish"), LOOK_POLISH, "look_polish"),
        "styling": _required_allowed(parsed.get("styling"), STYLING, "styling"),
        "setting": _required_allowed(parsed.get("setting"), SETTINGS, "setting"),
        "energy": _required_allowed(parsed.get("energy"), ENERGY, "energy"),
        "brand_signals": _string_list(parsed.get("brand_signals"))[:5],
        "regional_archetype": str(parsed.get("regional_archetype") or "visible creator; region not inferred"),
    }


def _provenance(evidence, status):
    return {"source": "local-image-evidence", "status": status, "images": evidence}


def _confidence(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.75


def _required_allowed(value, allowed, field):
    if value not in allowed:
        raise ActorVisionError(f"actor vision returned invalid {field}: {value!r}")
    return value


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _image_data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


def _parse_json_object(text):
    text = str(text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ActorVisionError("model did not return a JSON object")
    return json.loads(text[start : end + 1])
