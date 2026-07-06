import openai
from purgatory.domain.model import OpenedState

from app.application.common.ai_errors import (
    AIInvalidRequestError,
    AIRateLimitedError,
    AITimeoutError,
    AIUnavailableError,
    OpenAICallError,
)


def map_exception(exc: BaseException) -> OpenAICallError:
    """Translate any SDK or breaker exception to our domain type.

    The caller is expected to wrap the result with `raise ... from exc` so
    the original cause is preserved in tracebacks.
    """
    if isinstance(exc, OpenedState):
        return AIUnavailableError("circuit breaker is open")
    if isinstance(exc, openai.RateLimitError):
        return AIRateLimitedError(str(exc))
    if isinstance(exc, openai.APITimeoutError):
        return AITimeoutError(str(exc))
    if isinstance(exc, openai.APIConnectionError):
        return AIUnavailableError(f"connection error: {exc}")
    if isinstance(
        exc,
        openai.BadRequestError | openai.NotFoundError | openai.UnprocessableEntityError,
    ):
        return AIInvalidRequestError(str(exc))
    if isinstance(exc, openai.APIStatusError):
        # 5xx after SDK retries are exhausted, or other 4xx we didn't enumerate
        if exc.status_code >= 500:
            return AIUnavailableError(f"server error {exc.status_code}: {exc}")
        return AIInvalidRequestError(f"status {exc.status_code}: {exc}")
    return OpenAICallError(f"unexpected error: {type(exc).__name__}: {exc}")


def outcome_label(exc: OpenAICallError) -> str:
    if isinstance(exc, AIRateLimitedError):
        return "rate_limited"
    if isinstance(exc, AITimeoutError):
        return "timeout"
    if isinstance(exc, AIUnavailableError):
        return "unavailable"
    if isinstance(exc, AIInvalidRequestError):
        return "invalid_request"
    return "error"
