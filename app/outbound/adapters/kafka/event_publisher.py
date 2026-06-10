from typing import Any

from faststream.kafka import KafkaBroker


class KafkaEventPublisher:
    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish(self, message: dict[str, Any], topic: str, key: bytes | None = None) -> None:
        await self._broker.publish(
            message=message,
            topic=topic,
            key=key,
        )
