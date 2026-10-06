"""Capacidades y autenticación nativa del operador (F5, spec §2.2.2/§2.2.3).

Modelo de autorización: la **capacidad** es el único objeto que el backend
comprueba (``require_capacity``); los roles son contenedores de capacidades
(§2.2.3, RNF-03.c). La autenticación es **nativa**: el backend emite y verifica
sus propios JWT (login usuario+contraseña, sin IdP externo).

``get_operator`` valida el ``Authorization: Bearer <JWT>`` con
``app/services/jwt_native.py`` y combina las capacidades embebidas en el token
firmado con el mapeo rol→capacidad de ``app.role_capability``. Deny por defecto:
sin token válido no hay identidad y la petición se rechaza (fail-closed).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import raise_http_error
from app.models.tables import role_capability
from app.services.db import session_dependency
from app.services.jwt_native import (
    NativeJwtConfig,
    NativeJwtService,
    TokenError,
)

# Catálogo de capacidades (openapi ``components.schemas``; §2.2.3).
CAP_DASH_VIEW_LIVE = "dash.view.live"
CAP_DASH_VIEW_HISTORY = "dash.view.history"
CAP_DASH_EXPORT_CSV = "dash.export.csv"
CAP_AUDIT_VIEW = "audit.view"
CAP_PLATFORM_MANAGE_WEBHOOK = "platform.manage_webhook"
CAP_PLATFORM_MANAGE_USERS = "platform.manage_users"
CAP_PLATFORM_ROTATE_SECRETS = "platform.rotate_secrets"
CAP_PLATFORM_REPLAY = "platform.replay"

ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAP_DASH_VIEW_LIVE,
        CAP_DASH_VIEW_HISTORY,
        CAP_DASH_EXPORT_CSV,
        CAP_AUDIT_VIEW,
        CAP_PLATFORM_MANAGE_WEBHOOK,
        CAP_PLATFORM_MANAGE_USERS,
        CAP_PLATFORM_ROTATE_SECRETS,
        CAP_PLATFORM_REPLAY,
    }
)


@dataclass(frozen=True)
class OperatorIdentity:
    """Identidad resuelta del operador (sub + roles + capacidades)."""

    sub: str
    roles: frozenset[str]
    capabilities: frozenset[str]

    def has_capacity(self, capability: str) -> bool:
        return capability in self.capabilities


def require_capacity(capability: str, identity: OperatorIdentity) -> None:
    """Comprueba una capacidad (fail-closed); lanza ``403 CAPACIDAD_DENEGADA``.

    No revela qué datos existen (RF-02.k, AM-01): solo se deniega.
    """
    if not identity.has_capacity(capability):
        raise_http_error(
            "CAPACIDAD_DENEGADA",
            "El operador no posee la capacidad requerida.",
        )


def _reject(message: str) -> None:
    raise_http_error("UNAUTHORIZED", message)


async def resolve_capabilities(
    roles: list[str] | set[str] | frozenset[str],
    session: AsyncSession,
) -> set[str]:
    """Deriva capacidades desde roles consultando ``app.role_capability``.

    Ausencia de fila (o ``granted = false``) = denegación (fail-closed).
    """
    if not roles:
        return set()
    rows = await session.execute(
        select(role_capability.c.capability).where(
            role_capability.c.role.in_(list(roles)),
            role_capability.c.granted.is_(True),
        )
    )
    return {str(row[0]) for row in rows}


_jwt_service: NativeJwtService | None = None


def get_jwt_service() -> NativeJwtService:
    """Servicio JWT nativo compartido, construido desde el entorno (RNF-13)."""
    global _jwt_service
    if _jwt_service is None:
        settings = get_settings()
        _jwt_service = NativeJwtService(
            NativeJwtConfig(
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                signing_key=settings.jwt_signing_key,
                algorithm=settings.jwt_algorithm,
                access_token_ttl_seconds=settings.jwt_access_token_ttl_seconds,
                clock_skew_seconds=settings.jwt_clock_skew_seconds,
            )
        )
    return _jwt_service


def reset_jwt_service() -> None:
    """Invalida el servicio cacheado (tras rotar la clave de firma o en pruebas)."""
    global _jwt_service
    _jwt_service = None


async def _finalize_identity(
    *,
    sub: str,
    roles: set[str],
    embedded_capabilities: set[str],
    session: AsyncSession | None,
) -> OperatorIdentity:
    """Combina capacidades embebidas en el token con el mapeo rol→capacidad.

    La tabla ``role_capability`` es la fuente de verdad del mapeo (§2.2.3): si
    hay sesión disponible se consulta; sin ella se usan solo las capacidades
    embebidas en el token firmado.
    """
    capabilities = set(embedded_capabilities)
    if roles and session is not None:
        capabilities |= await resolve_capabilities(roles, session)
    return OperatorIdentity(
        sub=sub,
        roles=frozenset(roles),
        capabilities=frozenset(capabilities & ALL_CAPABILITIES),
    )


def _capabilities_from_claims(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(cap) for cap in value if cap}
    if isinstance(value, str):
        return {cap.strip() for cap in value.split(",") if cap.strip()}
    return set()


async def resolve_operator_identity(
    headers: Mapping[str, str],
    session: AsyncSession | None = None,
) -> OperatorIdentity:
    """Resuelve la identidad del operador desde el JWT nativo (fail-closed).

    Solo se acepta ``Authorization: Bearer <JWT>`` firmado por este backend;
    cualquier otro mecanismo se rechaza (P6: el cliente no es frontera de
    seguridad). Es reutilizable por la dependencia FastAPI y por el middleware
    RBAC (T37).
    """
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        _reject("Autenticación de operador ausente.")
    token = auth[len("Bearer ") :].strip()
    if not token:
        _reject("Autenticación de operador ausente.")

    try:
        claims = get_jwt_service().validate_access_token(token)
    except TokenError:
        _reject("Token de operador inválido.")

    return await _finalize_identity(
        sub=claims.sub,
        roles=set(claims.roles),
        embedded_capabilities=_capabilities_from_claims(list(claims.capabilities)),
        session=session,
    )


async def _resolve_operator(request: Request, session: AsyncSession) -> OperatorIdentity:
    """Resuelve la identidad del operador a partir de la petición."""
    return await resolve_operator_identity(request.headers, session)


async def get_operator(
    request: Request,
    session: AsyncSession = Depends(session_dependency),
) -> OperatorIdentity:
    """Dependencia FastAPI: autentica y resuelve la identidad/capacidades del operador."""
    return await _resolve_operator(request, session)
