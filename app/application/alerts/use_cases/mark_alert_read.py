from dataclasses import dataclass

from app.application.alerts.ports.alert_repository import AlertRepository
from app.domain.value_objects.ids import AlertId, UserId


class AlertNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MarkAlertReadCommand:
    user_id: UserId
    alert_id: AlertId


class MarkAlertReadUseCase:
    def __init__(self, repo: AlertRepository) -> None:
        self._repo = repo

    async def __call__(self, command: MarkAlertReadCommand) -> None:
        found = await self._repo.mark_read(command.alert_id, command.user_id)
        if not found:
            raise AlertNotFoundError(str(command.alert_id))
