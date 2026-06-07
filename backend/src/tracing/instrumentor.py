"""Phoenix OpenTelemetry tracer setup."""

import logging

logger = logging.getLogger(__name__)


def setup_instrumentation() -> None:
    """Configure Phoenix tracing via ``phoenix.otel.register``.

    Uses the canonical Phoenix SDK idiom: one ``register(...)`` call sets up
    the OTLP/HTTP exporter, a :class:`BatchSpanProcessor` (instead of the
    synchronous ``SimpleSpanProcessor`` that blocked every span on a network
    round-trip), the project resource attribute, and auto-instruments every
    installed OpenInference instrumentor — currently ``google-adk`` and
    ``google-genai``. That second one matters: the LLM judges and the
    proposal generator call ``google.genai`` directly, so without it ~40% of
    LLM traffic never reaches Phoenix.
    """
    from src.config import get_settings

    settings = get_settings()

    if not settings.phoenix_api_key:
        logger.warning("PHOENIX_API_KEY not set, skipping instrumentation")
        return

    try:
        from phoenix.otel import register

        register(
            project_name=settings.phoenix_project_name,
            endpoint=f"{settings.phoenix_collector_endpoint}/v1/traces",
            headers={"Authorization": f"Bearer {settings.phoenix_api_key}"},
            protocol="http/protobuf",
            auto_instrument=True,
            batch=True,
            verbose=False,
        )

        logger.info(
            "Phoenix instrumentation registered (endpoint=%s/v1/traces, "
            "project=%s)",
            settings.phoenix_collector_endpoint,
            settings.phoenix_project_name,
        )
    except ImportError as exc:
        logger.warning("Phoenix instrumentation packages not available: %s", exc)
    except Exception as exc:
        logger.error(
            "Failed to set up Phoenix instrumentation: %s", exc, exc_info=True
        )
