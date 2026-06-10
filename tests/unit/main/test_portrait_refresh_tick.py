from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.value_objects.ids import UserId
from app.main.portrait import refresh_tick as tick

pytestmark = pytest.mark.asyncio


def _session_factory_mock() -> MagicMock:
    """Build a session_factory whose `.begin()` yields a fresh mock session."""
    factory = MagicMock()

    def _begin() -> AsyncMock:
        cm = AsyncMock()
        cm.__aenter__.return_value = MagicMock(name="session")
        cm.__aexit__.return_value = None
        return cm

    factory.begin.side_effect = _begin
    return factory


async def test_refresh_one_portrait_user_opens_dedicated_tx() -> None:
    """Each call to refresh_one_portrait_user MUST open its own TX scope."""
    factory = _session_factory_mock()
    embedder = AsyncMock()
    user_id = UserId(uuid.uuid4())

    with patch.object(tick, "PortraitPipeline") as pipeline_cls:
        pipeline_instance = MagicMock()
        pipeline_instance.refresh = AsyncMock()
        pipeline_cls.return_value = pipeline_instance

        await tick.refresh_one_portrait_user(factory, embedder, user_id)

    factory.begin.assert_called_once()
    pipeline_instance.refresh.assert_awaited_once_with(user_id)


async def test_refresh_one_portrait_user_propagates_exception() -> None:
    """On pipeline failure: the exception bubbles up so the loop can re-mark dirty.

    The session_factory's `__aexit__` will roll back; we just assert the
    exception is re-raised (and not silently swallowed).
    """
    factory = _session_factory_mock()
    embedder = AsyncMock()
    user_id = UserId(uuid.uuid4())

    with patch.object(tick, "PortraitPipeline") as pipeline_cls:
        pipeline_instance = MagicMock()
        pipeline_instance.refresh = AsyncMock(side_effect=RuntimeError("boom"))
        pipeline_cls.return_value = pipeline_instance

        with pytest.raises(RuntimeError, match="boom"):
            await tick.refresh_one_portrait_user(factory, embedder, user_id)


async def test_pop_dirty_batch_uses_session_scope() -> None:
    factory = _session_factory_mock()

    with patch.object(tick, "SqlaPortraitQueue") as queue_cls:
        queue = MagicMock()
        queue.pop_dirty = AsyncMock(return_value=[UserId(uuid.uuid4())])
        queue_cls.return_value = queue

        result = await tick.pop_dirty_batch(factory, batch_size=10)

    assert len(result) == 1
    queue.pop_dirty.assert_awaited_once_with(limit=10)
    factory.begin.assert_called_once()


async def test_requeue_dirty_swallows_inner_errors() -> None:
    """`requeue_dirty` is best-effort: errors must not crash the loop."""
    factory = _session_factory_mock()
    user_id = UserId(uuid.uuid4())

    with patch.object(tick, "SqlaPortraitQueue") as queue_cls:
        queue = MagicMock()
        queue.mark_dirty = AsyncMock(side_effect=RuntimeError("db is sad"))
        queue_cls.return_value = queue

        # Must not raise.
        await tick.requeue_dirty(factory, user_id)

    queue.mark_dirty.assert_awaited_once_with(user_id)
