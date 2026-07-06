from app.application.insights.ports.ai_insight_client import InsightRequest, InsightResponse
from app.domain.value_objects.enums import Period

_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Honest degraded-mode preamble shown to the user when no LLM provider could
# generate the insight. Kept short; the structured summary follows.
_PREAMBLE = (
    "AI analysis is temporarily unavailable, so here is a direct summary of your "
    "financial data for this period."
)


def _period_label(request: InsightRequest) -> str:
    if request.period == Period.MONTHLY:
        return f"{_MONTH_NAMES[request.period_month]} {request.period_year}"
    return f"Week {request.period_month}, {request.period_year}"


class DeterministicInsightClient:
    """Vendor-free degraded-mode :class:`AIInsightClient`.

    Formats the already-assembled deterministic context chunks (built by
    ``_process_insight_steps`` from SQL aggregations — same data the LLM would
    have analysed) into a templated insight. Makes NO external call, so it cannot
    fail on network / quota / breaker — it is the terminal link in the insight
    failover chain and always returns a usable insight. Reports 0 tokens (no LLM).
    """

    async def generate(self, request: InsightRequest) -> InsightResponse:
        summary_chunks = [c for c in request.chunks if c.chunk_type == "monthly_summary"]
        shift_chunks = [c for c in request.chunks if c.chunk_type == "behavioral_shift"]

        body_parts: list[str] = [_PREAMBLE]
        body_parts.extend(c.content for c in summary_chunks)
        body_parts.extend(c.content for c in shift_chunks)
        if not summary_chunks and not shift_chunks:
            body_parts.append("No detailed breakdown is available for this period.")

        return InsightResponse(
            title=f"Your {_period_label(request)} summary",
            description="\n\n".join(body_parts),
            # A detected behavioral shift is worth surfacing slightly higher; the
            # plain summary stays neutral. No LLM judgement is available here.
            impact_score=6 if shift_chunks else 5,
            prompt_tokens=0,
            completion_tokens=0,
        )
