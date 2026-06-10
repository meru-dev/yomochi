# app/inbound/http/controllers/alerts/clear.py
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter

from app.application.alerts.use_cases.clear_alerts import ClearAlertsCommand, ClearAlertsUseCase
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


@router.delete("/alerts", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def clear_alerts(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ClearAlertsUseCase],
) -> None:
    await use_case(ClearAlertsCommand(user_id=identity.user_id))
