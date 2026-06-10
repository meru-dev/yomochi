from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.outbound.observability.prometheus import (
    consumer_dlq_events_total,
    consumer_idempotency_skips_total,
    insight_generation_duration_seconds,
)


class PrometheusMetricsRecorder(MetricsRecorder):
    def consumer_idempotency_skip(self, topic: str) -> None:
        consumer_idempotency_skips_total.labels(topic=topic).inc()

    def consumer_dlq_event(self, topic: str) -> None:
        consumer_dlq_events_total.labels(topic=topic).inc()

    def insight_generation_observed(self, context_quality: str, seconds: float) -> None:
        insight_generation_duration_seconds.labels(context_quality=context_quality).observe(seconds)
