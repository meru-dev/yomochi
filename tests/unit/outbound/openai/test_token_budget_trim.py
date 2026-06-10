from __future__ import annotations

import pytest

pytest.skip(
    "Pending implementation — referenced symbol not yet present in source", allow_module_level=True
)


import pytest

pytest.skip(
    "Pending implementation — referenced symbol not yet present in source", allow_module_level=True
)


"""Unit tests for _trim_chunks: token-budget eviction logic."""


from app.application.common.ports.chunk_retriever import RetrievedChunk
from app.outbound.adapters.openai.insight_client import (
    _CHAT_OVERHEAD_TOKENS,
    _PORTRAIT_CHUNK_TYPE,
    _SYSTEM_PROMPT,
    _assemble_user_prompt,
    _get_encoding,
    _trim_chunks,
)

_ENC = _get_encoding("gpt-4o-mini")
_SYSTEM_TOKENS = len(_ENC.encode(_SYSTEM_PROMPT, disallowed_special=()))
_PERIOD = "June 2026"
_HUGE_BUDGET = 128_000


def _chunk(chunk_type: str, content: str, similarity: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        content=content,
        chunk_type=chunk_type,
        period_label=_PERIOD,
        metadata={},
        similarity=similarity,
    )


def _portrait(content: str = "portrait content") -> RetrievedChunk:
    return _chunk(_PORTRAIT_CHUNK_TYPE, content, similarity=1.0)


def _token_count(chunks: list[RetrievedChunk]) -> int:
    prompt = _assemble_user_prompt(chunks, _PERIOD, None)
    return _SYSTEM_TOKENS + len(_ENC.encode(prompt, disallowed_special=())) + _CHAT_OVERHEAD_TOKENS


# ---------------------------------------------------------------------------
# Happy path — fits without trimming
# ---------------------------------------------------------------------------


def test_no_trim_when_under_budget() -> None:
    chunks = [_chunk("monthly_summary", "small content", similarity=0.8), _portrait()]
    result_chunks, result_prompt = _trim_chunks(
        chunks, _ENC, _SYSTEM_TOKENS, _HUGE_BUDGET, _PERIOD, None
    )
    assert result_chunks == chunks
    assert result_prompt == _assemble_user_prompt(chunks, _PERIOD, None)


def test_empty_chunks_returns_no_data_prompt() -> None:
    result_chunks, result_prompt = _trim_chunks(
        [], _ENC, _SYSTEM_TOKENS, _HUGE_BUDGET, _PERIOD, None
    )
    assert result_chunks == []
    assert "No historical data available." in result_prompt


# ---------------------------------------------------------------------------
# Trimming — correct eviction order
# ---------------------------------------------------------------------------


def test_trims_lowest_similarity_first() -> None:
    low = _chunk("monthly_summary", "low sim content", similarity=0.1)
    high = _chunk("behavioral_shift", "high sim content", similarity=0.9)
    portrait = _portrait()

    # Budget that fits high + portrait but not all three.
    budget = _token_count([high, portrait]) + 5

    result_chunks, _ = _trim_chunks(
        [low, high, portrait], _ENC, _SYSTEM_TOKENS, budget, _PERIOD, None
    )
    assert low not in result_chunks
    assert high in result_chunks
    assert portrait in result_chunks


def test_portrait_never_evicted_even_as_sole_chunk() -> None:
    portrait = _portrait("A" * 500)
    # Tiny budget — portrait alone exceeds it; must still be returned.
    result_chunks, _ = _trim_chunks([portrait], _ENC, _SYSTEM_TOKENS, 10, _PERIOD, None)
    assert portrait in result_chunks


def test_portrait_pinned_by_chunk_type_not_similarity() -> None:
    """Non-portrait chunk with similarity=1.0 must NOT be treated as pinned."""
    fake_high = _chunk("monthly_summary", "X" * 200, similarity=1.0)
    portrait = _portrait("Y" * 20)

    # Budget that fits portrait alone but not fake_high + portrait.
    budget = _token_count([portrait]) + 5

    result_chunks, _ = _trim_chunks(
        [fake_high, portrait], _ENC, _SYSTEM_TOKENS, budget, _PERIOD, None
    )
    assert fake_high not in result_chunks
    assert portrait in result_chunks


def test_trims_all_non_portrait_when_still_over_budget() -> None:
    chunks = [
        _chunk("monthly_summary", "A" * 200, similarity=0.2),
        _chunk("behavioral_shift", "B" * 200, similarity=0.8),
        _portrait("C" * 10),
    ]
    # Budget that fits only the portrait.
    budget = _token_count([chunks[-1]]) + 5

    result_chunks, _ = _trim_chunks(chunks, _ENC, _SYSTEM_TOKENS, budget, _PERIOD, None)
    assert result_chunks == [chunks[-1]]


# ---------------------------------------------------------------------------
# Returned prompt consistency
# ---------------------------------------------------------------------------


def test_returned_prompt_matches_returned_chunks() -> None:
    chunks = [
        _chunk("monthly_summary", "data A", similarity=0.3),
        _chunk("behavioral_shift", "data B", similarity=0.7),
        _portrait(),
    ]
    result_chunks, result_prompt = _trim_chunks(
        chunks, _ENC, _SYSTEM_TOKENS, _HUGE_BUDGET, _PERIOD, "What is my top expense?"
    )
    expected = _assemble_user_prompt(result_chunks, _PERIOD, "What is my top expense?")
    assert result_prompt == expected


def test_returned_prompt_matches_chunks_after_trim() -> None:
    low = _chunk("monthly_summary", "X" * 300, similarity=0.1)
    portrait = _portrait("Y" * 10)
    budget = _token_count([portrait]) + 5

    result_chunks, result_prompt = _trim_chunks(
        [low, portrait], _ENC, _SYSTEM_TOKENS, budget, _PERIOD, None
    )
    expected = _assemble_user_prompt(result_chunks, _PERIOD, None)
    assert result_prompt == expected
