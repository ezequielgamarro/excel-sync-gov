"""Middleware RBAC por capacidad, **deny por defecto** (spec RNF-03.c/h, T37).

Toda ruta bajo ``/api/`` tiene una política declarada: una **capacidad** exigida,
autenticación de **firma** (webhook) o **pública**. Cualquier ruta sin política
se **deniega** (fail-closed), de modo que añadir un endpoint sin declarar su
capacidad no lo expone accidentalmente.

La capacidad es el único objeto que el backend comprueba (§2.2.3): la identidad
se resuelve del **JWT nativo** firmado por el backend (usuario+contraseña, sin
IdP externo). Se registra el resultado de **cada** decisión
(``allowed``/``denied``) con métrica y evento de auditoría (RNF-03.h).

Este middleware es **defensa en profundidad**: los handlers siguen llamando a
``require_capacity`` para no depender de una sola capa. El WSS no pasa por aquí
(no es HTTP); su autorización y re-verificación viven en ``app/api/ws.py`` y
``app/services/revocation.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import APIError, build_error_body
from app.core.metrics import AUTHORIZATION_TOTAL
from app.services.capacity import (
    CAP_AUDIT_VIEW,
    CAP_DASH_EXPORT_CSV,
    CAP_DASH_VIEW_HISTORY,
    CAP_DASH_VIEW_LIVE,
    CAP_PLATFORM_MANAGE_USERS,
    CAP_PLATFORM_MANAGE_WEBHOOK,
    OperatorIdentity,
    require_capacity,
    resolve_operator_identity,
)

CAPABILITY = "capability"
SIGNATURE = "signature"
PUBLIC = "public"

_Authorizer = Callable[[Headers], Awaitable[OperatorIdentity]]


@dataclass(frozen=True)
class RoutePolicy:
    """Política de autorización de una ruta (método + patrón → capacidad)."""

    method: str
    pattern: re.Pattern[str]
    kind: str
    capability: str | None = None


def _p(method: str, regex: str, kind: str, capability: str | None = None) -> RoutePolicy:
    return RoutePolicy(method=method, pattern=re.compile(regex), kind=kind, capability=capability)


def build_default_policies() -> list[RoutePolicy]:
    """Políticas del contrato §10 (deny por defecto para lo no listado)."""
    return [
        # Webhook del origen: se autentica con HMAC (no con JWT de operador).
        _p("POST", r"^/api/v1/ingest/webhook$", SIGNATURE),
        # Auth nativa (pública): login/refresh/logout no requieren JWT previo.
        _p("POST", r"^/api/v1/auth/login$", PUBLIC),
        _p("POST", r"^/api/v1/auth/refresh$", PUBLIC),
        _p("POST", r"^/api/v1/auth/logout$", PUBLIC),
        # Hospitales: lectura pública de la planilla local (solo agregados).
        _p("GET", r"^/api/hospitales/estadisticas$", PUBLIC),
        # Estadísticas públicas del documento Excel (solo agregados).
        _p("GET", r"^/api/estadisticas$", PUBLIC),
        # Dashboard y WSS.
        _p("POST", r"^/api/v1/auth/ws-ticket$", CAPABILITY, CAP_DASH_VIEW_LIVE),
        _p("GET", r"^/api/v1/dashboard/snapshot$", CAPABILITY, CAP_DASH_VIEW_LIVE),
        _p("GET", r"^/api/v1/dashboard/consultas$", CAPABILITY, CAP_DASH_VIEW_LIVE),
        _p("GET", r"^/api/v1/dashboard/history$", CAPABILITY, CAP_DASH_VIEW_HISTORY),
        _p("GET", r"^/api/v1/dashboard/export\.csv$", CAPABILITY, CAP_DASH_EXPORT_CSV),
        # Auditoría.
        _p("GET", r"^/api/v1/audit/events$", CAPABILITY, CAP_AUDIT_VIEW),
        # Admin: webhook vs usuarios/roles.
        _p("GET", r"^/api/v1/admin/webhook$", CAPABILITY, CAP_PLATFORM_MANAGE_WEBHOOK),
        _p("GET", r"^/api/v1/admin/room-health$", CAPABILITY, CAP_PLATFORM_MANAGE_WEBHOOK),
        _p(
            "POST",
            r"^/api/v1/admin/webhook/secret/rotate$",
            CAPABILITY,
            CAP_PLATFORM_MANAGE_WEBHOOK,
        ),
        _p("GET", r"^/api/v1/admin/users$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p("POST", r"^/api/v1/admin/users$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p("GET", r"^/api/v1/admin/users/[^/]+$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p("PUT", r"^/api/v1/admin/users/[^/]+$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p("DELETE", r"^/api/v1/admin/users/[^/]+$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p(
            "POST",
            r"^/api/v1/admin/users/[^/]+/roles$",
            CAPABILITY,
            CAP_PLATFORM_MANAGE_USERS,
        ),
        _p(
            "DELETE",
            r"^/api/v1/admin/users/[^/]+/roles/[^/]+$",
            CAPABILITY,
            CAP_PLATFORM_MANAGE_USERS,
        ),
        _p(
            "POST",
            r"^/api/v1/admin/users/[^/]+/reset-password$",
            CAPABILITY,
            CAP_PLATFORM_MANAGE_USERS,
        ),
        _p("GET", r"^/api/v1/admin/roles$", CAPABILITY, CAP_PLATFORM_MANAGE_USERS),
        _p(
            "PUT",
            r"^/api/v1/admin/roles/[^/]+/capabilities$",
            CAPABILITY,
            CAP_PLATFORM_MANAGE_USERS,
        ),
    ]


async def _default_authorizer(headers: Headers) -> OperatorIdentity:
    """Autentica la petición con una sesión propia (solo para el middleware)."""
    from app.services.db import get_session

    session = await get_session()
    try:
        return await resolve_operator_identity(headers, session)
    finally:
        await session.close()


class RBACMiddleware:
    """Aplica la política de capacidades por ruta con deny por defecto."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool = True,
        policies: list[RoutePolicy] | None = None,
        authorizer: _Authorizer | None = None,
    ) -> None:
        self.app = app
        self._enabled = enabled
        self._policies = policies if policies is not None else build_default_policies()
        self._authorizer = authorizer or _default_authorizer

    def match(self, method: str, path: str) -> RoutePolicy | None:
        for policy in self._policies:
            if policy.method == method and policy.pattern.match(path):
                return policy
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        policy = self.match(method, path)

        # Deny por defecto: ruta ``/api/`` sin política declarada.
        if policy is None:
            AUTHORIZATION_TOTAL.labels(result="denied", capability="unmapped").inc()
            await self._deny(scope, receive, send, "CAPACIDAD_DENEGADA", "Ruta no autorizada.")
            return

        if policy.kind in (PUBLIC, SIGNATURE):
            AUTHORIZATION_TOTAL.labels(result="allowed", capability=policy.kind).inc()
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        identity: OperatorIdentity | None = None
        try:
            identity = await self._authorizer(headers)
            require_capacity(str(policy.capability), identity)
        except APIError as exc:
            AUTHORIZATION_TOTAL.labels(result="denied", capability=str(policy.capability)).inc()
            await self._audit_denied(scope, identity, path, str(policy.capability))
            await self._deny(scope, receive, send, exc.code, exc.message)
            return
        except Exception:
            AUTHORIZATION_TOTAL.labels(result="error", capability=str(policy.capability)).inc()
            await self._deny(scope, receive, send, "INTERNAL", "Error interno del servidor.")
            return

        AUTHORIZATION_TOTAL.labels(result="allowed", capability=str(policy.capability)).inc()
        await self.app(scope, receive, send)

    async def _deny(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        code: str,
        message: str,
    ) -> None:
        status = (
            401
            if code == "UNAUTHORIZED"
            else (403 if code in ("FORBIDDEN", "CAPACIDAD_DENEGADA") else 500)
        )
        response = JSONResponse(status_code=status, content=build_error_body(code, message))
        await response(scope, receive, send)

    async def _audit_denied(
        self,
        scope: Scope,
        identity: OperatorIdentity | None,
        path: str,
        capability: str,
    ) -> None:
        """Registra el intento denegado (RNF-03.h) sin PII."""
        try:
            from app.services.audit import record_audit

            client = scope.get("client")
            ip = client[0] if client else ""
            await record_audit(
                actor=identity.sub if identity else "anonymous",
                action="authz.denied",
                resource=f"{capability}:{path}",
                result="denied",
                ip=ip,
                user_agent=Headers(scope=scope).get("User-Agent", ""),
            )
        except Exception:  # pragma: no cover - la auditoría no debe tumbar la petición
            pass
