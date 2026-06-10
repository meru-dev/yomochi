# app/domain/services/alert_threshold.py
from decimal import Decimal

from app.domain.services.behavioral_shift_detector import DetectedShift

# Minimum absolute change to suppress noise (tiny % on tiny base).
# Values represent ~$20 USD equivalent per currency.
_MIN_AMOUNTS: dict[str, Decimal] = {
    "JPY": Decimal("3000"),
    "USD": Decimal("20"),
    "EUR": Decimal("20"),
    "GBP": Decimal("15"),
    "CNY": Decimal("150"),
    "KRW": Decimal("30000"),
    "SGD": Decimal("25"),
    "AUD": Decimal("30"),
}
_FALLBACK_MIN = Decimal("20")


def is_alertworthy(shift: DetectedShift) -> bool:
    """True for high-severity shifts above the currency-specific noise floor."""
    if shift.severity != "high":
        return False
    if not shift.currency or shift.abs_change == Decimal("0"):
        return True
    return shift.abs_change >= _MIN_AMOUNTS.get(shift.currency, _FALLBACK_MIN)
