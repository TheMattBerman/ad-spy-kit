import json
import os
import urllib.request

from .classification_cache import classification_cache_key
from .media_evidence import MediaEvidenceError, build_image_data_uri, validate_image_media
from .taxonomy import ALL_FORMATS, ALL_HOOK_TYPES, ALL_MECHANICS, ALL_MESSAGE_FRAMES, SCOREABLE_FORMATS, VIDEO_FORMATS
from .taxonomy_catalog import CATALOG_VERSION, catalog_payload, vision_classifier_prompt_payload
from .subscription_agent import SubscriptionAgentError, run_subscription_visual_agent
from .virlo_client import USER_AGENT, _load_dotenv_if_needed


class ClassificationError(Exception):
    pass


_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "primary_format",
        "format_confidence",
        "format_reason",
        "message_frame",
        "message_frame_confidence",
        "message_frame_reason",
        "primary_hook_type",
        "hook_type_confidence",
        "hook_type_reason",
        "mechanics",
    ],
    "properties": {
        "primary_format": {"type": "string"},
        "format_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "format_reason": {"type": "string"},
        "message_frame": {"type": "string"},
        "message_frame_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "message_frame_reason": {"type": "string"},
        "primary_hook_type": {"type": "string"},
        "hook_type_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "hook_type_reason": {"type": "string"},
        "mechanics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "confidence", "reason"],
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


def classify_creative(record, kind, evidence, dcfg, cache=None):
    """Classify observed creative from local visual evidence with one vision request.

    A scoreable visual format or mechanic is never inferred from record text.  The
    supplied manifest must come from :func:`media_evidence.build_evidence_manifest`.
    """
    llm = getattr(dcfg, "llm", None)
    if not llm:
        return _insufficient_visual_result(
            "No visual-classification route is configured.", provider="unconfigured", model=""
        )

    evidence_entries = _validated_evidence_entries(evidence)
    if not evidence_entries:
        return _insufficient_visual_result(
            "No validated local visual evidence was supplied; visual formats and mechanics are unscored.",
            provider=llm.tier,
            model=llm.model,
        )

    evidence_roles = [entry["role"] for entry in evidence_entries]
    prompt = _vision_prompt(record, kind, evidence_roles)
    evidence_refs = [_evidence_ref(entry) for entry in evidence_entries]
    provider = llm.tier
    model = llm.model
    cache_key = classification_cache_key(
        prompt=prompt,
        taxonomy=catalog_payload(),
        provider=provider,
        model=model,
        text=_record_text(record),
        evidence_hashes=[entry["sha256"] for entry in evidence_entries],
    )
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            if not isinstance(cached, dict):
                raise ClassificationError("classification cache entry must contain an object")
            result = dict(cached)
            provenance = dict(result.get("classification_provenance") or {})
            provenance["cache_hit"] = True
            result["classification_provenance"] = provenance
            return result

    if llm.tier == "subscription":
        try:
            content = run_subscription_visual_agent(
                prompt=prompt,
                image_paths=[entry["local_path"] for entry in evidence_entries],
                schema=_CLASSIFICATION_SCHEMA,
                cwd=record.get("_agent_cwd") or os.getcwd(),
            )
        except SubscriptionAgentError as error:
            raise ClassificationError(str(error)) from error
        result = _validated_vision_result(
            content, evidence_refs, "subscription", "codex", evidence_roles,
            opening_line=record.get("opening_line", ""), display_format=record.get("display_format", ""),
            static_ocr_text=record.get("static_ocr_text", ""), visual_evidence_scope=record.get("visual_evidence_scope", "")
        )
        result["classification_provenance"]["cache_key"] = cache_key
        if cache is not None:
            cache.set(cache_key, result)
        return result

    if llm.tier not in ("openrouter", "api_key"):
        raise ClassificationError(f"unsupported visual-classification tier: {llm.tier!r}")
    provider, model, url, headers = _provider_request_config(llm)
    content = [{"type": "text", "text": prompt}]
    content.extend(
        {"type": "image_url", "image_url": {"url": build_image_data_uri(entry["local_path"])}}
        for entry in evidence_entries
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "creative_classification", "strict": True, "schema": _CLASSIFICATION_SCHEMA},
        },
    }
    body = _post_json(url, headers, payload)
    result = _validated_vision_result(
        _response_content(body), evidence_refs, provider, llm.model, evidence_roles,
        opening_line=record.get("opening_line", ""), display_format=record.get("display_format", ""),
        static_ocr_text=record.get("static_ocr_text", ""), visual_evidence_scope=record.get("visual_evidence_scope", "")
    )
    result["classification_provenance"]["cache_key"] = cache_key
    if cache is not None:
        cache.set(cache_key, result)
    return result


