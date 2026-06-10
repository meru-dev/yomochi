from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type

from app.application.transactions.ports.category_list_reader import CategoryListReader
from app.application.transactions.ports.transaction_text_parser import TransactionTextParser
from app.domain.exceptions.domain_errors import InvalidTransactionTextError
from app.domain.value_objects.ids import UserId

_MAX_TEXT_LENGTH = 500


@dataclass(frozen=True, slots=True)
class ParseTransactionTextQuery:
    user_id: UserId
    text: str


@dataclass(frozen=True, slots=True)
class DraftTransaction:
    amount: str | None
    currency: str | None
    merchant: str | None
    transaction_type: str | None
    date: date_type | None
    suggested_category_id: str | None
    confidence: float
    requires_review: bool
    low_confidence_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParseTransactionTextResult:
    draft: DraftTransaction


class ParseTransactionTextUseCase:
    def __init__(
        self,
        category_list_reader: CategoryListReader,
        text_parser: TransactionTextParser,
    ) -> None:
        self._category_list_reader = category_list_reader
        self._text_parser = text_parser

    async def __call__(self, query: ParseTransactionTextQuery) -> ParseTransactionTextResult:
        text = query.text.strip()
        if not text:
            raise InvalidTransactionTextError("text is empty")
        if len(text) > _MAX_TEXT_LENGTH:
            raise InvalidTransactionTextError(f"text exceeds {_MAX_TEXT_LENGTH} characters")

        categories = await self._category_list_reader.list_for_user(query.user_id)
        category_pairs = [(c.id_, c.name) for c in categories if c.parent_id is not None]
        today = datetime.now(UTC).date()

        draft = await self._text_parser.parse(text, category_pairs, today)
        return ParseTransactionTextResult(draft=draft)
