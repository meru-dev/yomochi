import structlog

from app.application.common.ai_errors import (
    AIInvalidRequestError,
    AIRateLimitedError,
    AITimeoutError,
    AIUnavailableError,
    OpenAICallError,
)
from app.application.insights.ports.ai_insight_client import (
    AIInsightClient,
    InsightRequest,
    InsightResponse,
)
from app.outbound.observability.prometheus import insight_fallback_total

logger = structlog.get_logger(__name__)


def _reason(exc: OpenAICallError) -> str:
    """Bounded Prometheus `reason` label for a failed primary call."""
    if isinstance(exc, AIRateLimitedError):
        return "rate_limited"
    if isinstance(exc, AITimeoutError):
        return "timeout"
    if isinstance(exc, AIUnavailableError):  # incl. circuit-breaker OPEN
        return "unavailable"
    if isinstance(exc, AIInvalidRequestError):
        return "invalid_request"
    return "error"


class FallbackAIInsightClient:
    """Compose a primary :class:`AIInsightClient` with a fallback.

    Calls ``primary``; on any gateway-translated failure (``OpenAICallError`` and
    subclasses — rate-limit, timeout, 5xx, connection error, or circuit-breaker
    OPEN) it records a metric + warning and delegates to ``fallback`` so insight
    generation degrades instead of dying (no more whole-fleet outage when the
    primary provider is down).

    Only ``OpenAICallError`` is intercepted: an unexpected non-gateway error
    (e.g. a malformed structured-output response) still propagates so it lands in
    the DLQ and stays visible rather than being silently masked by degraded mode.
    """

    def __init__(self, primary: AIInsightClient, fallback: AIInsightClient) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(self, request: InsightRequest) -> InsightResponse:
        try:
            return await self._primary.generate(request)
        except OpenAICallError as exc:
            reason = _reason(exc)
            insight_fallback_total.labels(reason=reason).inc()
            logger.warning(
                "insight_primary_failed_using_fallback",
                reason=reason,
                error=str(exc),
            )
            return await self._fallback.generate(request)
