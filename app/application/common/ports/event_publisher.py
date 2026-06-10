from typing import Any, Protocol


class EventPublisher(Protocol):
    async def publish(
        self, message: dict[str, Any], topic: str, key: bytes | None = None
    ) -> None: ...
