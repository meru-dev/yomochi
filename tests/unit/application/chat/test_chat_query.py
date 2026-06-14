# tests/unit/application/chat/test_chat_query.py
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.chat.ports.chat_ai_client import ChatRequest, ChatResponse
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.work_unit import ChatWorkUnit
from app.application.chat.use_cases.chat_query import (
    ChatQueryCommand,
    ChatQueryResult,
    ChatQueryUseCase,
)
from app.application.insights.ports.chunk_retriever import RetrievedChunk
from app.domain.value_objects.enums import ContextQuality
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.system.uuid7_id_generator import Uuid7ChatTurnIdGenerator


class FixedClock:
    """Clock that returns the same instant on every call.

    A frozen clock means the user and assistant turns share a created_at, so
    ordering must fall back to the monotone UUID7 ids — exactly the invariant
    the +1µs hack used to paper over.
    """

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def today(self):
        return self._instant.date()


class FakeChatWorkUnitFactory:
    """Hands out a UoW bundling the given retriever + store; counts opens."""

    def __init__(self, retriever, store) -> None:
        self._uow = ChatWorkUnit(chunk_retriever=retriever, history_store=store)
        self.opens = 0

    def __call__(self):
        self.opens += 1

        @asynccontextmanager
        async def _scope():
            yield self._uow

        return _scope()


_ID_GEN = Uuid7ChatTurnIdGenerator()

_UID = UserId(uuid.uuid4())
_EMBEDDING = [0.1] * 1536
_MONTHLY_CHUNK = RetrievedChunk(
    content="Food 30000 JPY",
    chunk_type="monthly_summary",
    period_label="Apr 2026",
    metadata={},
)
_SHIFT_CHUNK = RetrievedChunk(
    content="Spending spike",
    chunk_type="behavioral_shift",
    period_label="Apr 2026",
    metadata={},
)
_PORTRAIT_CHUNK = RetrievedChunk(
    content="Portrait data",
    chunk_type="user_portrait",
    period_label="portrait",
    metadata={},
)
_AI_RESPONSE = ChatResponse(
    answer="You spent 30000 JPY on food.", prompt_tokens=100, completion_tokens=50
)


def _make_uc(
    search_result=None,
    portrait=None,
    history=None,
):
    retriever = AsyncMock()
    retriever.search = AsyncMock(
        return_value=[_MONTHLY_CHUNK, _SHIFT_CHUNK] if search_result is None else search_result
    )
    retriever.get_portrait = AsyncMock(return_value=portrait)

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=_EMBEDDING)

    ai_client = AsyncMock()
    ai_client.chat = AsyncMock(return_value=_AI_RESPONSE)

    store = AsyncMock()
    store.last_n = AsyncMock(return_value=history or [])
    store.save_turns = AsyncMock()

    async def _append_pair(uid, user_turn, assistant_turn):
        return user_turn, assistant_turn

    store.append_turn_pair = AsyncMock(side_effect=_append_pair)

    budget = AsyncMock()
    budget.check = AsyncMock(return_value=None)
    budget.record = AsyncMock(return_value=None)

    uc = ChatQueryUseCase(
        work_unit_factory=FakeChatWorkUnitFactory(retriever, store),
        embedder=embedder,
        ai_client=ai_client,
        token_budget=budget,
        id_generator=_ID_GEN,
        clock=FixedClock(datetime(2026, 6, 12, tzinfo=UTC)),
    )
    return uc, retriever, embedder, ai_client, store


@pytest.mark.asyncio
async def test_returns_answer_and_context_quality():
    uc, _, _, _, _ = _make_uc(
        search_result=[_MONTHLY_CHUNK, _SHIFT_CHUNK],
    )
    result = await uc(ChatQueryCommand(user_id=_UID, message="How much on food?"))
    assert isinstance(result, ChatQueryResult)
    assert result.answer == _AI_RESPONSE.answer
    assert result.context_quality == ContextQuality.FULL


@pytest.mark.asyncio
async def test_embeds_user_message():
    uc, _, embedder, _, _ = _make_uc()
    await uc(ChatQueryCommand(user_id=_UID, message="How much on food?"))
    embedder.embed.assert_called_once_with("How much on food?")


@pytest.mark.asyncio
async def test_portrait_prepended_when_present():
    uc, _, _, ai_client, _ = _make_uc(portrait=_PORTRAIT_CHUNK)
    await uc(ChatQueryCommand(user_id=_UID, message="Any trends?"))
    req: ChatRequest = ai_client.chat.call_args[0][0]
    assert req.chunks[0] == _PORTRAIT_CHUNK


@pytest.mark.asyncio
async def test_no_portrait_when_absent():
    uc, _, _, ai_client, _ = _make_uc(portrait=None)
    await uc(ChatQueryCommand(user_id=_UID, message="Any trends?"))
    req: ChatRequest = ai_client.chat.call_args[0][0]
    assert not any(c.chunk_type == "user_portrait" for c in req.chunks)


@pytest.mark.asyncio
async def test_saves_both_turns():
    uc, _, _, _, store = _make_uc()
    await uc(ChatQueryCommand(user_id=_UID, message="How much on food?"))
    args = store.append_turn_pair.call_args[0]
    user_turn, assistant_turn = args[1], args[2]
    assert user_turn.role == "user"
    assert user_turn.content == "How much on food?"
    assert assistant_turn.role == "assistant"
    assert assistant_turn.content == _AI_RESPONSE.answer


@pytest.mark.asyncio
async def test_frozen_clock_turns_share_timestamp_ordered_by_id():
    """With a frozen clock both turns share created_at; the assistant turn's
    UUID7 id must sort strictly after the user turn's so ordering is stable."""
    uc, _, _, _, store = _make_uc()
    await uc(ChatQueryCommand(user_id=_UID, message="How much on food?"))
    user_turn, assistant_turn = store.append_turn_pair.call_args[0][1:3]
    assert user_turn.created_at == assistant_turn.created_at
    assert assistant_turn.id > user_turn.id


@pytest.mark.asyncio
async def test_history_passed_to_ai_client():
    old_turn = ChatTurn(
        id=uuid.uuid4(),
        user_id=_UID,
        role="user",
        content="old question",
        chunks_used=(),
        created_at=datetime.now(UTC),
    )
    uc, _, _, ai_client, _ = _make_uc(history=[old_turn])
    await uc(ChatQueryCommand(user_id=_UID, message="new question"))
    req: ChatRequest = ai_client.chat.call_args[0][0]
    assert old_turn in req.history


@pytest.mark.asyncio
async def test_partial_quality_when_only_monthly():
    uc, _, _, _, _ = _make_uc(search_result=[_MONTHLY_CHUNK])
    result = await uc(ChatQueryCommand(user_id=_UID, message="Summary?"))
    assert result.context_quality == ContextQuality.PARTIAL


@pytest.mark.asyncio
async def test_none_quality_when_no_chunks():
    uc, _, _, _, _ = _make_uc(search_result=[], portrait=None)
    result = await uc(ChatQueryCommand(user_id=_UID, message="Summary?"))
    assert result.context_quality == ContextQuality.NONE
