import uuid

import pytest

from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightResult,
)
from app.domain.value_objects.enums import ContextQuality
from app.inbound.messaging.insight_consumer import handle_insight_event

pytestmark = pytest.mark.asyncio


class _FakeMetrics:
    def __init__(self) -> None:
        self.skips: list[str] = []
        self.dlqs: list[str] = []
        self.insights: list[tuple[str, float]] = []

    def consumer_idempotency_skip(self, topic: str) -> None:
        self.skips.append(topic)

    def consumer_dlq_event(self, topic: str) -> None:
        self.dlqs.append(topic)

    def insight_generation_observed(self, context_quality: str, seconds: float) -> None:
        self.insights.append((context_quality, seconds))


class _FakeStore:
    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._failures: dict[str, int] = {}

    async def is_processed(self, event_id: str) -> bool:
        return event_id in self._processed

    async def mark_processed(self, event_id: str, ttl_seconds: int) -> None:
        self._processed.add(event_id)

    async def increment_failures(self, event_id: str) -> int:
        self._failures[event_id] = self._failures.get(event_id, 0) + 1
        return self._failures[event_id]


class _FakeDlq:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


class _SucceedingProcessInsight:
    async def __call__(self, cmd: ProcessInsightCommand) -> ProcessInsightResult:
        return ProcessInsightResult(context_quality=ContextQuality.FULL, elapsed_seconds=0.1)


class _RaisingProcessInsight:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __call__(self, cmd: ProcessInsightCommand) -> ProcessInsightResult:
        raise self._exc


def _body(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": "InsightRequested",
        "payload": {
            "insight_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
        },
    }


async def test_skips_duplicate_event() -> None:
    store = _FakeStore()
    event_id = str(uuid.uuid4())
    await store.mark_processed(event_id, ttl_seconds=86400)

    metrics = _FakeMetrics()
    await handle_insight_event(
        _body(event_id),
        store=store,
        dlq_publisher=_FakeDlq(),
        process_insight=_SucceedingProcessInsight(),
        metrics=metrics,
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert metrics.skips == ["yomochi.insights.v1"]


async def test_marks_processed_on_success() -> None:
    store = _FakeStore()
    event_id = str(uuid.uuid4())

    await handle_insight_event(
        _body(event_id),
        store=store,
        dlq_publisher=_FakeDlq(),
        process_insight=_SucceedingProcessInsight(),
        metrics=_FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert event_id in store._processed


async def test_records_insight_metric_on_success() -> None:
    store = _FakeStore()
    metrics = _FakeMetrics()

    await handle_insight_event(
        _body(str(uuid.uuid4())),
        store=store,
        dlq_publisher=_FakeDlq(),
        process_insight=_SucceedingProcessInsight(),
        metrics=metrics,
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert len(metrics.insights) == 1
    assert metrics.insights[0][0] == "full"


async def test_retries_before_dlq() -> None:
    store = _FakeStore()
    dlq = _FakeDlq()
    event_id = str(uuid.uuid4())
    body = _body(event_id)

    for i in range(1, 4):
        if i < 3:
            with pytest.raises(RuntimeError):
                await handle_insight_event(
                    body,
                    store=store,
                    dlq_publisher=dlq,
                    process_insight=_RaisingProcessInsight(RuntimeError("boom")),
                    metrics=_FakeMetrics(),
                    dlq_topic="dlq.insights",
                    max_retries=3,
                    idempotency_ttl=86400,
                )
        else:
            await handle_insight_event(
                body,
                store=store,
                dlq_publisher=dlq,
                process_insight=_RaisingProcessInsight(RuntimeError("boom")),
                metrics=_FakeMetrics(),
                dlq_topic="dlq.insights",
                max_retries=3,
                idempotency_ttl=86400,
            )

    assert len(dlq.published) == 1
    assert dlq.published[0][1] == "dlq.insights"
    assert event_id in store._processed


async def test_malformed_payload_missing_insight_id_goes_through_failure_path() -> None:
    """InsightRequested with empty insight_id must raise → increment_failures, NOT mark_processed."""
    store = _FakeStore()
    dlq = _FakeDlq()
    event_id = str(uuid.uuid4())
    body = {
        "event_id": event_id,
        "event_type": "InsightRequested",
        "payload": {
            # insight_id intentionally absent / empty
            "user_id": str(uuid.uuid4()),
        },
    }

    with pytest.raises(ValueError, match="insight_event_malformed_payload"):
        await handle_insight_event(
            body,
            store=store,
            dlq_publisher=dlq,
            process_insight=_SucceedingProcessInsight(),
            metrics=_FakeMetrics(),
            dlq_topic="dlq.insights",
            max_retries=3,
            idempotency_ttl=86400,
        )

    # failure counter bumped — event NOT silently buried as processed
    assert store._failures.get(event_id, 0) == 1
    assert event_id not in store._processed
    assert len(dlq.published) == 0


async def test_malformed_payload_missing_user_id_goes_through_failure_path() -> None:
    """InsightRequested with empty user_id must raise → increment_failures, NOT mark_processed."""
    store = _FakeStore()
    dlq = _FakeDlq()
    event_id = str(uuid.uuid4())
    body = {
        "event_id": event_id,
        "event_type": "InsightRequested",
        "payload": {
            "insight_id": str(uuid.uuid4()),
            # user_id intentionally absent / empty
        },
    }

    with pytest.raises(ValueError, match="insight_event_malformed_payload"):
        await handle_insight_event(
            body,
            store=store,
            dlq_publisher=dlq,
            process_insight=_SucceedingProcessInsight(),
            metrics=_FakeMetrics(),
            dlq_topic="dlq.insights",
            max_retries=3,
            idempotency_ttl=86400,
        )

    assert store._failures.get(event_id, 0) == 1
    assert event_id not in store._processed
    assert len(dlq.published) == 0


async def test_parks_in_dlq_and_marks_processed_at_max_retries() -> None:
    store = _FakeStore()
    dlq = _FakeDlq()
    event_id = str(uuid.uuid4())
    metrics = _FakeMetrics()

    # Exhaust retries immediately by pre-setting failure count to max-1
    store._failures[event_id] = 2

    await handle_insight_event(
        _body(event_id),
        store=store,
        dlq_publisher=dlq,
        process_insight=_RaisingProcessInsight(RuntimeError("terminal")),
        metrics=metrics,
        dlq_topic="dlq.insights",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert len(dlq.published) == 1
    assert "x_error" in dlq.published[0][0]
    assert event_id in store._processed
    assert metrics.dlqs == ["yomochi.insights.v1"]
