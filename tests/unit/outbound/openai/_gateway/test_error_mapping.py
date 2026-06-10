import httpx
import openai
import pytest
from purgatory.domain.model import OpenedState

from app.application.common.ai_errors import (
    AIInvalidRequestError,
    AIRateLimitedError,
    AITimeoutError,
    AIUnavailableError,
    OpenAICallError,
)
from app.outbound.adapters.openai._gateway.error_mapping import (
    map_exception,
    outcome_label,
)


def _http_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://api.openai.com/v1/x"),
    )


def _api_status_error(cls: type[openai.APIStatusError], status_code: int) -> openai.APIStatusError:
    response = _http_response(status_code)
    body = {"error": {"message": "boom"}}
    return cls(message="boom", response=response, body=body)


@pytest.mark.parametrize(
    ("source_exc_factory", "expected_type", "expected_outcome"),
    [
        (lambda: OpenedState("openai"), AIUnavailableError, "unavailable"),
        (lambda: _api_status_error(openai.RateLimitError, 429), AIRateLimitedError, "rate_limited"),
        (
            lambda: openai.APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/x")),
            AITimeoutError,
            "timeout",
        ),
        (
            lambda: openai.APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/x")
            ),
            AIUnavailableError,
            "unavailable",
        ),
        (
            lambda: _api_status_error(openai.BadRequestError, 400),
            AIInvalidRequestError,
            "invalid_request",
        ),
        (
            lambda: _api_status_error(openai.NotFoundError, 404),
            AIInvalidRequestError,
            "invalid_request",
        ),
        (
            lambda: _api_status_error(openai.UnprocessableEntityError, 422),
            AIInvalidRequestError,
            "invalid_request",
        ),
        (
            lambda: _api_status_error(openai.InternalServerError, 500),
            AIUnavailableError,
            "unavailable",
        ),
    ],
)
def test_map_exception_translates_known_sdk_errors(
    source_exc_factory: object, expected_type: type[OpenAICallError], expected_outcome: str
) -> None:
    source = source_exc_factory()  # type: ignore[operator]
    translated = map_exception(source)
    assert isinstance(translated, expected_type)
    assert outcome_label(translated) == expected_outcome


def test_map_exception_falls_back_to_base_for_unknown() -> None:
    translated = map_exception(RuntimeError("unexpected"))
    assert isinstance(translated, OpenAICallError)
    assert not isinstance(
        translated,
        AIRateLimitedError | AITimeoutError | AIUnavailableError | AIInvalidRequestError,
    )
    assert outcome_label(translated) == "error"


def test_api_status_error_4xx_other_is_invalid_request() -> None:
    # 418 — generic 4xx not in our enumerated list
    exc = _api_status_error(openai.APIStatusError, 418)
    translated = map_exception(exc)
    assert isinstance(translated, AIInvalidRequestError)
