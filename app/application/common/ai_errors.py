class OpenAICallError(Exception):
    """Base for all gateway-emitted errors."""


class AIRateLimitedError(OpenAICallError):
    """OpenAI returned 429 after SDK retries were exhausted."""


class AITimeoutError(OpenAICallError):
    """The HTTP call timed out (connect/read)."""


class AIUnavailableError(OpenAICallError):
    """Sustained downstream failure: connection error, 5xx after retries,
    or circuit breaker is OPEN."""


class AIInvalidRequestError(OpenAICallError):
    """Client-side error from OpenAI (400/404/422): malformed request, model
    not found, content policy violation. Not retried by SDK and not soft-failed
    automatically — adapters decide."""
