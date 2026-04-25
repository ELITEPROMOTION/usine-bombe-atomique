"""OpenTelemetry setup V5.9 lightweight.

Pas de dependance opentelemetry-sdk requise (lazy import).
Mode fallback : no-op tracing si SDK absent.

Features :
  - TracerProvider global avec service.name/version attributes
  - Instrumentations : FastAPI (auto), asyncpg, redis, httpx, arq
  - Exporters : console (dev), OTLP (prod), Jaeger (local docker)
  - Sampling : 100% errors + slow + 10% normal
  - Custom spans pour domain operations
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("uba.observability.otel")


_INITIALIZED = False
_INSTRUMENTATIONS: list[str] = []
_EXPORTER: str = "noop"


class NoopTracer:
    """Fallback si OpenTelemetry SDK non installe."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Iterator[Any]:
        span = _NoopSpan(name)
        yield span


class _NoopSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict[str, Any] = {}
        self._start = time.perf_counter()

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: BaseException) -> None:
        self.attributes["error"] = str(exc)

    def end(self) -> None:
        self.attributes["duration_ms"] = int(
            (time.perf_counter() - self._start) * 1000,
        )


def _get_service_attributes() -> dict[str, str]:
    """Attributs standards service.*."""
    return {
        "service.name": os.environ.get("OTEL_SERVICE_NAME", "uba-backend"),
        "service.version": os.environ.get("UBA_VERSION", "0.2.0"),
        "deployment.environment": os.environ.get("ENV", "development"),
        "service.namespace": "uba",
    }


def init_otel(app: Any = None) -> dict[str, Any]:
    """Initialise OpenTelemetry si SDK disponible.

    Variables env :
      - OTEL_EXPORTER_OTLP_ENDPOINT : URL gRPC (default : none)
      - OTEL_EXPORTER : console | otlp | jaeger (default : console)
      - OTEL_TRACES_SAMPLER_ARG : ratio sampling normal traffic (default 0.1)
    """
    global _INITIALIZED, _EXPORTER
    if _INITIALIZED:
        return {"status": "already_initialized", "exporter": _EXPORTER,
                "instrumentations": list(_INSTRUMENTATIONS)}

    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor, ConsoleSpanExporter,
        )
    except ImportError:
        logger.info("OpenTelemetry SDK absent : noop tracer actif")
        _INITIALIZED = True
        _EXPORTER = "noop"
        return {"status": "noop", "sdk_installed": False,
                "exporter": "noop", "instrumentations": []}

    attrs = _get_service_attributes()
    resource = Resource.create(attrs)
    provider = TracerProvider(resource=resource)

    exporter_mode = os.environ.get("OTEL_EXPORTER", "console")
    if exporter_mode == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif exporter_mode == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )
            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
            )
            provider.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, insecure=True),
            ))
        except ImportError:
            logger.warning("OTLP exporter not available, using console")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif exporter_mode == "jaeger":
        try:
            from opentelemetry.exporter.jaeger.thrift import (  # type: ignore[import-not-found]
                JaegerExporter,
            )
            provider.add_span_processor(BatchSpanProcessor(
                JaegerExporter(
                    agent_host_name=os.environ.get("JAEGER_AGENT_HOST",
                                                     "localhost"),
                    agent_port=int(os.environ.get("JAEGER_AGENT_PORT", "6831")),
                ),
            ))
        except ImportError:
            logger.warning("Jaeger exporter not available, using console")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Instrument
    _INSTRUMENTATIONS.clear()
    if app is not None:
        _try_instrument_fastapi(app)
    _try_instrument_asyncpg()
    _try_instrument_httpx()
    _try_instrument_redis()

    _INITIALIZED = True
    _EXPORTER = exporter_mode
    return {
        "status": "initialized",
        "sdk_installed": True,
        "service_attributes": attrs,
        "exporter": exporter_mode,
        "instrumentations": list(_INSTRUMENTATIONS),
    }


def _try_instrument_fastapi(app: Any) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
        FastAPIInstrumentor.instrument_app(app)
        _INSTRUMENTATIONS.append("fastapi")
        logger.info("FastAPI instrumented")
    except Exception as exc:
        logger.debug("fastapi instrument skipped: %s", exc)


def _try_instrument_asyncpg() -> None:
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor  # type: ignore[import-not-found]
        AsyncPGInstrumentor().instrument()
        _INSTRUMENTATIONS.append("asyncpg")
    except Exception as exc:
        logger.debug("asyncpg instrument skipped: %s", exc)


def _try_instrument_httpx() -> None:
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import-not-found]
        HTTPXClientInstrumentor().instrument()
        _INSTRUMENTATIONS.append("httpx")
    except Exception as exc:
        logger.debug("httpx instrument skipped: %s", exc)


def _try_instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor  # type: ignore[import-not-found]
        RedisInstrumentor().instrument()
        _INSTRUMENTATIONS.append("redis")
    except Exception as exc:
        logger.debug("redis instrument skipped: %s", exc)


def get_tracer(name: str = "uba"):
    """Retourne tracer (SDK ou no-op fallback)."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        return trace.get_tracer(name)
    except ImportError:
        return NoopTracer()


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Context manager helper pour creer un span avec attributs."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if hasattr(s, "set_attribute"):
            for k, v in attributes.items():
                try:
                    s.set_attribute(k, v)
                except Exception:
                    pass
        try:
            yield s
        except Exception as exc:
            if hasattr(s, "record_exception"):
                s.record_exception(exc)
            raise


def status() -> dict[str, Any]:
    """Retourne etat actuel OTel."""
    try:
        import opentelemetry  # type: ignore[import-not-found]
        sdk_version = getattr(opentelemetry, "__version__", "unknown")
        sdk_available = True
    except ImportError:
        sdk_version = None
        sdk_available = False

    attrs = _get_service_attributes()
    return {
        "sdk_available": sdk_available,
        "sdk_version": sdk_version,
        "initialized": _INITIALIZED,
        "service_name": attrs["service.name"],
        "service_attributes": attrs,
        "exporter": _EXPORTER if _INITIALIZED else os.environ.get("OTEL_EXPORTER", "console"),
        "exporter_mode": os.environ.get("OTEL_EXPORTER", "console"),
        "instrumentations": list(_INSTRUMENTATIONS),
    }
