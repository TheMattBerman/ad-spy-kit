import tomllib
from dataclasses import dataclass, field

VALID_LLM_TIERS = ("subscription", "openrouter", "api_key")


class DiagnosticConfigError(Exception):
    pass


@dataclass
class LlmSpec:
    tier: str
    model: str = ""
    api_key_env: str = ""


@dataclass
class DiagnosticConfig:
    niche: str
    competitors: list = field(default_factory=list)
    llm: LlmSpec = field(default_factory=lambda: LlmSpec(tier="subscription"))
    own_brand: str = ""
    buyer_query: str = ""
    interest_query: str = ""


def _load_llm_spec(raw_llm: dict) -> LlmSpec:
    tier = raw_llm.get("tier", "subscription")
    if tier not in VALID_LLM_TIERS:
        raise DiagnosticConfigError(f"llm.tier must be one of {VALID_LLM_TIERS}: {tier!r}")

    model = raw_llm.get("model", "")
    api_key_env = raw_llm.get("api_key_env", "")

    if tier != "subscription":
        if not isinstance(model, str) or not model.strip():
            raise DiagnosticConfigError(f"llm.model must be a non-empty string when tier is {tier!r}")
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise DiagnosticConfigError(f"llm.api_key_env must be a non-empty string when tier is {tier!r}")
    else:
        if (isinstance(model, str) and model.strip()) or (isinstance(api_key_env, str) and api_key_env.strip()):
            raise DiagnosticConfigError(
                "llm.model/llm.api_key_env are set but llm.tier is \"subscription\" (they would be silently "
                "ignored) — set tier to \"openrouter\" or \"api_key\", or remove model/api_key_env"
            )

    return LlmSpec(tier=tier, model=model, api_key_env=api_key_env)


def load_diagnostic_config(path: str) -> DiagnosticConfig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    if "niche" not in raw:
        raise DiagnosticConfigError("missing required config key: niche")
    if not isinstance(raw["niche"], str) or not raw["niche"].strip():
        raise DiagnosticConfigError(f"niche must be a non-empty string: {raw['niche']!r}")

    competitors = raw.get("competitors", [])
    if not isinstance(competitors, list) or any(not isinstance(c, str) for c in competitors):
        raise DiagnosticConfigError("competitors must be a list of strings")

    own_brand = raw.get("own_brand", "")
    if not isinstance(own_brand, str):
        raise DiagnosticConfigError("own_brand must be a string")

    llm = LlmSpec(tier="subscription")
    if "llm" in raw:
        raw_llm = raw["llm"]
        if not isinstance(raw_llm, dict):
            raise DiagnosticConfigError("llm must be a table")
        llm = _load_llm_spec(raw_llm)

    rings = raw.get("rings", {})
    if rings and not isinstance(rings, dict):
        raise DiagnosticConfigError("rings must be a table")
    buyer_query = rings.get("buyer_query", "") if isinstance(rings, dict) else ""
    interest_query = rings.get("interest_query", "") if isinstance(rings, dict) else ""
    for key, value in (("rings.buyer_query", buyer_query), ("rings.interest_query", interest_query)):
        if value is not None and not isinstance(value, str):
            raise DiagnosticConfigError(f"{key} must be a string")

    return DiagnosticConfig(
        niche=raw["niche"],
        competitors=competitors,
        llm=llm,
        own_brand=own_brand.strip(),
        buyer_query=(buyer_query or "").strip(),
        interest_query=(interest_query or "").strip(),
    )
