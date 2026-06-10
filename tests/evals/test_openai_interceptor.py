from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.evals.openai_interceptor import (
    InterceptorMode,
    MissingSnapshotError,
    OpenAIInterceptor,
)
from tests.evals.snapshot import SnapshotStore, snapshot_key

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(root=tmp_path, component="insights")


@pytest.fixture
def stored_record(store: SnapshotStore) -> str:
    """Pre-populate a snapshot for replay tests."""
    from tests.evals.snapshot import SnapshotRecord

    key = snapshot_key(prompt="hello", model="gpt-4o-mini", inputs={"x": 1})
    record = SnapshotRecord(
        key=key,
        prompt="hello",
        model="gpt-4o-mini",
        request_kwargs={"temperature": 0},
        response={"choices": [{"message": {"content": "world"}}]},
        tokens_prompt=10,
        tokens_completion=5,
        cost_usd=0.0001,
        captured_at=SnapshotStore.now_iso(),
    )
    store.save(record)
    return key


async def test_snapshot_mode_replays_existing(store: SnapshotStore, stored_record: str) -> None:
    interceptor = OpenAIInterceptor(store=store, mode=InterceptorMode.SNAPSHOT)
    record = await interceptor.intercept(
        prompt="hello",
        model="gpt-4o-mini",
        inputs={"x": 1},
        live_call=lambda: pytest.fail("live_call should not be invoked in snapshot mode"),
    )
    assert record.response == {"choices": [{"message": {"content": "world"}}]}


async def test_snapshot_mode_miss_raises(store: SnapshotStore) -> None:
    interceptor = OpenAIInterceptor(store=store, mode=InterceptorMode.SNAPSHOT)
    with pytest.raises(MissingSnapshotError):
        await interceptor.intercept(
            prompt="new",
            model="gpt-4o-mini",
            inputs={},
            live_call=lambda: pytest.fail("live_call should not be invoked in snapshot mode"),
        )


async def test_live_mode_calls_through_and_records(store: SnapshotStore) -> None:
    captured = []

    async def fake_live_call() -> dict[str, object]:
        captured.append("called")
        return {
            "response": {"choices": [{"message": {"content": "live"}}]},
            "tokens_prompt": 11,
            "tokens_completion": 7,
            "cost_usd": 0.0002,
            "request_kwargs": {"temperature": 0.1},
        }

    interceptor = OpenAIInterceptor(store=store, mode=InterceptorMode.LIVE_UPDATE)
    record = await interceptor.intercept(
        prompt="fresh",
        model="gpt-4o-mini",
        inputs={"y": 2},
        live_call=fake_live_call,
    )
    assert captured == ["called"]
    assert record.response == {"choices": [{"message": {"content": "live"}}]}
    key = snapshot_key(prompt="fresh", model="gpt-4o-mini", inputs={"y": 2})
    assert store.load(key) is not None