def classify_format(record, kind, dcfg=None, fallback=None):
    fallback = fallback or "insufficient-evidence"
    llm = getattr(dcfg, "llm", None)
    if llm and llm.tier in ("openrouter", "api_key"):
        try:
            return _classify_with_api(record, kind, llm)
        except Exception as error:
            return {
                "format": "insufficient-evidence",
                "format_confidence": 0.0,
                "classification_reason": f"Configured provider failed: {error}",
                "classification_provider": llm.tier,
                "classification_model": llm.model,
                "classification_degraded": True,
            }
    label, confidence, reason = _rule_classify(record, kind, fallback)
    return {
        "format": label,
        "format_confidence": confidence,
        "classification_reason": reason,
        "classification_provider": "local-rule",
        "classification_model": "winning-creative-tracker-rules",
    }


def classify_message_frame(record, kind, dcfg=None, fallback=None):
    fallback = fallback or "insufficient-evidence"
    llm = getattr(dcfg, "llm", None)
    if llm and llm.tier in ("openrouter", "api_key"):
        try:
            return _classify_frame_with_api(record, kind, llm)
        except Exception as error:
            return {
                "message_frame": "insufficient-evidence",
                "message_frame_confidence": 0.0,
                "message_frame_reason": f"Configured provider failed: {error}",
                "message_frame_provider": llm.tier,
                "message_frame_model": llm.model,
                "message_frame_degraded": True,
            }
    label, confidence, reason = _rule_classify_frame(record, kind, fallback)
    return {
        "message_frame": label,
        "message_frame_confidence": confidence,
        "message_frame_reason": reason,
        "message_frame_provider": "local-rule",
        "message_frame_model": "winning-creative-tracker-rules",
    }


def classify_mechanics(record, kind, dcfg=None):
    labels, reason = _rule_classify_mechanics(record, kind)
    return {
        "mechanics": labels,
        "mechanics_reason": reason,
        "mechanics_provider": "local-rule",
        "mechanics_model": "winning-creative-tracker-rules",
    }


def _rule_classify(record, kind, fallback):
    label, confidence, reason = _rule_classify_candidate(record, kind, fallback)
    if label in VIDEO_FORMATS:
        return (
            "insufficient-evidence",
            0.0,
            "Video format cannot be assigned from text without watching the creative.",
        )
    return label, confidence, reason


