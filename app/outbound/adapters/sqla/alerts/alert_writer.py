# app/outbound/adapters/sqla/alerts/alert_writer.py
import json

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.alert import AlertType
from app.domain.services.alert_threshold import is_alertworthy
from app.domain.services.behavioral_shift_detector import DetectedShift
from app.domain.value_objects.ids import UserId

_SHIFT_TO_ALERT_TYPE: dict[str, AlertType] = {
    "expense_spike": AlertType.SPENDING_SPIKE,
    "category_spike": AlertType.SPENDING_SPIKE,
    "income_drop": AlertType.INCOME_DROP,
    "savings_collapse": AlertType.SAVINGS_COLLAPSE,
}


def _subtype(shift: DetectedShift) -> str:
    if shift.category:
        return f"{shift.type}:{shift.category}"
    return shift.type


def _build_title(shift: DetectedShift) -> str:
    pct = abs(shift.delta_pct * 100)
    if shift.type == "category_spike" and shift.category:
        return f"{shift.category} spending up {pct:.0f}%"
    if shift.type == "expense_spike":
        return f"Total spending up {pct:.0f}%"
    if shift.type == "income_drop":
        return f"Income down {pct:.0f}%"
    if shift.type == "savings_collapse":
        return f"Savings rate collapsed {pct:.0f}%"
    return "Unusual financial activity"


def _build_body(shift: DetectedShift) -> str:
    pct = abs(shift.delta_pct * 100)
    amt_str = (
        f"{shift.abs_change:.0f} {shift.currency}" if shift.abs_change and shift.currency else None
    )

    if shift.type == "category_spike" and shift.category:
        base = f"{shift.category} up {pct:.0f}% vs usual"
        direction = "above"
    elif shift.type == "expense_spike":
        base = f"Total expenses up {pct:.0f}% vs usual"
        direction = "above"
    elif shift.type == "income_drop":
        base = f"Income down {pct:.0f}% vs last 3 months"
        direction = "below"
    elif shift.type == "savings_collapse":
        base = f"Savings rate down {pct:.0f}% vs usual"
        direction = "below"
    else:
        base = f"Unusual change: {pct:.0f}%"
        direction = "above"

    return f"{base} ({amt_str} {direction} usual)" if amt_str else base


class SqlaAlertWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_shift_alerts(
        self,
        user_id: UserId,
        year: int,
        month: int,
        shifts: list[DetectedShift],
    ) -> None:
        alertworthy = [s for s in shifts if is_alertworthy(s)]
        if not alertworthy:
            return
        try:
            for shift in alertworthy:
                alert_type = _SHIFT_TO_ALERT_TYPE.get(shift.type)
                if alert_type is None:
                    continue
                await self._session.execute(
                    sa.text("""
                        INSERT INTO user_alerts
                            (user_id, type, subtype, title, body, metadata, period_year, period_month)
                        VALUES
                            (:user_id, :type, :subtype, :title, :body, CAST(:metadata AS jsonb), :year, :month)
                        ON CONFLICT (user_id, subtype, period_year, period_month)
                        DO NOTHING
                    """),
                    {
                        "user_id": str(user_id.value),
                        "type": alert_type.value,
                        "subtype": _subtype(shift),
                        "title": _build_title(shift),
                        "body": _build_body(shift),
                        "metadata": json.dumps(shift.to_metadata()),
                        "year": year,
                        "month": month,
                    },
                )
        except SQLAlchemyError as exc:
            raise StorageError from exc
