from dataclasses import dataclass

from app.application.alerts.ports.alert_repository import AlertRepository
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ClearAlertsCommand:
    user_id: UserId


class ClearAlertsUseCase:
    def __init__(self, repo: AlertRepository) -> None:
        self._repo = repo

    async def __call__(self, command: ClearAlertsCommand) -> None:
        await self._repo.clear_all(command.user_id)