def _rule_classify_candidate(record, kind, fallback):
    text = " ".join(
        str(record.get(key) or "")
        for key in ("hook_text", "primary_text", "headline", "creative_url", "post_url", "display_format")
    ).lower()
    if any(w in text for w in ("tiktok shop", "shop link", "checkout link", "link below", "yellow cart")):
        return "tiktok-shop-hustle", 0.72, "Text/source points to native TikTok Shop-style selling."
    if any(w in text for w in ("podcast", "street mic", "interview", "q&a", "quick-fire", "mic'd up", "mic up")):
        return "interview-podcast-street-mic", 0.72, "Text/source points to interview, podcast, or street-mic framing."
    if any(w in text for w in ("warehouse", "employee", "our team", "packing orders", "behind the counter")):
        return "employee-warehouse", 0.7, "Text/source points to employee or warehouse-native content."
    if any(w in text for w in ("grwm", "storytime", "gossip", "hot girl", "in my car")):
        return "gossip-grwm", 0.7, "Text/source points to GRWM, gossip, or casual story monologue framing."
    if any(w in text for w in ("video sales letter", " vsl", "mini vsl", "mechanism", "deep dive")):
        return "vsl", 0.7, "Text/source points to VSL-style explanation."
    if any(w in text for w in ("wall of text", "scrolling text", "text scrolling", "script on screen")):
        return "wall-of-text", 0.7, "Text/source points to text-dominant video."
    if any(w in text for w in ("split screen", "sludge", "gameplay", "kinetic sand")):
        return "split-screen-sludge", 0.7, "Text/source points to split-screen/sludge-style retention mechanics."
    if any(w in text for w in ("3-second loop", "micro gif", "micro-gif", "looped", "rapid loop")):
        return "micro-loop", 0.68, "Text/source points to a short looped visual."
    if any(w in text for w in ("visual metaphor", "desire metaphor", "cinematic", "tranquility", "total control")):
        return "desire-metaphor-short", 0.66, "Text/source points to a desire-metaphor short."
    if kind == "paid" and record.get("has_cards"):
        return "carousel", 0.74, "Paid snapshot contained carousel/cards."
    if any(w in text for w in ("tweet", "twitter thread", "reddit", "comment section", "social comment")):
        return "tweet-reddit-ui", 0.72, "Text/source points to social UI mimic creative."
    if any(w in text for w in ("advertorial", "forbes", "vogue", "gq", "news headline", "press outlet")):
        return "advertorial", 0.72, "Text/source points to advertorial or press-style screenshot creative."
    if any(w in text for w in ("notification", "lock screen", "text message", "imessage", "dm", "low battery", "calendar alert")):
        return "notification-ui", 0.72, "Text/source points to notification or phone UI creative."
    if any(w in text for w in ("dashboard", "screen", "software", "app", "demo", "walkthrough", "workflow")):
        return ("faceless-demo" if kind == "organic" else "ui-mimic"), 0.72, "Text/source points to software screen or demo."
    if any(w in text for w in ("founder", "building", "behind the scenes", "bts")):
        return "founder-bts", 0.7, "Text points to founder/building/behind-the-scenes framing."
    if any(w in text for w in ("pov", "day in the life", "ditl")):
        return "narrative-vlog-ditl", 0.68, "Text points to POV/day-in-life framing."
    if kind == "paid" and any(w in text for w in ("proof", "data", "%", "$", "save", "cost", "price")):
        return "infographic-proof", 0.66, "Paid text emphasizes proof/data/cost."
    if any(w in text for w in ("grid", "skus", "colorways", "product variations")):
        return "grid-static", 0.66, "Text/source points to a product grid static."
    if any(w in text for w in ("testimonial", "review", "star rating", "customer said")):
        return "testimonial-screenshot", 0.68, "Text/source points to testimonial or review screenshot creative."
    if any(w in text for w in ("before after", "before/after", "day 1", "day 30", "timeline")):
        return "timeline-proof", 0.68, "Text/source points to before/after or timeline proof."
    if any(w in text for w in ("first frame", "video screenshot", "screenshot from")):
        return "first-frame-static", 0.64, "Text/source points to a first-frame static."
    if any(w in text for w in ("thermal", "x-ray", "xray", "mri")):
        return "thermal-vision", 0.66, "Text/source points to thermal/X-ray/MRI-style visual proof."
    if any(w in text for w in ("flat lay", "flat-lay", "carry-on", "will it fit")):
        return "flat-lay-fit-test", 0.66, "Text/source points to a fit-test flat lay."
    if any(w in text for w in ("spot the difference", "visual iq")):
        return "spot-the-difference", 0.66, "Text/source points to a visual puzzle."
    if any(w in text for w in ("circle and arrow", "circle & arrow", "red arrow", "ms paint")):
        return "circle-arrow-explainer", 0.66, "Text/source points to circle/arrow explainer creative."
    if any(w in text for w in ("quadrant", "matrix", "venn diagram")):
        return "quadrant-matrix", 0.66, "Text/source points to quadrant/matrix visual."
    if any(w in text for w in ("chart", "graph", "line breakout", "spike")):
        return "chart-breakout", 0.66, "Text/source points to chart or graph creative."
    if kind == "paid" and len(text) > 400:
        return "native-photo-long-copy", 0.64, "Long paid text with no stronger visual signal."
    if fallback in ALL_FORMATS:
        return fallback, 0.62, "Conservative fallback from local rules."
    return "insufficient-evidence", 0.3, "No strong local signal matched a scoreable format."


def _record_text(record):
    return " ".join(
        str(record.get(key) or "")
        for key in ("hook_text", "primary_text", "headline", "body_text", "caption", "display_format")
    ).lower()


