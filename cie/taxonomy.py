VIDEO_FORMATS = (
    "yapper",
    "faceless-demo",
    "pov-fps",
    "group-reaction",
    "tiktok-shop-hustle",
    "interview-podcast-street-mic",
    "employee-warehouse",
    "founder-bts",
    "gossip-grwm",
    "authority-figure",
    "narrative-vlog-ditl",
    "de-influencing",
    "realistic-unboxing",
    "vsl",
    "wall-of-text",
    "desire-metaphor-short",
    "split-screen-sludge",
    "micro-loop",
    "ai-vo-broll",
    "ai-song",
    "asmr-audio-only",
    "voice-note-mimic",
    "retention-edit-technique",
    "ai-avatar-presenter",
    "ai-cinematic-broll",
    "ai-motion-graphics",
    "ai-animation",
    "partnership-native-mimic",
)

STATIC_FORMATS = (
    "text-only-founders-letter",
    "native-photo-long-copy",
    "post-it-note",
    "ui-mimic",
    "tweet-reddit-ui",
    "advertorial",
    "notification-ui",
    "infographic-proof",
    "grid-static",
    "testimonial-screenshot",
    "timeline-proof",
    "first-frame-static",
    "thermal-vision",
    "diagram-puzzle",
    "flat-lay-fit-test",
    "spot-the-difference",
    "circle-arrow-explainer",
    "quadrant-matrix",
    "chart-breakout",
    "carousel",
    "us-vs-them",
)

UNSCORED_FORMATS = (
    "insufficient-evidence",
)

ALL_FORMATS = frozenset(VIDEO_FORMATS + STATIC_FORMATS + UNSCORED_FORMATS)
SCOREABLE_FORMATS = frozenset(VIDEO_FORMATS + STATIC_FORMATS)

MESSAGE_FRAMES = (
    "us-vs-them",
    "old-way-new-way",
    "hidden-cost",
    "before-after",
    "mistake-to-avoid",
    "myth-bust",
    "contrarian-take",
    "proof-stack",
    "comparison",
    "social-proof",
    "authority-education",
    "self-diagnosis",
    "failed-attempts",
    "villain-callout",
    "identity-belonging",
    "risk-reversal",
    "urgency-scarcity",
    "feature-to-benefit",
    "how-it-works",
    "offer-led",
    "skeptical-expose",
    "reverse-psychology",
    "life-hack",
    "forbidden-secret",
    "ancestral-tradition",
    "skeptic-to-believer",
    "reasons-why",
    "avatar-callout",
    "cost-transparency",
    "challenge",
    "insufficient-evidence",
)

ALL_MESSAGE_FRAMES = frozenset(MESSAGE_FRAMES)

HOOK_TYPES = (
    "direct-callout", "pain-callout", "warning-shot", "us-vs-them", "curiosity-gap",
    "contrarian-snapback", "pov-mind-read", "shocking-stat", "before-after-tease",
    "listicle-promise", "authority-credential", "diagnostic-question", "in-media-res-panic",
    "hidden-feature-fakeout", "i-tried-x", "trend-hijack", "pattern-interrupt",
    "confession-receipts", "prediction-fortune-teller", "testimonial-social-proof",
)
ALL_HOOK_TYPES = frozenset(HOOK_TYPES + ("hook-unknown",))

MECHANICS = (
    "green-screen",
    "split-screen",
    "kinetic-captions",
    "loop",
    "story-poll-mimic",
    "carousel-reveal",
    "carousel-self-segmentation",
    "creator-handle",
    "stitch-bait",
)

ALL_MECHANICS = frozenset(MECHANICS)


class TaxonomyError(Exception):
    pass


def validate_format_tag(tag: str) -> bool:
    return tag in ALL_FORMATS


def validate_scoreable_format(tag: str) -> bool:
    return tag in SCOREABLE_FORMATS


def validate_message_frame(tag: str) -> bool:
    return tag in ALL_MESSAGE_FRAMES


def validate_mechanic_tag(tag: str) -> bool:
    return tag in ALL_MECHANICS


def validate_hook_type(tag: str) -> bool:
    return tag in ALL_HOOK_TYPES


def tally_formats(tagged_items: list) -> dict:
    tally = {}
    for item in tagged_items:
        fmt = item.get("format")
        if not validate_format_tag(fmt):
            raise TaxonomyError(f"unknown format tag: {fmt!r}")
        tally[fmt] = tally.get(fmt, 0) + 1
    return tally


def tally_mechanics(tagged_items: list) -> dict:
    tally = {}
    for item in tagged_items:
        mechanics = item.get("mechanics") or []
        if not isinstance(mechanics, list):
            raise TaxonomyError(f"mechanics must be a list: {mechanics!r}")
        for tag in mechanics:
            if not validate_mechanic_tag(tag):
                raise TaxonomyError(f"unknown mechanic tag: {tag!r}")
            tally[tag] = tally.get(tag, 0) + 1
    return tally


def tally_message_frames(tagged_items: list) -> dict:
    tally = {}
    for item in tagged_items:
        frame = item.get("message_frame")
        if frame in (None, ""):
            continue
        if not validate_message_frame(frame):
            raise TaxonomyError(f"unknown message frame: {frame!r}")
        tally[frame] = tally.get(frame, 0) + 1
    return tally


def tally_hook_types(tagged_items: list) -> dict:
    tally = {}
    for item in tagged_items:
        hook = item.get("hook_type")
        if hook in (None, "", "hook-unknown"):
            continue
        if not validate_hook_type(hook):
            raise TaxonomyError(f"unknown hook type: {hook!r}")
        tally[hook] = tally.get(hook, 0) + 1
    return tally
