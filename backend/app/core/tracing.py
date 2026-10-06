"""Trazas distribuidas OpenTelemetry y contexto W3C (spec RNF-07.b, T59).

El sistema propaga un ``trace_id`` **de extremo a extremo**:

1. **Origen (Apps Script)**: el webhook envía ``X-Correlation-Id`` (p. ej.
   ``as-<nonce>``) y, opcionalmente, un ``traceparent`` W3C.
2. **Backend**: este middleware resuelve el ``trace_id`` (W3C ``traceparent`` →
   ``X-Correlation-Id`` determinista → nuevo), lo inyecta en el contexto de
   logging y abre un span OpenTelemetry (si el SDK está disponible). El
   ``correlation_id`` del mensaje ``indicators.snapshot`` (§7.2) es el mismo
   identificador propagado.
3. **Cliente**: recibe ``X-Correlation-Id`` y ``X-Trace-Id`` en cada respuesta y
   el campo ``correlation_id`` en el sobre WSS, de modo que una actualización de
   KPI es rastreable extremo a extremo (RNF-07.b).

OpenTelemetry es **opcional**: con el SDK instalado se exportan spans por OTLP;
sin él, la propagación de contexto W3C sigue funcionando (degradación elegante).
Nunca se registran datos personales ni payloads en los atributos del span
(RNF-08.c).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from contextvars import ContextVar
from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_correlation_id

TRACE_ID_HEADER: Final = "X-Trace-Id"
TRACEPARENT_HEADER: Final = "traceparent"

# Formato W3C Trace Context: 00-<32 hex trace-id>-<16 hex parent-id>-<2 hex flags>.
_TRACEPARENT_RE: Final = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})"
    r"-(?P<flags>[0-9a-f]{2})$"
)
_HEX_TRACE_ID_RE: Final = re.compile(r"^[0-9a-f]{32}$")
_ZERO_TRACE_ID: Final = "0" * 32

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
span_id_var: ContextVar[str] = ContextVar("span_id", default="-")

# --- Puente opcional con OpenTelemetry ---------------------------------------
try:  # pragma: no cover - depende del entorno
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import (
        NonRecordingSpan as _OtelNonRecordingSpan,
    )
    from opentelemetry.trace import (
        SpanContext as _OtelSpanContext,
    )
    from opentelemetry.trace import (
        TraceFlags as _OtelTraceFlags,
    )
    from opentelemetry.trace import (
        set_span_in_context as _otel_set_span_in_context,
    )

    _HAS_OTEL = True
except Exception:  # pragma: no cover - OpenTelemetry no instalado
    _otel_trace = None  # type: ignore[assignment]
    _HAS_OTEL = False

_tracer: object | None = None


def has_opentelemetry() -> bool:
    """Indica si el SDK de OpenTelemetry está disponible en el proceso."""
    return _HAS_OTEL


def _get_tracer() -> object | None:
    global _tracer
    if not _HAS_OTEL:
        return None
    if _tracer is None:
        try:  # pragma: no cover - depende del entorno
            _tracer = _otel_trace.get_tracer("excel-sync-gov-backend")
        except Exception:
            _tracer = None
    return _tracer


def configure_tracing(
    service_name: str, exporter_endpoint: str = "", *, insecure: bool = False
) -> bool:
    """Configura el ``TracerProvider`` OTLP si el SDK está instalado.

    Devuelve ``True`` si se instaló un proveedor. Es *best-effort*: cualquier
    fallo (SDK ausente, endpoint no resoluble) no debe romper el arranque.
    """
    if not _HAS_OTEL:
        return False
    try:  # pragma: no cover - depende del entorno
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return False

    try:  # pragma: no cover - depende del entorno
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        exporter = _build_exporter(exporter_endpoint, insecure=insecure)
        if exporter is not None:
            provider.add_span_processor(BatchSpanProcessor(exporter))  # type: ignore[arg-type]
        _otel_trace.set_tracer_provider(provider)
        global _tracer
        _tracer = _otel_trace.get_tracer(service_name)
        return True
    except Exception:
        return False


def _build_exporter(endpoint: str, *, insecure: bool) -> object | None:  # pragma: no cover
    """Construye el exportador OTLP/HTTP; ``None`` si no hay dependencia/endpoint."""
    if not endpoint:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)
    except Exception:
        return None


def new_trace_id() -> str:
    """Genera un ``trace_id`` W3C válido (32 hex, no todo ceros)."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """Genera un ``span_id`` W3C válido (16 hex, no todo ceros)."""
    return secrets.token_hex(8)


def parse_traceparent(value: str) -> tuple[str, str] | None:
    """Extrae ``(trace_id, parent_span_id)`` de un ``traceparent`` válido."""
    match = _TRACEPARENT_RE.match((value or "").strip().lower())
    if match is None:
        return None
    trace_id = match.group("trace_id")
    span_id = match.group("span_id")
    if trace_id == _ZERO_TRACE_ID or span_id == "0" * 16:
        return None
    return trace_id, span_id


def trace_id_from_correlation(correlation_id: str) -> str:
    """Deriva un ``trace_id`` determinista del ``correlation_id`` del origen.

    Si el ``correlation_id`` ya es un hex de 32 caracteres se reutiliza; en caso
    contrario se toma el SHA-256 truncado, de modo que el mismo origen produce el
    mismo ``trace_id`` y la traza es reconstruible extremo a extremo.
    """
    value = (correlation_id or "").strip().lower()
    if _HEX_TRACE_ID_RE.match(value):
        return value
    if not value or value == "-":
        return new_trace_id()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def get_trace_id() -> str:
    """``trace_id`` del contexto actual (o ``-`` si no hay)."""
    return trace_id_var.get()


def get_span_id() -> str:
    """``span_id`` del contexto actual (o ``-`` si no hay)."""
    return span_id_var.get()


def _start_otel_span(
    trace_id: str, parent_span_id: str, name: str
) -> tuple[object | None, object | None]:
    """Abre un span OTel anclado al contexto W3C entrante (o ``(None, None)``)."""
    if not _HAS_OTEL:  # pragma: no cover - sin SDK
        return None, None
    tracer = _get_tracer()
    if tracer is None:
        return None, None
    try:  # pragma: no cover - depende del entorno
        parent = _OtelSpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(parent_span_id, 16),
            is_remote=True,
            trace_flags=_OtelTraceFlags.SAMPLED,  # type: ignore[arg-type]
        )
        context = _otel_set_span_in_context(_OtelNonRecordingSpan(parent))
        span = tracer.start_span(name, context=context)  # type: ignore[attr-defined]
        return tracer, span
    except Exception:
        return None, None


class TracingMiddleware:
    """Resuelve/propaga el ``trace_id`` y abre un span OpenTelemetry por petición.

    Colocado justo por dentro del ``CorrelationIdMiddleware`` (que ya fijó el
    ``correlation_id``), reutiliza ese identificador como ``trace_id`` cuando no
    hay un ``traceparent`` W3C válido. Añade ``X-Trace-Id`` a toda respuesta.
    """

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        self.app = app
        self._enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming_trace = parse_traceparent(headers.get(TRACEPARENT_HEADER) or "")
        if incoming_trace is not None:
            trace_id, parent_span_id = incoming_trace
        else:
            trace_id = trace_id_from_correlation(get_correlation_id())
            parent_span_id = new_span_id()

        span_id = new_span_id()
        token_trace = trace_id_var.set(trace_id)
        token_span = span_id_var.set(span_id)
        path = scope.get("path", "")
        method = scope.get("method", "")
        tracer, span = _start_otel_span(trace_id, parent_span_id, f"{method} {path}")

        async def send_with_trace(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            if span is not None:
                try:  # pragma: no cover - depende del entorno
                    span.set_attribute("http.route", path)  # type: ignore[attr-defined]
                    span.set_attribute("correlation_id", get_correlation_id())  # type: ignore[attr-defined]
                    span.end()  # type: ignore[attr-defined]
                except Exception:
                    pass
            span_id_var.reset(token_span)
            trace_id_var.reset(token_trace)


def reset_tracing_state() -> None:
    """Reinicia el ``TracerProvider``/tracer cacheado (pruebas)."""
    global _tracer
    _tracer = None
