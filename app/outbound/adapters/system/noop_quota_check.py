from app.application.common.ports.quota_check import QuotaResource
from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId


class NoOpQuotaCheck:
    """Quota check that always passes.

    Used by scheduler-driven flows where the action originates from system code
    rather than a user request (e.g. recurring transactions firing on schedule).
    The user has already paid for the rule itself; per-period transaction quotas
    do not apply to scheduled side-effects.
    """

    async def check_and_increment(
        self, user_id: UserId, resource: QuotaResource, plan: Plan
    ) -> None:
        pass
