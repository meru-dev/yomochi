from abc import abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID


class OutboxAdmin(Protocol):
    """Operational outbox maintenance — kept separate from the request-path
    ``OutboxRepository`` (ISP): event emitters depend only on ``append`` and never
    see this maintenance surface; only the admin replay tool depends on this port.
    """

    @abstractmethod
    async def requeue_failed(
        self,
        *,
        ids: Sequence[UUID] | None = None,
        event_type: str | None = None,
        failed_before: datetime | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> list[UUID]:
        """Flip quarantined (FAILED) outbox rows back to PENDING for replay.

        Selects FAILED rows matching the given filters (``ids`` / ``event_type`` /
        ``failed_before``, optionally capped by ``limit``), resets them to PENDING
        with ``retry_count=0`` and cleared ``last_error``/``failed_at`` so the
        poller gives them a fresh round of attempts. Returns the affected row ids.
        ``dry_run`` returns the ids that WOULD be requeued without mutating.
        """
        ...
