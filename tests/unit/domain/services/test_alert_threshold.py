# tests/unit/domain/services/test_alert_threshold.py
from decimal import Decimal

from app.domain.services.alert_threshold import is_alertworthy
from app.domain.services.behavioral_shift_detector import DetectedShift


def _shift(
    severity: str = "high",
    currency: str = "USD",
    abs_change: str = "100",
    type_: str = "expense_spike",
) -> DetectedShift:
    return DetectedShift(
        type=type_,
        severity=severity,
        delta_pct=0.4,
        currency=currency,
        abs_change=Decimal(abs_change),
    )


def test_medium_severity_never_alertworthy():
    assert not is_alertworthy(_shift(severity="medium"))


def test_high_severity_above_usd_threshold():
    assert is_alertworthy(_shift(currency="USD", abs_change="50"))


def test_high_severity_below_usd_threshold():
    assert not is_alertworthy(_shift(currency="USD", abs_change="5"))


def test_jpy_uses_higher_threshold():
    assert is_alertworthy(_shift(currency="JPY", abs_change="5000"))
    assert not is_alertworthy(_shift(currency="JPY", abs_change="500"))


def test_unknown_currency_uses_fallback():
    assert is_alertworthy(_shift(currency="XYZ", abs_change="50"))
    assert not is_alertworthy(_shift(currency="XYZ", abs_change="5"))


def test_no_currency_trusts_severity():
    s = DetectedShift(type="expense_spike", severity="high", delta_pct=0.4)
    assert is_alertworthy(s)


def test_zero_abs_change_trusts_severity():
    s = DetectedShift(
        type="expense_spike",
        severity="high",
        delta_pct=0.4,
        currency="USD",
        abs_change=Decimal("0"),
    )
    assert is_alertworthy(s)
