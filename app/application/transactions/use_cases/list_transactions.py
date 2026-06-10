from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from app.application.common.cursor import decode_cursor as _decode_raw
from app.application.common.cursor import encode_cursor as _encode_raw
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.domain.entities.transaction import Transaction
from app.domain.exceptions.domain_errors import InvalidCursorError
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ListTransactionsQuery:
    user_id: UserId
    limit: int = field(default=20)
    cursor: str | None = field(default=None)
    type_filter: str | None = field(default=None)
    currency_filter: str | None = field(default=None)
    category_id_filter: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class ListTransactionsResult:
    transactions: tuple[Transaction, ...]
    next_cursor: str | None


def decode_cursor(cursor: str) -> tuple[date, datetime, UUID]:
    try:
        raw = _decode_raw(cursor)
        return (
            date.fromisoformat(raw["date"]),
            datetime.fromisoformat(raw["created_at"]),
            UUID(raw["id"]),
        )
    except InvalidCursorError:
        raise
    except Exception as exc:
        raise InvalidCursorError("Invalid or expired pagination cursor") from exc


def encode_cursor(tx: Transaction) -> str:
    return _encode_raw(
        {
            "date": tx.date.isoformat(),
            "created_at": tx.created_at.isoformat(),
            "id": str(tx.id_),
        }
    )


class ListTransactionsUseCase:
    def __init__(self, transaction_repo: TransactionRepository) -> None:
        self._transaction_repo = transaction_repo

    async def __call__(self, query: ListTransactionsQuery) -> ListTransactionsResult:
        cursor_tuple = decode_cursor(query.cursor) if query.cursor else None
        transactions = await self._transaction_repo.list_by_user(
            user_id=query.user_id,
            limit=query.limit,
            cursor=cursor_tuple,
            type_filter=query.type_filter,
            currency_filter=query.currency_filter,
            category_id_filter=query.category_id_filter,
        )
        next_cursor = encode_cursor(transactions[-1]) if len(transactions) == query.limit else None
        return ListTransactionsResult(
            transactions=tuple(transactions),
            next_cursor=next_cursor,
        )
