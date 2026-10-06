"""Métricas Prometheus (RNF-07.a) y middleware de instrumentación.

Métricas expuestas en ``GET /metrics`` (solo red interna, RNF-07.c):

- ``http_request_duration_seconds`` (Histogram): latencia por método/endpoint.
- ``http_requests_total`` (Counter): peticiones por método/endpoint/estado.
- ``http_responses_4xx_5xx_total`` (Counter): respuestas 4xx/5xx por
  método/ruta/código (RNF-07.a).
- ``http_payload_bytes`` (Histogram): tamaño de payload (petición y respuesta),
  etiquetado por ``direction``.
- ``ingest_events_total`` (Counter): eventos de ingesta (eventos/s = rate()).
- ``wss_connections`` (Gauge): conexiones WSS activas (F4).
- ``rate_limited_total`` (Counter): rechazos por rate limit, por bucket.

Los contadores de ingesta y WSS quedan definidos para F3/F4 y hoy permanecen en
0; ``rate_limited_total`` lo incrementa el middleware de rate limiting (T19).
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Latencia de las peticiones HTTP por endpoint.",
    labelnames=["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
REQUEST_TOTAL = Counter(
    "http_requests_total",
    "Peticiones HTTP totales.",
    labelnames=["method", "path", "status"],
)
RESPONSE_REJECTIONS = Counter(
    "http_responses_4xx_5xx_total",
    "Respuestas de rechazo/error (4xx/5xx) por método, ruta y código.",
    labelnames=["method", "path", "status"],
)
PAYLOAD_SIZE = Histogram(
    "http_payload_bytes",
    "Tamaño del payload en bytes (direction=request|response).",
    labelnames=["direction"],
    buckets=(64, 256, 1024, 4096, 16384, 65536, 262144, 1048576),
)
INGEST_EVENTS = Counter(
    "ingest_events_total",
    "Eventos de ingesta aceptados (eventos/s = rate(ingest_events_total[1m])).",
    labelnames=["result"],
)
WSS_CONNECTIONS = Gauge(
    "wss_connections",
    "Conexiones WebSocket (WSS) activas.",
    labelnames=["room_id"],
)
RATE_LIMITED_TOTAL = Counter(
    "rate_limited_total",
    "Peticiones rechazadas por rate limiting.",
    labelnames=["bucket"],
)
AUTHORIZATION_TOTAL = Counter(
    "authorization_decisions_total",
    "Decisiones de autorización por capacidad (RNF-03.h).",
    labelnames=["result", "capability"],
)
# Alertas configurables (RNF-07.d, T60): 1 si la regla está disparada.
ALERT_ACTIVE = Gauge(
    "alert_active",
    "Alertas activas por regla (1 = disparada, 0 = normal).",
    labelnames=["rule", "severity"],
)
# Rebote/desviación de escritura SQL (RNF-07.d): fracción observada (0..1).
SQL_DEBOUNCE_RATIO = Gauge(
    "sql_debounce_ratio",
    "Fracción de escrituras SQL rebotadas/desviadas (RNF-07.d).",
)
# Mayor payload de ingesta observado (bytes) para la alerta de > 64 KB (RNF-07.d).
INGEST_MAX_PAYLOAD_BYTES = Gauge(
    "ingest_max_payload_bytes",
    "Mayor tamaño de payload de ingesta observado en bytes (RNF-07.d).",
)


class MetricsMiddleware:
    """Mide latencia, tamaño y códigos de estado de cada petición HTTP."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._enabled = settings.metrics_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        status = "500"
        size = 0
        # Tamaño del payload entrante sin consumir el cuerpo (Content-Length).
        try:
            request_size = int(Headers(scope=scope).get("content-length") or 0)
        except ValueError:
            request_size = 0
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status, size
            if message["type"] == "http.response.start":
                status = str(message.get("status", 500))
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            route = scope.get("route")
            path_label = getattr(route, "path", path) if route is not None else path
            REQUEST_DURATION.labels(method=method, path=path_label).observe(duration)
            REQUEST_TOTAL.labels(method=method, path=path_label, status=status).inc()
            PAYLOAD_SIZE.labels(direction="request").observe(request_size)
            PAYLOAD_SIZE.labels(direction="response").observe(size)
            if status.startswith("4") or status.startswith("5"):
                RESPONSE_REJECTIONS.labels(
                    method=method, path=path_label, status=status
                ).inc()


def render_metrics() -> Response:
    """Devuelve la exposición Prometheus (``text/plain; version=0.0.4``)."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
