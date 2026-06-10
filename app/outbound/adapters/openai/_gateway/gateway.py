import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

import structlog
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI
from purgatory.service._async.circuitbreaker import AsyncCircuitBreaker

from app.outbound.adapters.openai._gateway.error_mapping import (
    map_exception,
    outcome_label,
)
from app.outbound.observability.prometheus import (
    openai_call_duration_seconds,
    openai_call_total,
    openai_circuit_state,
    openai_tokens_total,
)

logger = structlog.get_logger(__name__)

Endpoint = Literal["chat", "embeddings", "vision"]

T = TypeVar("T")

_STATE_MAP = {"closed": 0, "half-opened": 1, "opened": 2}


@dataclass(frozen=True)
class UsageInfo:
    """Final usage sentinel emitted by stream_call after the last chunk."""

    prompt_tokens: int
    completion_tokens: int


class OpenAIGateway:
    def __init__(
        self,
        client: AsyncOpenAI,
        limiter: AsyncLimiter,
        breakers: dict[str, AsyncCircuitBreaker],
        default_read_timeout_seconds: float,
    ) -> None:
        self._client = client
        self._limiter = limiter
        self._breakers = breakers
        self._default_timeout = default_read_timeout_seconds
        # Pre-build the scoped client for the default timeout to avoid cloning on every call.
        self._default_scoped_client = client.with_options(timeout=default_read_timeout_seconds)

    async def call(
        self,
        *,
        endpoint: Endpoint,
        fn: Callable[[AsyncOpenAI], Awaitable[T]],
        timeout: float | None = None,
    ) -> T:
        scoped_client = (
            self._client.with_options(timeout=timeout)
            if timeout is not None
            else self._default_scoped_client
        )
        breaker = self._breakers[endpoint]
        start = time.perf_counter()
        try:
            async with breaker, self._limiter:
                result = await fn(scoped_client)
        except BaseException as exc:
            translated = map_exception(exc)
            openai_call_total.labels(endpoint=endpoint, outcome=outcome_label(translated)).inc()
            self._record_state(breaker)
            raise translated from exc

        elapsed = time.perf_counter() - start
        openai_call_total.labels(endpoint=endpoint, outcome="success").inc()
        openai_call_duration_seconds.labels(endpoint=endpoint).observe(elapsed)
        self._record_state(breaker)
        return result

    async def stream_call(
        self,
        *,
        endpoint: Endpoint,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float | None = None,
    ) -> AsyncGenerator[str | UsageInfo]:
        """Yield text tokens from an OpenAI streaming chat completion.

        Yields string content chunks, then a final `UsageInfo` sentinel
        when the stream finishes successfully. Circuit breaker and rate
        limiter wrap the entire stream. Usage metrics are recorded after
        the last chunk (via stream_options). Client-disconnect
        (GeneratorExit) is not counted as a failure.
        """
        scoped_client = (
            self._client.with_options(timeout=timeout)
            if timeout is not None
            else self._default_scoped_client
        )
        breaker = self._breakers[endpoint]
        prompt_tokens = 0
        completion_tokens = 0
        success = False
        try:
            async with breaker, self._limiter:
                response = await scoped_client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                    if chunk.usage:
                        prompt_tokens = chunk.usage.prompt_tokens
                        completion_tokens = chunk.usage.completion_tokens
                success = True
        except GeneratorExit:
            raise
        except BaseException as exc:
            translated = map_exception(exc)
            openai_call_total.labels(endpoint=endpoint, outcome=outcome_label(translated)).inc()
            self._record_state(breaker)
            raise translated from exc
        if success:
            openai_call_total.labels(endpoint=endpoint, outcome="success").inc()
            openai_tokens_total.labels(endpoint=f"{endpoint}_stream", direction="prompt").inc(
                prompt_tokens
            )
            openai_tokens_total.labels(endpoint=f"{endpoint}_stream", direction="completion").inc(
                completion_tokens
            )
            self._record_state(breaker)
            yield UsageInfo(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    def _record_state(self, breaker: AsyncCircuitBreaker) -> None:
        openai_circuit_state.set(_STATE_MAP.get(breaker.context.state, 2))
