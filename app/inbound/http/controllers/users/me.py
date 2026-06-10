from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.ports.user_repository import UserRepository

router = ErrorAwareRouter()


class MeResponse(BaseModel):
    id: str
    email: str
    plan: str


@router.get("/me", status_code=status.HTTP_200_OK, response_model=MeResponse)
@inject
async def get_me(
    identity: FromDishka[IdentityContext],
    user_repo: FromDishka[UserRepository],
) -> MeResponse:
    user = await user_repo.get_by_id(identity.user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(id=str(user.id_), email=str(user.email), plan=str(user.plan))
