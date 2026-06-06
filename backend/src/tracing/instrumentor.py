"""OpenInference instrumentation setup for Phoenix tracing."""

import logging

logger = logging.getLogger(__name__)


def setup_instrumentation() -> None:
    """Configure OpenTelemetry with Phoenix as the trace exporter.

    Sets up:
    - OTLP/HTTP exporter pointing at Phoenix Cloud collector
    - OpenInference ADK auto-instrumentor for Google ADK traces
    - Phoenix project name from settings via ``PHOENIX_PROJECT_NAME`` resource
      attribute
    """
    from src.config import get_settings

    settings = get_settings()

    if not settings.phoenix_api_key:
        logger.warning("PHOENIX_API_KEY not set, skipping instrumentation")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        # Configure OTLP/HTTP exporter to Phoenix Cloud collector.
        # Phoenix Cloud authenticates OTLP requests with an Authorization Bearer header.
        endpoint = f"{settings.phoenix_collector_endpoint}/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={
                "Authorization": f"Bearer {settings.phoenix_api_key}",
            },
        )

        resource = Resource.create(
            {"project.name": settings.phoenix_project_name}
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Set up OpenInference Google ADK instrumentor.
        # Verified via context7: the import path is
        # openinference.instrumentation.google_adk.GoogleADKInstrumentor
        from openinference.instrumentation.google_adk import (
            GoogleADKInstrumentor,
        )

        GoogleADKInstrumentor().instrument(tracer_provider=provider)

        logger.info(
            "OpenInference instrumentation configured, exporting to %s (project: %s)",
            endpoint,
            settings.phoenix_project_name,
        )
    except ImportError as exc:
        logger.warning("Instrumentation packages not available: %s", exc)
    except Exception as exc:
        logger.error("Failed to set up instrumentation: %s", exc, exc_info=True)