def _rule_classify_frame(record, kind, fallback):
    text = _record_text(record)
    checks = (
        (
            "us-vs-them",
            (" old way ", " new way ", "everyone else", "other gyms", "other software", "they want you", "vs ", "versus"),
            "Text frames a side-by-side enemy or old-world/new-world contrast.",
        ),
        (
            "skeptical-expose",
            ("expose", "investigation", "scam", "consumer report", "proving why"),
            "Text uses skeptical expose framing.",
        ),
        (
            "reverse-psychology",
            ("don't buy", "do not buy", "not for you", "skip this if"),
            "Text uses reverse-psychology filtering.",
        ),
        (
            "life-hack",
            ("life hack", "today years old", "shortcut", "insider trick", "wish i knew"),
            "Text frames the idea as hidden practical knowledge.",
        ),
        (
            "forbidden-secret",
            ("is this legal", "legal team", "hates this", "what they don't want", "secret"),
            "Text frames the idea as forbidden or restricted information.",
        ),
        (
            "ancestral-tradition",
            ("ancestral", "what they hid", "traditional", "ancient", "synthetic"),
            "Text contrasts modern synthetic options with older/traditional methods.",
        ),
        (
            "hidden-cost",
            ("hidden cost", "costing you", "leak", "waste", "overpay", "losing money", "bleeding", "missed revenue"),
            "Text points to an unseen cost or leak.",
        ),
        (
            "before-after",
            ("before", "after", "used to", "now", "went from", "transformation"),
            "Text uses a before/after transformation frame.",
        ),
        (
            "mistake-to-avoid",
            ("mistake", "stop doing", "wrong", "avoid", "do not", "never do"),
            "Text warns against a mistake.",
        ),
        (
            "myth-bust",
            ("myth", "not true", "lie", "truth", "wrong about", "believe"),
            "Text challenges a belief or myth.",
        ),
        (
            "contrarian-take",
            ("unpopular opinion", "hot take", "contrarian", "actually", "instead of", "stop selling"),
            "Text leads with a contrarian take.",
        ),
        (
            "proof-stack",
            ("proof", "case study", "%", "$", "data", "numbers", "results", "roi"),
            "Text leans on quantified proof or evidence.",
        ),
        (
            "comparison",
            ("compare", "comparison", "which one", "best", "versus", "vs.", "alternative"),
            "Text compares options.",
        ),
        (
            "skeptic-to-believer",
            ("thought i was crazy", "didn't believe", "skeptical", "look who's laughing", "proved them wrong"),
            "Text moves from skepticism to belief.",
        ),
        (
            "reasons-why",
            ("reasons why", "here are", "ways to", "things you need", "reasons to"),
            "Text uses a numbered/listed reasons frame.",
        ),
        (
            "avatar-callout",
            ("for left-handed", "for nurses", "for tradespeople", "for gym owners", "if you're a"),
            "Text calls out a specific avatar.",
        ),
        (
            "cost-transparency",
            ("retails for", "we sell it for", "markup", "middleman", "direct-to-consumer", "cost breakdown"),
            "Text explains price or markup economics.",
        ),
        (
            "social-proof",
            ("customers", "owners use", "trusted by", "reviews", "testimonial", "join", "thousands"),
            "Text leans on adoption or social proof.",
        ),
        (
            "self-diagnosis",
            ("how to know", "check if", "score", "audit", "diagnose", "three numbers", "signs you"),
            "Text invites the viewer to diagnose themselves.",
        ),
        (
            "failed-attempts",
            ("tried", "failed", "spent", "before we", "nothing worked", "finally"),
            "Text names failed attempts before a better answer.",
        ),
        (
            "villain-callout",
            ("blame", "vendor", "bloated", "trap", "scam", "trick", "broken system"),
            "Text gives the problem a visible enemy.",
        ),
        (
            "identity-belonging",
            ("for owners", "for operators", "if you are", "people like us", "your team", "founders like"),
            "Text signals identity or in-group belonging.",
        ),
        (
            "risk-reversal",
            ("free", "guarantee", "no contract", "cancel", "risk", "trial", "demo"),
            "Text lowers perceived risk.",
        ),
        (
            "urgency-scarcity",
            ("today", "limited", "last chance", "deadline", "before", "now open"),
            "Text uses timing pressure.",
        ),
        (
            "how-it-works",
            ("how it works", "walkthrough", "behind", "inside", "step by step", "from one screen"),
            "Text explains the mechanism or workflow.",
        ),
        (
            "feature-to-benefit",
            ("so you can", "that means", "without", "saves", "reduce", "increase"),
            "Text translates a feature into an outcome.",
        ),
        (
            "offer-led",
            ("%", "off", "discount", "month free", "pricing", "per month", "$"),
            "Text leads with an offer or price.",
        ),
        (
            "challenge",
            ("challenge", "blind ranking", "taste test", "can it", "we tested"),
            "Text uses a challenge or gamified test frame.",
        ),
    )
    padded = f" {text} "
    for label, needles, reason in checks:
        if any(needle in padded for needle in needles):
            return label, 0.72, reason
    if fallback in ALL_MESSAGE_FRAMES:
        return fallback, 0.58, "Conservative message-frame fallback from local rules."
    return "insufficient-evidence", 0.3, "No strong local signal matched a message frame."


