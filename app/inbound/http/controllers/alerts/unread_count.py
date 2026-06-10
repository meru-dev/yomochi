# app/inbound/http/controllers/alerts/unread_count.py
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.alerts.use_cases.list_alerts import ListAlertsQuery, ListAlertsUseCase
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


class UnreadCountResponse(BaseModel):
    count: int


@router.get(
    "/alerts/unread-count",
    status_code=status.HTTP_200_OK,
    response_model=UnreadCountResponse,
)
@inject
async def unread_count(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListAlertsUseCase],
) -> UnreadCountResponse:
    result = await use_case(ListAlertsQuery(user_id=identity.user_id, limit=0))
    return UnreadCountResponse(count=result.unread_count)
