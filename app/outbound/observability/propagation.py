from typing import Any

from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

PROPAGATOR = TraceContextTextMapPropagator()


def extract_context(carrier: Any) -> Context | None:
    """Resume a trace from an incoming W3C carrier (dict[str, str]).

    Returns None for missing / non-dict / empty carriers so handling proceeds on
    a fresh trace rather than orphan-attaching to a bogus parent.
    """
    if not isinstance(carrier, dict) or not carrier:
        return None
    return PROPAGATOR.extract({str(k): str(v) for k, v in carrier.items()})