def _rule_classify_mechanics(record, kind):
    text = _record_text(record)
    checks = (
        ("green-screen", ("green screen", "greenscreen"), "green-screen"),
        ("split-screen", ("split screen", "split-screen", "sludge"), "split-screen"),
        ("kinetic-captions", ("kinetic caption", "highlighted caption", "subtitle pattern"), "kinetic captions"),
        ("loop", ("loop", "gif", "micro-gif", "micro gif"), "looped creative"),
        ("story-poll-mimic", ("poll sticker", "quiz sticker", "story poll", "tap to vote"), "story poll mimic"),
        ("carousel-reveal", ("swipe to reveal", "blurred", "censored", "card 2"), "carousel reveal"),
        ("carousel-self-segmentation", ("choose your own", "for the side", "for the back", "self-segment"), "carousel self-segmentation"),
        ("creator-handle", ("whitelisting", "creator handle", "spark ad", "partnership ad"), "creator handle"),
        ("stitch-bait", ("stitch", "had to stitch", "viral clip"), "stitch bait"),
    )
    found = []
    reasons = []
    for tag, needles, reason in checks:
        if any(needle in text for needle in needles) and tag in ALL_MECHANICS:
            found.append(tag)
            reasons.append(reason)
    return found, "Observed " + ", ".join(reasons) + "." if reasons else "No optional mechanics detected."


