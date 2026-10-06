"""Errores uniformes del backend (spec §10, §10.5).

Cuerpo de error único para toda la API::

    { "error": { "code": str, "message": str, "correlation_id": str } }

- ``code`` es estable y programático (p. ej. ``CAPACIDAD_DENEGADA``,
  ``PAYLOAD_INVALID``, ``RATE_LIMITED``, ``ANTI_REPLAY``).
- ``message`` es legible y **sin PII** (RNF-08.c).
- ``correlation_id`` vincula el error con la traza/log de la petición (RNF-07.b).

Se registran handlers para 400/401/403/404/409/413/422/429/500/503 y para los
errores de validación de FastAPI/Starlette, de modo que ningún error escape con
un cuerpo distinto. El helper ``raise_http_error(code, message)`` es la vía
única para lanzar errores de negocio.
"""

from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_correlation_id

logger = logging.getLogger(__name__)

# Código de error → estado HTTP por defecto (§10.5).
_DEFAULT_STATUS_BY_CODE: dict[str, int] = {
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "AEAD_TAG_MISMATCH": 401,
    "FORBIDDEN": 403,
    "CAPACIDAD_DENEGADA": 403,
    "AGENT_REVOKED": 403,
    "BINARY_NOT_AUTHORIZED": 403,
    "KEY_NOT_ACTIVE": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "ANTI_REPLAY": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNPROCESSABLE": 422,
    "VALIDATION_ERROR": 422,
    "SNAPSHOT_INVALID": 422,
    "PAYLOAD_INVALID": 422,
    "RATE_LIMITED": 429,
    "INTERNAL": 500,
    "UNAVAILABLE": 503,
}

_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL",
    503: "UNAVAILABLE",
}

# Mensaje genérico y sin PII por estado (§10.5). Se usa cuando no hay un
# ``detail`` controlado o cuando el estado es 5xx, para no filtrar detalles
# internos (stack traces, nombres de dependencias, etc.).
_GENERIC_MESSAGE_BY_STATUS: dict[int, str] = {
    400: "La petición es inválida.",
    401: "No autenticado.",
    403: "Acceso denegado.",
    404: "Recurso no encontrado.",
    405: "Método no permitido.",
    409: "Conflicto con el estado actual del recurso.",
    413: "El payload supera el tamaño máximo permitido.",
    422: "La petición no cumple el esquema esperado.",
    429: "Demasiadas solicitudes; reintente más tarde.",
    500: "Error interno del servidor.",
    503: "Servicio no disponible temporalmente.",
}


class APIError(Exception):
    """Error de negocio con estado HTTP, código estable y mensaje sin PII."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def raise_http_error(code: str, message: str, *, status_code: int | None = None) -> NoReturn:
    """Lanza un ``APIError`` con cuerpo uniforme. ``status_code`` se deduce del ``code``."""
    status = status_code if status_code is not None else _DEFAULT_STATUS_BY_CODE.get(code, 500)
    raise APIError(status_code=status, code=code, message=message)


def build_error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Construye el cuerpo de error uniforme (con ``correlation_id`` del contexto)."""
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": get_correlation_id(),
        }
    }


def _json_error(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_error_body(code, message),
        headers=headers,
    )


def _code_for_status(status_code: int) -> str:
    return _STATUS_TO_CODE.get(status_code, "INTERNAL")


def _generic_message(status_code: int) -> str:
    """Mensaje de error genérico y sin PII asociado a un estado HTTP."""
    return _GENERIC_MESSAGE_BY_STATUS.get(status_code, "Error en la petición.")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los handlers de excepciones (cuerpo uniforme en todos los errores)."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return _json_error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # No se vuelca el detalle del payload (posible PII); mensaje genérico estable.
        return _json_error(422, "VALIDATION_ERROR", "La petición no cumple el esquema esperado.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _code_for_status(exc.status_code)
        # Los 5xx nunca exponen ``detail`` (puede contener detalles internos);
        # el resto usa el ``detail`` controlado o un mensaje genérico.
        if exc.status_code >= 500:
            message = _generic_message(exc.status_code)
        else:
            message = str(exc.detail) if exc.detail else _generic_message(exc.status_code)
        # Conserva cabeceras del error (p. ej. ``Retry-After`` en 429,
        # ``WWW-Authenticate``/``Allow``) sin reenviar diagnóstico interno.
        headers = dict(exc.headers) if exc.headers else None
        return _json_error(exc.status_code, code, message, headers=headers)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # 500 genérico, sin detalles internos (posible fuga de PII/secretos). El tipo
        # de excepción se registra sin payload para cumplir la política anti-PII.
        logger.error(
            "unhandled_exception",
            extra={"event": "unhandled", "result": type(exc).__name__},
        )
        return _json_error(500, "INTERNAL", _generic_message(500))
