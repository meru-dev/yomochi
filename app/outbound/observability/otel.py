from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_otel(service_name: str, otlp_endpoint: str, enabled: bool = True) -> None:
    """Set up the global OTel TracerProvider. Called once at process startup.

    Idempotent: if a real (non-proxy) TracerProvider is already installed, leave
    it in place. OTel itself refuses to override an installed provider, and this
    guard lets tests seed their own provider without production code clobbering it.
    """
    if not enabled:
        return
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        return

    resource = Resource.create({SERVICE_NAME: service_name})
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
