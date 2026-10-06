"""Gestión de usuarios y roles locales (spec §10.6, T36).

Expone la administración de **usuarios locales** (``app.user_account``) a los
``platform-admin``, protegida por la capacidad ``platform.manage_users`` (**deny
por defecto**, §2.2.3, RNF-03.c). No hay IdP externo: las contraseñas se hashean
con **Argon2id** y el mapeo rol→capacidad vive en ``app.role_capability``.

Cada mutación se **audita** (``user.created``, ``user.updated``, ``user.disabled``,
``role.assigned``, ``role.revoked``, ``role.capabilities.updated``,
``user.password.reset``). Sin segundo factor ni reautenticación por acción: las
acciones sensibles exigen la
capacidad y quedan auditadas.

Rate limit estricto de 50 req/min por ``sub``: lo aplica el middleware base para
``/api/v1/admin/*`` (T19, §10.6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.errors import raise_http_error
from app.core.logging import get_correlation_id
from app.models.tables import role_capability
from app.services import user_store
from app.services.audit import record_audit
from app.services.capacity import (
    ALL_CAPABILITIES,
    CAP_PLATFORM_MANAGE_USERS,
    CAP_PLATFORM_MANAGE_WEBHOOK,
    OperatorIdentity,
    get_operator,
    require_capacity,
    resolve_capabilities,
)
from app.services.db import session_dependency
from app.services.revocation import get_reauth_registry
from app.services.room_health import build_room_health
from app.services.source_health import build_source_health

router = APIRouter(tags=["Admin"])

_KNOWN_ROLES = user_store.known_roles()


async def _admin_guard(
    request: Request,
    operator: OperatorIdentity,
    *,
    action: str,
    resource: str,
) -> None:
    """Verifica capacidad y audita el intento (denegado o permitido)."""
    try:
        require_capacity(CAP_PLATFORM_MANAGE_USERS, operator)
    except Exception:
        await record_audit(
            actor=operator.sub,
            action=f"{action}_rejected",
            resource=resource,
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise


def _mapping(row: Any) -> Any:
    return getattr(row, "_mapping", row)


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _user_summary(row: Any, roles: list[str] | None = None) -> dict[str, Any]:
    data = _mapping(row)
    return {
        "id": str(data["user_id"]),
        "username": data["username"],
        "enabled": user_store.is_active(row),
        "estado": data["estado"],
        "lastLogin": _iso(data["last_login_at"]),
        "createdAt": _iso(data["created_at"]),
        "roles": roles if roles is not None else [],
    }


# =============================================================================
# Estado/salud del webhook de Google Sheets (§10.6, F6/T46)
# =============================================================================
@router.get("/webhook")
async def get_webhook_status(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    webhook_id: str | None = Query(default=None, max_length=64),
) -> JSONResponse:
    """Estado del origen (última recepción, ``key_id`` vigente, degradado, reintentos).

    Capacidad ``platform.manage_webhook`` (deny-by-default). No expone
    indicadores operativos (§2.2.3); solo salud del canal.
    """
    try:
        require_capacity(CAP_PLATFORM_MANAGE_WEBHOOK, operator)
    except Exception:
        await record_audit(
            actor=operator.sub,
            action="webhook.status_rejected",
            resource="webhook",
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise
    health = await build_source_health(session, webhook_id=webhook_id)
    if health is None:
        raise_http_error("NOT_FOUND", "No hay un webhook registrado.")
    return JSONResponse(status_code=200, content=health.as_dict())


@router.get("/room-health")
async def get_room_health(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    webhook_id: str | None = Query(default=None, max_length=64),
) -> JSONResponse:
    """Panel de salud de la sala (RNF-07.e, T61).

    Vista **interna** de ``platform-admin`` (capacidad
    ``platform.manage_webhook``): última actualización, edad del dato, estado del
    webhook (última recepción, reintentos), réplicas/storage y presencia WSS. No
    expone indicadores operativos (§2.2.3).
    """
    try:
        require_capacity(CAP_PLATFORM_MANAGE_WEBHOOK, operator)
    except Exception:
        await record_audit(
            actor=operator.sub,
            action="room.health_rejected",
            resource="room-health",
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise
    settings = get_settings()
    health = await build_room_health(
        session,
        room_id=settings.default_room_id,
        webhook_id=webhook_id,
    )
    return JSONResponse(status_code=200, content=health.as_dict())


# =============================================================================
# Usuarios locales
# =============================================================================
class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    roles: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    enabled: bool | None = None
    roles: list[str] | None = None


class RoleAssignRequest(BaseModel):
    roles: list[str] = Field(min_length=1)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=512)


class CapabilitiesUpdateRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)


@router.get("/users")
async def list_users(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    search: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.list", resource="users")
    rows = await user_store.list_users(session, search=search, limit=limit, offset=offset)
    users = []
    for row in rows:
        uid = _mapping(row)["user_id"]
        roles = await user_store.roles_for_user(session, uid)
        users.append(_user_summary(row, roles))
    return JSONResponse(status_code=200, content={"users": users, "meta": {"count": len(users)}})


@router.post("/users", status_code=201)
async def create_user(
    request: Request,
    body: UserCreateRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.create", resource=body.username)
    created = await user_store.create_user(
        session, username=body.username, password=body.password, roles=body.roles
    )
    await record_audit(
        actor=operator.sub,
        action="user.created",
        resource=created["id"],
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=201, content=created)


@router.get("/users/{user_id}")
async def get_user(
    request: Request,
    user_id: str,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.read", resource=user_id)
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    roles = await user_store.roles_for_user(session, _mapping(row)["user_id"])
    derived = sorted(await resolve_capabilities(roles, session))
    return JSONResponse(
        status_code=200,
        content={**_user_summary(row, roles), "capabilities": derived},
    )


@router.put("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    body: UserUpdateRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.update", resource=user_id)
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    if body.enabled is None and body.roles is None:
        raise_http_error("BAD_REQUEST", "Nada que actualizar.")
    await user_store.update_user(
        session, _mapping(row)["user_id"], enabled=body.enabled, roles=body.roles
    )
    if body.enabled is False:
        await get_reauth_registry().mark_revoked(
            _mapping(row)["sub"], reason="user_disabled"
        )
    await record_audit(
        actor=operator.sub,
        action="user.disabled" if body.enabled is False else "user.updated",
        resource=user_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content={"id": user_id, "updated": True})


@router.delete("/users/{user_id}")
async def delete_user(
    request: Request,
    user_id: str,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.delete", resource=user_id)
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    await user_store.disable_user(session, _mapping(row)["user_id"])
    await get_reauth_registry().mark_revoked(_mapping(row)["sub"], reason="user_disabled")
    await record_audit(
        actor=operator.sub,
        action="user.deleted",
        resource=user_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content={"id": user_id, "deleted": True})


@router.post("/users/{user_id}/roles")
async def assign_roles(
    request: Request,
    user_id: str,
    body: RoleAssignRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="role.assign", resource=user_id)
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    current = await user_store.roles_for_user(session, _mapping(row)["user_id"])
    await user_store.set_roles(
        session, _mapping(row)["user_id"], sorted(set(current) | set(body.roles))
    )
    await record_audit(
        actor=operator.sub,
        action="role.assigned",
        resource=user_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content={"id": user_id, "roles": body.roles})


@router.delete("/users/{user_id}/roles/{role_name}")
async def revoke_role(
    request: Request,
    user_id: str,
    role_name: str,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="role.revoke", resource=user_id)
    if role_name not in _KNOWN_ROLES:
        raise_http_error("BAD_REQUEST", "Rol desconocido.")
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    current = await user_store.roles_for_user(session, _mapping(row)["user_id"])
    await user_store.set_roles(
        session, _mapping(row)["user_id"], sorted(set(current) - {role_name})
    )
    # Pérdida de rol ⇒ revoca la sesión y cierra el WSS ≤ 30 s (RNF-03.e).
    await get_reauth_registry().mark_revoked(_mapping(row)["sub"], reason="role_revoked")
    await record_audit(
        actor=operator.sub,
        action="role.revoked",
        resource=user_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content={"id": user_id, "revoked": role_name})


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    request: Request,
    user_id: str,
    body: ResetPasswordRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="user.password.reset", resource=user_id)
    row = await user_store.get_user_by_id(session, user_id)
    if row is None:
        raise_http_error("NOT_FOUND", "Usuario no encontrado.")
    await user_store.reset_password(session, _mapping(row)["user_id"], body.new_password)
    await get_reauth_registry().mark_revoked(
        _mapping(row)["sub"], reason="password_reset"
    )
    await record_audit(
        actor=operator.sub,
        action="user.password.reset",
        resource=user_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content={"id": user_id, "reset": True})


# =============================================================================
# Roles y capacidades (mapeo en el backend, §10.6/T14)
# =============================================================================
@router.get("/roles")
async def list_roles(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(request, operator, action="role.list", resource="roles")
    rows = (
        await session.execute(
            select(role_capability.c.role, role_capability.c.capability).where(
                role_capability.c.granted.is_(True)
            )
        )
    ).all()
    mapping: dict[str, list[str]] = {}
    for role, capability in rows:
        mapping.setdefault(str(role), []).append(str(capability))
    return JSONResponse(
        status_code=200,
        content={
            "roles": [
                {"name": role, "capabilities": sorted(mapping.get(role, []))}
                for role in sorted(_KNOWN_ROLES)
            ]
        },
    )


@router.put("/roles/{role_name}/capabilities")
async def update_role_capabilities(
    request: Request,
    role_name: str,
    body: CapabilitiesUpdateRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    await _admin_guard(
        request, operator, action="role.capabilities.update", resource=role_name
    )
    if role_name not in _KNOWN_ROLES:
        raise_http_error("BAD_REQUEST", "Rol desconocido.")
    invalid = [cap for cap in body.capabilities if cap not in ALL_CAPABILITIES]
    if invalid:
        raise_http_error("BAD_REQUEST", "Capacidad desconocida.")
    try:
        await session.execute(delete(role_capability).where(role_capability.c.role == role_name))
        if body.capabilities:
            await session.execute(
                insert(role_capability),
                [
                    {"role": role_name, "capability": cap, "granted": True}
                    for cap in sorted(set(body.capabilities))
                ],
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await record_audit(
        actor=operator.sub,
        action="role.capabilities.updated",
        resource=role_name,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(
        status_code=200,
        content={"role": role_name, "capabilities": sorted(set(body.capabilities))},
    )
