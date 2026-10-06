"""Logging estructurado JSON a stdout, con correlación y sin PII (RNF-07.b, RNF-08.c/f).

Política anti-PII (spec §9.5, RNF-08.c, RNF-13.b):

- Los logs van a ``stdout`` en JSON de una sola línea y son **efímeros**
  (retención 14–30 días en el agregador), a diferencia de la bitácora de
  auditoría (append-only, 60 meses, RNF-08.d).
- **Prohibido** registrar: nombres de personas, matrículas, armas individuales,
  celdas sensibles del Excel, payloads descifrados, tokens, claves o cualquier
  otro secreto (RNF-08.c, RNF-13.b).
- Los identificadores personales/opacos se **seudonimizan** (hash truncado) o se
  **truncan**; nunca se registran en claro. El campo ``actor`` identifica al
  emisor (p. ej. el ``webhook_id`` del origen Google Sheets o el ``sub`` del
  operador autenticado) y también se seudonimiza.
- Solo se serializan campos ``extra`` de una **allowlist**; una **denylist**
  adicional bloquea claves ligadas a payloads, celdas, valores y secretos. Los
  valores largos se truncan para impedir volcados accidentales.
- Toda línea lleva ``correlation_id`` propagado desde la cabecera
  ``X-Correlation-Id`` (o generado como UUID si falta), para trazabilidad
  extremo a extremo sin revelar identidad (RNF-07.b).

Este módulo expone: ``correlation_id_var``/``get_correlation_id()``,
``CorrelationIdMiddleware``, ``configure_logging()``, ``get_logger()`` y los
helpers anti-PII ``hash_identifier()``/``truncate()``/``redact()`` y
``pseudonymize()``/``pseudonymize_ip()``/``is_denied_key()``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_ID_HEADER: Final = "X-Correlation-Id"
_DEFAULT_CORRELATION_ID: Final = "-"
_CORRELATION_ID_RE: Final = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# Límites anti-volcado: ningún valor/mensaje puede serializarse completo si es
# largo (payloads, celdas, documentos). Se trunca antes de emitir.
_MAX_STRING_LEN: Final = 256
_MAX_MESSAGE_LEN: Final = 1000

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default=_DEFAULT_CORRELATION_ID)

_LOGGING_CONFIGURED: bool = False

# Claves que **nunca** deben registrarse (payloads, celdas/valores del Excel,
# documentos crudos y secretos). La comparación es por subcadena para cubrir
# variantes como ``payload_ciphertext`` o ``celdas`` (RNF-08.c, RNF-13.b).
_DENIED_KEY_SUBSTRINGS: Final[tuple[str, ...]] = (
    "payload",
    "ciphertext",
    "plaintext",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "private_key",
    "session",
    "cell",
    "celda",
    "row",
    "fila",
    "value",
    "valor",
    "data",
    "datos",
    "document",
    "documento",
    "raw",
    "content",
    "body",
    "file",
    "fichero",
    "matricula",
    "nombre",
    "name",
)

# Claves cuyo valor se seudonimiza con hash truncado (nunca en claro).
_PSEUDONYMIZE_KEYS: Final[frozenset[str]] = frozenset({"sub", "webhook_id", "ip"})


def get_correlation_id() -> str:
    """Devuelve el ``correlation_id`` del contexto actual (o ``-`` si no hay)."""
    return correlation_id_var.get()


def generate_correlation_id() -> str:
    """Genera un identificador de correlación nuevo (prefijo ``tr-``)."""
    return f"tr-{uuid.uuid4().hex}"


def _is_valid_correlation_id(value: str) -> bool:
    return bool(_CORRELATION_ID_RE.match(value))


def _trace_context(getter: str) -> str:
    """Lee ``get_trace_id``/``get_span_id`` del contexto sin acoplar tracing↔logging.

    ``app.core.tracing`` importa este módulo; la importación perezosa aquí evita
    el ciclo y degrada a ``-`` si el contexto no está disponible (RNF-07.b).
    """
    try:
        from app.core import tracing

        getter_fn = getattr(tracing, getter, None)
        return str(getter_fn()) if callable(getter_fn) else _DEFAULT_CORRELATION_ID
    except Exception:
        return _DEFAULT_CORRELATION_ID


class CorrelationIdMiddleware:
    """Lee ``X-Correlation-Id`` (o genera uno) y lo propaga al contexto y a la respuesta.

    No confía en el valor entrante: lo valida contra una allowlist de caracteres
    y longitud (1–64) para evitar *log forging* e inyección de cabeceras. El valor
    efectivo queda disponible vía ``get_correlation_id()`` para todo el contexto
    de logging de la petición.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = (headers.get(CORRELATION_ID_HEADER) or "").strip()
        correlation_id = (
            incoming if _is_valid_correlation_id(incoming) else generate_correlation_id()
        )
        token = correlation_id_var.set(correlation_id)

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(CORRELATION_ID_HEADER, correlation_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            correlation_id_var.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Inyecta ``correlation_id`` en cada ``LogRecord`` desde el contexto."""

    def filter(self, record: logging.LogRecord) -> bool:
        setattr(record, "correlation_id", get_correlation_id())
        return True


class JsonFormatter(logging.Formatter):
    """Formatea cada ``LogRecord`` como un objeto JSON de una sola línea (stdout)."""

    # Solo se serializan estos campos ``extra`` (allowlist) para no volcar datos
    # arbitrarios/sensibles que un llamador pudiera pasar por error. La denylist
    # se aplica además como defensa en profundidad.
    _EXTRA_ALLOWED: Final[tuple[str, ...]] = (
        "event",
        "actor",
        "sub",
        "webhook_id",
        "doc_id",
        "event_id",
        "action",
        "result",
        "status_code",
        "path",
        "ip",
        "user_agent",
    )

    @staticmethod
    def _sanitize_extra(key: str, value: object) -> object | None:
        """Devuelve el valor sanitizado para ``key`` o ``None`` si está prohibido."""
        if is_denied_key(key):
            return None
        if isinstance(value, str):
            if key in _PSEUDONYMIZE_KEYS:
                return pseudonymize(value)
            return truncate(value, length=_MAX_STRING_LEN)
        if isinstance(value, (bool, int, float)):
            return value
        # Nunca serializar estructuras complejas (posibles payloads/celdas).
        return truncate(repr(value), length=_MAX_STRING_LEN)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": truncate(record.getMessage(), length=_MAX_MESSAGE_LEN),
            "correlation_id": getattr(record, "correlation_id", _DEFAULT_CORRELATION_ID),
            # Trazas distribuidas (RNF-07.b, T59): el `trace_id` vincula origen,
            # backend y cliente. Import perezoso para evitar un ciclo con tracing.
            "trace_id": _trace_context("get_trace_id"),
            "span_id": _trace_context("get_span_id"),
        }
        if record.exc_info is not None:
            payload["exception"] = truncate(
                self.formatException(record.exc_info), length=_MAX_MESSAGE_LEN
            )
        for key in self._EXTRA_ALLOWED:
            value = getattr(record, key, None)
            if value in (None, ""):
                continue
            sanitized = self._sanitize_extra(key, value)
            if sanitized is not None:
                payload[key] = sanitized
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Instala el formatter JSON en el logger raíz (idempotente)."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    # Reemplaza handlers previos (p. ej. los que añade uvicorn) para no duplicar líneas.
    root.handlers = [handler]
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger nombrado (hereda el formatter JSON del logger raíz)."""
    return logging.getLogger(name)


# --- Helpers anti-PII (RNF-08.c) ---------------------------------------------


def hash_identifier(value: str, *, length: int = 12) -> str:
    """Devuelve un hash SHA-256 truncado de un identificador (correlacionable, no reversible).

    Útil para registrar de forma trazable un ``sub``, ``webhook_id`` u otro
    identificador cuando sea imprescindible incluirlo en logs, sin exponer el
    valor en claro (RNF-08.c).
    """
    if not value:
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:length]


def pseudonymize(value: str, *, prefix: str = "", length: int = 12) -> str:
    """Seudonimiza un identificador (hash truncado, opcionalmente con prefijo).

    Nunca devuelve el valor original; es determinista para poder correlacionar
    eventos del mismo origen sin revelar identidad (RNF-08.c).
    """
    if not value:
        return ""
    hashed = hash_identifier(value, length=length)
    return f"{prefix}{hashed}" if prefix else hashed


def pseudonymize_ip(ip: str) -> str:
    """Seudonimiza una IP; nunca se registra la IP completa (RNF-08.c)."""
    return pseudonymize(ip, prefix="ip-")


def truncate(value: str, *, length: int = 40) -> str:
    """Trunca una cadena para logs, evitando volcar valores largos/sensibles."""
    if len(value) <= length:
        return value
    return f"{value[:length]}…"


def redact() -> str:
    """Marca un valor como no registrable (nunca incluir el contenido real)."""
    return "[REDACTED]"


def is_denied_key(key: str) -> bool:
    """Indica si una clave está en la denylist (celdas/valores/payload/secretos)."""
    lowered = key.lower()
    return any(token in lowered for token in _DENIED_KEY_SUBSTRINGS)
