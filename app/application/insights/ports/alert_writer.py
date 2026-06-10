# app/application/insights/ports/alert_writer.py
from typing import Protocol

from app.domain.services.behavioral_shift_detector import DetectedShift
from app.domain.value_objects.ids import UserId


class AlertWriter(Protocol):
    async def write_shift_alerts(
        self,
        user_id: UserId,
        year: int,
        month: int,
        shifts: list[DetectedShift],
    ) -> None: ...
