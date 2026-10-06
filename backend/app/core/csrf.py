"""Anti-CSRF y endurecimiento de cookies (spec AM-12, T63).

La autenticación del dashboard usa **bearer en memoria** (no cookies de sesión),
por lo que el riesgo de CSRF clásico es bajo; aun así se aplica **defensa en
profundidad** (P4):

- Toda **mutación** (``POST``/``PUT``/``PATCH``/``DELETE``) autenticada con un
  bearer debe presentar un ``X-CSRF-Token`` válido, derivado de forma
  determinista del propio bearer con un secreto del backend
  (``csrf_secret``/``jwt_signing_key``). El token se entrega en
  ``/auth/login`` y ``/auth/refresh`` y el cliente lo reenvía en cada mutación.
  Un sitio externo no puede leerlo ni fijar la cabecera sin superar el preflight
  CORS con allowlist exacta.
- El webhook del origen (``/ingest/webhook``) queda **exento**: se autentica con
  firma HMAC-SHA256 y no usa cookies ni bearer de operador.
- Si la petición mutante **no** lleva bearer (login/refresh/logout), se valida el
  ``Origin``/``Referer`` contra la allowlist CORS cuando están presentes; un
  navegador de otro origen queda rechazado.
- Cualquier ``Set-Cookie`` que emita la aplicación se normaliza a
  ``SameSite=Strict`` (AM-11/AM-12, §2.2.5).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import build_error_body

SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
#: Rutas mutantes exentas (autenticación por firma HMAC del webhook).
EXEMPT_PATHS: Final[tuple[str, ...]] = ("/api/v1/ingest/webhook",)
CSRF_INVALID_CODE: Final = "CSRF_INVALID"
CSRF_INVALID_MESSAGE: Final = "Solicitud mutante sin token anti-CSRF válido."


def issue_csrf_token(secret: str, binding: str) -> str:
    """Deriva un token anti-CSRF determinista ligado a la sesión (bearer)."""
    if not secret or not binding:
        return ""
    digest = hmac.new(
        secret.encode("utf-8"), f"csrf:{binding}".encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def validate_csrf_token(secret: str, binding: str, token: str) -> bool:
    """Compara el token en tiempo constante con el esperado."""
    expected = issue_csrf_token(secret, binding)
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


def _origin_allowed(origin: str, allowlist: tuple[str, ...]) -> bool:
    if not origin:
        return True
    if not allowlist:
        return False
    return origin.rstrip("/") in {item.rstrip("/") for item in allowlist}


class CSRFMiddleware:
    """Exige token anti-CSRF en mutaciones y normaliza ``SameSite=Strict``."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool = True,
        secret: str = "",
        header_name: str = "X-CSRF-Token",
        cors_origins: tuple[str, ...] = (),
        cookie_samesite: str = "Strict",
    ) -> None:
        self.app = app
        self._enabled = enabled and bool(secret)
        self._secret = secret
        self._header_name = header_name
        self._cors_origins = cors_origins
        self._cookie_samesite = cookie_samesite or "Strict"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Sin secreto configurado (desarrollo) el endurecimiento de cookies sigue
        # aplicando, pero la exigencia de token queda inactiva.
        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        if self._enabled and method not in SAFE_METHODS and path not in EXEMPT_PATHS:
            if not self._csrf_ok(scope):
                response = JSONResponse(
                    status_code=403,
                    content=build_error_body(CSRF_INVALID_CODE, CSRF_INVALID_MESSAGE),
                )
                await response(scope, receive, send)
                return

        async def send_with_cookie_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._normalize_set_cookie(message)
            await send(message)

        await self.app(scope, receive, send_with_cookie_policy)

    def _csrf_ok(self, scope: Scope) -> bool:
        headers = Headers(scope=scope)
        authorization = headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            binding = authorization[len("Bearer ") :].strip()
            token = headers.get(self._header_name, "")
            return validate_csrf_token(self._secret, binding, token)
        # Sin bearer (login/refresh/logout): valida el origen del navegador.
        origin = headers.get("Origin", "") or headers.get("Referer", "")
        return _origin_allowed(origin, self._cors_origins)

    def _normalize_set_cookie(self, message: Message) -> None:
        raw_headers = message.get("headers")
        if not raw_headers:
            return
        normalized: list[tuple[bytes, bytes]] = []
        for name, value in raw_headers:
            if name.lower() == b"set-cookie":
                text = value.decode("latin-1")
                if "samesite" not in text.lower():
                    text = f"{text}; SameSite={self._cookie_samesite}"
                normalized.append((name, text.encode("latin-1")))
            else:
                normalized.append((name, value))
        message["headers"] = normalized
