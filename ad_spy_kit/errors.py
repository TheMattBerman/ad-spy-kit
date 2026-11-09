"""Every user-facing failure in one place, each with the next step to take.

Agents and the CLI print `KitError.render()` verbatim, so the wording here is the wording
the user sees. Keep it factual: what is missing, why it matters, how to fix it.
"""

from __future__ import annotations

from dataclasses import dataclass


class KitError(Exception):
    """A failure the user can act on. `fix` is the one next step."""

    def __init__(self, message: str, *, fix: str = "", code: str = "kit_error") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.code = code

    def render(self) -> str:
        return f"{self.message}\n  → {self.fix}" if self.fix else self.message


class MissingKey(KitError):
    pass


class ExcludedBrand(KitError):
    pass


class SourceError(KitError):
    pass


def missing_scrapecreators_key() -> MissingKey:
    return MissingKey(
        "SCRAPECREATORS_API_KEY isn't set, so I can't check live ads.",
        fix=(
            "Two ways to fix this. StealAds (primary, early access): get access at "
            "https://stealads.ai, run `claude mcp add --transport http stealads "
            "https://mcp.stealads.ai/mcp`, then sign in at https://app.stealads.ai and "
            "connect with /mcp. Or a ScrapeCreators key: "
            "get one at https://scrapecreators.com and add SCRAPECREATORS_API_KEY=... to a "
            ".env file in the folder you run me from (or export it). "
            "Neither yet? `ad-spy-kit replay --sample foldbrook` shows a sample board for free."
        ),
        code="missing_scrapecreators_key",
    )


def scrapecreators_failed(status: int | None, detail: str = "") -> SourceError:
    """What a ScrapeCreators HTTP error means for the user, in plain words."""
    if status in (401, 403):
        return SourceError(
            f"ScrapeCreators turned down your API key (error {status}).",
            fix=(
                "Check SCRAPECREATORS_API_KEY in your .env for a typo, and your balance at "
                "https://scrapecreators.com. Nothing was spent."
            ),
            code="scrapecreators_key_rejected",
        )
    if status == 402:
        return SourceError(
            "Your ScrapeCreators account is out of credits (error 402).",
            fix="Top up at https://scrapecreators.com, then run it again. Nothing was spent.",
            code="scrapecreators_no_credits",
        )
    if status == 429:
        return SourceError(
            "ScrapeCreators says we're sending too many requests right now (error 429).",
            fix="Wait a minute and run it again.",
            code="scrapecreators_rate_limited",
        )
    where = f" (error {status})" if status else ""
    return SourceError(
        f"ScrapeCreators didn't answer properly{where}: {detail}".rstrip(": "),
        fix="Try again in a minute. If it keeps failing, check https://scrapecreators.com.",
        code="scrapecreators_error",
    )


@dataclass(frozen=True)
class LimitMessage:
    message: str
    fallback: str


# StealAds MCP error codes → what the user is told and what the kit does next.
# The orchestrator SKILL.md tells the agent to print these instead of the raw error.
STEALADS_LIMITS: dict[str, LimitMessage] = {
    "vendor_search_limit_exceeded": LimitMessage(
        "StealAds hit today's competitor-search limit on your plan.",
        "Try again after the daily reset, or check this brand with a ScrapeCreators key "
        "(SCRAPECREATORS_API_KEY).",
    ),
    "daily_import_limit_exceeded": LimitMessage(
        "StealAds hit today's ad-import cap, so some ads are missing.",
        "The board still renders from what came in, and says some ads are missing.",
    ),
    "generation_limit_exceeded": LimitMessage(
        "StealAds hit your plan's limit for making ads.",
        "You still get the written counter-ad briefs, and the board still renders.",
    ),
    "insufficient_credits": LimitMessage(
        "Your StealAds workspace is out of credits for this action.",
        "Top up at https://stealads.ai, or use a ScrapeCreators key. You still get the "
        "written counter-ad briefs.",
    ),
    "unauthorized": LimitMessage(
        "StealAds isn't connected in your agent, or the sign-in expired.",
        "Reconnect StealAds in your agent's connector settings, then run it again.",
    ),
    "competitor_not_found": LimitMessage(
        "StealAds couldn't match that brand to a Facebook page.",
        "Paste the brand's Ad Library page link (it has view_all_page_id= in it) or its "
        "page ID instead of the name.",
    ),
}


def explain_stealads_error(code: str, server_message: str | None = None) -> str:
    """Map a StealAds MCP error code to the line the user sees. Unknown codes pass through."""
    known = STEALADS_LIMITS.get((code or "").strip().lower())
    if known is None:
        detail = f" ({server_message})" if server_message else ""
        return (
            f"StealAds returned {code or 'an error'}{detail}.\n"
            "  → Try again, or use a ScrapeCreators key instead."
        )
    return f"{known.message}\n  → {known.fallback}"
