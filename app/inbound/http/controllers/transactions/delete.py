from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Response, status
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.delete_transaction import (
    DeleteTransactionCommand,
    DeleteTransactionUseCase,
)
from app.domain.value_objects.ids import TransactionId

router = ErrorAwareRouter()


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_transaction(
    transaction_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[DeleteTransactionUseCase],
) -> Response:
    await use_case(
        DeleteTransactionCommand(
            transaction_id=TransactionId(transaction_id),
            user_id=identity.user_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
