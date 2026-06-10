# app/domain/entities/alert.py
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.ids import AlertId, UserId


class AlertType(StrEnum):
    SPENDING_SPIKE = "spending_spike"
    INCOME_DROP = "income_drop"
    SAVINGS_COLLAPSE = "savings_collapse"


@dataclass(eq=False)
class Alert(EntityMixin):
    id_: AlertId
    user_id: UserId
    alert_type: AlertType
    title: str
    body: str
    metadata: dict[str, Any]
    period_year: int
    period_month: int
    is_read: bool
    created_at: datetime

    def mark_read(self) -> None:
        self.is_read = True
