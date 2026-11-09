"""Where a winner's hook comes from: what the viewer hears, sees on screen, or reads in the caption.

Priority is spoken > onscreen > copy. Every ad in ads.raw.json carries:

- `copy_hook`: the headline, else the first sentence of the post copy (always present).
- `spoken_hook`: a source-supplied spoken hook, else the first sentence of StealAds'
  `spoken_opener` (its `hook.spoken`, the first ~5 s of speech), else of `transcript`.
  The first candidate that reads clean wins; `spoken_hook_source` says which one
  ("stealads", "scrapecreators", "openrouter:<model>", or "source").
- `onscreen_hook`: the first line of `onscreen_text` (text burned into the creative).
- `hook_source`: the highest-priority source that is non-empty.
- `spoken_hook_rejected`: why the transcript opening was not used (garbled speech-to-text),
  else None. A rejected spoken hook falls back to on-screen, then caption.

`transcript` and `onscreen_text` keep the full source text, so gate A3 can check a hook
verbatim against the source it claims.
"""

from __future__ import annotations

import re
from typing import Any

HOOK_SOURCES = ("spoken", "onscreen", "copy")
# Small tags the board prints next to a hook.
HOOK_TAGS = {"spoken": "said", "onscreen": "on screen", "copy": "caption"}

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")

# A transcript opening the viewer can't have heard as written: speech-to-text dropped or
# misheard words. Such a hook is not quoted; the ad falls back to on-screen, then caption.
_ASR_TAG = re.compile(
    r"\[(?:music|inaudible|applause|laughter|silence|noise|unintelligible)[^\]]*\]"
    r"|\((?:inaudible|unintelligible|music)\)|♪|\ufffd",
    re.IGNORECASE,
)
_STUTTER = re.compile(r"\b([a-z']+)\s+\1\b", re.IGNORECASE)
# A subordinator straight into a verb has lost its subject ("because isn't just like").
_NO_SUBJECT = re.compile(
    r"\b(?:because|if|when|since|although|unless|whereas)\s+"
    r"(?:is|isn't|are|aren't|was|wasn't|were|weren't|does|doesn't|do|don't|did|didn't)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
CONFIDENCE_KEYS = ("transcript_confidence", "asr_confidence", "confidence")
MIN_CONFIDENCE = 0.6


def garbled_reason(hook: str | None, confidence: Any = None) -> str | None:
    """Why a spoken hook reads as a bad transcription, or None when it reads clean."""
    text = str(hook or "").strip()
    if not text:
        return None
    try:
        if confidence is not None and float(confidence) < MIN_CONFIDENCE:
            return f"transcript confidence {float(confidence):g} < {MIN_CONFIDENCE:g}"
    except (TypeError, ValueError):
        pass
    words = _WORD.findall(text)
    checks = (
        (_ASR_TAG.search(text), "speech-to-text tag"),
        (not words, "no words"),
        (text[0].islower(), "starts mid-sentence"),
        (_STUTTER.search(text), "repeated word"),
        (_NO_SUBJECT.search(text), "missing subject (words dropped)"),
    )
    return next((why for hit, why in checks if hit), None)


def first_sentence(text: str | None, limit: int = 120) -> str:
    """First sentence of free text (a transcript), verbatim, capped at `limit` chars."""
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if not flat:
        return ""
    line = _SENTENCE_END.split(flat, 1)[0]
    if len(line) > limit:
        line = line[:limit].rsplit(" ", 1)[0] + "…"
    return line


def first_line(body: str | None, limit: int = 80) -> str:
    """Verbatim opening of the ad copy, for rows whose headline is null."""
    line = next((ln.strip() for ln in (body or "").splitlines() if ln.strip()), "")
    for end in (". ", "? ", "! "):
        if end in line:
            line = line.split(end, 1)[0] + end.strip()
            break
    if len(line) > limit:
        line = line[:limit].rsplit(" ", 1)[0] + "…"
    return line


def _spoken_candidates(ad: dict[str, Any]) -> list[tuple[str, str]]:
    """(hook, source) in priority order: explicit, StealAds opener, transcript."""
    out = [
        (str(ad.get("spoken_hook") or "").strip(), ad.get("spoken_hook_source") or "source"),
        (first_sentence(ad.get("spoken_opener")), "stealads"),
        (first_sentence(ad.get("transcript")), ad.get("transcript_source") or "transcript"),
    ]
    return [(text, src) for text, src in out if text]


def resolve_hooks(ad: dict[str, Any]) -> dict[str, Any]:
    """Fill copy_hook / spoken_hook / onscreen_hook / hook_source on a mapped ad (in place)."""
    ad["copy_hook"] = str(ad.get("headline") or "").strip() or first_line(ad.get("body"))
    confidence = next((ad[k] for k in CONFIDENCE_KEYS if ad.get(k) is not None), None)
    spoken, spoken_src, rejected = "", None, None
    for text, src in _spoken_candidates(ad):
        why = garbled_reason(text, confidence)
        if not why:
            spoken, spoken_src, rejected = text, src, None
            break
        rejected = rejected or why
    ad["spoken_hook_rejected"] = rejected
    ad["spoken_hook_source"] = spoken_src
    onscreen = str(ad.get("onscreen_hook") or "").strip() or first_line(ad.get("onscreen_text"))
    ad["spoken_hook"] = spoken or None
    ad["onscreen_hook"] = onscreen or None
    ad["hook_source"] = "spoken" if spoken else "onscreen" if onscreen else "copy"
    return ad


def best_hook(ad: dict[str, Any]) -> tuple[str, str]:
    """(hook_text, hook_source) for an ad, by priority."""
    source = ad.get("hook_source") or "copy"
    text = ad.get(f"{source}_hook") or ad.get("copy_hook") or ""
    if not text:
        text = str(ad.get("headline") or "") or first_line(ad.get("body"))
    return text, source


def source_text(ad: dict[str, Any], source: str) -> str:
    """The text a hook from `source` must appear in verbatim (gate A3).

    An on-screen hook is checked against the stored `onscreen_hook` (the headline or biggest
    text the agent recorded), falling back to `onscreen_text` when no hook was stored.
    """
    if source == "onscreen" and ad.get("onscreen_hook"):
        return str(ad["onscreen_hook"])
    return evidence_text(ad, source)


def evidence_text(ad: dict[str, Any], source: str) -> str:
    """All the text from `source` an offer quote may come from (gate A3)."""
    if source == "spoken":
        parts = (ad.get("transcript"), ad.get("spoken_opener"), ad.get("spoken_hook"))
    elif source == "onscreen":
        parts = (ad.get("onscreen_text"), ad.get("onscreen_hook"))
    else:
        parts = (ad.get("headline"), ad.get("body"), ad.get("cta"))
    return " ".join(str(p or "") for p in parts)


def available_sources(ad: dict[str, Any]) -> list[str]:
    out = []
    heard = ad.get("transcript") or ad.get("spoken_opener")
    if ad.get("spoken_hook") or (heard and not ad.get("spoken_hook_rejected")):
        out.append("spoken")
    if ad.get("onscreen_hook") or ad.get("onscreen_text"):
        out.append("onscreen")
    out.append("copy")
    return out
