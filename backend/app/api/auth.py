"""Auth nativa del operador: login/refresh/logout (spec §2.2.2, T36).

Sin IdP externo ni segundo factor. El operador se autentica con
usuario y contraseña contra ``app.user_account`` (hash Argon2id); el backend
emite un **access JWT corto** (15 min) y un **refresh rotativo** con detección de
reutilización.

- ``POST /auth/login``   — credenciales → access + refresh.
- ``POST /auth/refresh`` — rotación del refresh (reuso revoca la cadena).
- ``POST /auth/logout``  — revoca la cadena, cierra el WSS ≤ 30 s, ``Clear-Site-Data``.

Todas las respuestas con credenciales llevan ``Cache-Control: no-store``. Los
errores son genéricos y se auditan sin filtrar la causa (fail-closed).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.csrf import issue_csrf_token
from app.core.errors import raise_http_error
from app.core.logging import get_correlation_id
from app.services.audit import record_audit
from app.services.capacity import get_jwt_service, resolve_capabilities
from app.services.db import session_dependency
from app.services.jwt_native import RefreshRotationService, TokenError
from app.services.revocation import get_reauth_registry
from app.services.user_store import (
    DbRefreshStore,
    get_user_by_sub,
    get_user_by_username,
    is_active,
    is_locked,
    record_login_failure,
    record_login_success,
    roles_for_user,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

_GENERIC_UNAUTHORIZED = "Credenciales inválidas o sesión no válida."
_NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=512)


def _rotation(session: AsyncSession) -> RefreshRotationService:
    return RefreshRotationService(DbRefreshStore(session))


async def _access_tokens(session: AsyncSession, sub: str) -> dict[str, object]:
    """Emite el access token de un ``sub`` activo con sus roles/capacidades."""
    user = await get_user_by_sub(session, sub)
    if user is None or not is_active(user):
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)
    user_id = user._mapping["user_id"]
    roles = await roles_for_user(session, user_id)
    capabilities = await resolve_capabilities(roles, session)
    access = get_jwt_service().issue_access_token(sub=sub, roles=roles, capabilities=capabilities)
    settings = get_settings()
    csrf_secret = settings.csrf_secret or settings.jwt_signing_key
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": get_jwt_service().config.access_token_ttl_seconds,
        "sub": sub,
        "roles": sorted(roles),
        "capabilities": sorted(capabilities),
        # Token anti-CSRF ligado a la sesión (AM-12, T63): el cliente lo reenvía
        # en cada mutación como `X-CSRF-Token`.
        "csrf_token": issue_csrf_token(csrf_secret, access),
    }


@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    """Login usuario+contraseña → access JWT corto + refresh rotativo."""
    user = await get_user_by_username(session, body.username)
    if user is None or not is_active(user) or is_locked(user):
        await record_audit(
            actor="anonymous",
            action="auth.login.rejected",
            resource="auth",
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)

    from app.services.passwords import verify_password

    if not verify_password(user._mapping["password_hash"], body.password):
        await record_login_failure(
            session, user._mapping["user_id"], int(user._mapping["failed_attempts"])
        )
        await record_audit(
            actor="anonymous",
            action="auth.login.rejected",
            resource="auth",
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)

    sub = str(user._mapping["sub"])
    await record_login_success(session, user._mapping["user_id"])
    # Una autenticación nueva limpia cualquier marca de revocación previa
    # (p. ej. `logout`); si no, el WSS cerraría con 4003 en el primer latido.
    await get_reauth_registry().clear_revoked(sub)
    tokens = await _access_tokens(session, sub)
    tokens["refresh_token"] = await _rotation(session).issue(sub)
    await record_audit(
        actor=sub,
        action="auth.login",
        resource="auth",
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content=tokens, headers=_NO_STORE)


@router.post("/refresh")
async def refresh(
    request: Request,
    body: RefreshRequest,
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    """Rota el refresh token y emite un nuevo par access+refresh (reuse detection)."""
    rotation = _rotation(session)
    record = await rotation.lookup(body.refresh_token)
    if record is None:
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)
    sub = record.sub
    try:
        new_refresh = await rotation.rotate(body.refresh_token)
    except TokenError as exc:
        # Reutilización de un refresh ya rotado: la cadena queda revocada.
        await record_audit(
            actor="anonymous",
            action="auth.refresh.reuse" if exc.reuse_detected else "auth.refresh.rejected",
            resource="auth",
            result="denied",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
        )
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)

    # El refresh válido recupera la sesión: limpia una marca de revocación previa.
    await get_reauth_registry().clear_revoked(sub)
    tokens = await _access_tokens(session, sub)
    tokens["refresh_token"] = new_refresh
    await record_audit(
        actor=sub,
        action="auth.refresh",
        resource="auth",
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
    )
    return JSONResponse(status_code=200, content=tokens, headers=_NO_STORE)


@router.post("/logout")
async def logout(
    request: Request,
    body: LogoutRequest | None = None,
    session: AsyncSession = Depends(session_dependency),
) -> Response:
    """Revoca el refresh, marca la sesión WSS y responde ``Clear-Site-Data``."""
    sub = "anonymous"
    if body is not None and body.refresh_token:
        sub = (await _rotation(session).revoke(body.refresh_token)) or sub
    if sub != "anonymous":
        # Cierra el WSS ≤ 30 s (RNF-03.e) al invalidar la sesión.
        await get_reauth_registry().mark_revoked(sub, reason="logout")
    await record_audit(
        actor=sub,
        action="auth.logout",
        resource="auth",
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return Response(
        status_code=204,
        headers={
            **_NO_STORE,
            # AM-10/AM-12: limpia caché, almacenamiento y cookies al cerrar sesión.
            "Clear-Site-Data": '"cache", "storage", "cookies"',
        },
    )