def _classify_with_api(record, kind, llm):
    _load_dotenv_if_needed(llm.api_key_env)
    api_key = os.environ.get(llm.api_key_env)
    if not api_key:
        raise ClassificationError(f"{llm.api_key_env} is not set")
    if llm.tier == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        model = llm.model
    else:
        if not llm.model.startswith("openai/"):
            raise ClassificationError("api_key tier currently supports openai/<model> identifiers")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        model = llm.model.split("/", 1)[1]
    prompt = (
        "Classify this creative into exactly one allowed format. "
        "Return JSON with keys format, confidence, reason. Allowed formats: "
        + ", ".join(sorted(ALL_FORMATS))
        + "\nKind: "
        + kind
        + "\nRecord: "
        + json.dumps(record, ensure_ascii=True)[:6000]
    )
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise ClassificationError(str(e)) from e
    content = body["choices"][0]["message"]["content"]
    parsed = _parse_json_object(content)
    fmt = parsed.get("format")
    if fmt not in ALL_FORMATS:
        raise ClassificationError(f"model returned unknown format: {fmt!r}")
    if fmt in VIDEO_FORMATS:
        # A video format must never be assigned from record text alone; it can only be
        # established by watching frames in the media-grounded path.
        return {
            "format": "insufficient-evidence",
            "format_confidence": 0.0,
            "classification_reason": "Video format cannot be assigned from text without watching the creative.",
            "classification_provider": llm.tier,
            "classification_model": llm.model,
        }
    confidence = parsed.get("confidence", 0.75)
    try:
        confidence = max(0, min(1, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.75
    return {
        "format": fmt,
        "format_confidence": confidence,
        "classification_reason": str(parsed.get("reason") or "LLM classified against closed taxonomy."),
        "classification_provider": llm.tier,
        "classification_model": llm.model,
    }


def _classify_frame_with_api(record, kind, llm):
    _load_dotenv_if_needed(llm.api_key_env)
    api_key = os.environ.get(llm.api_key_env)
    if not api_key:
        raise ClassificationError(f"{llm.api_key_env} is not set")
    if llm.tier == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        model = llm.model
    else:
        if not llm.model.startswith("openai/"):
            raise ClassificationError("api_key tier currently supports openai/<model> identifiers")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        model = llm.model.split("/", 1)[1]
    prompt = (
        "Classify this observed creative into exactly one allowed message frame. "
        "Do not write hooks, concepts, or new copy. Return JSON with keys frame, confidence, reason. "
        "Allowed frames: "
        + ", ".join(sorted(ALL_MESSAGE_FRAMES))
        + "\nKind: "
        + kind
        + "\nRecord: "
        + json.dumps(record, ensure_ascii=True)[:6000]
    )
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise ClassificationError(str(e)) from e
    content = body["choices"][0]["message"]["content"]
    parsed = _parse_json_object(content)
    frame = parsed.get("frame") or parsed.get("message_frame")
    if frame not in ALL_MESSAGE_FRAMES:
        raise ClassificationError(f"model returned unknown message frame: {frame!r}")
    confidence = parsed.get("confidence", 0.75)
    try:
        confidence = max(0, min(1, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.75
    return {
        "message_frame": frame,
        "message_frame_confidence": confidence,
        "message_frame_reason": str(parsed.get("reason") or "LLM classified against closed message-frame taxonomy."),
        "message_frame_provider": llm.tier,
        "message_frame_model": llm.model,
    }


def _parse_json_object(text):
    text = str(text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ClassificationError("model did not return a JSON object")
    return json.loads(text[start : end + 1])


def _provider_request_config(llm):
    _load_dotenv_if_needed(llm.api_key_env)
    api_key = os.environ.get(llm.api_key_env)
    if not api_key:
        raise ClassificationError(f"{llm.api_key_env} is not set")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
    if llm.tier == "openrouter":
        return llm.tier, llm.model, "https://openrouter.ai/api/v1/chat/completions", headers
    if llm.tier == "api_key" and llm.model.startswith("openai/"):
        return llm.tier, llm.model.split("/", 1)[1], "https://api.openai.com/v1/chat/completions", headers
    raise ClassificationError("api_key tier currently supports openai/<model> identifiers")


def _validated_evidence_entries(evidence):
    if not isinstance(evidence, dict):
        raise ClassificationError("evidence must be a manifest from build_evidence_manifest")
    entries = evidence.get("evidence")
    if not isinstance(entries, list):
        raise ClassificationError("evidence manifest must contain an evidence list")
    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ClassificationError("evidence entries must be objects")
        try:
            local_path = entry["local_path"]
            metadata = validate_image_media(local_path)
        except (KeyError, MediaEvidenceError) as error:
            raise ClassificationError(f"invalid local visual evidence: {error}") from error
        if entry.get("sha256") != metadata["sha256"] or entry.get("media_type") != metadata["media_type"]:
            raise ClassificationError(f"evidence manifest does not match local media: {local_path}")
        if not str(entry.get("role") or "").strip() or not str(entry.get("source_record_id") or "").strip():
            raise ClassificationError("evidence entries require role and source_record_id")
        validated.append({**entry, **metadata})
    return validated


def _vision_prompt(record, kind, evidence_roles):
    return (
        "Classify the observed creative from the attached local visual evidence. "
        "Return only the required JSON schema. Do not invent hooks, concepts, copy, audio, motion, or unseen context. "
        "A scoreable primary_format and every mechanic must be grounded in one or more attached images. "
        "If images do not establish a visual format, return primary_format=insufficient-evidence and mechanics=[]. "
        "When the evidence roles are thumbnail or creative only, do not claim that you observed motion, looping, "
        "audio, voice, or an unseen sequence. Those claims require one or more video-frame images. "
        "When multiple video-frame images are attached they are an ordered sequence of samples across the whole "
        "video from start to end; decide the primary_format from the format that DOMINATES the majority of the "
        "video's runtime, not from any single frame. A person being visible does not by itself make it a "
        "talking-head/yapper: a talking-head requires sustained direct-to-camera delivery across most frames. "
        "A face only in the intro, or a person in a corner while a screen or product dominates, is a demo/ui-mimic, "
        "not talking-head. Explain the dominant format in format_reason.\n"
        "Also classify exactly ONE primary hook type from the OPENING of the creative: opening-frame images, the first "
        "one or two attached video frames, opening on-screen text, and the observed opening_line below when provided. "
        "Choose the nearest hook-type catalog archetype whenever that opening evidence is legible, and assign its "
        "hook_type_confidence accordingly. The opening_line is observed transcript evidence: you may cite it but must "
        "not invent dialogue beyond it. Return primary_hook_type=hook-unknown only when there is genuinely no legible "
        "opening evidence, e.g. a single mid-video still or thumbnail-only evidence with no opening_line. For a "
        "static/image creative, the hook is NORMALLY on the creative: read the on-image headline/overlay text (the "
        "attached image and the provided OCR text) and the visual scroll-stopper, and assign the nearest catalog hook "
        "archetype. EXCEPTION for a zero-design native creative: if the static is a bare, native-looking visual with "
        "NO logo, headline, offer, or graphic marketing text burned into the image (a plain photo, a headshot, or a "
        "raw screenshot that looks like an organic post), then the ad's primary_text copy is doing the selling and IS "
        "the hook. Classify the hook from that primary_text (for example a curiosity-gap line, a long-form "
        "founder/testimonial story, or a native callout) and note in hook_type_reason that the copy carried it. For "
        "any static that DOES carry its own on-image headline or overlay, use that and treat primary_text as secondary. "
        "Never infer a VIDEO hook from caption or record text alone.\n"
        "Identify the MOST SPECIFIC format the evidence supports, and the MOST SPECIFIC message_frame. The catalog "
        "has many precise formats and angles; do NOT collapse a creative into a broad default like yapper or "
        "faceless-demo when a more specific catalog entry fits its distinctive signals (for example an AI-generated "
        "presenter is ai-avatar-presenter, not yapper; photoreal AI footage is ai-cinematic-broll; animated UI or "
        "diagrams are ai-motion-graphics). Read the disambiguation notes and choose the narrowest correct label. "
        "Only fall back to a broad format, or to insufficient-evidence, when no specific catalog entry genuinely matches.\n"
        "The catalog includes us-vs-them as a non-canonical visual signal and as a message frame: you may use it as "
        "message_frame, but primary_format must be a canonical scoreable format or insufficient-evidence.\n"
        f"Kind: {kind}\n"
        f"Attached evidence roles: {json.dumps(evidence_roles, ensure_ascii=True)}\n"
        f"Observed opening_line: {json.dumps(str(record.get('opening_line') or ''), ensure_ascii=True)}\n"
        f"Static creative OCR text (secondary to attached pixels): {json.dumps(str(record.get('static_ocr_text') or ''), ensure_ascii=True)}\n"
        f"Ad post copy (primary_text/headline) - the hook only for a zero-design native static, otherwise secondary: {json.dumps({'headline': record.get('headline', ''), 'primary_text': record.get('primary_text', '')}, ensure_ascii=True)}\n"
        f"Record text and metadata: {json.dumps(record, ensure_ascii=True, sort_keys=True)[:6000]}\n"
        f"Catalog definitions and visual signals: {vision_classifier_prompt_payload()}"
    )


def _post_json(url, headers, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise ClassificationError(f"provider request failed: {error}") from error


def _response_content(body):
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ClassificationError("provider response did not contain a chat completion") from error
    if not isinstance(content, str):
        raise ClassificationError("provider response content must be a JSON string")
    return content


def _validated_vision_result(
    content, evidence_refs, provider, configured_model, evidence_roles, opening_line="", display_format="", static_ocr_text="",
    visual_evidence_scope="",
):
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as error:
        raise ClassificationError("provider response was not strict JSON") from error
    if not isinstance(parsed, dict) or set(parsed) != set(_CLASSIFICATION_SCHEMA["required"]):
        raise ClassificationError("provider response did not match the required classification schema")

    primary_format = parsed["primary_format"]
    if primary_format not in SCOREABLE_FORMATS and primary_format != "insufficient-evidence":
        raise ClassificationError(f"provider returned non-canonical primary format: {primary_format!r}")
    message_frame = parsed["message_frame"]
    if message_frame not in ALL_MESSAGE_FRAMES:
        raise ClassificationError(f"provider returned unknown message frame: {message_frame!r}")
    hook_type = parsed["primary_hook_type"]
    if hook_type not in ALL_HOOK_TYPES:
        raise ClassificationError(f"provider returned unknown hook type: {hook_type!r}")
    # An unwatched video (a real video URL we could not fetch frames for) must obey the strict
    # video hook rule even when its display_format is DCO: never read a hook off a single mid-video
    # card still. A still-only static (image card, no video) takes the static path below.
    is_video = str(display_format or "").upper() == "VIDEO" or visual_evidence_scope == "unwatched"
    if is_video:
        has_hook_evidence = "video-frame" in evidence_roles or "opening-frame" in evidence_roles or bool(opening_line)
    else:
        has_hook_evidence = (
            "video-frame" in evidence_roles or "opening-frame" in evidence_roles or "creative" in evidence_roles
            or bool(str(static_ocr_text or "").strip()) or bool(opening_line)
        )
    if not has_hook_evidence:
        hook_type = "hook-unknown"
    mechanics = parsed["mechanics"]
    if not isinstance(mechanics, list):
        raise ClassificationError("provider mechanics must be a list")

    mechanic_labels = []
    mechanic_confidences = {}
    mechanic_reasons = {}
    for mechanic in mechanics:
        if not isinstance(mechanic, dict) or set(mechanic) != {"label", "confidence", "reason"}:
            raise ClassificationError("provider mechanic did not match the required schema")
        label = mechanic["label"]
        if label not in ALL_MECHANICS or label in mechanic_labels:
            raise ClassificationError(f"provider returned invalid mechanic: {label!r}")
        mechanic_labels.append(label)
        mechanic_confidences[label] = _confidence(mechanic["confidence"], f"mechanic {label}")
        mechanic_reasons[label] = _reason(mechanic["reason"], f"mechanic {label}")

    if primary_format == "insufficient-evidence" and mechanic_labels:
        # The model returned no scoreable format but still listed mechanics. The format is the
        # authority: drop the contradictory mechanics rather than aborting the whole run.
        mechanic_labels = []
        mechanic_confidences = {}
        mechanic_reasons = {}
    if "video-frame" not in evidence_roles and "opening-frame" not in evidence_roles and primary_format in VIDEO_FORMATS:
        return {
            **_insufficient_visual_result(
                f"{primary_format} is a video format but the creative was not watched "
                f"(no video-frame evidence); quarantined from the format landscape.",
                provider=provider,
                model=configured_model,
            ),
            "classification_provenance": {
                "mode": "media-grounded",
                "catalog_version": CATALOG_VERSION,
                "cache_hit": False,
                "degraded": False,
                "evidence_scope": "still-only",
                "quarantined": True,
                "quarantine_reason": f"unwatched:{primary_format}",
            },
        }
    return {
        "format": primary_format,
        "format_confidence": _confidence(parsed["format_confidence"], "format"),
        "classification_reason": _reason(parsed["format_reason"], "format"),
        "message_frame": message_frame,
        "message_frame_confidence": _confidence(parsed["message_frame_confidence"], "message frame"),
        "message_frame_reason": _reason(parsed["message_frame_reason"], "message frame"),
        "hook_type": hook_type,
        "hook_type_confidence": _confidence(parsed["hook_type_confidence"], "hook type"),
        "hook_type_reason": _reason(parsed["hook_type_reason"], "hook type"),
        "mechanics": mechanic_labels,
        "mechanics_confidences": mechanic_confidences,
        "mechanics_reasons": mechanic_reasons,
        "evidence_refs": evidence_refs,
        "classification_provider": provider,
        "classification_model": configured_model,
        "classification_provenance": {
            "mode": "media-grounded",
            "catalog_version": CATALOG_VERSION,
            "cache_hit": False,
            "degraded": False,
            "evidence_scope": "full-motion" if {"video-frame", "opening-frame"}.intersection(evidence_roles) else "still-only",
        },
    }


def _confidence(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ClassificationError(f"{field} confidence must be a number from 0 to 1")
    return float(value)


def _reason(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ClassificationError(f"{field} reason must be a non-empty string")
    return value.strip()


def _evidence_ref(entry):
    return {
        "role": entry["role"],
        "source_record_id": entry["source_record_id"],
        "sha256": entry["sha256"],
        "media_type": entry["media_type"],
    }


def _insufficient_visual_result(reason, *, provider, model):
    return {
        "format": "insufficient-evidence",
        "format_confidence": 0.0,
        "classification_reason": reason,
        "message_frame": "insufficient-evidence",
        "message_frame_confidence": 0.0,
        "message_frame_reason": reason,
        "hook_type": "hook-unknown",
        "hook_type_confidence": 0.0,
        "hook_type_reason": reason,
        "mechanics": [],
        "mechanics_confidences": {},
        "mechanics_reasons": {},
        "evidence_refs": [],
        "classification_provider": provider,
        "classification_model": model,
        "classification_provenance": {
            "mode": "media-grounded",
            "catalog_version": CATALOG_VERSION,
            "cache_hit": False,
            "degraded": True,
        },
    }
