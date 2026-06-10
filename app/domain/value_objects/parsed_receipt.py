from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ParsedReceiptDraft:
    merchant: str | None
    amount: Decimal | None
    currency: str | None
    date_str: str | None  # ISO format "YYYY-MM-DD"
    suggested_category_code: str | None
    merchant_type: str | None = None  # "combini" | "restaurant" | "other"
    line_items: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @property
    def notes(self) -> str | None:
        if not self.line_items:
            return None
        return "\n".join(
            f"{item.get('name', '?')}: {item.get('price', '?')}" for item in self.line_items
        )
