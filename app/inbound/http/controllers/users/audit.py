from datetime import datetime

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.use_cases.list_audit_events import (
    ListAuditEventsQuery,
    ListAuditEventsUseCase,
)

router = APIRouter()


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime
    ip: str | None
    user_agent: str | None


class ListAuditEventsResponse(BaseModel):
    events: list[AuditEventOut]
    next_cursor: str | None


@router.get("/audit-events", response_model=ListAuditEventsResponse)
@inject
async def list_audit_events(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListAuditEventsUseCase],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),  # noqa: B008
    to_date: datetime | None = Query(default=None),  # noqa: B008
) -> ListAuditEventsResponse:
    result = await use_case(
        ListAuditEventsQuery(
            user_id=identity.user_id,
            limit=limit,
            cursor=cursor,
            event_type_filter=event_type,
            from_date=from_date,
            to_date=to_date,
        )
    )
    return ListAuditEventsResponse(
        events=[
            AuditEventOut(
                id=e.id,
                event_type=e.event_type.value,
                occurred_at=e.occurred_at,
                ip=e.ip,
                user_agent=e.user_agent,
            )
            for e in result.events
        ],
        next_cursor=result.next_cursor,
    )
