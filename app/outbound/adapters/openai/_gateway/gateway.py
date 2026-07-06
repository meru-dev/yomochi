import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

import structlog
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI, omit
from purgatory.service._async.circuitbreaker import AsyncCircuitBreaker

from app.application.common.ai_errors import AIRateLimitedError, OpenAICallError
from app.outbound.adapters.openai._gateway.error_mapping import (
    map_exception,
    outcome_label,
)
from app.outbound.observability.prometheus import (
    openai_cached_tokens_total,
    openai_call_duration_seconds,
    openai_call_total,
    openai_circuit_state,
    openai_limiter_rejected_total,
    openai_limiter_waiting,
    openai_tokens_total,
)

logger = structlog.get_logger(__name__)

# Per-endpoint-class rate-limit + circuit-breaker buckets.
Endpoint = Literal["chat", "vision", "parse"]

T = TypeVar("T")

_STATE_MAP = {"closed": 0, "half-opened": 1, "opened": 2}


def cached_tokens_from_usage(usage: Any) -> int:
    """Extract prompt-cache hit count from an OpenAI usage object.

    ``prompt_tokens_details.cached_tokens`` is the subset of ``prompt_tokens``
    served from OpenAI's automatic prompt cache. Both the details object and the
    field may be absent/None on older models or error paths; anything that is not
    a concrete int (incl. None) is treated as 0 cache hits.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details is not None else None
    return cached if isinstance(cached, int) else 0


@dataclass(frozen=True)
class UsageInfo:
    """Final usage sentinel emitted by stream_call after the last chunk."""

    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class ContentDelta:
    """An answer token streamed by stream_call_with_tools (finish_reason="stop")."""

    text: str


@dataclass(frozen=True)
class ToolCallsDelta:
    """Fully-assembled tool calls for one round (finish_reason="tool_calls").

    Emitted ONCE per round, after the streamed tool-call argument fragments have
    been concatenated per ``index`` into the same shape the non-streamed path
    builds: ``{id, type:"function", function:{name, arguments}}``.
    """

    tool_calls: list[dict[str, Any]]


class OpenAIGateway:
    def __init__(
        self,
        client: AsyncOpenAI,
        limiters: dict[str, AsyncLimiter],
        breakers: dict[str, AsyncCircuitBreaker],
        default_read_timeout_seconds: float,
        max_queue: int = 64,
    ) -> None:
        self._client = client
        self._limiters = limiters
        self._breakers = breakers
        self._default_timeout = default_read_timeout_seconds
        self._max_queue = max_queue
        # Live waiter count per endpoint, used to bound the limiter queue.
        self._waiting: dict[str, int] = dict.fromkeys(limiters, 0)
        # Pre-build the scoped client for the default timeout to avoid cloning on every call.
        self._default_scoped_client = client.with_options(timeout=default_read_timeout_seconds)

    @asynccontextmanager
    async def _acquire(self, endpoint: str) -> AsyncIterator[None]:
        """Acquire the endpoint's rate-limit token with a bounded waiter queue.

        Rejects fast (``AIRateLimitedError``) when too many callers are already
        queued for this bucket, instead of letting the AsyncLimiter queue grow
        unbounded. The token bucket itself is per endpoint class so a burst on one
        class (e.g. vision/parse) cannot starve another (e.g. interactive chat).
        """
        if self._waiting[endpoint] >= self._max_queue:
            openai_limiter_rejected_total.labels(endpoint=endpoint).inc()
            raise AIRateLimitedError(f"openai limiter queue full for endpoint {endpoint!r}")
        gauge = openai_limiter_waiting.labels(endpoint=endpoint)
        self._waiting[endpoint] += 1
        gauge.inc()
        try:
            await self._limiters[endpoint].acquire()
        finally:
            self._waiting[endpoint] -= 1
            gauge.dec()
        yield

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
            async with self._acquire(endpoint), breaker:
                result = await fn(scoped_client)
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            translated = exc if isinstance(exc, OpenAICallError) else map_exception(exc)
            openai_call_total.labels(endpoint=endpoint, outcome=outcome_label(translated)).inc()
            self._record_state(breaker)
            if translated is exc:
                raise
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
        prompt_cache_key: str | None = None,
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
        cached_tokens = 0
        success = False
        try:
            async with self._acquire(endpoint), breaker:
                response = await scoped_client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    prompt_cache_key=prompt_cache_key or omit,
                )
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                    if chunk.usage:
                        prompt_tokens = chunk.usage.prompt_tokens
                        completion_tokens = chunk.usage.completion_tokens
                        cached_tokens = cached_tokens_from_usage(chunk.usage)
                success = True
        except GeneratorExit:
            raise
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            translated = exc if isinstance(exc, OpenAICallError) else map_exception(exc)
            openai_call_total.labels(endpoint=endpoint, outcome=outcome_label(translated)).inc()
            self._record_state(breaker)
            if translated is exc:
                raise
            raise translated from exc
        if success:
            openai_call_total.labels(endpoint=endpoint, outcome="success").inc()
            self._record_stream_tokens(
                endpoint, model, prompt_tokens, completion_tokens, cached_tokens
            )
            self._record_state(breaker)
            yield UsageInfo(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    async def stream_call_with_tools(
        self,
        *,
        endpoint: Endpoint,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]],
        timeout: float | None = None,
        prompt_cache_key: str | None = None,
    ) -> AsyncGenerator[ContentDelta | ToolCallsDelta | UsageInfo]:
        """Stream a chat completion WITH tools enabled, as discriminated events.

        Same breaker + limiter + timeout + error-mapping + disconnect handling as
        ``stream_call``. Per chunk, ``delta.content`` is yielded as a
        ``ContentDelta`` (an answer token); ``delta.tool_calls`` fragments are
        concatenated per ``index`` and, when the model finishes requesting tools
        (``finish_reason == "tool_calls"``), emitted ONCE as a ``ToolCallsDelta``.
        A final ``UsageInfo`` sentinel is yielded after the last chunk on success.
        Usage metrics are recorded once per call (per round) like ``stream_call``.
        """
        scoped_client = (
            self._client.with_options(timeout=timeout)
            if timeout is not None
            else self._default_scoped_client
        )
        breaker = self._breakers[endpoint]
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        # Accumulate streamed tool-call fragments keyed by their delta `index`.
        # Each entry holds the (sticky) id/name plus the growing arguments string.
        fragments: dict[int, dict[str, str]] = {}
        success = False
        try:
            async with self._acquire(endpoint), breaker:
                response = await scoped_client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    prompt_cache_key=prompt_cache_key or omit,
                )
                async for chunk in response:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        delta = choice.delta
                        if delta.content:
                            yield ContentDelta(text=delta.content)
                        if delta.tool_calls:
                            _accumulate_tool_calls(fragments, delta.tool_calls)
                        if choice.finish_reason == "tool_calls":
                            yield ToolCallsDelta(tool_calls=_assemble_tool_calls(fragments))
                    if chunk.usage:
                        prompt_tokens = chunk.usage.prompt_tokens
                        completion_tokens = chunk.usage.completion_tokens
                        cached_tokens = cached_tokens_from_usage(chunk.usage)
                success = True
        except GeneratorExit:
            raise
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            translated = exc if isinstance(exc, OpenAICallError) else map_exception(exc)
            openai_call_total.labels(endpoint=endpoint, outcome=outcome_label(translated)).inc()
            self._record_state(breaker)
            if translated is exc:
                raise
            raise translated from exc
        if success:
            openai_call_total.labels(endpoint=endpoint, outcome="success").inc()
            self._record_stream_tokens(
                endpoint, model, prompt_tokens, completion_tokens, cached_tokens
            )
            self._record_state(breaker)
            yield UsageInfo(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    @staticmethod
    def _record_stream_tokens(
        endpoint: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
    ) -> None:
        stream_endpoint = f"{endpoint}_stream"
        openai_tokens_total.labels(endpoint=stream_endpoint, direction="prompt").inc(prompt_tokens)
        openai_tokens_total.labels(endpoint=stream_endpoint, direction="completion").inc(
            completion_tokens
        )
        if cached_tokens:
            openai_cached_tokens_total.labels(endpoint=stream_endpoint, model=model).inc(
                cached_tokens
            )

    def _record_state(self, breaker: AsyncCircuitBreaker) -> None:
        openai_circuit_state.set(_STATE_MAP.get(breaker.context.state, 2))


def _accumulate_tool_calls(fragments: dict[int, dict[str, str]], tool_calls: Any) -> None:
    """Merge a chunk's ChoiceDeltaToolCall fragments into ``fragments`` by index.

    ``id`` and ``function.name`` arrive once (on the first fragment for an index);
    ``function.arguments`` arrives as string pieces that must be concatenated.
    """
    for tc in tool_calls:
        slot = fragments.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
        if tc.id:
            slot["id"] = tc.id
        fn = tc.function
        if fn is not None:
            if fn.name:
                slot["name"] = fn.name
            if fn.arguments:
                slot["arguments"] += fn.arguments


def _assemble_tool_calls(fragments: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
    """Build the non-streamed tool-call shape, ordered by streamed ``index``."""
    return [
        {
            "id": slot["id"],
            "type": "function",
            "function": {"name": slot["name"], "arguments": slot["arguments"]},
        }
        for _index, slot in sorted(fragments.items())
    ]
