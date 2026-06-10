# app/inbound/http/controllers/alerts/mark_read.py
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter

from app.application.alerts.use_cases.mark_alert_read import (
    AlertNotFoundError,
    MarkAlertReadCommand,
    MarkAlertReadUseCase,
)
from app.application.common.ports.identity_context import IdentityContext
from app.domain.value_objects.ids import AlertId

router = ErrorAwareRouter()


@router.patch(
    "/alerts/{alert_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    error_map={AlertNotFoundError: status.HTTP_404_NOT_FOUND},
)
@inject
async def mark_alert_read(
    alert_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[MarkAlertReadUseCase],
) -> None:
    await use_case(MarkAlertReadCommand(user_id=identity.user_id, alert_id=AlertId(alert_id)))
