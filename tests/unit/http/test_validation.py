import pytest
from pydantic import ValidationError

from app.inbound.http.controllers.transactions.create import CreateTransactionRequest
from app.inbound.http.controllers.transactions.update import UpdateTransactionRequest

# --- CreateTransactionRequest ---


def test_create_valid_request():
    req = CreateTransactionRequest(
        amount="42.50",
        currency="USD",
        date="2024-01-15",
        type="expense",
        merchant="Starbucks",
    )
    assert req.amount == "42.50"


def test_create_text_amount_fails():
    with pytest.raises(ValidationError) as exc_info:
        CreateTransactionRequest(
            amount="fifty",
            currency="USD",
            date="2024-01-15",
            type="expense",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("amount",) for e in errors)


def test_create_invalid_type_fails():
    with pytest.raises(ValidationError) as exc_info:
        CreateTransactionRequest(
            amount="10",
            currency="USD",
            date="2024-01-15",
            type="purchase",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("type",) for e in errors)


def test_create_invalid_category_uuid_fails():
    with pytest.raises(ValidationError) as exc_info:
        CreateTransactionRequest(
            amount="10",
            currency="USD",
            date="2024-01-15",
            type="expense",
            category_id="not-a-uuid",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("category_id",) for e in errors)


def test_create_valid_category_uuid_passes():
    req = CreateTransactionRequest(
        amount="10",
        currency="USD",
        date="2024-01-15",
        type="expense",
        category_id="550e8400-e29b-41d4-a716-446655440000",
    )
    assert req.category_id is not None


# --- UpdateTransactionRequest ---


def test_update_text_amount_fails():
    with pytest.raises(ValidationError) as exc_info:
        UpdateTransactionRequest(amount="abc")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("amount",) for e in errors)


def test_update_invalid_type_fails():
    with pytest.raises(ValidationError) as exc_info:
        UpdateTransactionRequest(type="purchase")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("type",) for e in errors)


def test_update_none_amount_passes():
    req = UpdateTransactionRequest(amount=None)
    assert req.amount is None


# --- RequestInsightBody ---

from app.inbound.http.controllers.insights.request import RequestInsightBody


def test_insight_invalid_period_fails():
    with pytest.raises(ValidationError) as exc_info:
        RequestInsightBody(period="daily", period_year=2024, period_month=1)
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("period",) for e in errors)


def test_insight_valid_period_passes():
    body = RequestInsightBody(period="monthly", period_year=2024, period_month=1)
    assert body.period == "monthly"


# --- SearchRequest ---

from app.inbound.http.controllers.search import SearchRequest


def test_search_empty_query_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchRequest(query="")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("query",) for e in errors)


def test_search_query_too_long_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchRequest(query="a" * 201)
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("query",) for e in errors)


def test_search_valid_query_passes() -> None:
    req = SearchRequest(query="coffee")
    assert req.query == "coffee"
    assert req.limit == 20  # default


def test_search_limit_zero_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchRequest(query="coffee", limit=0)
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("limit",) for e in errors)


def test_search_limit_over_100_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchRequest(query="coffee", limit=101)
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("limit",) for e in errors)


def test_search_limit_boundary_values_pass() -> None:
    assert SearchRequest(query="x", limit=1).limit == 1
    assert SearchRequest(query="x", limit=100).limit == 100
