from typing import Any

from faststream.kafka import KafkaBroker

from app.outbound.observability.propagation import PROPAGATOR


class KafkaEventPublisher:
    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish(self, message: dict[str, Any], topic: str, key: bytes | None = None) -> None:
        # Inject the active span's W3C carrier (traceparent/tracestate) so the
        # consumer can resume the same trace. Empty when no span is recording.
        headers: dict[str, str] = {}
        PROPAGATOR.inject(headers)
        await self._broker.publish(
            message=message,
            topic=topic,
            key=key,
            headers=headers or None,
        )
