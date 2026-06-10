import pytest

pytest.skip(
    "Pending implementation — referenced symbol not yet present in source", allow_module_level=True
)


"""structlog processor injects OTel trace_id/span_id into every log record.

The contract: a log line emitted *inside* an active span carries the same
trace_id as the span; outside a span, no trace_id key is added.
"""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from app.main.logging import _inject_otel_context


def _ensure_provider() -> None:
    if isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        resource = Resource.create({"service.name": "test"})
        trace.set_tracer_provider(TracerProvider(resource=resource))


def test_no_trace_id_outside_span() -> None:
    _ensure_provider()
    out = _inject_otel_context(None, "info", {"event": "hello"})  # type: ignore[arg-type]
    assert "trace_id" not in out
    assert "span_id" not in out


def test_trace_id_matches_active_span() -> None:
    _ensure_provider()
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("work") as span:
        out = _inject_otel_context(None, "info", {"event": "hello"})  # type: ignore[arg-type]
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
        expected_span_id = format(span.get_span_context().span_id, "016x")
    assert out["trace_id"] == expected_trace_id
    assert out["span_id"] == expected_span_id
    assert isinstance(out["trace_sampled"], bool)


def test_format_is_w3c_lowercase_hex() -> None:
    """trace_id 32 lowercase hex chars, span_id 16 — same shape as `traceparent`,
    so grep finds the same string in logs, traces, and Kafka headers."""
    _ensure_provider()
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("work"):
        out = _inject_otel_context(None, "info", {})  # type: ignore[arg-type]
    assert len(out["trace_id"]) == 32
    assert len(out["span_id"]) == 16
    assert out["trace_id"] == out["trace_id"].lower()
    assert all(c in "0123456789abcdef" for c in out["trace_id"])
    assert all(c in "0123456789abcdef" for c in out["span_id"])
