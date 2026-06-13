# tests/unit/application/insights/test_embedding_pipeline_alerts.py
from decimal import Decimal

from app.domain.services.behavioral_shift_detector import DetectedShift
from app.outbound.adapters.sqla.alerts.alert_writer import _build_body, _build_title, _subtype


def _shift(
    type_: str = "expense_spike",
    category: str | None = None,
    delta_pct: float = 0.4,
    currency: str = "JPY",
    abs_change: str = "4200",
) -> DetectedShift:
    return DetectedShift(
        type=type_,
        severity="high",
        delta_pct=delta_pct,
        category=category,
        currency=currency,
        abs_change=Decimal(abs_change),
    )


def test_subtype_without_category():
    assert _subtype(_shift("expense_spike")) == "expense_spike"


def test_subtype_with_category():
    assert _subtype(_shift("category_spike", category="Coffee")) == "category_spike:Coffee"


def test_title_expense_spike():
    assert _build_title(_shift("expense_spike")) == "Total spending up 40%"


def test_title_category_spike():
    assert _build_title(_shift("category_spike", category="Coffee")) == "Coffee spending up 40%"


def test_title_income_drop():
    assert _build_title(_shift("income_drop", delta_pct=-0.32)) == "Income down 32%"


def test_body_includes_amount_and_currency():
    body = _build_body(_shift("expense_spike", currency="JPY", abs_change="4200"))
    assert "40%" in body
    assert "4200 JPY above usual" in body


def test_body_without_amount():
    s = DetectedShift(type="expense_spike", severity="high", delta_pct=0.4)
    body = _build_body(s)
    assert "40%" in body
    assert "above usual" not in body


def test_body_income_drop_uses_below_usual():
    body = _build_body(_shift("income_drop", delta_pct=-0.25, currency="USD", abs_change="500"))
    assert "25%" in body
    assert "500 USD below usual" in body


# Pipeline integration tests
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.insights.embedding_pipeline import EmbeddingPipeline
from app.domain.services.behavioral_shift_detector import DetectedShift
from app.domain.services.monthly_aggregator import MonthlyAggregation
from app.domain.value_objects.ids import UserId


def _make_agg(
    year=2026, month=5, income=1000.0, expenses=500.0, currency="USD"
) -> MonthlyAggregation:
    from decimal import Decimal as D  # noqa: N817

    total_income = D(str(income))
    total_expenses = D(str(expenses))
    net = total_income - total_expenses
    sr = float(net / total_income) if total_income > 0 else 0.0
    return MonthlyAggregation(
        year=year,
        month=month,
        currency=currency,
        total_income=total_income,
        total_expenses=total_expenses,
        net_savings=net,
        savings_rate=sr,
        expense_volatility=0.0,
        top_categories=[("Food", total_expenses, 1.0)],
        transaction_count=5,
        avg_transaction_amount=total_expenses / 5,
        income_sources_count=1,
        largest_single_expense=total_expenses,
    )


@pytest.mark.asyncio
async def test_alert_writer_called_when_shifts_detected():
    """AlertWriter.write_shift_alerts called when detector returns shifts."""
    from decimal import Decimal

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.upsert = AsyncMock()
    alert_writer = AsyncMock()
    alert_writer.write_shift_alerts = AsyncMock()

    high_shift = DetectedShift(
        type="expense_spike",
        severity="high",
        delta_pct=0.5,
        currency="USD",
        abs_change=Decimal("200"),
    )
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[high_shift])

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
        shift_detector=detector,
        alert_writer=alert_writer,
    )

    uid = UserId(uuid4())
    current = _make_agg(month=5, expenses=750)
    history = [_make_agg(month=m, expenses=500) for m in range(2, 5)]
    await pipeline._write_shift_chunk(uid, 2026, 5, [current], history)

    alert_writer.write_shift_alerts.assert_called_once_with(uid, 2026, 5, [high_shift])


@pytest.mark.asyncio
async def test_alert_writer_not_called_when_none():
    """No error when alert_writer=None (backward compatible)."""
    from decimal import Decimal

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.upsert = AsyncMock()

    high_shift = DetectedShift(
        type="expense_spike",
        severity="high",
        delta_pct=0.5,
        currency="USD",
        abs_change=Decimal("200"),
    )
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[high_shift])

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
        shift_detector=detector,
        alert_writer=None,
    )
    uid = UserId(uuid4())
    current = _make_agg(month=5, expenses=750)
    history = [_make_agg(month=m, expenses=500) for m in range(2, 5)]
    await pipeline._write_shift_chunk(uid, 2026, 5, [current], history)
    # must not raise


@pytest.mark.asyncio
async def test_alert_writer_not_called_when_no_shifts():
    """AlertWriter not called when detector returns empty list."""
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.upsert = AsyncMock()
    alert_writer = AsyncMock()
    alert_writer.write_shift_alerts = AsyncMock()

    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])  # no shifts

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
        shift_detector=detector,
        alert_writer=alert_writer,
    )
    uid = UserId(uuid4())
    current = _make_agg(month=5)
    history = [_make_agg(month=m) for m in range(2, 5)]
    await pipeline._write_shift_chunk(uid, 2026, 5, [current], history)

    alert_writer.write_shift_alerts.assert_not_called()


# ── Semantic-hash skip tests ───────────────────────────────────────────────────
from app.domain.services.monthly_aggregator import compute_semantic_hash


@pytest.mark.asyncio
async def test_monthly_chunk_skips_embed_when_hash_unchanged():
    """Embedder NOT called for monthly chunk when stored semantic_hash matches."""
    aggs = [_make_agg(month=5)]
    matching_hash = compute_semantic_hash(aggs)

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.get_semantic_hash = AsyncMock(return_value=matching_hash)
    chunk_writer.upsert = AsyncMock()

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
    )
    uid = UserId(uuid4())
    await pipeline._write_monthly_chunk(uid, 2026, 5, aggs)

    embedder.embed.assert_not_called()
    chunk_writer.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_monthly_chunk_embeds_when_hash_differs():
    """Embedder IS called for monthly chunk when stored hash does not match."""
    aggs = [_make_agg(month=5)]

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.get_semantic_hash = AsyncMock(return_value="stale-hash")
    chunk_writer.upsert = AsyncMock()

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
    )
    uid = UserId(uuid4())
    await pipeline._write_monthly_chunk(uid, 2026, 5, aggs)

    embedder.embed.assert_awaited_once()
    chunk_writer.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_shift_chunk_skips_embed_when_hash_unchanged():
    """Embedder NOT called for shift chunk when stored semantic_hash matches."""
    from decimal import Decimal

    current = _make_agg(month=5, expenses=750)
    history = [_make_agg(month=m, expenses=500) for m in range(2, 5)]
    matching_hash = compute_semantic_hash([current], bucket_pct=0.10)

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    chunk_writer = AsyncMock()
    chunk_writer.get_semantic_hash = AsyncMock(return_value=matching_hash)
    chunk_writer.upsert = AsyncMock()

    high_shift = DetectedShift(
        type="expense_spike",
        severity="high",
        delta_pct=0.5,
        currency="USD",
        abs_change=Decimal("200"),
    )
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[high_shift])

    pipeline = EmbeddingPipeline(
        budget_reader=AsyncMock(),
        chunk_writer=chunk_writer,
        embedder=embedder,
        shift_detector=detector,
    )
    uid = UserId(uuid4())
    await pipeline._write_shift_chunk(uid, 2026, 5, [current], history)

    embedder.embed.assert_not_called()
    chunk_writer.upsert.assert_not_called()
