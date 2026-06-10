from abc import abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.application.transactions.use_cases.parse_transaction_text import DraftTransaction


class TransactionTextParser(Protocol):
    @abstractmethod
    async def parse(
        self,
        text: str,
        categories: list[tuple[str, str]],
        today: date,
    ) -> "DraftTransaction": ...
