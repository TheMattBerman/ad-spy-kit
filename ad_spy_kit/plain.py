"""Plain words for codes that reach a reader: ad formats, urgency, Black Friday tags.

Every format slug in cie/taxonomy.py has a name a founder would say out loud. A test keeps
this map complete, so a new slug can't print raw on a board.
"""

from __future__ import annotations

FORMAT_NAMES: dict[str, str] = {
    "yapper": "person talking to camera",
    "faceless-demo": "product demo, no face",
    "partnership-native-mimic": "made to look like a creator post",
    "testimonial-screenshot": "screenshot of a review",
    "native-photo-long-copy": "plain photo with a long caption",
    "carousel": "swipeable carousel",
    "us-vs-them": "us vs. them comparison",
    "de-influencing": '"don\'t buy that, buy this"',
    "micro-loop": "short looping clip",
    "voice-note-mimic": "made to look like a voice note",
    "first-frame-static": "video that opens on a still image",
    "diagram-puzzle": "diagram or puzzle",
    "text-only-founders-letter": "letter from the founder",
    "quadrant-matrix": "comparison grid",
    "interview-podcast-street-mic": "interview or street mic",
    "ai-cinematic-broll": "AI-made cinematic footage",
    "flat-lay-fit-test": "flat lay or try-on",
    "founder-bts": "founder behind the scenes",
    "chart-breakout": "chart",
    "spot-the-difference": "spot the difference",
    "insufficient-evidence": "not enough to tell",
    "gossip-grwm": "get ready with me chat",
    "ai-vo-broll": "AI voiceover over stock footage",
    "retention-edit-technique": "fast-cut edit",
    "vsl": "long sales video",
    "ai-avatar-presenter": "AI presenter",
    "split-screen-sludge": "split screen with a side video",
    "thermal-vision": "thermal camera view",
    "tiktok-shop-hustle": "TikTok Shop style pitch",
    "infographic-proof": "infographic",
    "ai-song": "AI-made song",
    "employee-warehouse": "staff or warehouse footage",
    "narrative-vlog-ditl": "day-in-the-life vlog",
    "circle-arrow-explainer": "circles-and-arrows explainer",
    "timeline-proof": "before and after timeline",
    "asmr-audio-only": "ASMR sound",
    "grid-static": "image grid",
    "post-it-note": "sticky note",
    "ai-animation": "AI animation",
    "desire-metaphor-short": "short visual metaphor",
    "tweet-reddit-ui": "made to look like a tweet or Reddit post",
    "authority-figure": "expert or doctor",
    "group-reaction": "group reaction",
    "advertorial": "article-style ad",
    "notification-ui": "made to look like a phone notification",
    "wall-of-text": "wall of text",
    "pov-fps": "point-of-view footage",
    "realistic-unboxing": "unboxing",
    "ai-motion-graphics": "AI motion graphics",
    "ui-mimic": "made to look like an app screen",
}

URGENCY_NAMES = {"countdown": "countdown", "date": "deadline", "stock": "limited stock"}

# Black Friday tags. Ads not tied to a sale get no tag at all.
BF_NAMES = {"bf_live": "Black Friday", "bf_teaser": "Black Friday teaser"}

VERDICT_NAMES = {"sat": "crowded", "dead": "worn out", "open": "open"}


def format_name(slug: str | None) -> str:
    return FORMAT_NAMES.get(str(slug or ""), str(slug or "").replace("-", " "))
