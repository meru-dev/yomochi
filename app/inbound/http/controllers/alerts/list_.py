# app/inbound/http/controllers/alerts/list_.py
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Query, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.alerts.use_cases.list_alerts import ListAlertsQuery, ListAlertsUseCase
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


class AlertResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    period_year: int
    period_month: int
    is_read: bool
    created_at: str


class ListAlertsResponse(BaseModel):
    items: list[AlertResponse]
    unread_count: int
    next_cursor: str | None


@router.get("/alerts", status_code=status.HTTP_200_OK, response_model=ListAlertsResponse)
@inject
async def list_alerts(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListAlertsUseCase],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ListAlertsResponse:
    result = await use_case(ListAlertsQuery(user_id=identity.user_id, limit=limit, cursor=cursor))
    return ListAlertsResponse(
        items=[
            AlertResponse(
                id=str(a.id_.value),
                type=a.alert_type.value,
                title=a.title,
                body=a.body,
                period_year=a.period_year,
                period_month=a.period_month,
                is_read=a.is_read,
                created_at=a.created_at.isoformat(),
            )
            for a in result.alerts
        ],
        unread_count=result.unread_count,
        next_cursor=result.next_cursor,
    )
