from abc import abstractmethod
from typing import Protocol


class MetricsRecorder(Protocol):
    @abstractmethod
    def consumer_idempotency_skip(self, topic: str) -> None: ...

    @abstractmethod
    def consumer_dlq_event(self, topic: str) -> None: ...

    @abstractmethod
    def insight_generation_observed(self, context_quality: str, seconds: float) -> None: ...
